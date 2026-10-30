"""Versioned learning evidence, daily plans, content workflow and skill portfolio."""
import json,time,datetime,sqlite3,uuid,os
from account_service import configured as mail_configured
from content_v05 import NODES,TRANSFER,PRACTICES
CORE=('tense','clause','conditional','subjunctive','nonfinite','agreement')
INTERVALS=(1,3,7,14,30)

def schema(c):
 columns={r[1] for r in c.execute('PRAGMA table_info(questions)')}
 for name,decl in [('node','TEXT'),('status',"TEXT NOT NULL DEFAULT 'published'"),('difficulty',"TEXT NOT NULL DEFAULT 'medium'")]:
  if name not in columns:c.execute('ALTER TABLE questions ADD COLUMN '+name+' '+decl)
 c.executescript('''CREATE TABLE IF NOT EXISTS subskills(id TEXT PRIMARY KEY,topic TEXT REFERENCES topics(id),title TEXT,prereq TEXT,lesson TEXT,example TEXT);
 CREATE TABLE IF NOT EXISTS review_cards(user_id INTEGER REFERENCES users(id),node TEXT REFERENCES subskills(id),stage INTEGER DEFAULT 0,due REAL,last REAL,PRIMARY KEY(user_id,node));
 CREATE TABLE IF NOT EXISTS study_preferences(user_id INTEGER PRIMARY KEY REFERENCES users(id),minutes INTEGER DEFAULT 15);
 CREATE TABLE IF NOT EXISTS content_audit(id INTEGER PRIMARY KEY,actor INTEGER,action TEXT,question_id INTEGER,created REAL);
 CREATE TABLE IF NOT EXISTS skill_work(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),task TEXT,answer TEXT,chat_request TEXT,created REAL);
 CREATE TABLE IF NOT EXISTS question_skill_attempts(attempt_id INTEGER PRIMARY KEY REFERENCES attempts(id),node TEXT REFERENCES subskills(id));
 CREATE INDEX IF NOT EXISTS review_due ON review_cards(user_id,due);
 CREATE INDEX IF NOT EXISTS skill_work_user ON skill_work(user_id,id);''')
 if 'save_id' not in {r[1] for r in c.execute('PRAGMA table_info(skill_work)')}:c.execute('ALTER TABLE skill_work ADD COLUMN save_id TEXT')
 c.execute('CREATE UNIQUE INDEX IF NOT EXISTS skill_work_save_id ON skill_work(user_id,save_id) WHERE save_id IS NOT NULL')
 if not c.execute("SELECT 1 FROM migrations WHERE version='0.5'").fetchone():
  for n in NODES:c.execute('INSERT OR IGNORE INTO subskills VALUES(?,?,?,?,?,?)',n[:6])
  # Existing item labels use a transparent initial heuristic; teachers may replace a label.
  for r in c.execute('SELECT id,topic,prompt,explanation FROM questions WHERE node IS NULL').fetchall():
   n=initial_label(r['topic'],r['prompt']+' '+r['explanation'])
   if n:c.execute('UPDATE questions SET node=? WHERE id=?',(n,r['id']))
  for n,transfer in zip(NODES,TRANSFER):
   for q in [n[6:],transfer]:
    if c.execute('SELECT 1 FROM questions WHERE topic=? AND prompt=?',(n[1],q[0])).fetchone():continue
    c.execute('INSERT INTO questions(topic,prompt,options,answer,explanation,node) VALUES(?,?,?,?,?,?)',(n[1],q[0],json.dumps(q[1],ensure_ascii=False),q[2],q[3],n[0]))
  # Backfill prior observations without changing the original attempts.
  c.execute('INSERT OR IGNORE INTO question_skill_attempts SELECT a.id,q.node FROM attempts a JOIN questions q ON q.id=a.question_id WHERE q.node IS NOT NULL')
  for row in c.execute('SELECT a.user_id,q.node,MAX(a.created) last FROM attempts a JOIN questions q ON q.id=a.question_id WHERE q.node IS NOT NULL GROUP BY a.user_id,q.node').fetchall():
   c.execute('INSERT OR IGNORE INTO review_cards VALUES(?,?,0,?,?)',(row['user_id'],row['node'],row['last']+86400,row['last']))
  c.execute("INSERT INTO migrations VALUES('0.5')")

def initial_label(topic,text):
 text=text.lower()
 options={
 'tense':('tense-perfect' if any(s in text for s in ['since','so far','完成','already','yet','for five']) else 'tense-past' if any(s in text for s in ['yesterday','过去','last','when i']) else 'tense-present'),
 'clause':('clause-relative' if any(s in text for s in ['定语','先行词','book','whose']) else 'clause-adverb' if any(s in text for s in ['although','because','状语从句']) else 'clause-noun'),
 'conditional':('conditional-unless' if 'unless' in text else 'conditional-real'),
 'subjunctive':('subjunctive-mixed' if 'now' in text and 'had' in text else 'subjunctive-past' if any(s in text for s in ['had','过去事实']) else 'subjunctive-now'),
 'nonfinite':('nonfinite-participle' if any(s in text for s in ['分词','written','broken']) else 'nonfinite-gerund' if any(s in text for s in ['enjoy','avoid','介词','动名词']) else 'nonfinite-infinitive'),
 'agreement':('agreement-either' if any(s in text for s in ['either','neither']) else 'agreement-each' if any(s in text for s in ['each','every','everyone']) else 'agreement-head')}
 return options.get(topic)

def observe(c,uid,question_ids,assisted=None):
 """One review decision per node per submission; any failure resets that node."""
 grouped={};now=time.time()
 for qid in question_ids:
  row=c.execute('SELECT a.id,a.correct,q.node FROM attempts a JOIN questions q ON q.id=a.question_id WHERE a.user_id=? AND q.id=? ORDER BY a.id DESC LIMIT 1',(uid,qid)).fetchone()
  if not row or not row['node']:continue
  c.execute('INSERT OR IGNORE INTO question_skill_attempts VALUES(?,?)',(row['id'],row['node']))
  grouped.setdefault(row['node'],[]).append(row['correct'])
  from event_service import grammar
  grammar(c,uid,row['id'],assisted)
 for node,scores in grouped.items():
  old=c.execute('SELECT * FROM review_cards WHERE user_id=? AND node=?',(uid,node)).fetchone()
  if assisted is True and all(scores):
   if old:c.execute('UPDATE review_cards SET due=MIN(due,?) WHERE user_id=? AND node=?',(now+86400,uid,node))
   else:c.execute('INSERT INTO review_cards VALUES(?,?,0,?,?)',(uid,node,now+86400,now))
   continue
  # Early repeated practice cannot accelerate the spaced schedule.
  if old and old['due']>now and all(scores):continue
  stage=min((old['stage']+1 if old else 0),4) if all(scores) else 0
  c.execute('INSERT OR REPLACE INTO review_cards VALUES(?,?,?,?,?)',(uid,node,stage,now+86400*INTERVALS[stage],now))

def evidence(c,uid):
 out=[]
 for n in c.execute('SELECT * FROM subskills ORDER BY rowid'):
  rows=c.execute('''SELECT a.id,a.question_id,a.correct,a.created FROM attempts a JOIN question_skill_attempts s ON s.attempt_id=a.id WHERE a.user_id=? AND s.node=? ORDER BY a.id''',(uid,n['id'])).fetchall()
  first={};latest={}
  for r in rows:first.setdefault(r['question_id'],r);latest[r['question_id']]=r
  recent=rows[-10:];count=len(first);success=sum(r['correct'] for r in first.values())
  card=c.execute('SELECT stage,due FROM review_cards WHERE user_id=? AND node=?',(uid,n['id'])).fetchone()
  latest_error=any(not r['correct'] for r in latest.values())
  state='待测评' if not count else '证据不足' if count<3 else '需要巩固' if latest_error or success/count<.7 else '初步稳定'
  item=dict(n);item.update(total=len(rows),distinct=count,first_correct=success,first_accuracy=round(100*success/count) if count else None,recent_accuracy=round(100*sum(r['correct'] for r in recent)/len(recent)) if recent else None,state=state,due=card['due'] if card else None,stage=card['stage'] if card else None)
  item['available']=c.execute("SELECT COUNT(*) FROM questions WHERE node=? AND status='published'",(n['id'],)).fetchone()[0]
  out.append(item)
 return out

def summary(c,uid):
 nodes=evidence(c,uid);now=time.time();byid={n['id']:n for n in nodes}
 due=sorted([n for n in nodes if n['due'] and n['due']<=now and n['available']],key=lambda n:n['due'])
 preferred=c.execute('SELECT minutes FROM study_preferences WHERE user_id=?',(uid,)).fetchone();minutes=preferred[0] if preferred else 15
 # Prefer low evidence, then first-attempt difficulty, while respecting prerequisite teaching order.
 ordered=sorted(nodes,key=lambda n:(0 if n['state']=='需要巩固' else 1 if n['distinct']<3 else 2,n['first_accuracy'] if n['first_accuracy'] is not None else 50,n['total']))
 target=next((n for n in ordered if n['available']),nodes[0]);pr=byid.get(target['prereq']);prerequisite=False
 if pr and (pr['distinct']<2 or (pr['first_accuracy'] or 0)<70) and pr['available']:target=pr;prerequisite=True
 tasks=[]
 if due:tasks.append({'kind':'review','title':'到期复习：'+due[0]['title'],'node':due[0]['id'],'minutes':min(5,minutes),'reason':'上次作答后已到复习时间；错题会回到 1 天间隔。'})
 tasks.append({'kind':'lesson','title':'学习：'+target['title'],'node':target['id'],'minutes':min(5,minutes),'reason':'前置知识仍需验证，先补这一环。' if prerequisite else f"已做 {target['distinct']} 道不同题；首次正确率为 "+(str(target['first_accuracy'])+'%。' if target['first_accuracy'] is not None else '待建立。')})
 if minutes>=10:tasks.append({'kind':'verify','title':'验证理解：'+target['title'],'node':target['id'],'minutes':5,'reason':'优先抽取未做过的题，再练最近回答错误的题。'})
 if minutes>=20:tasks.append({'kind':'skill','title':'综合训练：阅读与表达','minutes':5,'reason':'把语法应用到语境中。'})
 # Include a language skill in the daily plan; grammar and language records remain distinct.
 from lab_service import report as studio_report
 studio=studio_report(c,uid)
 profile=c.execute('SELECT focus FROM lab_profile WHERE user_id=?',(uid,)).fetchone()
 focus=profile[0] if profile else 'listening'
 labels={'listening':'听力与听写','speaking':'口语表达','reading':'阅读证据','writing':'写作修改'}
 tasks=[t for t in tasks if t['kind']!='skill']
 studied=c.execute("SELECT 1 FROM lab_work WHERE user_id=? AND date(created,'unixepoch','+8 hours')=date(?,'unixepoch','+8 hours')",(uid,now)).fetchone()
 skill_task={'kind':'studio','title':'主题训练：'+labels[focus],'minutes':5,'reason':'结合你的优先训练方式，从理解材料走向独立表达；可只完成其中一项。'}
 if not studied:tasks.insert(0,skill_task)
 elif minutes>=20:tasks.append(skill_task)
 # Keep the entire plan within the chosen daily budget.
 used=0;bounded=[]
 for task in tasks:
  if used+task['minutes']<=minutes:bounded.append(task);used+=task['minutes']
 first=c.execute('''SELECT COUNT(*),COALESCE(SUM(a.correct),0) FROM attempts a WHERE user_id=? AND a.id=(SELECT MIN(b.id) FROM attempts b WHERE b.user_id=a.user_id AND b.question_id=a.question_id)''',(uid,)).fetchone()
 repeated=c.execute('''SELECT COUNT(*),COALESCE(SUM(a.correct),0) FROM attempts a WHERE user_id=? AND a.id!=(SELECT MIN(b.id) FROM attempts b WHERE b.user_id=a.user_id AND b.question_id=a.question_id)''',(uid,)).fetchone()
 days=[dict(r) for r in c.execute("SELECT date(created,'unixepoch','+8 hours') day,COUNT(*) total,SUM(correct) correct FROM attempts WHERE user_id=? GROUP BY day ORDER BY day DESC LIMIT 30",(uid,))]
 work=c.execute('SELECT COUNT(*) FROM skill_work WHERE user_id=?',(uid,)).fetchone()[0]
 return {'studio':studio,'nodes':nodes,'due':due,'minutes':minutes,'tasks':bounded,'plan_minutes':used,'first':{'total':first[0],'correct':first[1]},'repeat':{'total':repeated[0],'correct':repeated[1]},'days':days,'skill_count':work,'coverage':sum(n['distinct']>0 for n in nodes),'limitations':'首次与重复作答的题目、间隔可能不同；两者差异不是学习效果的因果证明。细项初始标签含规则映射，教师可在题库中校正。'}

def quiz_rows(c,uid,data):
 node=data.get('node');mode=data.get('mode')
 if node:
  if not c.execute('SELECT 1 FROM subskills WHERE id=?',(node,)).fetchone():raise ValueError('细项不存在')
 elif mode=='review':
  row=c.execute("SELECT r.node FROM review_cards r WHERE r.user_id=? AND r.due<=? AND EXISTS(SELECT 1 FROM questions q WHERE q.node=r.node AND q.status='published') ORDER BY r.due LIMIT 1",(uid,time.time())).fetchone()
  if not row:return []
  node=row[0]
 else:return None
 return c.execute('''SELECT q.id,q.topic,q.prompt,q.options FROM questions q WHERE q.node=? AND q.status='published'
 ORDER BY CASE WHEN NOT EXISTS(SELECT 1 FROM attempts a WHERE a.user_id=? AND a.question_id=q.id) THEN 0
 WHEN (SELECT correct FROM attempts a WHERE a.user_id=? AND a.question_id=q.id ORDER BY a.id DESC LIMIT 1)=0 THEN 1 ELSE 2 END,RANDOM() LIMIT 5''',(node,uid,uid)).fetchall()

def validate_question(c,data):
 opts=data.get('options');a=data.get('answer')
 if not isinstance(opts,list) or len(opts)!=4 or any(not isinstance(x,str) or not 1<=len(x.strip())<=500 for x in opts) or type(a)!=int or not 0<=a<4:raise ValueError('选项或答案无效')
 for key in ('prompt','explanation','topic'):
  if not isinstance(data.get(key),str) or not 1<=len(data[key].strip())<=3000:raise ValueError('字段无效')
 if data['topic'] not in CORE:raise ValueError('知识主题无效')
 node=data.get('node') or None
 if node and not c.execute('SELECT 1 FROM subskills WHERE id=? AND topic=?',(node,data['topic'])).fetchone():raise ValueError('细项与主题不匹配')
 status=data.get('status','draft');difficulty=data.get('difficulty','medium')
 if status not in ('draft','published','disabled') or difficulty not in ('easy','medium','hard'):raise ValueError('状态或难度无效')
 return (data['topic'],data['prompt'].strip(),json.dumps(opts,ensure_ascii=False),a,data['explanation'].strip(),node,status,difficulty)

def save_question(c,uid,data):
 values=validate_question(c,data);old=data.get('id')
 if old:
  if type(old)!=int or not c.execute('SELECT 1 FROM questions WHERE id=?',(old,)).fetchone():raise ValueError('题目不存在')
  # Immutable old item preserves its attempts and already-issued quizzes.
  c.execute("UPDATE questions SET status='disabled' WHERE id=?",(old,))
 qid=c.execute('INSERT INTO questions(topic,prompt,options,answer,explanation,node,status,difficulty) VALUES(?,?,?,?,?,?,?,?)',values).lastrowid
 c.execute('INSERT INTO content_audit(actor,action,question_id,created) VALUES(?,?,?,?)',(uid,'replace:'+str(old) if old else 'create',qid,time.time()))
 return qid

def get(c,uid,admin,path,query):
 if path=='/api/study':return summary(c,uid),200
 if path=='/api/practices':
  history=[]
  for row in c.execute('SELECT * FROM skill_work WHERE user_id=? ORDER BY id DESC LIMIT 30',(uid,)):
   r=dict(row);turn=c.execute("SELECT reply FROM chat_turns WHERE user_id=? AND request_id=? AND status='complete'",(uid,r['chat_request'])).fetchone();r['feedback']=turn[0] if turn else '';history.append(r)
  return {'tasks':PRACTICES,'history':history},200
 if path.startswith('/api/manage/'):
  if not admin:return {'error':'需要管理员权限'},403
  if path=='/api/manage/questions':
   term=query.get('q',[''])[0][:100];status=query.get('status',[''])[0];topic=query.get('topic',[''])[0]
   clauses=['(q.prompt LIKE ? OR q.explanation LIKE ?)'];args=['%'+term+'%']*2
   if status:clauses.append('q.status=?');args.append(status)
   if topic:clauses.append('q.topic=?');args.append(topic)
   where=' AND '.join(clauses);total=c.execute('SELECT COUNT(*) FROM questions q WHERE '+where,args).fetchone()[0]
   page=max(1,min(10000,int(query.get('page',['1'])[0])))
   rows=[dict(r) for r in c.execute('SELECT q.* FROM questions q WHERE '+where+' ORDER BY id DESC LIMIT 30 OFFSET ?',args+[(page-1)*30])]
   for r in rows:r['options']=json.loads(r['options'])
   return {'items':rows,'total':total,'page':page},200
  if path=='/api/manage/monitor':
   day=time.strftime('%Y-%m-%d',time.gmtime());counts=[dict(r) for r in c.execute('SELECT status,COUNT(*) count FROM chat_turns WHERE created>? GROUP BY status',(time.time()-86400,))]
   errors=[dict(r) for r in c.execute("SELECT id,error,updated FROM chat_turns WHERE status='failed' ORDER BY id DESC LIMIT 10")]
   counts.extend([dict(r) for r in c.execute("SELECT 'studio-'||status status,COUNT(*) count FROM lab_jobs WHERE created>? GROUP BY status",(time.time()-86400,))])
   errors.extend([dict(r) for r in c.execute("SELECT id,error,updated FROM lab_jobs WHERE status='failed' ORDER BY id DESC LIMIT 5")])
   duration=c.execute("SELECT AVG(updated-created) FROM chat_turns WHERE status='complete' AND finish_reason!='lesson' AND created>?",(time.time()-86400,)).fetchone()[0]
   from corpus_service import reports as content_reports
   return {'corpus_reports':content_reports(c),'mail_enabled':mail_configured(),'mail_24h':[dict(r) for r in c.execute('SELECT status,COUNT(*) count FROM mail_events WHERE created>? GROUP BY status',(time.time()-86400,))],'model':os.getenv('FLOW_AI_MODEL',''),'daily_limit':int(os.getenv('FLOW_AI_DAILY_LIMIT','0')),'day':day,'used':c.execute('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE day=?',(day,)).fetchone()[0],'turns_24h':counts,'average_seconds':round(duration,1) if duration else None,'errors':errors,'drafts':c.execute("SELECT COUNT(*) FROM questions WHERE status='draft'").fetchone()[0],'pending_stale':c.execute("SELECT COUNT(*) FROM chat_turns WHERE status='pending' AND updated<?",(time.time()-120,)).fetchone()[0]},200
 return None

def post(c,uid,admin,path,data,chat):
 if path=='/api/study/preferences':
  minutes=data.get('minutes')
  if type(minutes)!=int or minutes not in (5,10,15,20,30):return {'error':'请选择 5、10、15、20 或 30 分钟'},400
  c.execute('INSERT OR REPLACE INTO study_preferences VALUES(?,?)',(uid,minutes));c.execute('UPDATE learner_goals SET minutes=? WHERE user_id=?',(minutes,uid));c.commit();return {'ok':True},200
 if path=='/api/practices/save':
  task=next((t for t in PRACTICES if t['id']==data.get('task')),None);answer=data.get('answer','');rid=data.get('chat_request','')
  if not task or not isinstance(answer,str) or not 1<=len(answer.strip())<=750:return {'error':'练习内容需为 1–750 字符'},400
  if rid:
   turn=c.execute("SELECT message FROM chat_turns WHERE user_id=? AND request_id=? AND topic=? AND status='complete'",(uid,rid,task['topic'])).fetchone()
   if not turn or not turn[0].startswith('【训练任务:'+task['id']+'】') or answer.strip() not in turn[0]:return {'error':'反馈记录与练习不匹配'},400
  save_id=data.get('save_id') or uuid.uuid4().hex
  if not isinstance(save_id,str) or not 12<=len(save_id)<=80:return {'error':'保存标识不正确'},400
  existing=c.execute('SELECT * FROM skill_work WHERE user_id=? AND save_id=?',(uid,save_id)).fetchone()
  if existing:
   if existing['task']!=task['id'] or existing['answer']!=answer.strip():return {'error':'保存标识已经使用'},409
   return {'ok':True},200
  c.execute('INSERT INTO skill_work(user_id,task,answer,chat_request,created,save_id) VALUES(?,?,?,?,?,?)',(uid,task['id'],answer.strip(),rid,time.time(),save_id));c.commit();return {'ok':True},200
 if path.startswith('/api/manage/'):
  if not admin:return {'error':'需要管理员权限'},403
  if path=='/api/manage/question':
   qid=save_question(c,uid,data);c.commit();return {'ok':True,'id':qid},200
  if path=='/api/manage/import':
   items=data.get('items')
   if not isinstance(items,list) or not 1<=len(items)<=15:return {'error':'每批导入 1–15 道题；请拆分大文件'},400
   # Validate the entire batch before any mutation. Imports always await human review.
   prepared=[{**q,'id':None,'status':'draft'} for q in items]
   for q in prepared:validate_question(c,q)
   ids=[save_question(c,uid,q) for q in prepared];c.commit();return {'ok':True,'ids':ids},200
  if path=='/api/manage/status':
   qid=data.get('id');status=data.get('status')
   if type(qid)!=int or status not in ('published','disabled','draft'):raise ValueError()
   if not c.execute('SELECT 1 FROM questions WHERE id=?',(qid,)).fetchone():return {'error':'题目不存在'},404
   c.execute('UPDATE questions SET status=? WHERE id=?',(status,qid));c.execute('INSERT INTO content_audit(actor,action,question_id,created) VALUES(?,?,?,?)',(uid,'status:'+status,qid,time.time()));c.commit();return {'ok':True},200
  if path=='/api/manage/generate':
   node=c.execute('SELECT * FROM subskills WHERE id=?',(data.get('node'),)).fetchone()
   if not node:return {'error':'请选择细项'},400
   # Use the same bounded quota and idempotency mechanism as all tutor calls.
   message='为英语学习平台生成一道关于「'+node['title']+'」的全新四选一迁移练习。仅输出JSON对象，不要代码围栏：{"prompt":"英文题干","options":["A选项","B选项","C选项","D选项"],"answer":0,"explanation":"中文解析"}。answer为0到3的整数。题目须有唯一答案。'
   out,status=chat(c,uid,{'topic':node['topic'],'message':message,'request_id':data.get('request_id')})
   if status!=200:return out,status
   if out.get('mode')!='ai':return {'error':'AI 尚未配置，可手动录入草稿'},400
   # Do not execute or publish generated content. A teacher must inspect the draft.
   try:
    text=out['reply'].strip();text=text.removeprefix('```json').removeprefix('```').removesuffix('```').strip();q=json.loads(text)
    q.update(topic=node['topic'],node=node['id'],status='draft',id=None)
    validate_question(c,q)
   except (ValueError,TypeError,AttributeError):return {'error':'AI 未返回有效题目，未保存。可到该知识点对话查看原文。'},422
   # Same generation request may be safely reloaded without duplicate drafts.
   c.execute('BEGIN IMMEDIATE')
   marker='generated:'+out['request_id'];existing=c.execute('SELECT question_id FROM content_audit WHERE actor=? AND action=?',(uid,marker)).fetchone()
   if existing:c.rollback();return {'ok':True,'id':existing[0]},200
   qid=save_question(c,uid,q);c.execute('INSERT INTO content_audit(actor,action,question_id,created) VALUES(?,?,?,?)',(uid,marker,qid,time.time()));c.commit();return {'ok':True,'id':qid},200
 return None
