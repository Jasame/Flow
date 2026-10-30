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
 target=next((n for n in sorted(nodes,key=lambda x:(x['state']!='需要巩固',x['distinct'],x['total'])) if n['available']),nodes[0])
 byid={n['id']:n for n in nodes};seen=set()
 while target.get('prereq') in byid and target['id'] not in seen:
  seen.add(target['id']);prior=byid[target['prereq']]
  if prior['distinct']>=3 and prior['state']=='初步稳定':break
  target=prior
 return {'nodes':nodes,'edges':[{'from':n['prereq'],'to':n['id']} for n in nodes if n['prereq'] in byid], 'recommended':target['id'],'note':'连线代表教学前置关系；语料训练次数单独记录。语法状态由真实题目作答形成，AI 关联与解释仍需核对。'}
