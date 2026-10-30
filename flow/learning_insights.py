"""Observed learning evidence, never a certified language score."""
import json,time
from collections import Counter,defaultdict

def schema(c):
    c.execute('CREATE TABLE IF NOT EXISTS material_difficulty(user_id INTEGER REFERENCES users(id),pack TEXT REFERENCES lab_packs(id),rating TEXT,updated REAL,PRIMARY KEY(user_id,pack))')

def expression(c,uid,compact=False):
    out={}
    for skill in ('speaking','writing'):
        rows=c.execute('SELECT id,answer,details,parent,created,feedback_request FROM lab_work WHERE user_id=? AND skill=? ORDER BY id DESC LIMIT 60',(uid,skill)).fetchall()
        reviewed=[];issues=Counter();samples=[]
        for row in rows:
            detail=json.loads(row['details']);feedback=detail.get('feedback',{});check=feedback.get('task_check',{})
            disputed=c.execute('SELECT 1 FROM feedback_disputes d JOIN lab_jobs j ON j.id=d.job WHERE d.user_id=? AND j.request_id=?',(uid,row['feedback_request'])).fetchone()
            if check.get('status')=='ai-reviewed' and not disputed:reviewed.append(check)
            if disputed:feedback={}
            for issue in feedback.get('priorities',[]):issues[issue['issue']]+=1
            if len(samples)<2:samples.append({'work':row['id'],'quote':row['answer'][:120],'created':row['created'],'supported':detail.get('assisted'),'task_review':check.get('status','unverified')})
        out[skill]={'works':len(rows),'reviewed':len(reviewed),'on_task':sum(x.get('on_task') is True for x in reviewed),'revision_pairs':sum(r['parent'] is not None for r in rows),'recurring_issues':[{'issue':k,'works':v} for k,v in issues.most_common(2) if v>=2],'samples':samples if not compact else samples[:1],'next_review_at':rows[0]['created']+86400 if rows else None,'next':'先保存一份自己的表达，再核对一个主要问题。' if not rows else '换一个情境再表达，并在至少24小时后复练；保留原稿以比较同类问题。','note':'AI切题意见、作品和修订是观察线索，不证明独立掌握；文本不用于判定发音。'}
    if compact:
        return {skill:{'works':d['works'],'reviewed':d['reviewed'],'revision_pairs':d['revision_pairs'],'recurring_issues':[{'issue':i['issue'][:100],'works':i['works']} for i in d['recurring_issues'][:1]],'recent_quote':d['samples'][0]['quote'][:80] if d['samples'] else ''} for skill,d in out.items()}
    return out

def calibrations(c,uid):
    """Latest unaided objective attempt per learner/material/skill, last 90 days."""
    groups=defaultdict(list);seen=set()
    rows=c.execute("SELECT e.user_id,e.item,e.node,e.correct FROM learning_events e JOIN lab_packs p ON p.id=e.item WHERE (p.owner IS NULL OR p.owner=?) AND (p.owner IS NULL OR e.user_id=?) AND e.evaluator='rule' AND e.assisted=0 AND e.correct IS NOT NULL AND e.node IN ('skill:listening','skill:reading') AND e.created>? ORDER BY e.created DESC,e.id DESC LIMIT 20000",(uid,uid,time.time()-90*86400))
    for row in rows:
        key=(row['user_id'],row['item'],row['node'])
        if key in seen:continue
        seen.add(key);groups[row['item']].append((row['user_id'],row['correct']))
    out={}
    for pack,values in groups.items():
        learners=len({x[0] for x in values});ready=learners>=20
        out[pack]={'learners':learners if ready else None,'attempts':len(values) if ready else None,'pass_rate':round(sum(x[1] for x in values)/len(values),2) if ready else None,'status':'已有观察样本，仍需教学审核' if ready else '样本不足，沿用教学建议分级','calibrated':ready,'note':'只统计近90天每位学习者每种理解训练的最近独立检查；通过率受使用人群影响，不等于CEFR难度认证。'}
    return out

def material(c,uid,pack):
    out=calibrations(c,uid).get(pack,{'calibrated':False,'status':'样本不足，沿用教学建议分级','pass_rate':None})
    vote=c.execute('SELECT rating FROM material_difficulty WHERE user_id=? AND pack=?',(uid,pack)).fetchone()
    return {**out,'my_rating':vote[0] if vote else None}
