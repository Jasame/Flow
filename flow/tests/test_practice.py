import unittest,tempfile,sys,json,time,copy
from pathlib import Path
from collections import Counter
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,practice_service as practice,quality_service as quality,lab_service as lab,event_service as events,growth_service as growth
from content_v09 import GRADED
class PracticeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'practice.db');self.p.start();app.init();self.c=app.db();self.c.executemany('INSERT INTO users(username,password) VALUES(?,?)',[('one','hash'),('two','hash')]);self.c.execute("INSERT INTO lab_profile VALUES(1,'A2','travel','listening')");self.c.commit()
 def tearDown(self):self.c.close();self.p.stop();self.tmp.cleanup()
 def record(self,pack,skill,correct=True,assisted=False,ago=0,source=None):
  p=lab.pack_for(self.c,1,pack);events.record(self.c,1,'skill:'+skill,source or pack+skill+str(ago),'comprehension',pack,practice.family(p),correct,assisted,'rule',created=time.time()-ago);self.c.commit()
 def test_authored_corpus_has_full_coverage_no_duplicate_bodies_and_valid_questions(self):
  self.assertEqual(len(GRADED),108);self.assertEqual(len({p['body'] for p in GRADED}),108);self.assertEqual(len({p['family'] for p in GRADED}),36);self.assertEqual(Counter(p['level'] for p in GRADED),{'A2':36,'B1':36,'B2':36})
  for p in GRADED:
   self.assertEqual(quality.checks(p)['errors'],[],p['id']);self.assertEqual(quality.checks(p)['warnings'],[],p['id']);self.assertTrue(p['body'].startswith(p['knowledge'][0]['quote']));self.assertFalse(p['grading_basis']['certified'])
  for theme in ('campus','travel','life','work','culture','science'):
   for level in practice.LEVELS:self.assertEqual(sum(p['theme']==theme and p['level']==level for p in GRADED),6)
 def test_listening_and_reading_calibrate_separately_after_distinct_situations(self):
  for slug in ('quiet-room','deadline','club-budget','group-roles','lab-safety','feedback-rewrite'):self.record('graded-'+slug+'-a2','reading')
  bands=practice.bands(self.c,1);self.assertEqual(bands['reading']['level'],'B1');self.assertEqual(bands['listening']['level'],'A2');self.assertEqual(bands['speaking']['level'],'A2');self.assertEqual(bands['writing']['level'],'A2')
  self.assertEqual(practice.overview(self.c,1,'reading')['target'],'B1');self.assertEqual(practice.overview(self.c,1,'listening')['target'],'A2')
 def test_sibling_versions_do_not_supply_three_distinct_calibration_samples(self):
  for level in practice.LEVELS:self.record('graded-quiet-room-'+level.lower(),'reading')
  self.assertEqual(practice.bands(self.c,1)['reading']['families'],1)
 def test_hinted_or_ai_opinions_cannot_advance_band(self):
  for slug in ('quiet-room','deadline','club-budget'):self.record('graded-'+slug+'-a2','reading',True,True)
  self.assertEqual(practice.bands(self.c,1)['reading']['level'],'A2');self.assertFalse(practice.bands(self.c,1)['reading']['calibrated'])
 def test_sibling_version_is_not_new_transfer_context(self):
  self.record('graded-quiet-room-a2','reading',ago=2*86400);self.record('graded-quiet-room-b1','reading');state=events.state(self.c,1,'skill:reading');self.assertEqual(state['transfer'],0);self.assertEqual(state['delayed'],1)
 def test_reading_sibling_before_listening_marks_familiar_material(self):
  p=lab.pack_for(self.c,1,'graded-quiet-room-a2');lab.post(self.c,1,'/api/lab/support',{'pack':p['id'],'skill':'reading','action':'start'});lab.post(self.c,1,'/api/lab/comprehension',{'pack':p['id'],'skill':'reading','choices':[q['answer'] for q in p['questions']],'save_id':'practice-reading-001'})
  other=lab.pack_for(self.c,1,'graded-quiet-room-b1');lab.post(self.c,1,'/api/lab/support',{'pack':other['id'],'skill':'listening','action':'start'});out,_=lab.post(self.c,1,'/api/lab/comprehension',{'pack':other['id'],'skill':'listening','choices':[q['answer'] for q in other['questions']],'save_id':'practice-listening-001'})
  self.assertEqual(out['details']['assisted'],1);self.assertEqual(events.state(self.c,1,'skill:listening')['independent'],0)
 def test_recommendations_prioritize_level_then_theme_and_distinct_families(self):
  d=practice.overview(self.c,1);self.assertEqual(d['total'],154);self.assertEqual(len(d['items']),6);self.assertTrue(all(p['level']=='A2' and p['theme']=='travel' for p in d['items']));self.assertEqual(len({p['grading']['family'] for p in d['items']}),6)
 def test_preferences_and_learner_evidence_do_not_cross_accounts(self):
  practice.post(self.c,1,'/api/practice/preferences',{'skill':'writing','mode':'stretch'});self.assertEqual(practice.overview(self.c,1)['target'],'B1');self.assertEqual(practice.preferences(self.c,2)['mode'],'steady');self.assertEqual(practice.bands(self.c,2)['reading']['evidence_ids'],[])
 def test_unapproved_private_content_excluded_and_disabled_public_content_removed(self):
  first=practice.overview(self.c,1)['items'][0];row=self.c.execute('SELECT * FROM lab_packs WHERE id=?',(first['id'],)).fetchone();p=json.loads(row['content']);self.c.execute("INSERT INTO material_reviews(pack,content_hash,status,checks,note,created) VALUES(?,?,'disabled','{}','test',?)",(p['id'],quality.digest(p),time.time()));self.c.execute('INSERT INTO lab_packs VALUES(?,1,?,?,?)',('private-candidate','gemini',json.dumps(dict(p,id='private-candidate')),time.time()));self.c.commit()
  d=practice.overview(self.c,1);self.assertNotIn(first['id'],[p['id'] for p in d['items']]);self.assertNotIn('private-candidate',[p['id'] for p in d['items']]);self.assertEqual(d['total'],153)
 def test_stage_uses_personalized_rank_and_catalog_exposes_grading(self):
  candidates=growth.material_candidates(self.c,1);self.assertEqual(candidates[0]['level'],'A2');detail=lab.get(self.c,1,'/api/lab/pack',{'id':['graded-quiet-room-a2']})[0]['pack'];self.assertIn('rationale',detail['grading']);self.assertEqual(detail['grading']['family'],'graded-quiet-room')
if __name__=='__main__':unittest.main()
