"""Small, persistent guided lessons. Guided success never certifies independent ability."""
import json,re,time
import event_service as events
LESSONS={
 'food':{'title':'自己说一句点餐请求','meaning':'我想要汤，谢谢。','example':"I'd like soup, please.",'contrast':'把 soup 换成 water，就能表达想要水。','prompt':'请选择“我想要水，谢谢”的表达。','options':["I'd like water, please.",'The water is yesterday.','I water like please.'],'target':"I'd like water, please.",'node':'skill:writing','skill':'writing'},
 'directions':{'title':'问一句路','meaning':'请问，车站在哪里？','example':'Excuse me. Where is the station?','contrast':'把 station 换成 hotel，问酒店在哪里。','prompt':'请选择询问酒店位置的表达。','options':['Where is the hotel?','The hotel is a person.','Where hotel the is?'],'target':'Where is the hotel?','node':'skill:writing','skill':'writing'},
 'hotel':{'title':'说明自己有预订','meaning':'我有一个预订。','example':'I have a booking.','contrast':'先用 I have 表示“我有”，再接 a booking。','prompt':'请选择“我有一个预订”。','options':['I have a booking.','I booking has.','Have booking I a.'],'target':'I have a booking.','node':'skill:writing','skill':'writing'},
 'grammar:tense-present':{'title':'先弄懂一句，再做语法题','meaning':'她每天步行。','example':'She walks every day.','contrast':'每天的习惯：She walks every day. 正在发生：She is walking now. 说 he/she 时，习惯动作的动词通常要变化。','prompt':'每天的习惯应该怎样说？','options':['She walks every day.','She walking every day.','She walk every day.'],'target':'He walks every day.','write_prompt':'把 She 换成 He，写出目标句：He walks every day.','node':'tense-present','skill':'grammar'}
}

LESSONS.update({
 'work-request':{'title':'用一句话提出工作请求','meaning':'你能把文件发给我吗？','example':'Could you send me the file, please?','contrast':'把 file 换成 report，就能请求一份报告。','prompt':'请选择“你能把报告发给我吗？”','options':['Could you send me the report, please?','Could you sent me the report?','The report send you me.'],'target':'Could you send me the report, please?','node':'skill:writing','skill':'writing'},
 'work-confirm':{'title':'确认收到一封邮件','meaning':'谢谢你的邮件。','example':'Thank you for your email.','contrast':'确认收到文件，可以接一句：I have the file.','prompt':'请选择“我收到文件了”。','options':['I have the file.','I has the file.','The file have I.'],'target':'I have the file.','node':'skill:writing','skill':'writing'},
 'campus-help':{'title':'请别人再说一次','meaning':'请你再说一次，可以吗？','example':'Could you say that again, please?','contrast':'没听清时可以直接使用这句；不需要先说一大段。','prompt':'没听清时怎样礼貌地请求重复？','options':['Could you say that again, please?','You said yesterday again.','Again that could say.'],'target':'Could you say that again, please?','node':'skill:writing','skill':'writing'}
})
ROUTES={'travel':('food','directions','hotel'),'work':('work-request','work-confirm','campus-help'),'campus':('campus-help','work-request','food')}

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS foundation_preferences(user_id INTEGER PRIMARY KEY REFERENCES users(id),mode TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS foundation_progress(user_id INTEGER REFERENCES users(id),lesson TEXT,step INTEGER NOT NULL DEFAULT 0,answer TEXT NOT NULL DEFAULT '',updated REAL,PRIMARY KEY(user_id,lesson));
 CREATE TABLE IF NOT EXISTS foundation_review_requests(user_id INTEGER,request_id TEXT,lesson TEXT,answer TEXT,result TEXT,PRIMARY KEY(user_id,request_id));
 CREATE TABLE IF NOT EXISTS foundation_reviews(user_id INTEGER REFERENCES users(id),lesson TEXT,completed REAL,due REAL,round INTEGER DEFAULT 0,last_answer TEXT DEFAULT '',PRIMARY KEY(user_id,lesson));''')
 if 'draft_revision' not in {r[1] for r in c.execute('PRAGMA table_info(foundation_progress)')}:c.execute('ALTER TABLE foundation_progress ADD COLUMN draft_revision INTEGER NOT NULL DEFAULT 0')
 # Clean legacy choice values only: genuine text drafts remain untouched.
 c.execute("UPDATE foundation_progress SET answer='' WHERE step=2 AND answer='0'")
 from lexicon_service import save,sync_packs
 basic_words=[('water','水',"I'd like water, please.",'travel'),('soup','汤',"I'd like soup, please.",'travel'),('file','文件','Could you send me the file, please?','work'),('report','报告','Could you send me the report, please?','work'),('hotel','酒店','Where is the hotel?','travel'),('station','车站','Where is the station?','travel'),('again','再一次','Could you say that again, please?','campus')]
 for word,meaning,example,theme in basic_words:
  if not c.execute("SELECT 1 FROM lexicon WHERE lemma=? AND owner IS NULL AND status='published'",(word,)).fetchone():save(c,{'word':word,'sense':'basic','meaning':meaning,'example':example,'level':'A2','theme':theme,'source':'Flow基础微课配套原创示例，持续校对中'},'published','foundation')
 sync_packs(c)
 for key,d in LESSONS.items():
  c.execute('INSERT OR IGNORE INTO kg_nodes VALUES(?,?,?,NULL,?)',('lesson:'+key,'lesson',d['title'],key))
  c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',('lesson:'+key,d['node'],'trains','curriculum'))
  for word in ('booking','file','report','water','soup','hotel','station','again'):
   if re.search(r'\b'+word+r'\b',d['example']+' '+d['target'],re.I):
    for r in c.execute("SELECT id FROM lexicon WHERE lemma=? AND owner IS NULL AND status='published'",(word,)).fetchall():c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',('sense:'+r['id'],'lesson:'+key,'practised_in','curriculum'))
 for r in c.execute('SELECT user_id,lesson,updated,answer FROM foundation_progress WHERE step>=3').fetchall():
  c.execute('INSERT OR IGNORE INTO foundation_reviews(user_id,lesson,completed,due) VALUES(?,?,?,?)',(r['user_id'],r['lesson'],r['updated'],r['updated']+86400))
  record_links(c,r['user_id'],r['lesson'],r['answer'],r['updated'])
 c.execute("INSERT OR IGNORE INTO migrations VALUES('3.2-continuity')")

def is_basic(c,uid):
 p=c.execute('SELECT mode FROM foundation_preferences WHERE user_id=?',(uid,)).fetchone()
 if p:return p[0]=='basic'
 row=c.execute('SELECT placement FROM coach_profiles WHERE user_id=?',(uid,)).fetchone()
 if not row:return False
 d=json.loads(row[0]);scores=d.get('scores',{});total=sum(s.get('total',0)-s.get('hinted',0) for s in scores.values());good=sum(s.get('correct',0)-s.get('hinted',0) for s in scores.values())
 return d.get('mode')=='foundation' or total<4 or good/max(1,total)<.5

def lesson(c,uid,key):
 if key in LESSONS:return dict(LESSONS[key])
 if key.startswith('word:'):
  from lexicon_service import entry_for
  r=entry_for(c,uid,key[5:]);e=r['data'];return {'title':'先认识 '+e['word'],'meaning':e['meaning'],'example':e['example'],'contrast':'先看词义和例句，再回忆词条原形。','prompt':'请选择 '+e['word']+' 的含义。','options':[e['meaning'],'与当前词条含义不同','我想先回看例句'],'target':e['word'],'node':'sense:'+r['id'],'skill':'vocabulary','write_prompt':'对照词卡写出词条：'+e['word']}
 if key.startswith('grammar:'):
  r=c.execute('SELECT id,title,lesson,example FROM subskills WHERE id=?',(key[8:],)).fetchone()
  if not r:raise ValueError('知识点不存在')
  return {'title':'先学：'+r['title'],'meaning':r['lesson'],'example':r['example'],'contrast':'理解后对照仿写；有支持的练习不计独立测评。','prompt':'这一步先做什么？','options':['对照例句理解结构，再仿写','跳过讲解反复猜题','用XP判断已经掌握'],'target':r['example'],'node':r['id'],'skill':'grammar','write_prompt':'对照例句写一遍：'+r['example']}
 raise ValueError('基础课程不存在或已不可用')

def record_links(c,uid,key,answer,created=None):
 if key not in LESSONS:return
 events.record(c,uid,'lesson:'+key,'foundation:'+key,'guided',key,'foundation:'+key,evaluator='practice',assisted=True,details={'answer':answer,'guided':True},created=created)
 for r in c.execute("SELECT source FROM kg_edges WHERE target=? AND relation='practised_in'",('lesson:'+key,)).fetchall():events.record(c,uid,r[0],'foundation:'+key,'exposure',key,'foundation:'+key,evaluator='practice',assisted=True,details={'lesson':key,'note':'在短句中接触，不代表独立理解该词义'},created=created)

def view(c,uid,key):
 d=lesson(c,uid,key);r=c.execute('SELECT * FROM foundation_progress WHERE user_id=? AND lesson=?',(uid,key)).fetchone()
 # Rotate guided choices by account/lesson, and map the submitted index on the server.
 offset=(uid+sum(map(ord,key)))%len(d['options']);d['options']=d['options'][offset:]+d['options'][:offset]
 review=c.execute('SELECT * FROM foundation_reviews WHERE user_id=? AND lesson=?',(uid,key)).fetchone()
 return {'lesson':key,'step':r['step'] if r else 0,'answer':r['answer'] if r else '', 'updated':r['updated'] if r else 0,'review_meaning':{'food':'我想要水，谢谢。','directions':'酒店在哪里？','work-request':'你能把报告发给我吗？','work-confirm':'我收到文件了。'}.get(key,d['meaning']),'revision':r['draft_revision'] if r else 0,**d,'due':review['due'] if review else None,'note':'这是有支持的学习。复习记录与独立测评分别保存。'}

def recommended(c,uid):
 now=time.time();rows=c.execute('SELECT * FROM foundation_progress WHERE user_id=? ORDER BY updated DESC',(uid,)).fetchall();done={r['lesson'] for r in rows if r['step']>=3}
 for r in rows:
  if r['step']>=3:continue
  try:d=lesson(c,uid,r['lesson'])
  except ValueError:continue
  return {'lesson':r['lesson'],'title':'继续：'+d['title'],'completed':len(done),'review':False}
 reviews=c.execute('SELECT * FROM foundation_reviews WHERE user_id=? ORDER BY due',(uid,)).fetchall()
 for r in reviews:
  if r['due']>now:continue
  try:d=lesson(c,uid,r['lesson'])
  except ValueError:continue
  return {'lesson':r['lesson'],'title':'复习：'+d['title'],'completed':len(done),'review':True,'due':r['due']}
 row=c.execute('SELECT goal,interests FROM coach_profiles WHERE user_id=?',(uid,)).fetchone();text=' '.join(row) if row else ''
 route=ROUTES['travel' if not row else 'work' if re.search('工作|职场|work|email',text,re.I) else 'travel' if re.search('旅行|旅游|点餐|travel',text,re.I) else 'campus']
 key=next((k for k in route if k not in done),None)
 if key:return {'lesson':key,'title':LESSONS[key]['title'],'completed':len(done),'review':False}
 for r in reviews:
  try:d=lesson(c,uid,r['lesson'])
  except ValueError:continue
  return {'lesson':r['lesson'],'title':'再练一句：'+d['title'],'completed':len(done),'review':True,'due':r['due'],'optional':True}
 return None

def get(c,uid,path,q):
 if path=='/api/foundation/lesson':return view(c,uid,q.get('id',['food'])[0]),200
 return None

def normalize(s):
 s=s.casefold().replace('’',"'").replace("i'd",'i would').replace("i've",'i have')
 return ' '.join(re.findall(r"[a-z0-9]+",s))

def post(c,uid,path,data):
 if path=='/api/foundation/mode':
  mode=data.get('mode')
  if mode not in ('basic','standard'):raise ValueError('学习模式不正确')
  c.execute('INSERT OR REPLACE INTO foundation_preferences VALUES(?,?)',(uid,mode));c.commit();return {'ok':True},200
 key=data.get('lesson');answer=data.get('answer','')
 if path not in ('/api/foundation/draft','/api/foundation/step','/api/foundation/review'):return None
 if not isinstance(key,str) or not isinstance(answer,str) or len(answer)>1200:raise ValueError('回答格式或长度不正确')
 d=lesson(c,uid,key)
 if path=='/api/foundation/draft':
  revision=data.get('revision')
  if revision is not None and (type(revision)!=int or not 0<=revision<=9000000000000000):raise ValueError('草稿版本不正确')
  if revision is None:c.execute('UPDATE foundation_progress SET answer=?,updated=?,draft_revision=draft_revision+1 WHERE user_id=? AND lesson=? AND step=2',(answer,time.time(),uid,key))
  else:c.execute('UPDATE foundation_progress SET answer=?,updated=?,draft_revision=? WHERE user_id=? AND lesson=? AND step=2 AND draft_revision<?',(answer,time.time(),revision,uid,key,revision))
  c.commit();return {'ok':True,'current':view(c,uid,key)},200
 if path=='/api/foundation/review':
  rid=data.get('request_id')
  if rid is not None and (not isinstance(rid,str) or not 12<=len(rid)<=100):raise ValueError('请求标识不正确')
  c.execute('BEGIN IMMEDIATE')
  prior=c.execute('SELECT * FROM foundation_review_requests WHERE user_id=? AND request_id=?',(uid,rid)).fetchone() if rid else None
  if prior:
   c.rollback()
   if prior['lesson']!=key or prior['answer']!=answer:raise ValueError('请为修改后的复习使用新的请求标识')
   return json.loads(prior['result']),200
  r=c.execute('SELECT * FROM foundation_reviews WHERE user_id=? AND lesson=?',(uid,key)).fetchone()
  if not r:c.rollback();raise ValueError('请先完成这节基础课')
  passed=normalize(answer)==normalize(d['target'])
  if not passed:c.rollback();return {'ok':False,'message':'这次先借助目标句，再写一遍：'+d['target']},200
  now=time.time();round=r['round']+1
  # Early optional practice never postpones an already scheduled review.
  due=now+min(7,2**min(round,3))*86400 if now>=r['due'] else r['due']
  c.execute('UPDATE foundation_reviews SET due=?,round=?,last_answer=? WHERE user_id=? AND lesson=?',(due,round,answer,uid,key))
  events.record(c,uid,d['node'],'foundation-review:'+key+':'+str(round),'recall',key,'foundation:'+key,evaluator='practice',assisted=True,details={'answer':answer,'note':'课程复习，不是独立能力认证'})
  result={'ok':True,'due':due,'next':recommended(c,uid),'message':'这次复习已保存。下一次复习会继续提醒。'}
  if rid:c.execute('INSERT INTO foundation_review_requests VALUES(?,?,?,?,?)',(uid,rid,key,answer,json.dumps(result,ensure_ascii=False)))
  if key in LESSONS:events.record(c,uid,'lesson:'+key,'foundation-review:'+key+':'+str(round),'recall',key,'foundation:'+key,evaluator='practice',assisted=True,details={'answer':answer,'note':'课程复习，独立运用待验证'})
  c.commit();return result,200
 step=data.get('step')
 if type(step)!=int or step not in (0,1,2):raise ValueError('学习步骤不正确')
 c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT step FROM foundation_progress WHERE user_id=? AND lesson=?',(uid,key)).fetchone();current=r[0] if r else 0
 if current!=step:c.rollback();return {'error':'进度已同步到最新步骤','current':view(c,uid,key)},409
 offset=(uid+sum(map(ord,key)))%len(d['options']);correct_index=(-offset)%len(d['options'])
 passed=step==0 or step==1 and answer==str(correct_index) or step==2 and normalize(answer)==normalize(d['target'])
 if not passed:c.rollback();return {'ok':False,'message':'这一小步还可再试。'+('请练指定形式，也接受常见缩写：'+d['target'] if step==2 else '先对照上面的中英例句，再选一次。')},200
 c.execute('INSERT INTO foundation_progress(user_id,lesson,step,answer,updated) VALUES(?,?,?,?,?) ON CONFLICT(user_id,lesson) DO UPDATE SET step=excluded.step,answer=excluded.answer,updated=excluded.updated',(uid,key,step+1,answer if step==2 else '',time.time()))
 if step==2:
  events.record(c,uid,d['node'],'foundation:'+key,'guided',key,'foundation:'+key,evaluator='practice',assisted=True,details={'answer':answer,'guided':True,'skill':d['skill']})
  record_links(c,uid,key,answer)
  c.execute('INSERT OR IGNORE INTO foundation_reviews(user_id,lesson,completed,due) VALUES(?,?,?,?)',(uid,key,time.time(),time.time()+86400))
 c.commit();return {'ok':True,'current':view(c,uid,key),'next':recommended(c,uid)},200
