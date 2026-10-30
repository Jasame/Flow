import json,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,foundation_service as f,coach_service as coach,lab_service as lab,event_service as ev,graph_service as graph,lexicon_service as lex
from placement_content import ITEMS
class ContinuityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'state.db');self.p.start();app.init();self.c=app.db();self.c.execute("INSERT INTO users(username,password) VALUES('one','x')");self.c.execute("INSERT INTO users(username,password) VALUES('two','x')");self.c.commit()
 def tearDown(self):self.c.close();self.p.stop();self.tmp.cleanup()
 def start(self,key):
  f.post(self.c,1,'/api/foundation/step',{'lesson':key,'step':0})
  d=f.view(self.c,1,key);choice=d['options'].index(f.lesson(self.c,1,key)['options'][0]);f.post(self.c,1,'/api/foundation/step',{'lesson':key,'step':1,'answer':str(choice)})
 def complete(self,key):
  self.start(key);return f.post(self.c,1,'/api/foundation/step',{'lesson':key,'step':2,'answer':f.lesson(self.c,1,key)['target']})
 def profile(self,goal):
  token=coach.begin(self.c,1)[0]['token'];coach.assess(self.c,1,{'token':token,'goal':goal,'interests':'','minutes':10,'writing':'','answers':{p['id']:{'choice':None,'hinted':False} for p in ITEMS}})
 def test_choice_value_not_a_text_draft(self):
  self.start('food');self.assertEqual(f.view(self.c,1,'food')['answer'],'')
 def test_dynamic_resume_and_goal_route(self):
  self.profile('工作邮件');self.assertEqual(f.recommended(self.c,1)['lesson'],'work-request');key='word:'+lex.key('suggest','advice');self.start(key);self.assertEqual(f.recommended(self.c,1)['lesson'],key)
 def test_versioned_draft_ignores_late_request(self):
  self.start('food')
  for version,text in [(8,'new'),(7,'old')]:f.post(self.c,1,'/api/foundation/draft',{'lesson':'food','answer':text,'revision':version})
  self.assertEqual(f.view(self.c,1,'food')['answer'],'new');self.assertEqual(f.view(self.c,2,'food')['answer'],'')
 def test_studio_drafts_ignore_late_versions(self):
  for revision,answer in [(20,'new draft'),(19,'old draft')]:lab.post(self.c,1,'/api/lab/draft',{'pack':'campus-a2','skill':'writing','answer':answer,'revision':revision})
  self.assertEqual(self.c.execute('SELECT answer FROM lab_drafts WHERE user_id=1').fetchone()[0],'new draft')
  import adaptive_service as adaptive
  entry=lex.key('suggest','advice')
  for revision,answer in [(20,'new draft'),(19,'old draft')]:
   adaptive.post(self.c,1,False,'/api/vocab/draft',{'entry':entry,'answer':answer,'revision':revision});coach.post(self.c,1,'/api/coach/draft',{'message':answer,'revision':revision})
  self.assertEqual(self.c.execute('SELECT answer FROM learner_drafts WHERE user_id=1').fetchone()[0],'new draft');self.assertEqual(self.c.execute('SELECT message FROM coach_drafts WHERE user_id=1').fetchone()[0],'new draft')
 def test_shorthand_and_full_form_and_replayed_submit(self):
  self.start('food');r,status=f.post(self.c,1,'/api/foundation/step',{'lesson':'food','step':2,'answer':'I would like water, please.'});self.assertTrue(r['ok']);self.assertEqual(status,200)
  self.assertEqual(f.post(self.c,1,'/api/foundation/step',{'lesson':'food','step':2,'answer':"I'd like water, please."})[1],409)
  self.assertEqual(self.c.execute("SELECT count(*) FROM learning_events WHERE user_id=1 AND node='skill:writing' AND source='foundation:food'").fetchone()[0],1)
 def test_review_due_and_idempotent_retry(self):
  self.profile('旅行');self.complete('food');now=time.time()+86401
  with patch.object(f.time,'time',return_value=now):
   self.assertTrue(f.recommended(self.c,1)['review']);data={'lesson':'food','answer':"I'd like water, please.",'request_id':'same-review-00001'};a=f.post(self.c,1,'/api/foundation/review',data)[0];b=f.post(self.c,1,'/api/foundation/review',data)[0];self.assertEqual(a,b)
  self.assertEqual(self.c.execute('SELECT round FROM foundation_reviews').fetchone()[0],1);self.assertEqual(ev.state(self.c,1,'skill:writing')['independent'],0)
 def test_early_practice_does_not_delay_scheduled_review(self):
  self.complete('hotel');before=f.view(self.c,1,'hotel')['due'];f.post(self.c,1,'/api/foundation/review',{'lesson':'hotel','answer':'I have a booking.'});self.assertEqual(f.view(self.c,1,'hotel')['due'],before)
 def test_graph_has_concrete_lesson_and_exposure_only(self):
  self.complete('hotel');d=graph.detail(self.c,1,'lesson:hotel');self.assertTrue(d['state']['events']);self.assertEqual(d['state']['independent'],0)
  entry=self.c.execute("SELECT id FROM lexicon WHERE lemma='booking' AND owner IS NULL LIMIT 1").fetchone()[0];self.assertGreater(ev.state(self.c,1,'sense:'+entry)['exposures'],0);self.assertEqual(ev.state(self.c,1,'sense:'+entry)['independent'],0)
 def test_coach_context_knows_guided_sentence(self):
  self.profile('旅行');self.complete('food');ctx=coach.prompt_context(self.c,1,'我刚才学了什么');self.assertIn("I'd like water",' ' .join(m['content'] for m in ctx));self.assertIn('foundation_recent',str(ctx));self.assertLess(sum(len(m['content']) for m in ctx),8000)
 def test_migration_preserves_real_draft_and_backfills_review(self):
  self.start('food');f.post(self.c,1,'/api/foundation/draft',{'lesson':'food','answer':'My real draft'});self.complete('hotel');self.c.commit();self.c.close();app.init();self.c=app.db();self.assertEqual(f.view(self.c,1,'food')['answer'],'My real draft');self.assertIsNotNone(f.view(self.c,1,'hotel')['due'])
  old=time.time()-86400*5;self.c.execute("INSERT INTO foundation_progress(user_id,lesson,step,answer,updated) VALUES(1,'directions',3,'Where is the hotel?',?)",(old,));self.c.commit();self.c.close();app.init();self.c=app.db();self.assertEqual(self.c.execute("SELECT created FROM learning_events WHERE user_id=1 AND node='lesson:directions'").fetchone()[0],old)
 def test_completed_starter_route_hands_off_to_active_stage(self):
  import growth_service as growth,loop_service as loop
  self.profile('工作邮件')
  for key in f.ROUTES['work']:self.complete(key)
  self.assertTrue(f.recommended(self.c,1)['optional']);growth.stage(self.c,1,{'request_id':'handoff-stage-00001'});self.assertIsNone(loop.overview(self.c,1)['next_action']);self.assertTrue(loop.overview(self.c,1)['unit'])
 def test_task_resume_checks_owner_expiry_and_preserves_hint(self):
  import adaptive_service as adaptive
  data,_=adaptive.start(self.c,1,{'kind':'grammar','node':'tense-present'});token=data['task']['token'];adaptive.hint(self.c,1,{'token':token})
  d,_=adaptive.get(self.c,1,False,'/api/adaptive/task',{'token':[token]});self.assertTrue(d['task']['assisted']);self.assertNotIn('answer',d['task'])
  with self.assertRaises(ValueError):adaptive.get(self.c,2,False,'/api/adaptive/task',{'token':[token]})
  self.c.execute('UPDATE adaptive_tasks SET expires=0 WHERE token=?',(token,));self.c.commit()
  with self.assertRaises(ValueError):adaptive.get(self.c,1,False,'/api/adaptive/task',{'token':[token]})
if __name__=='__main__':unittest.main()
