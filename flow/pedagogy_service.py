"""One explainable next action and explicit semantic meaning for graph edges."""
RELATION_GUIDE={
 'has_sense':('词义定位','同一个词可能有不同含义，练习针对当前义项。','打开义项，核对语境中的意思。','不表示掌握'),
 'has_pattern':('表达扩展','这个义项有可学习的搭配，认识词义不等于会用搭配。','先看结构，再独立造句。','不共享通过状态'),
 'uses_grammar':('结构解释','这个搭配涉及此语法结构，可用于解释表达错误。','对照原句，检查结构选择。','不自动判定薄弱'),
 'introduced_by':('教学来源','这个词条由该教学材料引入。','回到来源理解用法。','不是先修关系'),
 'occurs_in':('语境检索','材料出现了对应词形；仍需核对是不是当前义项。','打开原文寻找上下文。','不证明义项一致'),
 'practised_in':('练习机会','这份材料被编排为该知识点的练习语境。','进入练习并保存自己的回答。','完成材料不等于通过本知识点'),
 'trains':('训练目标','这份材料支持此类练习。','选择具体技能开始练习。','不是能力证据'),
 'prerequisite':('教学先修','教学编排建议先了解这一环节，再练后续结构。','先做小检查，已有证据时可以直接继续。','不是必须按顺序学的绝对规则')}

def relation(edge):
 title,why,action,limit=RELATION_GUIDE.get(edge['relation'],('已有联系','系统保存了这条教学关系。','查看两个节点的内容。','不代表掌握'))
 return dict(edge,source_label={'published':'已发布词条','curriculum':'教学编排','literal':'原文匹配'}.get(edge.get('origin'),'已保存的教学关系'),category=title,meaning=why,learning_action=action,limit=limit)

def next_action(c,uid,missions,queue):
 from foundation_service import is_basic,recommended
 basic=is_basic(c,uid)
 # Remediation is a short detour, preserving the learner's saved chapter.
 repair=next((r for r in queue if r['ready'] and r['purpose'] in ('repair','unassisted')),None)
 if repair:
  failures=c.execute("SELECT correct FROM learning_events WHERE user_id=? AND node=? AND evaluator='rule' AND correct IS NOT NULL ORDER BY created DESC,id DESC LIMIT 2",(uid,repair['node'])).fetchall()
  if (basic or len(failures)==2 and all(r[0]==0 for r in failures)) and repair['kind']=='grammar':
   key='grammar:'+repair['target'];progress=c.execute('SELECT step FROM foundation_progress WHERE user_id=? AND lesson=?',(uid,key)).fetchone()
   if not progress or progress[0]<3:return {'type':'foundation','lesson':key,'title':'先学一句，再回来练','reason':'先通过对照例句和有支持的练习弄懂结构，不用继续猜题。','minutes':3,'evidence_ids':repair['evidence_ids'],'label':'学习不等于测评'}
 if basic:
  next_lesson=recommended(c,uid)
  if next_lesson and not (next_lesson.get('optional') and any(m['status']=='active' for m in missions)):return {'type':'foundation','lesson':next_lesson['lesson'],'review':next_lesson.get('review',False),'title':next_lesson['title'],'reason':'先回忆练过的表达，需要时再看例句；复习记录不会自动变成独立掌握。' if next_lesson.get('review') else '先理解一句，再做替换和短句表达；每次只完成一个小步骤。','minutes':3,'evidence_ids':[],'label':'基础起步 · 可分次继续'}
 if repair:return {'type':'repair','title':'先补这一小步：'+repair['title'],'reason':repair['reason'],'kind':repair['kind'],'target':repair['target'],'node':repair['node'],'evidence_ids':repair['evidence_ids'],'minutes':3,'label':'补练后回到原计划'}
 from practice_service import rank
 import json
 rows=c.execute("SELECT * FROM learning_events WHERE user_id=? AND node IN ('skill:listening','skill:reading') AND evaluator='rule' AND correct IS NOT NULL ORDER BY created DESC,id DESC",(uid,)).fetchall();seen=set()
 for row in rows:
  if row['node'] in seen:continue
  seen.add(row['node'])
  if row['correct']!=0:continue
  skill=row['node'].split(':')[1];packs=c.execute('SELECT * FROM lab_packs WHERE owner IS NULL OR owner=?',(uid,)).fetchall();ranked,_=rank(c,uid,packs,skill=skill,mode='repair')
  new=next((r for r in ranked if not r['seen_family']),None)
  if new:return {'type':'material_repair','title':'换一篇短材料再练'+('听力' if skill=='listening' else '阅读'),'reason':'最近理解检查未通过，先在较低或相同档的新情境复练；不直接把错误归因于某个语法点。','pack':new['pack']['id'],'skill':skill,'evidence_ids':[row['id']],'minutes':new['grading']['minutes'],'label':'保存后重新检查下一步'}
 return None
