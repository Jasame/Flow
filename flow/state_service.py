"""One current-learning-state projection, rebuilt from raw learning_events.

Course pages, the knowledge graph, review, the coach context and next-step choice all
read this projection, so a node has one current state and one reason everywhere.
First-attempt accuracy stays a historical statistic and is never used as a current label.
States are rule summaries, not mastery probabilities.
"""
import json,time
import event_service as events
POLICY='flow-evidence-3.0'
# Keys stay compatible with event_service.summarize(); labels are what students read.
LABELS={'待建立':'还没开始','待验证':'练过，待独立检查','独立完成一次':'独立做对过一次','独立完成':'独立做对过不同的题','延迟记得':'隔天还能做对','迁移已有证据':'换个情境也能用','需要巩固':'最近一次没做对，先短补练','提示后完成':'借助提示完成，待独立检查'}
STABLE=('独立完成一次','独立完成','延迟记得','迁移已有证据')
PURPOSE={'start':'先开始一次学习','diagnostic':'做一个小检查，了解起点','repair':'短补练后换一道新题验证','unassisted':'隔天不看提示再做一次','delayed':'隔天独立回忆','transfer':'换个新题或新情境试试','maintain':'按复习时间保持'}
TERMS={'独立':'没有用提示、也不是近期刚做过的同一题','隔天还能做对':'和上次独立做对至少隔 24 小时','换个情境也能用':'在不同的题目或材料里也做对'}

def support_of(row):
 """Why a structured check counts as supported. Unknown history stays unknown."""
 if row is None or row['assisted'] is None:return 'unknown' if row is not None else None
 if row['assisted']==0:return 'none'
 try:d=json.loads(row['details']) if isinstance(row['details'],str) else row['details'] or {}
 except ValueError:d={}
 return d.get('support') or ('familiar' if d.get('familiar') else 'hint')

def project(node,rows):
 # Skipped starting-check questions are kept as records but never make a node look practised.
 rows=[r for r in rows if not events.skipped(r)]
 s=events.summarize(node,rows);checks=events.checks(rows);latest=checks[-1] if checks else None
 best='迁移已有证据' if s['transfer'] else '延迟记得' if s['delayed'] else '独立完成' if s['independent'] else None
 if not rows:purpose='start'
 elif not checks:purpose='diagnostic'
 elif not latest['correct']:purpose='repair'
 elif latest['assisted']!=0:purpose='unassisted'
 elif not s['delayed']:purpose='delayed'
 elif not s['transfer']:purpose='transfer'
 else:purpose='maintain'
 label=LABELS.get(s['state'],s['state'])
 if s['state'] in ('需要巩固','提示后完成') and best:label+='（此前已'+LABELS[best]+'，历史记录保留）'
 basis=[latest['id']] if latest else [r['id'] for r in rows[-1:]]
 s.update(policy=POLICY,label=label,history_best=best,purpose=purpose,purpose_label=PURPOSE[purpose],
  participation={'events':len(rows),'checks':len(checks),'exposures':s['exposures'],'guided':sum(r['evaluator']=='practice' for r in rows)},
  support_need=support_of(latest) if latest else None,
  latest={'id':latest['id'],'correct':latest['correct'],'assisted':latest['assisted'],'evaluator':latest['evaluator'],'created':latest['created']} if latest else None,
  basis=basis,updated=rows[-1]['created'] if rows else None,stable=s['state'] in STABLE)
 return s

def grouped(c,uid,prefix=None):
 out={}
 q='SELECT * FROM learning_events WHERE user_id=?'+(' AND node NOT LIKE ? AND node NOT LIKE ? AND node NOT LIKE ?' if prefix=='grammar' else '')+' ORDER BY created,id'
 args=(uid,'sense:%','skill:%','lesson:%') if prefix=='grammar' else (uid,)
 for r in c.execute(q,args):out.setdefault(r['node'],[]).append(dict(r))
 return out

def node_state(c,uid,node):
 return project(node,[dict(r) for r in c.execute('SELECT * FROM learning_events WHERE user_id=? AND node=? ORDER BY created,id',(uid,node))])

def grammar_states(c,uid):
 rows=grouped(c,uid,'grammar')
 return {r['id']:project(r['id'],rows.get(r['id'],[])) for r in c.execute('SELECT id FROM subskills ORDER BY rowid')}

def grammar_target(c,uid,nodes=None,queue=None):
 """The single rule for which grammar subskill to work on next, with its reason.

 1. A ready review item (repair, unassisted, delayed, transfer) from the shared queue.
 2. Otherwise the first subskill in teaching order without independent evidence.
 3. Otherwise the subskill with the least independent evidence.
 A teaching prerequisite is suggested first only for new learning and only when it has no
 record at all; it is never used to explain an observed error.
 """
 if nodes is None:
  from learning_service import evidence
  nodes=evidence(c,uid)
 byid={n['id']:n for n in nodes};available=[n for n in nodes if n['available']]
 if not available:return None
 if queue is None:
  from growth_service import review_queue
  queue=review_queue(c,uid)
 ready=next((x for x in queue if x['kind']=='grammar' and x['ready'] and x['purpose'] in ('repair','unassisted','delayed','transfer') and byid.get(x['node'],{}).get('available')),None)
 if ready:
  n=byid[ready['node']];return {'node':n['id'],'title':n['title'],'purpose':ready['purpose'],'reason':ready['reason'],'basis':ready['evidence_ids'],'prereq_redirect':False,'policy':POLICY}
 fresh=next((n for n in available if not n['independent']),None)
 if fresh:
  prior=byid.get(fresh['prereq'])
  if prior and prior['available'] and prior['state']=='待建立':
   return {'node':prior['id'],'title':prior['title'],'purpose':'diagnostic','reason':'按教学顺序，先看「'+prior['title']+'」这一环（还没有任何记录）；这是学习顺序建议，不是错误诊断。','basis':[],'prereq_redirect':True,'policy':POLICY}
  return {'node':fresh['id'],'title':fresh['title'],'purpose':'diagnostic' if fresh['state']=='待建立' else fresh['purpose'],'reason':'还没有独立做对的记录，先做一个小检查。' if fresh['state']=='待建立' else '已有练习，但还没有独立做对的记录（'+fresh['label']+'）。','basis':fresh.get('basis',[]),'prereq_redirect':False,'policy':POLICY}
 n=min(available,key=lambda n:(n['delayed']>0,n['transfer']>0,n['independent'],n['order']))
 return {'node':n['id'],'title':n['title'],'purpose':n['purpose'],'reason':'各细项都有独立记录；这一项证据最少，继续积累（'+n['label']+'）。','basis':n.get('basis',[]),'prereq_redirect':False,'policy':POLICY}
