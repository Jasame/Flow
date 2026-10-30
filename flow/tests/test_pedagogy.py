import unittest,tempfile,sys,json,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,adaptive_service as adaptive,event_service as events,lexicon_service as lex,graph_service as graph,loop_service as loop,practice_service as practice,lab_service as lab,quality_service as quality,coach_service as coach
from content_v30 import REVISED
from placement_content import ITEMS
class PedagogyTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'pedagogy.db');self.p.start();app.init();self.c=app.db();self.c.executemany('INSERT INTO users(username,password) VALUES(?,?)',[('one','hash'),('two','hash')]);self.c.commit();self.entry=lex.key('suggest','advice');self.node=lex.node_id(self.entry)
 def tearDown(self):self.c.close();self.p.stop();self.tmp.cleanup()
 def test_wrong_answer_produces_primary_repair_without_replacing_saved_plan(self):
  events.record(self.c,1,self.node,'failed','meaning','a','a',False,False,'rule');self.c.commit();a=loop.overview(self.c,1)['next_action'];self.assertEqual(a['type'],'repair');self.assertEqual(a['target'],self.entry);self.assertEqual(a['evidence_ids'],[1]);self.assertIsNone(loop.overview(self.c,2)['next_action'])
  events.record(self.c,1,self.node,'fixed','meaning','b','b',True,False,'rule');self.c.commit();self.assertIsNone(loop.overview(self.c,1)['next_action'])
 def test_recognition_does_not_unlock_delayed_spelling_or_pattern_mastery(self):
  events.record(self.c,1,self.node,'recognition','meaning','a','a',True,False,'rule',created=time.time()-2*86400);events.record(self.c,1,self.node,'spelling','spelling','b','b',True,False,'rule');self.c.commit();s=events.state(self.c,1,self.node);self.assertEqual(s['delayed'],0);self.assertEqual(s['transfer'],0)
  w=__import__('growth_service').weekly(self.c,1);self.assertFalse(any(x['badge'] in ('delayed','week','transfer') for x in w['achievements']))
  g=graph.network(self.c,1);patterns=[n for n in g['nodes'] if n['kind']=='pattern' and n['ref']==self.entry];self.assertTrue(patterns);self.assertTrue(all(n['status']=='unknown' for n in patterns))
 def test_relation_meanings_are_bound_to_actual_edges_and_owned_nodes(self):
  d=graph.detail(self.c,1,self.node);self.assertTrue(d['relationship_meanings'])
  for e in d['relationship_meanings']:
   self.assertTrue(e['meaning']);self.assertTrue(e['learning_action']);self.assertTrue(self.c.execute('SELECT 1 FROM kg_edges WHERE source=? AND target=? AND relation=?',(e['source'],e['target'],e['relation'])).fetchone())
  literal=next(e for e in d['relationship_meanings'] if e['relation']=='occurs_in');self.assertIn('不证明义项一致',literal['limit'])
 def test_answer_exposure_blocks_reverse_skill_and_sibling_independent_claim(self):
  p=lab.pack_for(self.c,1,'graded-quiet-room-a2-r30')
  for i,skill in enumerate(('listening','reading')):
   lab.post(self.c,1,'/api/lab/support',{'pack':p['id'],'skill':skill,'action':'start'})
   out,_=lab.post(self.c,1,'/api/lab/comprehension',{'pack':p['id'],'skill':skill,'choices':[q['answer'] for q in p['questions']],'save_id':'exposure-check-'+str(i)})
  self.assertEqual(out['details']['assisted'],1);self.assertIn('答案可能已暴露',out['details']['support_note']);self.assertEqual(events.state(self.c,1,'skill:reading')['independent'],0)
 def test_revisions_keep_old_answers_but_only_recommend_new_versions(self):
  old=lab.pack_for(self.c,1,'graded-quiet-room-b2');new=lab.pack_for(self.c,1,old['id']+'-r30');self.assertEqual(old['questions'][0]['prompt'],'When is the room free?');self.assertNotEqual(old['questions'],new['questions']);self.assertEqual(old['body'],new['body'])
  self.assertFalse(quality.recommendable(self.c,self.c.execute('SELECT * FROM lab_packs WHERE id=?',(old['id'],)).fetchone()));self.assertEqual(practice.overview(self.c,1)['total'],154)
  for p in REVISED:self.assertEqual(quality.checks(p)['errors'],[],p['id'])
 def test_three_samples_do_not_jump_and_confirmed_level_survives_inactivity(self):
  self.c.execute("INSERT INTO lab_profile VALUES(1,'A2','travel','reading')");self.c.commit()
  packs=[p for p in REVISED if p['level']=='A2'][:6]
  for i,p in enumerate(packs):
   events.record(self.c,1,'skill:reading','band-'+str(i),'comprehension',p['id'],'family:'+p['family'],True,False,'rule')
   if i==2:self.assertEqual(practice.bands(self.c,1)['reading']['level'],'A2')
  self.c.commit();practice.update_bands(self.c,1);self.c.commit();self.assertEqual(practice.bands(self.c,1)['reading']['level'],'B1')
  self.c.execute('UPDATE learning_events SET created=created-30*86400');self.c.commit();self.assertEqual(practice.bands(self.c,1)['reading']['level'],'B1')
 def test_failed_input_material_proposes_unseen_parallel_context(self):
  p=lab.pack_for(self.c,1,'travel-a2');events.record(self.c,1,'skill:listening','listen-fail','comprehension',p['id'],p['id'],False,False,'rule');self.c.commit();a=loop.overview(self.c,1)['next_action'];self.assertEqual(a['type'],'material_repair');self.assertEqual(a['skill'],'listening');self.assertNotEqual(a['pack'],p['id'])
 def test_feedback_can_acknowledge_no_error_instead_of_inventing_one(self):
  out=lab.validate_feedback({'strength':'Clear request','priorities':[],'revision':'Could you help?','next_question':'What do you need?'})
  self.assertEqual(out['priorities'],[])
 def test_placement_has_multiple_input_samples_and_keeps_unknown_output(self):
  self.assertGreaterEqual(sum(p['skill']=='listening' for p in ITEMS),2);self.assertGreaterEqual(sum(p['skill']=='reading' for p in ITEMS),2)
if __name__=='__main__':unittest.main()
