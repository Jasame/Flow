"""Local listening pilot built from an imported candidate pack (first: FLOW-PACK-001).

Start item -> what it tests and two possible reasons -> short checks (or straight to the explanation)
-> a branch chosen only from the check results -> its own teaching action and guided practice
-> independent verification on a new notice -> "完成本次听力" -> back to the plan.

Rules kept here:
- Visibility follows the imported pack's status: 'candidate' is admin-only; 'pilot' is admins plus
  enrolled pilot members; nothing is listed, linked or recommended to anyone else. A changed
  source pack disables the pilot until the curated version is reviewed again.
- The server never sends a correct option, evidence or explanation before that item is submitted.
- A hint, or an answer seen before (a full-answer hint or an earlier run), makes a correct answer
  "supported practice", never independent.
- Results live in pilot tables, apart from the official evidence that drives the graph and
  recommendations; personal verification is never used as formal evaluation material.
"""
import json,time,re
from pathlib import Path
from functools import lru_cache
HERE=Path(__file__).resolve().parent/'corpus_data'/'pilot'
PILOTS={'PILOT-001':'flow-pack-001.json'}
STEPS=('initial','intro','check','uncertain','teach','practice','verify','done')

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS pilot_members(user_id INTEGER NOT NULL REFERENCES users(id),pilot TEXT NOT NULL,added_by TEXT NOT NULL,created REAL NOT NULL,PRIMARY KEY(user_id,pilot));
 CREATE TABLE IF NOT EXISTS pilot_runs(id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),pilot TEXT NOT NULL,version INTEGER NOT NULL,source_hash TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',state TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL,finished REAL);
 CREATE INDEX IF NOT EXISTS pilot_runs_user ON pilot_runs(user_id,pilot,status);
 CREATE TABLE IF NOT EXISTS pilot_answers(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL REFERENCES pilot_runs(id),user_id INTEGER NOT NULL REFERENCES users(id),pilot TEXT NOT NULL,item TEXT NOT NULL,role TEXT NOT NULL,selected TEXT NOT NULL,correct INTEGER,skipped INTEGER NOT NULL DEFAULT 0,hint_level INTEGER NOT NULL DEFAULT 0,support TEXT NOT NULL,purpose TEXT NOT NULL DEFAULT 'learning',created REAL NOT NULL,UNIQUE(run_id,item));
 CREATE TABLE IF NOT EXISTS pilot_events(id INTEGER PRIMARY KEY,run_id INTEGER NOT NULL REFERENCES pilot_runs(id),user_id INTEGER NOT NULL,kind TEXT NOT NULL,data TEXT NOT NULL,created REAL NOT NULL);''')

@lru_cache(maxsize=8)
def content(pid):
 if pid not in PILOTS:raise ValueError('试点不存在')
 return json.loads((HERE/PILOTS[pid]).read_text(encoding='utf-8'))

@lru_cache(maxsize=8)
def audio_manifest(pid):
 p=HERE/(pid.lower()+'-audio.json')
 return json.loads(p.read_text(encoding='utf-8')) if p.is_file() else {}

def access(c,uid,pid):
 """(allowed, reason). Admins see candidates; pilot members see 'pilot' packs; nobody else."""
 if pid not in PILOTS:return False,'试点不存在'
 p=content(pid);row=c.execute('SELECT status,content_hash FROM corpus_packs WHERE pack_id=?',(p['source_pack'],)).fetchone()
 if not row:return False,'原始练习包还没有导入'
 if row['content_hash']!=p['source_hash']:return False,'原始练习包已更新，试点改编版需要重新审核'
 admin=c.execute('SELECT admin FROM users WHERE id=?',(uid,)).fetchone()
 if admin and admin[0]:return row['status']!='rejected',('管理员预览' if row['status']=='candidate' else row['status'])
 if row['status'] not in ('pilot','approved'):return False,'练习包未开放'
 if row['status']=='pilot' and not c.execute('SELECT 1 FROM pilot_members WHERE user_id=? AND pilot=?',(uid,pid)).fetchone():return False,'只对试点成员开放'
 return True,row['status']

def require(c,uid,pid):
 ok,why=access(c,uid,pid)
 if not ok:raise LookupError(why)
 return content(pid)

# ---------- items ----------
def items(p):
 out={p['initial']['id']:('initial',p['initial']),p['verification']['id']:('verification',p['verification'])}
 for s in p['check_sets']:
  for q in s:out[q['id']]=('check',q)
 for name,b in p['branches'].items():
  for q in b.get('drill',[]):out[q['id']]=('drill',q)
  if b.get('card'):out[b['card']['id']]=('card',b['card'])
  if b.get('practice'):out[b['practice']['id']]=('practice',b['practice'])
 return out

def clip_url(pid,name):
 f=audio_manifest(pid).get(name,{}).get('file')
 return '/api/pilot/audio?pilot='+pid+'&clip='+f[:-4] if f else None

def public(pid,q,role):
 """What a learner may see before answering: no correct key, evidence, explanation or script."""
 v={'id':q['id'],'role':role,'prompt':q.get('prompt',''),'prompt_zh':q.get('prompt_zh',''),'audio':clip_url(pid,q['clip']) if q.get('clip') else None}
 if q.get('options'):v['options']=[{'key':o['key'],'text':o['text']} for o in q['options']]
 if role=='card':v.update(slots=[s['activity'] for s in q['slots']],choices=q['choices'])
 hints=q.get('hints') or ([q['hint']] if q.get('hint') else [])
 v['hint_levels']=len(hints);return v

def hints_of(q):return q.get('hints') or ([q['hint']] if q.get('hint') else [])

# ---------- runs ----------
def fresh_state():return {'step':'initial','check_set':0,'branch':None,'decision':None,'hints':{},'path':['initial']}

def owned(c,uid,run_id):
 if type(run_id)!=int:raise ValueError('练习标识不正确')
 r=c.execute('SELECT * FROM pilot_runs WHERE id=? AND user_id=?',(run_id,uid)).fetchone()
 if not r:raise LookupError('练习不存在')
 require(c,uid,r['pilot']);return r

def event(c,run,uid,kind,data):c.execute('INSERT INTO pilot_events(run_id,user_id,kind,data,created) VALUES(?,?,?,?,?)',(run,uid,kind,json.dumps(data,ensure_ascii=False),time.time()))

def save_state(c,run_id,st):
 c.execute('UPDATE pilot_runs SET state=?,updated=? WHERE id=?',(json.dumps(st,ensure_ascii=False),time.time(),run_id))

def answers(c,run_id):return {r['item']:dict(r) for r in c.execute('SELECT * FROM pilot_answers WHERE run_id=? ORDER BY id',(run_id,))}

def start(c,uid,data):
 pid=data.get('pilot','PILOT-001');p=require(c,uid,pid)
 c.execute('BEGIN IMMEDIATE')
 old=c.execute("SELECT * FROM pilot_runs WHERE user_id=? AND pilot=? AND status='active' ORDER BY id DESC LIMIT 1",(uid,pid)).fetchone()
 if old and not data.get('restart'):c.rollback();return view(c,uid,old['id']),200
 if old:c.execute("UPDATE pilot_runs SET status='abandoned',updated=? WHERE id=?",(time.time(),old['id']))
 now=time.time();rid=c.execute('INSERT INTO pilot_runs(user_id,pilot,version,source_hash,status,state,created,updated) VALUES(?,?,?,?,?,?,?,?)',(uid,pid,p['version'],p['source_hash'],'active',json.dumps(fresh_state()),now,now)).lastrowid
 event(c,rid,uid,'start',{'pilot':pid,'version':p['version'],'source_pack':p['source_pack']});c.commit()
 return view(c,uid,rid),200

def view(c,uid,run_id):
 r=owned(c,uid,run_id);p=content(r['pilot']);st=json.loads(r['state']);done=answers(c,r['id']);pid=r['pilot']
 out={'run':r['id'],'pilot':pid,'title':p['title'],'level':p['level'],'status':r['status'],'step':st['step'],'audio_note':p['audio_note'],'status_note':p['status_note'],'answered':{k:feedback(p,k,v) for k,v in done.items()}}
 step=st['step']
 if step=='initial':out['item']=public(pid,p['initial'],'initial')
 elif step=='intro':
  sel=done[p['initial']['id']]['selected'];d=p['initial']['distractors'].get(sel,{})
  out['intro']={**p['intro'],'your_choice':sel,'choice_note':d.get('text',''),'choice_cause':d.get('cause'),'cause_note':'起始题选了哪个干扰项只用来解释，不决定接下来练什么。'}
 elif step=='check':
  out['items']=[public(pid,q,'check') for q in p['check_sets'][st['check_set']]];out['set']=st['check_set']+1
 elif step=='uncertain':
  out['decision']=st['decision'];out['can_retry']=st['check_set']+1<len(p['check_sets'])
 elif step in ('teach','practice'):
  b=p['branches'][st['branch']];out['branch']={'code':st['branch'],'name':b['name'],'why':b['why'],'action':b['action'],'points':b['points']};out['decision']=st['decision']
  if step=='teach':
   if b.get('drill'):out['drill']=[public(pid,q,'drill') for q in b['drill']]
   if b.get('card'):out['card']=public(pid,b['card'],'card')
  else:out['item']=public(pid,b['practice'],'practice')
 elif step=='verify':
  v=p['verification'];out['item']=public(pid,v,'verification');out['context_id']=v['context_id'];out['seen_before']=seen_before(c,uid,v['id'],r['id'])
  out['note']='这是一则新通知，用来检查同一种能力。不用提示独立做对，才记为独立完成。'
 elif step=='done':
  out['summary']=summary(c,r,p,st,done)
 return out

def seen_before(c,uid,item,run_id):
 return bool(c.execute('SELECT 1 FROM pilot_answers WHERE user_id=? AND item=? AND run_id!=?',(uid,item,run_id)).fetchone())

def feedback(p,item_id,a):
 role,q=items(p)[item_id];out={'item':item_id,'role':role,'selected':a['selected'],'skipped':bool(a['skipped']),'correct':None if a['correct'] is None else bool(a['correct']),'support':a['support'],'hint_level':a['hint_level']}
 if role=='card':
  out['correct_slots']={s['activity']:s['correct'] for s in q['slots']}
 elif not a['skipped']:
  out['correct_key']=q['correct'];out['correct_text']=next(o['text'] for o in q['options'] if o['key']==q['correct'])
  if q.get('explanation'):out['explanation']=q['explanation']
  if q.get('evidence'):out['evidence']=q['evidence']
  d=(q.get('distractors') or {}).get(a['selected'])
  if d:out['distractor']=d
  if q.get('clip'):out['transcript']=p['clips'][q['clip']]['text']
 return out

def expected(p,st):
 """Items the learner may answer at this step."""
 s=st['step']
 if s=='initial':return [p['initial']['id']]
 if s=='check':return [q['id'] for q in p['check_sets'][st['check_set']]]
 if s=='teach':
  b=p['branches'][st['branch']];return [q['id'] for q in b.get('drill',[])]+([b['card']['id']] if b.get('card') else [])
 if s=='practice':return [p['branches'][st['branch']]['practice']['id']]
 if s=='verify':return [p['verification']['id']]
 return []

def decide(p,results):
 """Branch only from the two short checks. The start item's distractor only explains."""
 if any(r['skipped'] for r in results.values()):return {'branch':None,'code':'skipped','text':p['uncertain']['skipped']}
 if any(r['hint_level'] for r in results.values()):return {'branch':None,'code':'hinted','text':p['uncertain']['hinted']}
 t=results['time']['correct'];b=results['binding']['correct']
 if not t and b:return {'branch':'time','code':'time','text':p['branches']['time']['why']}
 if t and not b:return {'branch':'binding','code':'binding','text':p['branches']['binding']['why']}
 code='both_right' if t and b else 'both_wrong'
 return {'branch':None,'code':code,'text':p['uncertain'][code]}

def answer(c,uid,data):
 r=owned(c,uid,data.get('run'));p=content(r['pilot']);item=data.get('item');catalog=items(p)
 if item not in catalog:raise ValueError('题目不存在')
 role,q=catalog[item];skip=data.get('skip') is True;choice=data.get('choice')
 c.execute('BEGIN IMMEDIATE')
 r=c.execute('SELECT * FROM pilot_runs WHERE id=?',(r['id'],)).fetchone();st=json.loads(r['state'])
 old=c.execute('SELECT * FROM pilot_answers WHERE run_id=? AND item=?',(r['id'],item)).fetchone()
 if old:
  same=(skip and old['skipped']) or (not skip and old['selected']==(json.dumps(choice,sort_keys=True,ensure_ascii=False) if role=='card' else choice))
  c.rollback()
  if same:return {'replayed':True,'feedback':feedback(p,item,dict(old)),'view':view(c,uid,r['id'])},200
  return {'error':'这道题已经提交过，结果不会改变。'},409
 if r['status']!='active' or item not in expected(p,st):c.rollback();return {'error':'现在不是这道题的步骤，请刷新。'},409
 if skip and role not in ('check',):c.rollback();return {'error':'这一步不能跳过。'},400
 level=int(st['hints'].get(item,0))
 if role=='card':
  if not isinstance(choice,dict) or set(choice)!={s['activity'] for s in q['slots']} or any(v not in q['choices'] for v in choice.values()):c.rollback();raise ValueError('请为每项活动选一个时间')
  correct=all(choice[s['activity']]==s['correct'] for s in q['slots']);selected=json.dumps(choice,sort_keys=True,ensure_ascii=False)
 elif skip:correct=None;selected=''
 else:
  if choice not in [o['key'] for o in q['options']]:c.rollback();raise ValueError('请选择一个选项')
  correct=choice==q['correct'];selected=choice
 hints=hints_of(q);revealed=bool(hints) and role=='verification' and level>=len(hints)
 seen=role=='verification' and seen_before(c,uid,item,r['id'])
 support='answer_seen' if revealed or seen else 'hint' if level else 'guided' if role in ('drill','card','practice') else 'none'
 purpose=q.get('purpose','learning') if role=='verification' else 'diagnosis' if role in ('initial','check') else 'learning'
 c.execute('INSERT INTO pilot_answers(run_id,user_id,pilot,item,role,selected,correct,skipped,hint_level,support,purpose,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(r['id'],uid,r['pilot'],item,role,selected,None if correct is None else int(correct),int(skip),level,support,purpose,time.time()))
 done=answers(c,r['id'])
 # advance
 if st['step']=='initial':
  st['initial']={'selected':selected,'correct':correct,'cause':(p['initial']['distractors'].get(selected) or {}).get('cause')}
  st['step']='verify' if correct else 'intro'
 elif st['step']=='check':
  ids=[q2['id'] for q2 in p['check_sets'][st['check_set']]]
  if all(i in done for i in ids):
   results={catalog[i][1]['focus']:done[i] for i in ids};d=decide(p,results);d['set']=st['check_set']+1;d['items']={catalog[i][1]['focus']:{'item':i,'correct':done[i]['correct'],'skipped':bool(done[i]['skipped']),'hint_level':done[i]['hint_level']} for i in ids}
   st.setdefault('checks',[]).append(d);st['decision']=d
   if d['branch']:st['branch']=d['branch'];st['step']='teach'
   else:st['step']='uncertain'
 elif st['step']=='teach':
  if all(i in done for i in expected(p,st)):st['step']='practice'
 elif st['step']=='practice':st['step']='verify'
 elif st['step']=='verify':st['step']='done'
 if st['path'][-1]!=st['step']:st['path'].append(st['step'])
 save_state(c,r['id'],st);c.commit()
 return {'feedback':feedback(p,item,done[item]),'view':view(c,uid,r['id'])},200

def hint(c,uid,data):
 r=owned(c,uid,data.get('run'));p=content(r['pilot']);item=data.get('item');catalog=items(p)
 if item not in catalog:raise ValueError('题目不存在')
 role,q=catalog[item];hs=hints_of(q)
 c.execute('BEGIN IMMEDIATE');st=json.loads(c.execute('SELECT state FROM pilot_runs WHERE id=?',(r['id'],)).fetchone()[0])
 if item not in expected(p,st) or c.execute('SELECT 1 FROM pilot_answers WHERE run_id=? AND item=?',(r['id'],item)).fetchone():c.rollback();return {'error':'这道题现在不能看提示'},409
 if not hs:c.rollback();return {'error':'这道题没有提示'},400
 level=min(int(st['hints'].get(item,0))+1,len(hs));st['hints'][item]=level
 event(c,r['id'],uid,'hint',{'item':item,'level':level});save_state(c,r['id'],st);c.commit()
 reveals=role=='verification' and level==len(hs)
 return {'level':level,'text':hs[level-1],'more':level<len(hs),'note':'看过提示后，这道题做对记为有支持的练习。' if not reveals else '这条提示给出了答案：这道题会记为“看过答案”，不计独立完成。'},200

def action(c,uid,data):
 r=owned(c,uid,data.get('run'));p=content(r['pilot']);act=data.get('action')
 c.execute('BEGIN IMMEDIATE');r=c.execute('SELECT * FROM pilot_runs WHERE id=?',(r['id'],)).fetchone();st=json.loads(r['state'])
 if r['status']!='active':c.rollback();return {'error':'这次练习已经结束'},409
 s=st['step']
 if act=='check' and s=='intro':st['step']='check'
 elif act=='retry' and s=='uncertain' and st['check_set']+1<len(p['check_sets']):st['check_set']+=1;st['step']='check'
 elif act=='explain' and s in ('intro','uncertain'):st['branch']='general';st['decision']=st.get('decision') or {'branch':'general','code':'chosen','text':'你选择直接看讲解。'};st['step']='teach'
 elif act=='continue' and s=='teach' and not expected(p,st):st['step']='verify'
 else:c.rollback();return {'error':'这一步不能这样操作，请刷新。'},409
 if st['path'][-1]!=st['step']:st['path'].append(st['step'])
 event(c,r['id'],uid,'action',{'action':act,'from':s,'to':st['step']});save_state(c,r['id'],st);c.commit()
 return view(c,uid,r['id']),200

def finish(c,uid,data):
 r=owned(c,uid,data.get('run'));st=json.loads(r['state'])
 if r['status']=='complete':return {'ok':True,'replayed':True,'next':'#home'},200
 if st['step']!='done':return {'error':'先完成新通知验证，再结束本次听力。'},409
 c.execute("UPDATE pilot_runs SET status='complete',finished=?,updated=? WHERE id=? AND status='active'",(time.time(),time.time(),r['id']))
 event(c,r['id'],uid,'finish',{});c.commit()
 return {'ok':True,'next':'#home','profile':'#report'},200

def summary(c,r,p,st,done):
 v=done.get(p['verification']['id'])
 if not v:return None
 label={'none':'独立完成' if v['correct'] else '独立作答，未做对','hint':'用了提示后'+('做对' if v['correct'] else '仍未做对')+'：记为有支持的练习','answer_seen':'看过答案：不计独立完成'}[v['support']]
 return {'correct':bool(v['correct']),'support':v['support'],'label':label,'purpose':'个人验证（不用于计算推荐准确率）'}

def trace(c,uid,r):
 p=content(r['pilot']);st=json.loads(r['state']);done=answers(c,r['id']);cat=items(p)
 def row(i):
  a=done.get(i)
  if not a:return None
  role,q=cat[i];return {'item':i,'origin':q.get('origin'),'role':role,'selected':a['selected'],'correct':None if a['correct'] is None else bool(a['correct']),'skipped':bool(a['skipped']),'hint_level':a['hint_level'],'support':a['support'],'purpose':a['purpose'],'at':a['created']}
 b=p['branches'].get(st.get('branch')) if st.get('branch') else None
 hints=[json.loads(e['data']) for e in c.execute("SELECT data FROM pilot_events WHERE run_id=? AND kind='hint' ORDER BY id",(r['id'],))]
 return {'run':r['id'],'pilot':r['pilot'],'title':p['title'],'source_pack':p['source_pack'],'version':r['version'],'status':r['status'],'started':r['created'],'finished':r['finished'],'path':st['path'],
  'initial':{**(row(p['initial']['id']) or {}),'cause':(st.get('initial') or {}).get('cause')} if row(p['initial']['id']) else None,
  'checks':[{'set':d['set'],'code':d['code'],'branch':d['branch'],'text':d['text'],'items':[row(x['item']) for x in d['items'].values()]} for d in st.get('checks',[])],
  'branch':{'code':st['branch'],'name':b['name'],'why':(st.get('decision') or {}).get('text')} if b else None,
  'teaching':[row(q['id']) for q in (b or {}).get('drill',[])]+([row(b['card']['id'])] if b and b.get('card') else []),
  'practice':row(b['practice']['id']) if b and b.get('practice') else None,
  'verification':{**row(p['verification']['id']),'context':p['verification']['context_id']} if row(p['verification']['id']) else None,
  'hints':hints,'summary':summary(c,r,p,st,done)}

def history(c,uid):
 out=[]
 for r in c.execute('SELECT * FROM pilot_runs WHERE user_id=? ORDER BY id DESC LIMIT 20',(uid,)).fetchall():
  if access(c,uid,r['pilot'])[0]:out.append(trace(c,uid,r))
 return {'runs':out,'note':'试点记录单独保存，不进入能力图谱和自动推荐；新通知验证是个人验证，不作为正式评测。'}

def listing(c,uid):
 out=[]
 for pid in PILOTS:
  ok,why=access(c,uid,pid)
  if not ok:continue
  p=content(pid);active=c.execute("SELECT id,state FROM pilot_runs WHERE user_id=? AND pilot=? AND status='active' ORDER BY id DESC LIMIT 1",(uid,pid)).fetchone()
  out.append({'id':pid,'title':p['title'],'level':p['level'],'skill':p['skill'],'status':why,'status_note':p['status_note'],'audio_note':p['audio_note'],'active_run':active['id'] if active else None,'minutes':'约 10 分钟'})
 return {'pilots':out}

def audio(c,uid,q):
 pid=(q.get('pilot') or [''])[0];clip=(q.get('clip') or [''])[0]
 if not re.fullmatch(r'[a-f0-9]{20}',clip):return None
 ok,_=access(c,uid,pid)
 if not ok:return None
 if not any(v['file']==clip+'.m4a' for v in audio_manifest(pid).values()):return None
 path=HERE/'audio'/(clip+'.m4a')
 return path.read_bytes() if path.is_file() else None

def get(c,uid,admin,path,q):
 try:
  if path=='/api/pilot/list':return listing(c,uid),200
  if path=='/api/pilot/run':
   rid=(q.get('id') or [''])[0]
   if not rid.isdigit():raise ValueError('练习标识不正确')
   return view(c,uid,int(rid)),200
  if path=='/api/pilot/history':return history(c,uid),200
  if path=='/api/pilot/admin/review':
   if not admin:return {'error':'需要管理员权限'},403
   return {'packs':[{'id':r['pack_id'],'candidate':r['candidate_id'],'version':r['version'],'status':r['status'],'structure':json.loads(r['structure'])} for r in c.execute('SELECT * FROM corpus_packs ORDER BY pack_id')],
    'candidates':[{'id':r['candidate_id'],'version':r['version'],'level':r['level'],'theme':r['theme'],'status':r['status'],'review':json.loads(r['review'])} for r in c.execute('SELECT * FROM corpus_candidates ORDER BY candidate_id')]},200
 except LookupError as e:return {'error':str(e)},404
 return None

def post(c,uid,admin,path,data):
 try:
  if path=='/api/pilot/start':return start(c,uid,data)
  if path=='/api/pilot/answer':return answer(c,uid,data)
  if path=='/api/pilot/hint':return hint(c,uid,data)
  if path=='/api/pilot/action':return action(c,uid,data)
  if path=='/api/pilot/finish':return finish(c,uid,data)
  if path=='/api/pilot/play':
   r=owned(c,uid,data.get('run'));event(c,r['id'],uid,'play',{'item':str(data.get('item',''))[:40],'rate':data.get('rate') if data.get('rate') in (0.8,1,1.0) else 1});c.commit();return {'ok':True},200
  if path=='/api/pilot/admin/member':
   if not admin:return {'error':'需要管理员权限'},403
   return member(c,uid,data)
  if path=='/api/pilot/admin/status':
   if not admin:return {'error':'需要管理员权限'},403
   import corpus_import
   corpus_import.set_pack_status(c,data.get('pack'),data.get('status'),'user:'+str(uid),data.get('note',''));return {'ok':True},200
 except LookupError as e:
  if c.in_transaction:c.rollback()
  return {'error':str(e)},404
 return None

def member(c,actor,data,actor_label=None):
 pid=data.get('pilot','PILOT-001')
 if pid not in PILOTS:raise ValueError('试点不存在')
 u=c.execute('SELECT id FROM users WHERE username=?',(data.get('username'),)).fetchone()
 if not u:raise ValueError('用户不存在')
 if data.get('add',True):c.execute('INSERT OR IGNORE INTO pilot_members VALUES(?,?,?,?)',(u[0],pid,actor_label or 'user:'+str(actor),time.time()))
 else:c.execute('DELETE FROM pilot_members WHERE user_id=? AND pilot=?',(u[0],pid))
 c.commit();return {'ok':True},200

if __name__=='__main__':
 import sys,app
 app.init()
 with app.db() as c:
  cmd=sys.argv[1:]
  if cmd[:1]==['enroll']:print(member(c,None,{'username':cmd[1],'pilot':cmd[2] if len(cmd)>2 else 'PILOT-001'},'cli')[0])
  elif cmd[:1]==['status']:__import__('corpus_import').set_pack_status(c,cmd[1],cmd[2],'cli',' '.join(cmd[3:]));print('ok')
  else:print('usage: pilot_service.py enroll <username> [pilot] | status <pack_id> <candidate|pilot|rejected> <note>')
