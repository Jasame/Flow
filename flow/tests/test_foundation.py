import unittest,tempfile,sys,json,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,foundation_service as basic,coach_service as coach,adaptive_service as adaptive,event_service as events,lexicon_service as lex,graph_service as graph,practice_service as practice,corpus_service as corpus
from placement_content import ITEMS
class FoundationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patch=patch.object(app,'DB',Path(self.tmp.name)/'basic.db');self.patch.start();app.init();self.c=app.db();self.c.executemany('INSERT INTO users(username,password) VALUES(?,?)',[('one','x'),('two','x')]);self.c.commit()
 def tearDown(self):self.c.close();self.patch.stop();self.tmp.cleanup()
 def profile(self):
  token=coach.begin(self.c,1)[0]['token'];coach.assess(self.c,1,{'token':token,'goal':'旅游点餐','interests':'旅行','minutes':15,'writing':'','answers':{p['id']:{'choice':None,'hinted':False} for p in ITEMS}})
 def complete(self,key):
  d=basic.view(self.c,1,key)
  for step,answer in [(0,''),(1,str(d['options'].index(basic.lesson(self.c,1,key)['options'][0]))),(2,d['target'])]:self.assertTrue(basic.post(self.c,1,'/api/foundation/step',{'lesson':key,'step':step,'answer':answer})[0]['ok'])
 def test_four_easy_items_cannot_establish_b1(self):
  token=coach.begin(self.c,1)[0]['token'];answers={p['id']:{'choice':p['answer'] if p['tier']==1 else None,'hinted':False} for p in ITEMS}
  result,_=coach.assess(self.c,1,{'token':token,'goal':'旅游','interests':'','minutes':15,'writing':'','answers':answers});self.assertEqual(result['band'],'A2')
 def test_low_evidence_gets_pending_label_and_guided_course(self):
  self.profile();s=coach.snapshot(self.c,1);self.assertTrue(s['foundation']['basic']);self.assertIn('待校准',s['profile']['placement']['label']);self.assertEqual(s['learning_loop']['next_action']['type'],'foundation')
 def test_guided_success_is_not_independent_and_progress_survives_reopen(self):
  self.complete('food');d=basic.view(self.c,1,'food');self.assertEqual(d['step'],3);self.assertEqual(events.state(self.c,1,'skill:writing')['independent'],0);self.assertEqual(basic.view(self.c,2,'food')['step'],0);self.assertEqual(basic.recommended(self.c,1)['lesson'],'directions')
 def test_draft_restores_and_late_draft_cannot_overwrite_completed_work(self):
  for step,answer in [(0,''),(1,str(basic.view(self.c,1,'food')['options'].index(basic.LESSONS['food']['options'][0])))]:basic.post(self.c,1,'/api/foundation/step',{'lesson':'food','step':step,'answer':answer})
  basic.post(self.c,1,'/api/foundation/draft',{'lesson':'food','answer':'My draft'})
  self.assertEqual(basic.view(self.c,1,'food')['answer'],'My draft')
  basic.post(self.c,1,'/api/foundation/step',{'lesson':'food','step':2,'answer':"I'd like water, please."})
  basic.post(self.c,1,'/api/foundation/draft',{'lesson':'food','answer':'Late draft'})
  self.assertEqual(basic.view(self.c,1,'food')['answer'],"I'd like water, please.")
 def test_wrong_and_forged_step_do_not_advance(self):
  self.assertEqual(basic.post(self.c,1,'/api/foundation/step',{'lesson':'food','step':2,'answer':"I'd like water, please."})[1],409)
  basic.post(self.c,1,'/api/foundation/step',{'lesson':'food','step':0})
  self.assertFalse(basic.post(self.c,1,'/api/foundation/step',{'lesson':'food','step':1,'answer':str((basic.view(self.c,1,'food')['options'].index(basic.LESSONS['food']['options'][0])+1)%3)})[0]['ok']);self.assertEqual(basic.view(self.c,1,'food')['step'],1)
 def test_new_word_learns_before_recall_and_owner_is_checked(self):
  self.profile();entry=lex.key('suggest','advice');d,status=adaptive.start(self.c,1,{'kind':'vocab','entry':entry});self.assertEqual(d['foundation'],'word:'+entry)
  self.complete('word:'+entry);self.assertIn('task',adaptive.start(self.c,1,{'kind':'vocab','entry':entry})[0]);self.assertEqual(events.state(self.c,1,'sense:'+entry)['independent'],0)
  with self.assertRaises(ValueError):basic.view(self.c,2,'word:private-does-not-exist')
 def test_repeated_failure_opens_micro_lesson_even_in_standard_mode(self):
  basic.post(self.c,1,'/api/foundation/mode',{'mode':'standard'})
  for i in range(2):events.record(self.c,1,'tense-present','fail-'+str(i),'choice',str(i),str(i),False,False,'rule')
  self.c.commit();a=__import__('loop_service').overview(self.c,1)['next_action'];self.assertEqual(a['lesson'],'grammar:tense-present');self.complete(a['lesson']);self.assertEqual(__import__('loop_service').overview(self.c,1)['next_action']['type'],'repair')
 def test_graph_materials_share_recommendation_band_and_current_versions(self):
  self.profile();d=graph.detail(self.c,1,'tense-present')
  for p in d['materials']:
   row=self.c.execute('SELECT content FROM lab_packs WHERE id=?',(p['id'],)).fetchone();self.assertEqual(json.loads(row[0])['level'],'A2');self.assertFalse(p['id'].startswith('graded-') and not p['id'].endswith('-r30'))
 def test_catalog_default_order_matches_personalized_recommendation(self):
  self.profile();recommended=practice.overview(self.c,1)['items'];catalog=corpus.catalog(self.c,1);self.assertEqual([p['id'] for p in catalog[:6]],[p['id'] for p in recommended[:6]])
if __name__=='__main__':unittest.main()
