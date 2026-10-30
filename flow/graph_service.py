"""Typed, owner-filtered graph API and local evidence views."""
import json
from collections import defaultdict
import lexicon_service as lex
import event_service as events
RELATIONS={'has_sense':'包含义项','has_pattern':'常用搭配','uses_grammar':'涉及语法','introduced_by':'教学引入','occurs_in':'原文词形匹配','practised_in':'语境练习','trains':'训练方式','prerequisite':'教学先修'}

def visible(c,uid):
 rows=[]
 for r in c.execute('SELECT * FROM kg_nodes WHERE owner IS NULL OR owner=?',(uid,)):
  n=dict(r)
  if n['kind'] in ('word','sense','pattern'):
   entry=c.execute("SELECT 1 FROM lexicon WHERE id=? AND status='published' AND (owner IS NULL OR owner=?)",(n['ref'],uid)).fetchone()
   if not entry:continue
  elif n['kind']=='material':
   if not c.execute('SELECT 1 FROM lab_packs WHERE id=? AND (owner IS NULL OR owner=?)',(n['ref'],uid)).fetchone():continue
  rows.append(n)
 return rows

def network(c,uid,include_focus=True):
 nodes=visible(c,uid);valid={n['id'] for n in nodes}
 edges=[dict(r) for r in c.execute('SELECT source,target,relation,origin FROM kg_edges') if r['source'] in valid and r['target'] in valid]
 grouped=defaultdict(list)
 for r in c.execute('SELECT * FROM learning_events WHERE user_id=? ORDER BY created,id',(uid,)):grouped[r['node']].append(dict(r))
 states={}
 for n in nodes:
  key=lex.node_id(n['ref']) if n['kind'] in ('word','sense') else n['id']
  n['state_node']=key;n['evidence_scope']='义项引用' if n['kind']=='word' else '节点自身'
  if n['kind']=='material':continue
  if key not in states:states[key]=events.summarize(key,grouped[key])
  state=states[key];n['state']=state['state']
  n['status']='repair' if state['state'] in ('需要巩固','提示后完成') else 'transfer' if state['transfer'] else 'delayed' if state['delayed'] else 'independent' if state['independent'] else 'observed' if state['events'] else 'unknown'
  n['counts']={k:state[k] for k in ('independent','delayed','transfer','events')}
 graph={'nodes':nodes,'edges':edges,'relations':RELATIONS,'policy':'flow-evidence-2.1','summary':{'knowledge':sum(n['kind'] in ('sense','grammar') for n in nodes),'connected':sum(bool(s['events']) for key,s in states.items() if key.startswith('sense:') or any(n['id']==key and n['kind']=='grammar' for n in nodes)),'independent':sum(bool(s['independent']) for s in states.values()),'delayed':sum(bool(s['delayed']) for s in states.values()),'transfer':sum(bool(s['transfer']) for s in states.values()),'skills':sum(n['kind']=='skill' for n in nodes)},'note':'图谱关系来自教学编排、原文匹配或已发布词条。词形匹配不证明义项相同，仍需结合语境核对。AI提出的个人薄弱点单独保存为待验证观察，不直接成为公共事实。'}
 if include_focus:graph['focus']=focus(c,uid,graph)
 return graph

def focus(c,uid,graph=None):
 """Stage anchors and actual adjacent edges, without inferring semantic links."""
 from growth_service import review_queue
 graph=graph or network(c,uid,False);byid={n['id']:n for n in graph['nodes']}
 basic=__import__('foundation_service').is_basic(c,uid)
 queue=[r for r in review_queue(c,uid) if r['node'] in byid and r['purpose']!='diagnostic'][:3]
 targets=[];anchors=[]
 for r in queue:
  anchors.append(r['node']);targets.append({k:r[k] for k in ('node','title','kind','target','reason','ready','ready_at','purpose','evidence_ids')})
 missions=[]
 for row in c.execute("SELECT m.*,g.position,g.rationale FROM coach_missions m LEFT JOIN growth_mission_meta g ON g.mission=m.id WHERE m.user_id=? AND m.status='active' ORDER BY m.chapter DESC,COALESCE(g.position,99),m.created,m.id LIMIT 6",(uid,)):
  m=dict(row);node=lex.node_id(m['entry']) if m['entry'] else m['node'] if m['node'] else 'material:'+m['pack'] if m['pack'] else 'skill:'+m['skill']
  if node not in byid:continue
  anchors.append(node)
  missions.append({'id':m['id'],'node':node,'skill':m['skill'],'title':m['title'],'reason':m['rationale'] or m['instruction'],'minutes':m['minutes']})
 if not anchors:
  recent=c.execute("SELECT lesson FROM foundation_progress WHERE user_id=? AND step>=3 ORDER BY updated DESC LIMIT 1",(uid,)).fetchone()
  if recent and 'lesson:'+recent[0] in byid:anchors.append('lesson:'+recent[0])
 if not anchors:
  # A new learner sees a labelled exploration, never a fabricated diagnosis.
  initial=next((n for n in graph['nodes'] if n['kind']=='sense'),None)
  if initial:anchors.append(initial['id'])
 anchors=list(dict.fromkeys(anchors));seen=set(anchors);front=set(anchors)
 for hop in range(3):
  candidates=[]
  for e in graph['edges']:
   if e['source'] in front:candidates.append(e['target'])
   if e['target'] in front:candidates.append(e['source'])
  from content_v30 import SUPERSEDED
  candidates=[x for x in set(candidates)-seen if not (byid[x]['kind']=='material' and byid[x]['ref'] in SUPERSEDED)]
  candidates=sorted(candidates,key=lambda x:({'pattern':0,'sense':1,'word':2,'grammar':3,'material':4,'skill':5}.get(byid[x]['kind'],9),x))
  if hop==0:
   # Reserve application contexts before a high-degree grammar hub consumes the budget.
   applications=[]
   for anchor in anchors:
    if byid[anchor]['kind']!='grammar':continue
    material=next((e['target'] for e in graph['edges'] if e['source']==anchor and e['relation']=='practised_in' and e['target'] in candidates),None)
    if material and material not in applications:applications.append(material)
   candidates=applications+[x for x in candidates if x not in applications]
  front=set(candidates[:min(8 if hop<2 else 30,max(0,30-len(seen)))]);seen.update(front)
 nodes=[byid[x] for x in anchors]+[n for n in graph['nodes'] if n['id'] in seen and n['id'] not in anchors]
 decision=None
 if anchors:
  anchor=byid[anchors[0]];state=events.state(c,uid,anchor.get('state_node',anchor['id']));proof=[]
  for event in state['evidence'][:2]:
   details=event['details'];quote=details.get('answer') or details.get('evidence') or details.get('feedback',{}).get('task_check',{}).get('evidence') or ''
   proof.append({'id':event['id'],'quote':str(quote)[:180],'kind':event['kind'],'evaluator':event['evaluator'],'created':event['created'],'supported':event['assisted']})
  decision={'node':anchor['id'],'title':anchor['title'],'state':state['state'],'reason':targets[0]['reason'] if targets else missions[0]['reason'] if missions else '当前记录还不足以判断掌握，先从一个小练习了解。','evidence':proof,'next':'按当前阶段完成一次新语境练习；有到期验证时再独立回忆。','criterion':'表达先比较原稿、修订和隔天的新表达；AI切题意见不等于独立掌握。' if anchor['id'] in ('skill:writing','skill:speaking') else '至少24小时后，不看提示在不同题目或新语境中再次通过；不因浏览、聊天或相邻节点而自动掌握。'}
 return {'decision':decision,'mode':'personal' if targets or missions or any(byid[a]['kind']=='lesson' and byid[a].get('counts',{}).get('events') for a in anchors) else 'explore','anchors':anchors,'nodes':nodes,'edges':[e for e in graph['edges'] if e['source'] in seen and e['target'] in seen],'targets':targets,'missions':missions,'summary':graph['summary'],'note':'当前阶段与复习证据决定焦点；连线仅展示已保存的关系，节点位置不代表先修顺序。'}

def detail(c,uid,node):
 graph=network(c,uid,False);byid={n['id']:n for n in graph['nodes']}
 if node not in byid:raise ValueError('节点不存在或无权访问')
 n=byid[node];front={node};seen={node}
 for _ in range(3):
  nxt=set()
  for edge in graph['edges']:
   if edge['source'] in front:nxt.add(edge['target'])
   if edge['target'] in front:nxt.add(edge['source'])
  front=(nxt-seen);seen|=front
  if len(seen)>150:break
 selected=[x for x in graph['nodes'] if x['id'] in seen];out={'node':n,'network':{'nodes':selected,'edges':[e for e in graph['edges'] if e['source'] in seen and e['target'] in seen]},'relations':RELATIONS,'note':graph['note']}
 state_node=lex.node_id(n['ref']) if n['kind'] in ('word','sense') else node
 out['state']=events.state(c,uid,state_node)
 if n['kind'] in ('word','sense','pattern'):out['entry']=lex.detail(c,uid,n['ref'])
 if n['kind']=='lesson':out['foundation']=__import__('foundation_service').view(c,uid,n['ref'])
 if n['kind']=='grammar':out['lesson']=dict(c.execute('SELECT lesson,example,prereq FROM subskills WHERE id=?',(node,)).fetchone())
 from growth_service import review_queue
 from content_v30 import SUPERSEDED
 out['relationship_meanings']=[__import__('pedagogy_service').relation(e) for e in out['network']['edges'] if (e['source']==node or e['target']==node) and not any(x.startswith('material:') and x.removeprefix('material:') in SUPERSEDED and x!=node for x in (e['source'],e['target']))]
 out['next_check']=next((r for r in review_queue(c,uid) if r['node']==state_node),None)
 materials={x['ref'] for x in selected if x['kind']=='material'}
 from practice_service import rank
 ranked,plan=rank(c,uid,c.execute('SELECT * FROM lab_packs WHERE owner IS NULL OR owner=?',(uid,)).fetchall(),node=state_node,skill='reading')
 out['materials']=[{'id':r['pack']['id'],'title':r['pack']['title']} for r in ranked if r['pack']['id'] in materials and r['pack']['level']==plan['target']][:4]
 out['observations']=[dict(r) for r in c.execute("SELECT id,job,node,evidence,reason,status,created FROM ai_observations WHERE user_id=? AND node=? ORDER BY id DESC LIMIT 5",(uid,node))]
 return out
