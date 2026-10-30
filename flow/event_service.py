"""Append-only learning evidence. Rule checks, self ratings and AI opinions stay distinct."""
import json,time
DAY=86400

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS learning_events(
 id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),node TEXT NOT NULL,source TEXT NOT NULL,
 kind TEXT NOT NULL,item TEXT NOT NULL,context TEXT NOT NULL DEFAULT '',correct INTEGER,assisted INTEGER,
 evaluator TEXT NOT NULL,details TEXT NOT NULL DEFAULT '{}',created REAL NOT NULL,
 UNIQUE(user_id,node,source));
 CREATE INDEX IF NOT EXISTS learning_event_node ON learning_events(user_id,node,id);
 CREATE INDEX IF NOT EXISTS learning_event_time ON learning_events(user_id,created);''')

def record(c,uid,node,source,kind,item,context='',correct=None,assisted=None,evaluator='rule',details=None,created=None):
 c.execute('INSERT OR IGNORE INTO learning_events(user_id,node,source,kind,item,context,correct,assisted,evaluator,details,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
 (uid,node,source,kind,item,context,None if correct is None else int(correct),None if assisted is None else int(assisted),evaluator,json.dumps(details or {},ensure_ascii=False),time.time() if created is None else created))

def grammar(c,uid,attempt,assisted=None):
 r=c.execute('SELECT a.*,s.node FROM attempts a JOIN question_skill_attempts s ON s.attempt_id=a.id WHERE a.id=? AND a.user_id=?',(attempt,uid)).fetchone()
 if r:record(c,uid,r['node'],'grammar:'+str(r['id']),'choice',str(r['question_id']),'question:'+str(r['question_id']),bool(r['correct']),assisted,'rule' if assisted is not None else 'legacy',created=r['created'])

def studio(c,uid,work_id):
 r=c.execute('SELECT w.*,p.content FROM lab_work w JOIN lab_packs p ON p.id=w.pack WHERE w.id=? AND w.user_id=?',(work_id,uid)).fetchone()
 if not r:return
 p=json.loads(r['content']);d=json.loads(r['details']);source='studio:'+str(work_id)
 # Comprehension checks apply to the material, never certify all associated grammar.
 objective=d.get('kind') in ('comprehension','dictation');correct=all(x['correct'] for x in d.get('results',[])) if d.get('kind')=='comprehension' else d.get('accuracy')==100 if d.get('kind')=='dictation' else None
 context=__import__('practice_service').family(p)
 node='skill:'+r['skill'];record(c,uid,node,source,'comprehension' if objective else 'expression' if d.get('kind')=='work' else 'dictation',r['pack'],context,correct,d.get('assisted'),'rule' if objective else 'practice',{'work':work_id,'kind':d.get('kind')},r['created'])
 from content_v07 import metadata
 for n in metadata(p)['grammar']:record(c,uid,n,source,'exposure',r['pack'],r['pack'],evaluator='practice',details={'skill':r['skill'],'work':work_id},created=r['created'])


def state(c,uid,node):
 rows=[dict(r) for r in c.execute('SELECT * FROM learning_events WHERE user_id=? AND node=? ORDER BY created,id',(uid,node))]
 return summarize(node,rows)

def summarize(node,rows):
 verified=[r for r in rows if r['correct'] is not None and r['evaluator'] in ('rule','legacy')]
 independent=[r for r in verified if r['assisted']==0 and r['correct']==1]
 distinct={r['item'] for r in independent};delayed=[];transfer=[];anchors=[];seen_sources=set()
 for r in independent:
  if r['source'] in seen_sources:continue
  seen_sources.add(r['source'])
  compatible=[p for p in anchors if not node.startswith('sense:') or p['kind']==r['kind']]
  if compatible and compatible[0]['created']<=r['created']-DAY:delayed.append(r)
  if any(p['context']!=r['context'] and p['created']<=r['created']-DAY for p in compatible):transfer.append(r)
  if not compatible or len(compatible)==1 and compatible[0]['context']!=r['context']:anchors.append(r)
 status='待建立' if not rows else '待验证'
 if independent:status='独立完成' if len(distinct)>=2 else '独立完成一次'
 if delayed:status='延迟记得'
 if transfer:status='迁移已有证据'
 if verified and not verified[-1]['correct']:status='需要巩固'
 elif verified and verified[-1]['assisted']==1 and not delayed:status='提示后完成'
 return {'node':node,'state':status,'events':len(rows),'verified':len(verified),'independent':len(independent),'distinct':len(distinct),'delayed':len(delayed),'transfer':len(transfer),'self_ratings':sum(r['evaluator']=='self' for r in rows),'ai_observations':sum(r['evaluator']=='ai' for r in rows),'exposures':sum(r['kind']=='exposure' for r in rows),'last':rows[-1]['created'] if rows else None,'evidence':[{'id':r['id'],'kind':r['kind'],'item':r['item'],'context':r['context'],'correct':r['correct'],'assisted':r['assisted'],'evaluator':r['evaluator'],'created':r['created'],'details':json.loads(r['details'])} for r in rows[-8:][::-1]],'note':'状态是规则汇总，不是能力概率。延迟验证至少间隔24小时；迁移证据限定于新题或新语境中的结构化练习。自评与AI意见不等同于客观通过。'}

def report(c,uid):
 now=time.time();rows=[dict(r) for r in c.execute('SELECT node,correct,assisted,evaluator,created FROM learning_events WHERE user_id=? ORDER BY id',(uid,))]
 nodes={r['node'] for r in rows};states=[state(c,uid,n) for n in nodes];days=[]
 for i in range(6,-1,-1):
  from datetime import datetime,timedelta,timezone
  day=(datetime.now(timezone(timedelta(hours=8))).date()-timedelta(days=i)).isoformat()
  matches=[r for r in rows if datetime.fromtimestamp(r['created'],timezone(timedelta(hours=8))).date().isoformat()==day]
  objective=[r for r in matches if r['correct'] is not None and r['assisted']==0 and r['evaluator']=='rule']
  days.append({'day':day,'events':len(matches),'independent_checks':len(objective),'correct':sum(r['correct'] for r in objective)})
 return {'events':len(rows),'nodes':len(nodes),'independent':sum(s['independent'] for s in states),'delayed':sum(s['delayed'] for s in states),'transfer':sum(s['transfer'] for s in states),'needs_review':sum(s['state']=='需要巩固' for s in states),'days':days,'states':states,'note':'记录反映已观察到的表现；不承诺学习效果，也不把重复练习、AI反馈和独立验证混为一谈。'}
