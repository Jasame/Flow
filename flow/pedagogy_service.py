"""One explainable next action and explicit semantic meaning for graph edges."""
import json
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
   if not progress or progress[0]<3:return {'type':'foundation','lesson':key,'title':'先学一句：'+repair['title'],'reason':('这一项连着两次没做对。' if len(failures)==2 and all(r[0]==0 for r in failures) else '')+'先看例句弄懂结构，再做一道有支持的练习，不用继续猜题。','minutes':3,'evidence_ids':repair['evidence_ids'],'label':'学习不等于测评'}
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


def latest_dispute(c,uid):
 """A misclick or misread report on the most recent failed grammar check turns repair into a fresh re-check."""
 row=c.execute("SELECT e.*,d.reason FROM attempt_disputes d JOIN learning_events e ON e.user_id=d.user_id AND e.source='grammar:'||d.attempt WHERE d.user_id=? AND d.reason IN ('misclick','misread') ORDER BY d.created DESC LIMIT 1",(uid,)).fetchone()
 if not row or row['correct']!=0:return None
 # Other answers from the same submission are saved milliseconds later; only a genuinely later check counts.
 later=c.execute("SELECT 1 FROM learning_events WHERE user_id=? AND node=? AND evaluator IN ('rule','legacy') AND correct IS NOT NULL AND created>?",(uid,row['node'],row['created']+2)).fetchone()
 return None if later else row

def next_step(c,uid,queue=None,return_to=None,missions=None,detours_only=False):
 """The single next step shown on home, after a quiz, after a task and in the coach.

 Order: a disputed miss is re-checked with a new item; a short repair detour (then return);
 a failed dictation gets a dictation drill (separate from listening comprehension); otherwise
 the shared grammar target. The result always says why, on what evidence, and where to go back to.
 """
 from growth_service import review_queue
 from state_service import grammar_target,POLICY
 queue=review_queue(c,uid) if queue is None else queue
 back={'kind':'plan','label':'回到今天的计划'} if not return_to else {'kind':'route','label':'回到刚才的位置','route':return_to} if isinstance(return_to,str) and len(return_to)<=200 else {'kind':'plan','label':'回到今天的计划'}
 disputed=latest_dispute(c,uid)
 if disputed:
  title=c.execute('SELECT title FROM subskills WHERE id=?',(disputed['node'],)).fetchone()
  return {'type':'recheck','node':disputed['node'],'title':'换一道新题再确认：'+(title[0] if title else disputed['node']),'reason':'你反馈上次是'+('点错了' if disputed['reason']=='misclick' else '题意理解不同')+'；原记录保留，先用一道新题确认，不急着补课。','basis':[disputed['id']],'minutes':2,'return_to':back,'policy':POLICY}
 if missions is None:
  try:
   from coach_service import mission_list
   missions=mission_list(c,uid)
  except Exception:missions=[]
 action=next_action(c,uid,missions,queue)
 if action and action['type'] in ('foundation','repair','material_repair'):
  action=dict(action);action.setdefault('basis',action.get('evidence_ids',[]));action['return_to']=back;action['policy']=POLICY
  # Only a repair detour promises a fresh verification item; a plain next lesson does not.
  detour=action['type'] in ('repair','material_repair') or bool(action.get('evidence_ids'))
  action['then']=('补完后换一道新题验证，再' if detour else '完成这一小步后，可以')+back['label']
  return action
 d=c.execute("SELECT * FROM learning_events WHERE user_id=? AND node='skill:dictation' AND evaluator='rule' ORDER BY created DESC,id DESC LIMIT 1",(uid,)).fetchone()
 if d and d['correct']==0:
  details=json.loads(d['details'])
  if d['created']>__import__('time').time()-3*86400:return {'type':'dictation_repair','title':'听写：只练漏掉和写错的词','reason':'上次听写有 '+str(details.get('missing',0))+' 处漏写、'+str(details.get('replaced',0))+' 处写错。听写只练逐词回忆与拼写，不代表听力理解没过。','basis':[d['id']],'pack':d['item'],'minutes':3,'return_to':back,'policy':POLICY}
 if detours_only:return None
 # With a saved stage in progress, its next task is the next step; nothing else competes with it.
 if any(m['status']=='active' for m in missions):return None
 # Before any learning record exists, the start flow (starting check or first lesson) leads instead.
 if not c.execute('SELECT 1 FROM learning_events WHERE user_id=? LIMIT 1',(uid,)).fetchone():return None
 t=grammar_target(c,uid,queue=queue)
 if not t:return None
 return {'type':'grammar','node':t['node'],'title':('复习：' if t['purpose'] in ('repair','unassisted','delayed','transfer') else '学习：')+t['title'],'purpose':t['purpose'],'reason':t['reason'],'basis':t['basis'],'minutes':4,'return_to':back,'policy':POLICY}
