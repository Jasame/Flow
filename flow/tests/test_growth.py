import unittest,tempfile,time,json,sys,copy,datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,growth_service as growth,event_service as events,adaptive_service as adaptive,coach_service as coach,quality_service as quality,lab_service as lab,lexicon_service as lex
from placement_content import ITEMS
class GrowthTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.dbpatch=patch.object(app,'DB',Path(self.tmp.name)/'growth.db');self.dbpatch.start();app.init();self.c=app.db();self.c.executemany('INSERT INTO users(username,password,admin) VALUES(?,?,?)',[('learner','hash',0),('other','hash',0),('teacher','hash',1)]);self.c.commit();self.entry=lex.key('suggest','advice');self.node=lex.node_id(self.entry)
 def tearDown(self):self.c.close();self.dbpatch.stop();self.tmp.cleanup()
 def profile(self,minutes=10):
  token=coach.begin(self.c,1)[0]['token'];coach.assess(self.c,1,{'token':token,'goal':'旅行交流','interests':'文化','minutes':minutes,'writing':'','answers':{p['id']:{'choice':None,'hinted':False} for p in ITEMS}})
 def record(self,source,correct=True,assisted=False,ago=0,context='entry',node=None,evaluator='rule'):
  events.record(self.c,1,node or self.node,source,'spelling',context,context,correct,assisted,evaluator,created=time.time()-ago);self.c.commit()
 def q(self):return next(x for x in growth.review_queue(self.c,1) if x['node']==self.node)
 def test_practice_difficulty_adapts_only_after_distinct_independent_samples(self):
  self.profile();self.assertEqual(growth.difficulty(self.c,1)['level'],'A2')
  for level,correct,expected in [('A2',True,'B1'),('B1',True,'B2'),('B2',False,'B1')]:
   packs=[r['id'] for r in self.c.execute('SELECT id,content FROM lab_packs') if json.loads(r['content'])['level']==level][:6]
   for pack in packs:
    for skill in ('listening','reading'):events.record(self.c,1,'skill:'+skill,level+skill+pack,'comprehension',pack,pack,correct,False,'rule')
   self.c.commit();self.assertEqual(growth.difficulty(self.c,1)['level'],expected)
  self.assertEqual(coach.snapshot(self.c,1)['profile']['placement']['band'],'A2')
 def test_recommended_graph_path_contains_only_existing_edges(self):
  self.profile();self.record('suggest-needs-review',False)
  plan=growth.curriculum(self.c,1);path=plan['tasks'][0]['path'];self.assertGreaterEqual(len(path),3)
  for a,b in zip(path,path[1:]):self.assertTrue(self.c.execute('SELECT 1 FROM kg_edges WHERE source=? AND target=?',(a['id'],b['id'])).fetchone())
 def test_reading_listening_difference_is_a_hypothesis_with_evidence(self):
  for i,pack in enumerate(('travel-a2','campus-a2')):
   events.record(self.c,1,'skill:listening','listen-'+pack,'comprehension',pack,pack,False,False,'rule',created=time.time()-10+i)
   events.record(self.c,1,'skill:reading','read-'+pack,'comprehension',pack,pack,True,False,'rule',created=time.time()-5+i)
  self.c.commit();hypotheses=growth.diagnostics(self.c,1)['hypotheses'];gap=next(x for x in hypotheses if x['kind']=='listening_gap');self.assertEqual(gap['status'],'待验证');self.assertEqual(len(gap['evidence_ids']),4)
 def test_repair_then_hint_then_delay_uses_actual_evidence(self):
  self.record('wrong',False);self.assertEqual(self.q()['purpose'],'repair')
  self.record('hint',True,True);self.assertEqual(self.q()['purpose'],'unassisted')
  self.record('pass');q=self.q();self.assertEqual(q['purpose'],'delayed');self.assertFalse(q['ready']);self.assertEqual(len(q['evidence_ids']),1)
 def test_early_verify_rejected_but_ordinary_practice_available(self):
  self.record('pass');adaptive.enroll(self.c,1,self.entry);self.c.commit()
  self.assertEqual(adaptive.start(self.c,1,{'kind':'vocab','entry':self.entry,'verify':True})[1],409)
  self.assertEqual(adaptive.start(self.c,1,{'kind':'vocab','entry':self.entry})[1],200)
 def test_rapid_repeats_cannot_starve_delay_and_new_context_is_required(self):
  self.record('anchor',ago=2*86400,context='old')
  self.record('recent',ago=5,context='old')
  self.record('today',context='old')
  state=events.state(self.c,1,self.node);self.assertGreater(state['delayed'],0);self.assertEqual(state['transfer'],0)
  self.record('new',context='new');self.assertGreater(events.state(self.c,1,self.node)['transfer'],0)
 def test_ai_and_self_do_not_create_evidence_achievements(self):
  self.record('opinion',evaluator='ai');self.record('rating',evaluator='self')
  self.assertEqual(growth.weekly(self.c,1)['achievements'],[]);self.assertEqual(growth.diagnostics(self.c,1)['dimensions'][0]['independent_passes'],0)
 def test_six_skill_theme_plan_budget_and_stage_idempotence(self):
  self.profile();plan=growth.curriculum(self.c,1);self.assertEqual({m['skill'] for m in plan['tasks']},set(growth.SKILLS));self.assertEqual(plan['theme'],'travel')
  self.assertGreaterEqual(len({m['pack'] for m in plan['tasks'] if m['pack']}),2);self.assertLess([m['skill'] for m in plan['tasks']].index('listening'),[m['skill'] for m in plan['tasks']].index('reading'))
  for s in {m['session'] for m in plan['tasks']}:self.assertLessEqual(sum(m['minutes'] for m in plan['tasks'] if m['session']==s),10)
  data={'request_id':'rules-stage-request-001'};self.assertEqual(growth.stage(self.c,1,data)[1],200);self.assertTrue(growth.stage(self.c,1,data)[0]['cached']);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM coach_missions').fetchone()[0],6)
  self.assertEqual(growth.stage(self.c,1,{'request_id':'rules-stage-request-002'})[1],409)
  growth.stage(self.c,1,{'request_id':'rules-stage-request-002','replace':True});self.assertEqual(self.c.execute("SELECT COUNT(*) FROM coach_missions WHERE status='archived'").fetchone()[0],6)
 def test_review_queue_and_reports_do_not_expose_other_users(self):
  self.record('private-answer');self.assertEqual(growth.review_queue(self.c,2),[]);self.assertEqual(growth.weekly(self.c,2)['current']['independent_checks'],0)
 def test_speaking_and_writing_remain_unknown_without_samples(self):
  self.profile();d=growth.diagnostics(self.c,1)
  for s in d['dimensions']:
   if s['skill'] in ('speaking','writing'):self.assertEqual(s['status'],'待了解')
 def test_reading_same_material_prevents_independent_listening_claim(self):
  p=lab.pack_for(self.c,1,'travel-a2');choices=[q['answer'] for q in p['questions']]
  for skill in ('reading','listening'):
   lab.post(self.c,1,'/api/lab/support',{'pack':p['id'],'skill':skill,'action':'start'})
   result,_=lab.post(self.c,1,'/api/lab/comprehension',{'pack':p['id'],'skill':skill,'choices':choices,'save_id':'linked-'+skill+'-001'})
  self.assertEqual(result['details']['assisted'],1);self.assertEqual(events.state(self.c,1,'skill:listening')['independent'],0)
 def test_weekly_boundaries_use_beijing_and_compare_prior_week(self):
  now=datetime.datetime(2026,10,19,0,30,tzinfo=growth.TZ).timestamp()
  events.record(self.c,1,self.node,'past','meaning','a','a',True,False,'rule',created=now-8*86400)
  events.record(self.c,1,self.node,'present','meaning','b','b',True,False,'rule',created=now-1200);self.c.commit()
  w=growth.weekly(self.c,1,now);self.assertEqual(w['current']['start'],'2026-10-13');self.assertEqual(w['current']['end'],'2026-10-19');self.assertEqual(w['previous']['independent_checks'],1);self.assertEqual(w['current']['independent_checks'],1)
  self.assertTrue(any(x['badge']=='week' for x in w['achievements']));self.assertTrue(any(x['badge']=='transfer' for x in w['achievements']))
 def test_correcting_ai_hypothesis_is_owned_audited_and_removes_recommendation(self):
  self.c.execute("INSERT INTO ai_observations(user_id,job,node,evidence,reason,created) VALUES(1,'analysis','tense-present','I goes','可能需要巩固',?)",(time.time(),));self.c.commit();ref=self.c.execute('SELECT id FROM ai_observations').fetchone()[0]
  self.assertTrue(any(r['purpose']=='hypothesis' for r in growth.review_queue(self.c,1)))
  with self.assertRaises(ValueError):growth.post(self.c,2,False,'/api/growth/correct',{'kind':'observation','id':ref,'correction':'这不是我的意思'})
  growth.post(self.c,1,False,'/api/growth/correct',{'kind':'observation','id':ref,'correction':'刚才是笔误，希望用新题检查。'})
  self.assertFalse(any(r['purpose']=='hypothesis' for r in growth.review_queue(self.c,1)));self.assertEqual(self.c.execute('SELECT COUNT(*) FROM teaching_corrections').fetchone()[0],1)
 def test_learner_corrections_enter_bounded_coach_context(self):
  self.profile();self.c.execute("INSERT INTO coach_memories(user_id,kind,text,evidence,created) VALUES(1,'difficulty','不认识词','不认识',?)",(time.time(),));ref=self.c.execute('SELECT id FROM coach_memories').fetchone()[0];self.c.commit()
  growth.post(self.c,1,False,'/api/growth/correct',{'kind':'memory','id':ref,'correction':'我认识词，主要是连读听不清'})
  prompt=coach.prompt_context(self.c,1,'继续');self.assertIn('连读听不清',prompt[0]['content']);self.assertLess(sum(len(m['content']) for m in prompt),8000)
 def test_unreviewed_ai_material_not_recommended_and_hash_guarded(self):
  self.profile();p=copy.deepcopy(lab.pack_for(self.c,1,'travel-a2'));p.pop('origin',None);p['id']='daily-quality';p['daily_day']='2026-10-19';p['provenance']={'sources':[{'url':'https://example.org'}]}
  self.c.execute('INSERT INTO lab_packs VALUES(?,NULL,?,?,?)',(p['id'],'daily',json.dumps(p),time.time()+10));self.c.commit();growth.post(self.c,1,False,'/api/growth/settings',{'theme':'travel','hotspots':True})
  self.assertNotIn(p['id'],[x['id'] for x in growth.material_candidates(self.c,1)])
  data={'pack':p['id'],'hash':quality.digest(p),'status':'approved','note':'逐项核对教学内容与来源','confirmed':{k:True for k in ('language','answers','difficulty','vocabulary','sources')}}
  self.assertEqual(quality.post(self.c,1,False,'/api/growth/quality/review',data)[1],403)
  self.assertEqual(quality.post(self.c,3,True,'/api/growth/quality/review',dict(data,hash='stale'))[1],409)
  self.assertEqual(quality.post(self.c,3,True,'/api/growth/quality/review',data)[1],200);self.assertIn(p['id'],[x['id'] for x in growth.material_candidates(self.c,1)])
  p['title']='修改后需重新审核';self.c.execute('UPDATE lab_packs SET content=? WHERE id=?',(json.dumps(p),p['id']));self.c.commit();self.assertNotIn(p['id'],[x['id'] for x in growth.material_candidates(self.c,1)])
 def test_duplicate_options_block_publication_and_revisions_preserve_original(self):
  row=self.c.execute("SELECT * FROM lab_packs WHERE id='travel-a2'").fetchone();original=row['content'];p=json.loads(original);p['questions'][0]['options'][1]=p['questions'][0]['options'][0]
  self.assertTrue(quality.checks(p)['errors'])
  p=json.loads(original);p['title']='旅行场景教学修订版'
  result,status=quality.post(self.c,3,True,'/api/growth/quality/revise',{'pack':row['id'],'hash':quality.digest(json.loads(original)),'content':p,'note':'补充修订标题并保留原题记录'})
  self.assertEqual(status,200);self.assertNotEqual(result['pack'],row['id']);self.assertEqual(self.c.execute('SELECT content FROM lab_packs WHERE id=?',(row['id'],)).fetchone()[0],original)
  new=self.c.execute('SELECT * FROM lab_packs WHERE id=?',(result['pack'],)).fetchone();self.assertEqual(quality.info(self.c,new)['status'],'candidate')
 def test_transfer_when_no_new_context_available_is_honestly_labelled(self):
  # A private sense with no material links cannot claim a new context.
  entry=lex.save(self.c,{'word':'testword','sense':'personal','meaning':'测试词','example':'A testword appears.'},'published','personal',owner=1,entry='private-testword')
  node=lex.node_id(entry);events.record(self.c,1,node,'old1','meaning','a','entry:'+entry,True,False,'rule',created=time.time()-3*86400);events.record(self.c,1,node,'old2','meaning','b','entry:'+entry,True,False,'rule',created=time.time()-2*86400);self.c.commit()
  t=adaptive.start(self.c,1,{'kind':'vocab','entry':entry,'verify':True})[0]['task'];self.assertEqual(t['payload']['verification']['purpose'],'delayed');self.assertIn('暂未提供',t['payload']['transfer_note'])
if __name__=='__main__':unittest.main()
