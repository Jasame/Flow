"""Read-only, evidence-grounded learning continuity. No AI calls or artificial mastery."""
import datetime,json,time
import event_service as events
TZ=datetime.timezone(datetime.timedelta(hours=8))
MODES={'meaning':'理解','spelling':'拼写','application':'表达'}

def overview(c,uid,missions=None,now=None):
 now=time.time() if now is None else now
 day=datetime.datetime.fromtimestamp(now,TZ).date()
 start=datetime.datetime.combine(day,datetime.time(),TZ).timestamp()
 grouped={}
 for row in c.execute('SELECT * FROM learning_events WHERE user_id=? AND created<=? ORDER BY created,id',(uid,now)):
  r=dict(row);grouped.setdefault(r['node'],[]).append(r)
 latest=sorted((r for rows in grouped.values() for r in rows),key=lambda r:(r['created'],r['id']),reverse=True)[:12]
 titles={r['id']:r['title'] for r in c.execute('SELECT id,title FROM kg_nodes WHERE owner IS NULL OR owner=?',(uid,))}
 changes=[]
 for r in latest:
  rows=grouped[r['node']];pos=next(i for i,x in enumerate(rows) if x['id']==r['id'])
  before=events.summarize(r['node'],rows[:pos]);after=events.summarize(r['node'],rows[:pos+1])
  changes.append({'id':r['id'],'node':r['node'],'title':titles.get(r['node'],r['node']),'kind':r['kind'],'evaluator':r['evaluator'],'correct':r['correct'],'assisted':r['assisted'],'before':before['state'],'after':after['state'],'changed':before['state']!=after['state'],'created':r['created'],'item':r['item'],'context':r['context']})
 words=[]
 for row in c.execute("SELECT l.id,l.lemma FROM lexicon l JOIN vocab_enroll e ON e.entry=l.id AND e.user_id=? WHERE l.status='published' AND (l.owner IS NULL OR l.owner=?) ORDER BY e.due,l.id LIMIT 12",(uid,uid)):
  node='sense:'+row['id'];rows=grouped.get(node,[]);modes=[]
  for mode,label in MODES.items():
   subset=[r for r in rows if r['kind']==mode];checks=[r for r in subset if r['evaluator']=='rule' and r['correct'] is not None];last=checks[-1] if checks else None
   status='待练习'
   if subset:status='已收集表达，待验证' if mode=='application' else '待独立检查'
   if last:status='需要巩固' if last['correct']==0 else '提示后完成' if last['assisted']==1 else '独立通过' if last['assisted']==0 else '提示情况未知'
   modes.append({'mode':mode,'label':label,'status':status,'checks':len(checks),'independent_passes':sum(r['correct']==1 and r['assisted']==0 for r in checks),'evidence_ids':[r['id'] for r in subset[-3:]]})
  words.append({'entry':row['id'],'node':node,'title':row['lemma'],'modes':modes})
 if missions is None:
  from coach_service import mission_list
  missions=mission_list(c,uid)
 active=[m for m in missions if m['status']=='active'];unit=None
 if active:
  ordered=[]
  for m in active:
   meta=c.execute('SELECT position,session,rationale FROM growth_mission_meta WHERE mission=?',(m['id'],)).fetchone()
   ordered.append((meta['session'] if meta else 1,meta['position'] if meta else 99,m,meta))
  ordered.sort(key=lambda x:(x[0],x[1],x[2]['created'],x[2]['id']));session=ordered[0][0];selected=[x for x in ordered if x[0]==session]
  unit={'chapter':selected[0][2]['chapter'],'session':session,'remaining_minutes':sum(x[2]['minutes'] for x in selected),'tasks':[{'id':x[2]['id'],'skill':x[2]['skill'],'title':x[2]['title'],'minutes':x[2]['minutes'],'reason':x[3]['rationale'] if x[3] else x[2]['instruction']} for x in selected]}
 today=[r for rows in grouped.values() for r in rows if start<=r['created']<=now]
 # A work can yield several graph events; never report these as several completed exercises.
 sources={r['source'] for r in today if not (r['kind']=='placement' and r['correct'] is None)};checks=[r for r in today if r['evaluator']=='rule' and r['correct'] is not None and r['assisted']==0]
 from growth_service import review_queue
 action=__import__('pedagogy_service').next_action(c,uid,missions,review_queue(c,uid,now))
 return {'next_action':action,'day':day.isoformat(),'unit':unit,'today':{'activities':len(sources),'independent_checks':len(checks),'correct':sum(r['correct']==1 for r in checks)},'changes':changes,'words':words,'note':'当前单元沿用已保存的阶段任务，完成后继续下一项；单元可跨天。表达样本和AI反馈不计为独立通过。'}

def context(c,uid):
 d=overview(c,uid)
 return {'next_action':d['next_action'],'day':d['day'],'resume':{'chapter':d['unit']['chapter'],'session':d['unit']['session'],'next_task':d['unit']['tasks'][0]['title']} if d['unit'] else None,'recent_changes':[{k:r[k] for k in ('id','node','before','after','evaluator','assisted')} for r in d['changes'][:3]],'today':d['today']}
