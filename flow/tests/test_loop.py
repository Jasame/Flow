import unittest,tempfile,time,sys,datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,loop_service as loop,event_service as events,adaptive_service as adaptive,lexicon_service as lex,coach_service as coach,growth_service as growth
from placement_content import ITEMS
class LoopTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'loop.db');self.p.start();app.init();self.c=app.db();self.c.executemany('INSERT INTO users(username,password) VALUES(?,?)',[('learner','x'),('other','x')]);self.c.commit();self.entry=lex.key('suggest','advice');self.node=lex.node_id(self.entry)
 def tearDown(self):self.c.close();self.p.stop();self.tmp.cleanup()
 def record(self,source,kind,correct=None,assisted=None,evaluator='rule',created=None):events.record(self.c,1,self.node,source,kind,kind,'context',correct,assisted,evaluator,created=created)
 def test_modes_never_inherit_passes_and_private_data_stays_owned(self):
  adaptive.enroll(self.c,1,self.entry);self.record('m','meaning',True,False);self.record('a','application',True,False,'ai');self.c.commit()
  d=loop.overview(self.c,1);w=d['words'][0];m={x['mode']:x for x in w['modes']};self.assertEqual(m['meaning']['independent_passes'],1);self.assertEqual(m['spelling']['status'],'待练习');self.assertEqual(m['application']['independent_passes'],0);self.assertEqual(m['application']['status'],'已收集表达，待验证')
  other=loop.overview(self.c,2);self.assertEqual(other['changes'],[]);self.assertEqual(other['words'],[]);self.assertEqual(other['today']['activities'],0)
 def test_state_trace_follows_each_event_not_current_final_state(self):
  self.record('first','meaning',True,False,created=time.time()-100);self.record('wrong','spelling',False,False,created=time.time()-50);self.c.commit();d=loop.overview(self.c,1)
  self.assertEqual(d['changes'][0]['after'],'需要巩固');self.assertEqual(d['changes'][0]['before'],'独立完成一次');self.assertEqual(d['changes'][1]['after'],'独立完成一次');self.assertNotEqual(d['changes'][0]['id'],d['changes'][1]['id'])
 def test_today_beijing_boundary_deduplicates_activity_and_ignores_future(self):
  now=datetime.datetime(2026,10,21,0,10,tzinfo=loop.TZ).timestamp()
  self.record('old','meaning',True,False,created=now-1200);self.record('work:1','meaning',True,False,created=now-60)
  events.record(self.c,1,'tense-present','work:1','exposure','a',evaluator='practice',created=now-60)
  self.record('future','spelling',True,False,created=now+60);self.c.commit();d=loop.overview(self.c,1,now=now)
  self.assertEqual(d['day'],'2026-10-21');self.assertEqual(d['today']['activities'],1);self.assertEqual(d['today']['independent_checks'],1);self.assertEqual(len(d['changes']),3)
 def test_resume_moves_after_completion_and_survives_reopening(self):
  token=coach.begin(self.c,1)[0]['token'];coach.assess(self.c,1,{'token':token,'goal':'旅行交流','interests':'旅行','minutes':10,'writing':'','answers':{p['id']:{'choice':None,'hinted':False} for p in ITEMS}});growth.stage(self.c,1,{'request_id':'loop-stage-request-001'})
  d=loop.overview(self.c,1);u=d['unit'];self.assertLessEqual(u['remaining_minutes'],10);first=u['tasks'][0]['id'];self.assertEqual(loop.overview(self.c,1)['unit']['tasks'][0]['id'],first)
  self.c.execute("UPDATE coach_missions SET status='done',done=? WHERE id=?",(time.time(),first));self.c.commit();self.assertNotEqual(loop.overview(self.c,1)['unit']['tasks'][0]['id'],first)
  snap=coach.snapshot(self.c,1);self.assertIn('learning_loop',snap);prompt=coach.prompt_context(self.c,1,'继续下一项');self.assertIn('learning_loop',prompt[0]['content']);self.assertLess(sum(len(x['content']) for x in prompt),8000)
 def test_legacy_hint_unknown_is_not_independent(self):
  adaptive.enroll(self.c,1,self.entry);self.record('legacy','meaning',True,None);self.c.commit();d=loop.overview(self.c,1);self.assertEqual(d['words'][0]['modes'][0]['status'],'提示情况未知');self.assertEqual(d['today']['independent_checks'],0)
if __name__=='__main__':unittest.main()
