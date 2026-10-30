"""Evidence-led curriculum, delayed verification, diagnostics and weekly reports.
No model call is needed for scoring, scheduling, reporting or awarding evidence badges.
"""
import json,time,secrets,re,datetime
from collections import defaultdict
import event_service as events
import lexicon_service as lex
import quality_service as quality
DAY=86400
TZ=datetime.timezone(datetime.timedelta(hours=8))
SKILLS={'vocabulary':'词汇','grammar':'语法','listening':'听力','speaking':'口语','reading':'阅读','writing':'写作'}
POLICY='flow-evidence-2.1'

def schema(c):
 quality.schema(c)
 c.executescript('''CREATE TABLE IF NOT EXISTS teaching_corrections(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),kind TEXT,ref INTEGER,original TEXT,correction TEXT,created REAL);
 CREATE TABLE IF NOT EXISTS growth_stage_requests(user_id INTEGER REFERENCES users(id),request_id TEXT,chapter INTEGER,created REAL,PRIMARY KEY(user_id,request_id));
 CREATE TABLE IF NOT EXISTS growth_mission_meta(mission TEXT PRIMARY KEY REFERENCES coach_missions(id),position INTEGER,session INTEGER,rationale TEXT,path TEXT,verification TEXT);
 CREATE TABLE IF NOT EXISTS growth_settings(user_id INTEGER PRIMARY KEY REFERENCES users(id),theme TEXT DEFAULT 'auto',hotspots INTEGER DEFAULT 0);''')
 c.execute("INSERT OR IGNORE INTO migrations VALUES('2.1')")

def history(c,uid):
 grouped=defaultdict(list)
 for r in c.execute('SELECT * FROM learning_events WHERE user_id=? ORDER BY created,id',(uid,)):grouped[r['node']].append(dict(r))
 return grouped

def structured(rows):return [r for r in rows if r['correct'] is not None and r['evaluator']=='rule']
def successes(rows):return [r for r in structured(rows) if r['correct']==1 and r['assisted']==0]

def settings(c,uid):
 r=c.execute('SELECT theme,hotspots FROM growth_settings WHERE user_id=?',(uid,)).fetchone()
 return dict(r) if r else {'theme':'auto','hotspots':0}

def theme_for(c,uid):
 s=settings(c,uid)
 if s['theme']!='auto':return s['theme']
 p=c.execute('SELECT goal,interests FROM coach_profiles WHERE user_id=?',(uid,)).fetchone()
 if not p:
  lab=c.execute('SELECT theme FROM lab_profile WHERE user_id=?',(uid,)).fetchone()
  if lab:return lab[0]
 text=' '.join(p) if p else ''
 for pattern,theme in [('旅行|旅游|travel','travel'),('职场|工作|work','work'),('科学|科技|science','science'),('电影|文化|culture','culture'),('生活|日常|life','life')]:
  if re.search(pattern,text,re.I):return theme
 return 'campus'

def node_targets(c,uid):
 out={r['id']:{'node':r['id'],'title':r['title'],'kind':'grammar','target':r['id'],'due':None,'prereq':r['prereq']} for r in c.execute('SELECT id,title,prereq FROM subskills WHERE EXISTS(SELECT 1 FROM questions WHERE node=subskills.id AND status=\'published\')')}
 for r in c.execute("SELECT l.id,l.lemma,e.due FROM lexicon l LEFT JOIN vocab_enroll e ON e.entry=l.id AND e.user_id=? WHERE l.status='published' AND (l.owner IS NULL OR l.owner=?) AND (e.entry IS NOT NULL OR EXISTS(SELECT 1 FROM learning_events v WHERE v.user_id=? AND v.node='sense:'||l.id))",(uid,uid,uid)):
  node=lex.node_id(r['id']);out[node]={'node':node,'title':r['lemma'],'kind':'vocab','target':r['id'],'due':r['due'],'prereq':None}
 for r in c.execute('SELECT node,due FROM review_cards WHERE user_id=?',(uid,)):
  if r['node'] in out:out[r['node']]['due']=r['due']
 return out

def review_queue(c,uid,now=None):
 now=time.time() if now is None else now;grouped=history(c,uid);targets=node_targets(c,uid);out=[]
 observations={}
 for r in c.execute("SELECT * FROM ai_observations WHERE user_id=? AND status='proposed' ORDER BY id DESC",(uid,)):
  if r['node'] not in observations and not any(x['created']>r['created'] for x in structured(grouped[r['node']])):observations[r['node']]=dict(r)
 for node,target in targets.items():
  rows=grouped[node];checks=structured(rows);good=successes(rows);last=checks[-1] if checks else None;prior=good[-1] if good else None;state=events.summarize(node,rows)
  purpose='diagnostic';reason='尚缺独立题目证据，先做一个小检查。';priority=5;ready=now;evidence=[]
  if last and last['correct']==0:purpose='repair';reason='最近一次结构化练习未通过，先修复错误，再延迟验证。';priority=0;evidence=[last['id']]
  elif last and last['assisted']==1:purpose='unassisted';reason='最近使用过提示或做过熟悉题，隔天再安排独立验证；现在可继续普通练习或原计划。';priority=1;ready=last['created']+DAY;evidence=[last['id']]
  elif node in observations:purpose='hypothesis';reason='AI从真实表达提出了待验证线索，先用题目检查；尚未认定为薄弱点。';priority=2;evidence=[]
  elif prior:
   ready=max(prior['created']+DAY,target['due'] or 0)
   purpose='transfer' if state['delayed'] else 'delayed';priority=3 if purpose=='delayed' else 4
   reason='至少间隔24小时后独立回忆。' if purpose=='delayed' else '已有延迟回忆证据，接下来尝试不同题目或新材料语境。'
   evidence=[prior['id']]
  elif target['due'] is not None and target['due']<=now:priority=2;reason='已到复习时间，但尚缺独立通过证据。'
  if not rows and node not in observations:continue
  out.append({**target,'purpose':purpose,'reason':reason,'priority':priority,'ready_at':ready,'ready':ready<=now,'state':state['state'],'evidence_ids':evidence,'observation':observations.get(node),'prior_contexts':list(dict.fromkeys(r['context'] for r in good))[-20:]})
 out.sort(key=lambda r:(not r['ready'],r['priority'],r['ready_at'],r['node']))
 return out

def diagnostics(c,uid):
 grouped=history(c,uid);allrows=[r for rows in grouped.values() for r in rows];dimensions=[];hypotheses=[]
 for skill,title in SKILLS.items():
  if skill=='grammar':rows=[r for node,items in grouped.items() if not node.startswith(('sense:','skill:')) for r in items if r['kind']!='exposure']
  elif skill=='vocabulary':rows=grouped['skill:vocabulary']+[r for node,items in grouped.items() if node.startswith('sense:') for r in items]
  else:rows=grouped['skill:'+skill]
  rows=sorted(rows,key=lambda r:(r['created'],r['id']));checks=structured(rows);good=successes(rows);samples=[r for r in rows if r['kind'] in ('expression','feedback')]
  state='待了解' if not checks and not samples else '已采集表达，待继续验证' if not checks else '有独立通过证据' if good else '需要独立检查'
  if checks and checks[-1]['correct']==0:state='最近检查需要巩固'
  dimensions.append({'skill':skill,'title':title,'status':state,'checks':len(checks),'independent_passes':len(good),'contexts':len({r['context'] for r in good}),'samples':len(samples),'evidence_ids':[r['id'] for r in sorted(rows,key=lambda r:r['created'])[-4:]],'note':'未采集的能力保持待了解；表达样本和AI反馈不等同于客观通过。'})
 # Compare performance on the same material; this is a hypothesis, not a diagnosis of hearing.
 read={r['context']:r for r in successes(grouped['skill:reading'])};pairs=[]
 for r in structured(grouped['skill:listening']):
  if not r['correct'] and r['assisted']==0 and r['context'] in read:pairs.append((r,read[r['context']]))
 if len({a['context'] for a,b in pairs})>=2:
  hypotheses.append({'kind':'listening_gap','title':'可能存在“看得懂，但听辨仍困难”的情况','reason':'至少两份相同材料出现阅读独立通过、听力未通过。可先练短句听辨，并换新材料复测。','evidence_ids':[x['id'] for pair in pairs[-2:] for x in pair],'status':'待验证'})
 wrongwords=[r for node,items in grouped.items() if node.startswith('sense:') for r in structured(items) if not r['correct']]
 if len({r['node'] for r in wrongwords[-10:]})>=2:hypotheses.append({'kind':'word_recall','title':'部分词义或主动回忆需要巩固','reason':'不同词条有未通过记录；先区分理解题与拼写回忆，再观察新语境使用。','evidence_ids':[r['id'] for r in wrongwords[-3:]],'status':'待验证'})
 observations=[dict(r) for r in c.execute("SELECT id,node,evidence,reason,status,created FROM ai_observations WHERE user_id=? AND status='proposed' ORDER BY id DESC LIMIT 12",(uid,))]
 return {'dimensions':dimensions,'hypotheses':hypotheses,'difficulty':difficulty(c,uid),'observations':observations,'calibration':min(3,c.execute('SELECT COUNT(DISTINCT pack) FROM lab_work WHERE user_id=?',(uid,)).fetchone()[0]),'note':'前几次训练用于持续校准；不根据少量题目生成完整能力等级。'}

def difficulty(c,uid):
 from practice_service import bands,starting,LEVELS
 d=bands(c,uid);base=starting(c,uid);level=min((d[s]['level'] for s in ('reading','listening')),key=LEVELS.index)
 return {'level':level,'starting_level':base,'reason':'综合单元取听读建议中较稳妥的一档；两项分别观察，至少六个不同情境才调整，表达另行采样。','evidence_ids':list(dict.fromkeys(i for s in ('reading','listening') for i in d[s]['evidence_ids']))}

def material_candidates(c,uid,node=None):
 from practice_service import rank
 ranked,_=rank(c,uid,c.execute('SELECT * FROM lab_packs WHERE owner IS NULL OR owner=?',(uid,)).fetchall(),node=node)
 return [r['pack'] for r in ranked]

def curriculum(c,uid):
 queue=review_queue(c,uid);ready=[x for x in queue if x['ready']];grammar=next((x for x in ready if x['kind']=='grammar'),None)
 if not grammar:
  from adaptive_service import grammar_choice
  chosen=grammar_choice(c,uid)
  if chosen:grammar={'node':chosen[0],'target':chosen[0],'kind':'grammar','title':c.execute('SELECT title FROM subskills WHERE id=?',(chosen[0],)).fetchone()[0],'reason':chosen[1],'evidence_ids':[],'purpose':'diagnostic'}
 # Respect prerequisites with evidence, instead of propagating a hypothetical weakness.
 if grammar:
  prior=c.execute('SELECT prereq FROM subskills WHERE id=?',(grammar['node'],)).fetchone()[0]
  if prior and not events.state(c,uid,prior)['independent']:
   grammar={'node':prior,'target':prior,'kind':'grammar','title':c.execute('SELECT title FROM subskills WHERE id=?',(prior,)).fetchone()[0],'reason':'先补目标知识点的先修环节；尚缺该环节的独立通过证据。','evidence_ids':[],'purpose':'diagnostic'}
 packs=material_candidates(c,uid,grammar['node'] if grammar else None)
 if not packs:raise ValueError('暂无通过结构检查的可推荐材料，请先审核语料')
 pack=packs[0];mid='material:'+pack['id'];linked_words={r[0] for r in c.execute("SELECT n.ref FROM kg_edges e JOIN kg_nodes n ON n.id=e.source WHERE e.target=? AND e.relation IN ('occurs_in','introduced_by')",(mid,))}
 vocab=next((x for x in ready if x['kind']=='vocab'),None)
 if not vocab:
  rows=[dict(r) for r in c.execute("SELECT * FROM lexicon WHERE status='published' AND (owner IS NULL OR owner=?)",(uid,))];rows.sort(key=lambda r:(r['id'] not in linked_words,c.execute('SELECT 1 FROM vocab_enroll WHERE user_id=? AND entry=?',(uid,r['id'])).fetchone() is not None,json.loads(r['content'])['theme']!=pack['theme']))
  if rows:vocab={'target':rows[0]['id'],'node':lex.node_id(rows[0]['id']),'title':rows[0]['lemma'],'reason':'先理解本主题中有关联的词汇义项，再尝试在表达中使用。' if rows[0]['id'] in linked_words else '补充与你的目标相关的词汇；本篇未找到直接词形关联。','evidence_ids':[],'purpose':'diagnostic'}
 if not grammar or not vocab:raise ValueError('词条或语法题不足，无法建立完整阶段')
 word=lex.entry_for(c,uid,vocab['target']);pattern=c.execute("SELECT n.id,n.title,e.target FROM kg_edges e JOIN kg_nodes n ON n.id=e.source WHERE e.relation='uses_grammar' AND n.ref=? LIMIT 1",(vocab['target'],)).fetchone()
 path=[{'kind':'sense','id':vocab['node'],'title':word['lemma']}]
 if pattern:path.extend([{'kind':'pattern','id':pattern['id'],'title':pattern['title']},{'kind':'grammar','id':pattern['target'],'title':c.execute('SELECT title FROM subskills WHERE id=?',(pattern['target'],)).fetchone()[0]}])
 if vocab['target'] in linked_words and (not pattern or c.execute("SELECT 1 FROM kg_edges WHERE source=? AND target=? AND relation='practised_in'",(pattern['target'],mid)).fetchone()):path.append({'kind':'material','id':mid,'title':pack['title']})
 tasks=[]
 # Listening first avoids making a first-listen claim after reading the same text.
 order=('vocabulary','grammar','listening','reading','speaking','writing');profile=c.execute('SELECT minutes FROM coach_profiles WHERE user_id=?',(uid,)).fetchone();budget=profile[0] if profile else 15;session=1;used=0
 titles={'vocabulary':'理解与回忆：'+word['lemma'],'grammar':'验证：'+grammar['title'],'listening':'先听：'+pack['title'],'reading':'再读：'+pack['title'],'speaking':'复述并换一个自己的场景','writing':'写出自己的版本'}
 for i,s in enumerate(order):
  requested={'vocabulary':3,'grammar':3,'listening':5,'reading':5,'speaking':6,'writing':10}[s]
  minutes=min(requested,budget)
  if used+minutes>budget:session+=1;used=0
  used+=minutes
  target=vocab if s=='vocabulary' else grammar if s=='grammar' else None
  chosen_pack=pack
  if s in ('listening','reading','speaking','writing'):
   from practice_service import rank,family
   ranked,_=rank(c,uid,c.execute('SELECT * FROM lab_packs WHERE owner IS NULL OR owner=?',(uid,)).fetchall(),skill=s)
   chosen_pack=next((r['pack'] for r in ranked if s!='reading' or family(r['pack'])!=family(pack)),ranked[0]['pack'] if ranked else pack)
  reason=target['reason'] if target else '按本项技能的建议难度练习；听读使用平行情境，避免靠记住答案通过。表达作品用于后续修改，不自动算掌握。'
  instruction={'vocabulary':'先独立回答词义或回忆表达，再把它用于一句自己的英语。','grammar':'先独立做题，需要时再使用提示；后续再用不同题目验证。','listening':'先不看原文听短文，完成理解或听写，再核对原文。','reading':'阅读新情境并用原文证据回答问题，标出一句想学会使用的表达。','speaking':'参考主题 '+pack['title']+'，用自己的经历复述或回答追问，尝试使用 '+word['lemma']+'；录音分析并保存作品。','writing':'围绕 '+pack['title']+' 写一个自己的版本，尝试使用 '+word['lemma']+'，根据反馈修订。'}[s]
  instruction=instruction.replace(pack['title'],chosen_pack['title'])
  tasks.append({'skill':s,'title':titles[s].replace(pack['title'],chosen_pack['title']),'instruction':instruction+' 本单元先完成一个小步骤，可保存草稿后分次继续。 推荐原因：'+reason,'node':grammar['node'] if s=='grammar' else '', 'entry':vocab['target'] if s=='vocabulary' else '', 'pack':chosen_pack['id'] if s not in ('vocabulary','grammar') else '', 'minutes':minutes,'position':i+1,'session':session,'rationale':reason,'evidence_ids':target['evidence_ids'] if target else [],'verification':target['purpose'] if target else 'practice','path':path if chosen_pack['id']==pack['id'] else [x for x in path if x['kind']!='material']})
 return {'difficulty':difficulty(c,uid),'tasks':tasks,'theme':pack['theme'],'material':{'id':pack['id'],'title':pack['title'],'level':pack['level']},'sessions':session,'daily_minutes':budget,'policy':POLICY,'note':'六维覆盖按可用时间分成多个学习单元；同篇重复练习不作为新语境迁移。图谱中的词形关联仍需核对义项。'}

def stage(c,uid,data):
 from lab_service import identifier
 rid=identifier(data.get('request_id'))
 old=c.execute('SELECT chapter FROM growth_stage_requests WHERE user_id=? AND request_id=?',(uid,rid)).fetchone()
 if old:return {'ok':True,'chapter':old[0],'cached':True},200
 if not c.execute('SELECT 1 FROM coach_profiles WHERE user_id=?',(uid,)).fetchone():raise ValueError('请先建立学习起点')
 plan=curriculum(c,uid);c.execute('BEGIN IMMEDIATE')
 old=c.execute('SELECT chapter FROM growth_stage_requests WHERE user_id=? AND request_id=?',(uid,rid)).fetchone()
 if old:c.rollback();return {'ok':True,'chapter':old[0],'cached':True},200
 active=c.execute("SELECT 1 FROM coach_missions WHERE user_id=? AND status='active'",(uid,)).fetchone()
 if active and data.get('replace') is not True:c.rollback();return {'error':'已有进行中的阶段；如需调整，请明确选择替换计划'},409
 chapter=c.execute('SELECT COALESCE(MAX(chapter),0)+1 FROM coach_missions WHERE user_id=?',(uid,)).fetchone()[0]
 c.execute("UPDATE coach_missions SET status='archived' WHERE user_id=? AND status='active'",(uid,))
 for m in plan['tasks']:
  mid=secrets.token_urlsafe(16);c.execute('INSERT INTO coach_missions(id,user_id,chapter,skill,title,instruction,node,entry,pack,minutes,created) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(mid,uid,chapter,m['skill'],m['title'],m['instruction'],m['node'],m['entry'],m['pack'],m['minutes'],time.time()))
  c.execute('INSERT INTO growth_mission_meta VALUES(?,?,?,?,?,?)',(mid,m['position'],m['session'],m['rationale'],json.dumps({'nodes':m['path'],'evidence_ids':m['evidence_ids']},ensure_ascii=False),m['verification']))
 c.execute('INSERT INTO growth_stage_requests VALUES(?,?,?,?)',(uid,rid,chapter,time.time()));c.commit();return {'ok':True,'chapter':chapter,'plan':plan},200

def weekly(c,uid,now=None):
 now=time.time() if now is None else now;today=datetime.datetime.fromtimestamp(now,TZ).date();start=datetime.datetime.combine(today-datetime.timedelta(days=6),datetime.time.min,TZ).timestamp();end=datetime.datetime.combine(today+datetime.timedelta(days=1),datetime.time.min,TZ).timestamp();grouped=history(c,uid);allrows=sorted([r for items in grouped.values() for r in items],key=lambda r:(r['created'],r['id']))
 def period(a,b):
  rows=[r for r in allrows if a<=r['created']<b];checks=[r for r in rows if r['correct'] is not None and r['evaluator']=='rule' and r['assisted']==0];distinct={(r['node'],r['item']) for r in checks};works=c.execute('SELECT skill,COUNT(*) n FROM lab_work WHERE user_id=? AND created>=? AND created<? GROUP BY skill',(uid,a,b)).fetchall()
  return {'start':datetime.datetime.fromtimestamp(a,TZ).date().isoformat(),'end':datetime.datetime.fromtimestamp(b-1,TZ).date().isoformat(),'independent_checks':len(checks),'distinct_items':len(distinct),'correct':sum(r['correct'] for r in checks),'hinted_checks':sum(r['assisted']==1 for r in rows if r['correct'] is not None and r['evaluator']=='rule'),'work':{r['skill']:r['n'] for r in works},'active_days':len({datetime.datetime.fromtimestamp(r['created'],TZ).date() for r in rows}),'evidence_ids':[r['id'] for r in checks[-8:]]}
 current=period(start,end);previous=period(start-7*DAY,start);changes=[];achievements=[]
 for node,rows in grouped.items():
  past=[r for r in rows if r['created']<start];before=events.summarize(node,past);after=events.summarize(node,[r for r in rows if r['created']<end]);title=c.execute('SELECT title FROM kg_nodes WHERE id=?',(node,)).fetchone();title=title[0] if title else node
  if before['state']!=after['state'] and any(start<=r['created']<end for r in rows):changes.append({'node':node,'title':title,'before':before['state'],'after':after['state'],'evidence_ids':[r['id'] for r in rows if start<=r['created']<end][-4:]})
  good=successes(rows)
  for badge,label,delay,different in [('independent','首次独立通过',0,False),('delayed','隔天仍能回忆',DAY,False),('week','隔周仍能回忆',7*DAY,False),('transfer','新语境结构化验证',DAY,True)]:
   chosen=None;prior=None;anchors=[]
   for r in good:
    p=next((p for p in anchors if p['created']<=r['created']-delay and (not node.startswith('sense:') or p['kind']==r['kind']) and (not different or p['context']!=r['context'])),None) if delay else None
    if not delay or p:chosen=r;prior=p;break
    same=[p for p in anchors if not node.startswith('sense:') or p['kind']==r['kind']]
    if not same or len(same)==1 and same[0]['context']!=r['context']:anchors.append(r)
   if chosen:
    ids=[chosen['id']] if prior is None else [prior['id'],chosen['id']]
    achievements.append({'badge':badge,'node':node,'title':title+' · '+label,'evidence_ids':ids,'created':chosen['created']})
 nextsteps=review_queue(c,uid,now)[:4]
 return {'current':current,'previous':previous,'changes':changes[:12],'achievements':sorted(achievements,key=lambda a:a['created'],reverse=True)[:24],'next':nextsteps,'note':'按北京时间统计最近7个自然日与此前7日。次数和正确数会受题目与提示影响，不能直接解释为能力提升；成就只代表对应的可核对结构化证据。'}

def overview(c,uid):
 return {'diagnostics':diagnostics(c,uid),'queue':review_queue(c,uid)[:30],'weekly':weekly(c,uid),'settings':settings(c,uid),'policy':POLICY}

def get(c,uid,admin,path,q):
 found=quality.get(c,uid,admin,path,q)
 if found is not None:return found
 if path=='/api/growth':return overview(c,uid),200
 if path=='/api/growth/weekly':return weekly(c,uid),200
 if path=='/api/growth/plan':return curriculum(c,uid),200
 return None

def post(c,uid,admin,path,data):
 found=quality.post(c,uid,admin,path,data)
 if found is not None:return found
 if path=='/api/growth/stage':return stage(c,uid,data)
 if path=='/api/growth/settings':
  if data.get('theme') not in ('auto','campus','travel','life','work','culture','science') or type(data.get('hotspots'))!=bool:raise ValueError('主题设置不正确')
  c.execute('INSERT OR REPLACE INTO growth_settings VALUES(?,?,?)',(uid,data['theme'],int(data['hotspots'])));c.commit();return {'ok':True},200
 if path=='/api/growth/correct':
  from lab_service import text
  kind=data.get('kind');ref=data.get('id');correction=text(data.get('correction'),maximum=600)
  if type(ref)!=int or kind not in ('memory','observation'):raise ValueError('纠正对象不正确')
  table='coach_memories' if kind=='memory' else 'ai_observations';row=c.execute('SELECT * FROM '+table+' WHERE id=? AND user_id=?',(ref,uid)).fetchone()
  if not row:raise ValueError('记录不存在或无权访问')
  original=row['text'] if kind=='memory' else row['reason']
  c.execute('INSERT INTO teaching_corrections(user_id,kind,ref,original,correction,created) VALUES(?,?,?,?,?,?)',(uid,kind,ref,original,correction,time.time()))
  if kind=='memory':c.execute('UPDATE coach_memories SET text=?,evidence=? WHERE id=? AND user_id=?',(correction,correction,ref,uid))
  else:c.execute("UPDATE ai_observations SET status='corrected' WHERE id=? AND user_id=?",(ref,uid))
  c.commit();return {'ok':True},200
 return None
