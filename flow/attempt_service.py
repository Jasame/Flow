"""Server-owned attempt sessions shared by every grammar assessment entry.

A diagnostic quiz, a topic quiz, a subskill check, a review, a wrong-item retry and an adaptive
task all decide support the same way: hints are recorded by the server when they are shown,
and an item answered within the familiarity window counts as a familiar (supported) item.
The client never declares that an answer was independent.
"""
import hashlib,json,secrets,time
POLICY='flow-evidence-3.0'
FAMILIAR_WINDOW=86400
ENTRIES=('diagnostic','topic','node','review','wrongs','adaptive')
HINT_LEVELS={1:'线索',2:'对比',3:'部分支架',4:'完整答案'}

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS attempt_sessions(token TEXT PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),entry TEXT NOT NULL,target TEXT NOT NULL DEFAULT '',items TEXT NOT NULL,hints TEXT NOT NULL DEFAULT '{}',status TEXT NOT NULL DEFAULT 'active',signature TEXT NOT NULL DEFAULT '',result TEXT NOT NULL DEFAULT '',policy TEXT NOT NULL,created REAL NOT NULL,expires REAL NOT NULL,completed REAL);
 CREATE INDEX IF NOT EXISTS attempt_session_user ON attempt_sessions(user_id,created);
 CREATE TABLE IF NOT EXISTS attempt_disputes(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),attempt INTEGER NOT NULL REFERENCES attempts(id),reason TEXT NOT NULL,note TEXT NOT NULL DEFAULT '',created REAL NOT NULL,UNIQUE(user_id,attempt));''')
 c.execute("INSERT OR IGNORE INTO migrations VALUES('3.5-attempts')")

def version(row):
 return hashlib.sha256(json.dumps([row['prompt'],row['options'],row['answer']],ensure_ascii=False).encode()).hexdigest()[:12]

def exposure(c,uid,qid,now=None,exclude=None):
 """Answers are shown after every submission and by a full-answer hint (level 4) in any
 session or adaptive task; an item seen within the window is familiar. `exclude` is the
 session/task being submitted, whose own hints are counted separately as hint support."""
 now=time.time() if now is None else now;since=now-FAMILIAR_WINDOW
 last=c.execute('SELECT MAX(created) FROM attempts WHERE user_id=? AND question_id=?',(uid,qid)).fetchone()[0]
 seen=[last] if last else []
 for r in c.execute('SELECT token,hints,created FROM attempt_sessions WHERE user_id=? AND created>? AND token IS NOT ?',(uid,since,exclude)):
  if int(json.loads(r['hints'] or '{}').get(str(qid),0))>=4:seen.append(r['created'])
 for r in c.execute("SELECT answer,created FROM adaptive_tasks WHERE user_id=? AND kind='grammar' AND hint_level>=4 AND created>? AND token IS NOT ?",(uid,since,exclude)):
  if json.loads(r['answer']).get('question')==qid:seen.append(r['created'])
 last=max(seen) if seen else None
 return {'familiar':bool(last and last>since),'last_seen':last}

def recheck(c,uid,session,now=None):
 """Re-read exposure at submit time, inside the caller's write transaction.
 Another tab or entry may have shown this item's answer after this session was opened;
 familiarity only ever turns on here, never off."""
 if not session:return session
 items=json.loads(session['items']);changed=[]
 for i in items:
  if not i.get('familiar') and exposure(c,uid,i['question'],now,exclude=session['token'])['familiar']:
   i['familiar']=True;i['exposed_after_open']=True;changed.append(i['question'])
 if changed:c.execute('UPDATE attempt_sessions SET items=? WHERE token=?',(json.dumps(items),session['token']))
 return {**session,'items':json.dumps(items),'rechecked':changed}

def open_session(c,uid,entry,question_ids,target='',token=None,now=None):
 if entry not in ENTRIES:raise ValueError('测评入口不正确')
 now=time.time() if now is None else now;token=token or secrets.token_urlsafe(24);items=[]
 for qid in question_ids:
  q=c.execute('SELECT * FROM questions WHERE id=?',(qid,)).fetchone()
  items.append({'question':qid,'node':q['node'],'version':version(q),'context':'question:'+str(qid),**exposure(c,uid,qid,now)})
 c.execute('INSERT INTO attempt_sessions(token,user_id,entry,target,items,policy,created,expires) VALUES(?,?,?,?,?,?,?,?)',(token,uid,entry,target or '',json.dumps(items),POLICY,now,now+3600))
 return token,items

def get(c,uid,token):
 if not isinstance(token,str):return None
 r=c.execute('SELECT * FROM attempt_sessions WHERE token=? AND user_id=?',(token,uid)).fetchone()
 return dict(r) if r else None

def support(session,qid,hint_level=None):
 """Evidence metadata for one item. Same inputs give the same evidence from every entry."""
 items={i['question']:i for i in json.loads(session['items'])} if session else {}
 item=items.get(qid,{});level=hint_level if hint_level is not None else int(json.loads(session['hints']).get(str(qid),0)) if session else 0
 reason='hint' if level else 'familiar' if item.get('familiar') else 'none'
 return {'assisted':reason!='none','support':reason,'hint_level':level,'familiar':bool(item.get('familiar')),'session':session['token'] if session else None,'entry':session['entry'] if session else None,'version':item.get('version'),'policy':POLICY}

def signature(answers):
 return hashlib.sha256(json.dumps(answers,sort_keys=True).encode()).hexdigest()

def complete(c,token,answers,result):
 c.execute("UPDATE attempt_sessions SET status='complete',signature=?,result=?,completed=? WHERE token=?",(signature(answers),json.dumps(result,ensure_ascii=False),time.time(),token))

def grammar_hint(c,qid,level):
 """Layered help: 1 clue, 2 contrast, 3 partial scaffold (two options ruled out), 4 full answer."""
 from content_subskills import PAGES
 q=c.execute('SELECT * FROM questions WHERE id=?',(qid,)).fetchone()
 if not q:raise ValueError('题目不存在')
 node=c.execute('SELECT * FROM subskills WHERE id=?',(q['node'],)).fetchone() if q['node'] else None
 page=PAGES.get(q['node']) if q['node'] else None;options=json.loads(q['options'])
 if level==1:text=page['clue'] if page else (node['lesson'] if node else '先找句子里的时间、逻辑或主语线索。')
 elif level==2:text='对比一下：'+(' / '.join(s for s,_ in page['contrast'][:2]) if page else (node['example'] if node else '回看课程中的例句。'))
 elif level==3:
  # Rule out two wrong options in a fixed, item-specific order, so a retry shows the same scaffold.
  wrong=sorted((i for i in range(len(options)) if i!=q['answer']),key=lambda i:hashlib.sha256(f'{qid}:{i}'.encode()).hexdigest())
  removed=sorted(wrong[:2] if len(wrong)>2 else wrong[:1])
  text='可以先排除：'+'、'.join('ABCD'[i]+'. '+options[i] for i in removed)
 elif level==4:text='参考答案：'+'ABCD'[q['answer']]+'. '+options[q['answer']]+'。'+q['explanation']
 else:raise ValueError('提示层级不正确')
 return {'level':level,'kind':HINT_LEVELS[level],'text':text,'reveals_answer':level==4}

def hint(c,uid,data):
 token=data.get('token');qid=data.get('question');level=data.get('level')
 if type(qid)!=int or type(level)!=int or level not in HINT_LEVELS:raise ValueError('提示请求不正确')
 c.execute('BEGIN IMMEDIATE');s=get(c,uid,token)
 if not s or s['expires']<time.time():c.rollback();return {'error':'测评不存在或已过期'},400
 if s['status']!='active':c.rollback();return {'error':'测评已提交，提示不会再改变记录'},409
 if qid not in {i['question'] for i in json.loads(s['items'])}:c.rollback();return {'error':'题目不属于本次测评'},400
 hints=json.loads(s['hints']);hints[str(qid)]=max(level,int(hints.get(str(qid),0)))
 c.execute('UPDATE attempt_sessions SET hints=? WHERE token=?',(json.dumps(hints),token));out=grammar_hint(c,qid,level);c.commit()
 return {'hint':out,'assisted':True,'note':'看过提示后，这道题会记为“有支持的练习”，不计独立通过。'},200

DISPUTES={'misclick':'我点错了','misread':'我对题意理解不同','explanation':'解析或提示可能有误'}

def dispute(c,uid,data):
 """A learner can say a recorded mistake was a misclick or a different reading of the item.
 The original result is never rewritten; the next step becomes a fresh re-check instead of a lesson."""
 attempt=data.get('attempt');reason=data.get('reason');note=data.get('note','')
 if type(attempt)!=int or reason not in DISPUTES or not isinstance(note,str) or len(note)>400:raise ValueError('反馈内容不正确')
 if not c.execute('SELECT 1 FROM attempts WHERE id=? AND user_id=?',(attempt,uid)).fetchone():raise ValueError('作答不存在或无权反馈')
 c.execute('INSERT OR REPLACE INTO attempt_disputes(user_id,attempt,reason,note,created) VALUES(?,?,?,?,?)',(uid,attempt,reason,note.strip(),time.time()))
 if reason=='explanation':c.execute('INSERT INTO teaching_corrections(user_id,kind,ref,original,correction,created) VALUES(?,?,?,?,?,?)',(uid,'attempt',attempt,'',note.strip() or DISPUTES[reason],time.time()))
 c.commit();return {'ok':True,'message':'已记下。原作答记录保留；下一步会先换一道新题再确认一次。'},200

def disputed(c,uid,event_row):
 """Returns the dispute reason for the attempt behind a grammar event, if any."""
 if not event_row or not str(event_row['source']).startswith('grammar:'):return None
 r=c.execute('SELECT reason FROM attempt_disputes WHERE user_id=? AND attempt=?',(uid,int(event_row['source'].split(':')[1]))).fetchone()
 return r[0] if r else None

def post(c,uid,path,data):
 if path=='/api/attempt/hint':return hint(c,uid,data)
 if path=='/api/attempt/dispute':return dispute(c,uid,data)
 return None
