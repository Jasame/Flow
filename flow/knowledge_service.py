"""Evidence-based graph: teaching prerequisites, linked material and separate exposure."""
import json
from learning_service import evidence
from content_v07 import metadata

def graph(c,uid):
 nodes=evidence(c,uid);materials=[];exposure={}
 for r in c.execute('SELECT pack,skill,COUNT(*) count FROM lab_work WHERE user_id=? GROUP BY pack,skill',(uid,)):
  exposure.setdefault(r['pack'],{})[r['skill']]=r['count']
 for r in c.execute('SELECT content,origin FROM lab_packs WHERE owner IS NULL OR owner=? ORDER BY created DESC',(uid,)):
  p=json.loads(r['content']);m=metadata(p)
  if m['grammar']:materials.append({k:p[k] for k in ('id','title','level')}|{'grammar':m['grammar'],'daily_day':p.get('daily_day'),'origin':r['origin'],'knowledge':p.get('knowledge',[]),'practice':exposure.get(p['id'],{})})
 for n in nodes:
  related=[p for p in materials if n['id'] in p['grammar']];n['materials']=related[:12]
  n['material_count']=len(related);n['practice_count']=sum(sum(p['practice'].values()) for p in related)
 from state_service import grammar_target,POLICY
 chosen=grammar_target(c,uid,nodes)
 byid={n['id']:n for n in nodes}
 return {'nodes':nodes,'edges':[{'from':n['prereq'],'to':n['id']} for n in nodes if n['prereq'] in byid], 'recommended':chosen['node'] if chosen else nodes[0]['id'],'recommended_reason':chosen['reason'] if chosen else '','policy':POLICY,'legend':[{'state':k,'label':v} for k,v in __import__('state_service').LABELS.items()],'note':'连线代表教学前置关系；语料训练次数单独记录。语法状态由真实题目作答形成，AI 关联与解释仍需核对。'}
