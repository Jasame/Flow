import unittest,sys,tempfile,time,json,os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,coach_service as coach,lab_service as lab,event_service as ev,chat_service as chat
from placement_content import ITEMS
class CoachTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'coach.db');self.p.start();app.init();self.c=app.db();self.c.executemany('INSERT INTO users(username,password) VALUES(?,?)',[('one','hash'),('two','hash')]);self.c.commit();self.token=coach.begin(self.c,1)[0]['token']
 def tearDown(self):self.c.close();self.p.stop();self.tmp.cleanup()
 def assess(self,skip=False):
  return coach.assess(self.c,1,{'token':self.token,'goal':'旅行英语与大学阅读','interests':'旅行，科技','minutes':20,'writing':'I study English.','answers':{p['id']:{'choice':None if skip else p['answer'],'hinted':False} for p in ITEMS}})
 def raw(self,missions=False):
  result={'reply':'我们先练一个真实情境。','turn_summary':'学习者提出旅行目标，本轮讨论练习安排。','memory_updates':[{'kind':'goal','text':'希望练习旅行英语','evidence':'我想练旅行英语'}],'observations':[],'missions':[]}
  if missions:
   entry=self.c.execute("SELECT id FROM lexicon WHERE status='published' LIMIT 1").fetchone()[0]
   result['missions']=[{'skill':s,'title':s+'练习','instruction':'结合兴趣练习这一维度','node':'tense-present','entry':entry,'pack':'campus-a2','minutes':5} for s in coach.SKILLS]
  return result
 def send(self,raw=None,rid='coach-request-0001',message='我想练旅行英语',new_stage=False):
  with patch.object(lab,'ai_enabled',return_value=True),patch('chat_service.request_model',return_value=(json.dumps(raw or self.raw()),'stop')) as model:
   result=coach.chat(self.c,1,{'message':message,'request_id':rid,'new_stage':new_stage})
  return result,model.call_count
 def test_placement_hides_answers_and_is_low_stakes(self):
  items=coach.begin(self.c,1)[0]['items'];self.assertTrue(all('answer' not in p for p in items));r,s=self.assess();self.assertEqual(s,200);self.assertEqual(r['band'],'B2');self.assertEqual(r['scores']['speaking']['total'],0);self.assertEqual(self.assess()[1],200)
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM learning_events').fetchone()[0],len(ITEMS))
 def test_skipped_assessment_keeps_unknown_and_does_not_forge_mastery(self):
  r,_=self.assess(True);self.assertEqual(r['band'],'A2');self.assertEqual(ev.state(self.c,1,'skill:listening')['independent'],0)
 def test_conversation_memory_is_persistent_private_and_idempotent(self):
  self.assess();out,calls=self.send();self.assertEqual(out[1],200);self.assertEqual(calls,1);self.assertEqual(self.send()[1],0)
  self.assertEqual(len(coach.snapshot(self.c,1)['turns']),1);self.assertEqual(coach.snapshot(self.c,2)['turns'],[]);self.assertEqual(len(coach.snapshot(self.c,1)['memories']),1);self.assertEqual(coach.snapshot(self.c,2)['memories'],[])
 def test_memory_and_observation_must_quote_actual_user_message(self):
  self.assess();raw=self.raw();raw['memory_updates'][0]['evidence']='从未说过'
  self.assertEqual(self.send(raw)[0][1],502);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM coach_memories').fetchone()[0],0)
 def test_stage_covers_all_dimensions_and_preserves_existing_plan(self):
  self.assess();self.assertEqual(self.send(self.raw(True))[0][1],200);self.assertEqual(len(coach.snapshot(self.c,1)['missions']),6)
  self.send(self.raw(True),'coach-request-0002');self.assertEqual(self.c.execute('SELECT COUNT(*) FROM coach_missions').fetchone()[0],6)
  self.send(self.raw(True),'coach-request-0003',new_stage=True);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM coach_missions').fetchone()[0],12)
 def test_partial_plan_does_not_publish(self):
  self.assess();raw=self.raw(True);raw['missions']=raw['missions'][:2];self.assertEqual(self.send(raw)[0][1],502);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM coach_missions').fetchone()[0],0)
 def test_real_work_completes_quest_once_without_claiming_ability(self):
  self.assess();self.send(self.raw(True));pack=lab.pack_for(self.c,1,'campus-a2')
  mission=self.c.execute("SELECT id FROM coach_missions WHERE skill='writing'").fetchone()[0]
  feedback={'strength':'A clear start','priorities':[],'revision':'My own short answer.','next_question':'Can you add one detail?','links':[],'task_check':{'on_task':True,'evidence':'My own short answer.','reason':'完成这次短表达要求。'}}
  with patch.object(lab,'ai_enabled',return_value=True),patch.object(lab,'request_model',return_value=(json.dumps(feedback),'stop')):
   lab.feedback(self.c,1,{'pack':pack['id'],'skill':'writing','answer':'My own short answer.','coach_mission':mission,'request_id':'reviewed-work-0001'})
  lab.post(self.c,1,'/api/lab/save',{'pack':pack['id'],'skill':'writing','answer':'My own short answer.','coach_mission':mission,'feedback_request':'reviewed-work-0001','save_id':'coach-work-save-001'})
  first=coach.snapshot(self.c,1);second=coach.snapshot(self.c,1);self.assertEqual(first['growth']['xp'],20);self.assertEqual(second['growth']['xp'],20);self.assertEqual(ev.state(self.c,1,'skill:writing')['independent'],0)
 def test_context_retains_old_retrievable_summary_and_is_bounded(self):
  self.assess();self.send();ctx=coach.prompt_context(self.c,1,'旅行');self.assertIn('希望练习旅行英语',ctx[0]['content']);self.assertLess(sum(len(m['content']) for m in ctx),8000)
  self.assertEqual(coach.retrieved(self.c,2,'旅行'),[])
 def test_no_individual_twenty_call_limit(self):
  self.assess();day=time.strftime('%Y-%m-%d',time.gmtime());self.c.execute('INSERT INTO ai_usage VALUES(?,?,200)',(1,day));self.c.commit()
  with patch.dict(os.environ,{'FLOW_AI_DAILY_LIMIT':'0'}):self.assertEqual(self.send()[0][1],200)
  self.assertIsNone(chat.remaining(self.c,1))
 def test_text_only_speaking_draft_does_not_complete_a_voice_mission(self):
  self.assess();self.send(self.raw(True));mission=self.c.execute("SELECT id FROM coach_missions WHERE skill='speaking'").fetchone()[0];raw=self.raw();raw['memory_updates']=[]
  with patch.object(lab,'ai_enabled',return_value=True),patch('chat_service.request_model',return_value=(json.dumps(raw),'stop')):
   self.assertEqual(coach.chat(self.c,1,{'message':'I would like to practise speaking about my day.','request_id':'coach-oral-draft-001','mission':mission})[1],200)
  self.assertEqual(self.c.execute('SELECT status FROM coach_missions WHERE id=?',(mission,)).fetchone()[0],'active')
 def test_custom_mission_instructions_reach_feedback_and_owned_saved_work(self):
  self.assess();self.send(self.raw(True));mission=self.c.execute("SELECT * FROM coach_missions WHERE skill='writing'").fetchone();self.c.execute('UPDATE coach_missions SET instruction=? WHERE id=?',('Write a polite travel request.',mission['id']));self.c.commit()
  data={'pack':'campus-a2','skill':'writing','answer':'Could you help me plan a trip?','request_id':'mission-feedback-0001','coach_mission':mission['id']}
  reply={'strength':'Clear request','priorities':[{'issue':'Detail','evidence':'trip','suggestion':'Add a date'}],'revision':'Could you help me plan a trip next week?','next_question':'When will you travel?','links':[]}
  reply['task_check']={'on_task':True,'evidence':'Could you help me plan a trip?','reason':'针对任务给出礼貌旅行请求。'}
  with patch.object(lab,'ai_enabled',return_value=True),patch.object(lab,'request_model',return_value=(json.dumps(reply),'stop')) as model:
   result,status=lab.feedback(self.c,1,data);self.assertEqual(status,200);self.assertIn('Write a polite travel request.',model.call_args.args[0][1]['content'])
   with self.assertRaises(ValueError):lab.feedback(self.c,2,dict(data,request_id='mission-forbidden-001'))
  saved,status=lab.post(self.c,1,'/api/lab/save',{'pack':'campus-a2','skill':'writing','answer':data['answer'],'feedback_request':data['request_id'],'coach_mission':mission['id'],'save_id':'mission-save-0001'})
  self.assertEqual(status,200);self.assertEqual(saved['details']['coach_mission'],mission['id']);self.assertEqual(coach.snapshot(self.c,1)['growth']['xp'],20)
 def test_new_work_reflection_is_idempotently_keyed_and_does_not_make_fake_memory(self):
  self.assess();self.send(self.raw(True));saved,_=lab.post(self.c,1,'/api/lab/save',{'pack':'campus-a2','skill':'writing','answer':'I wrote a new answer.','save_id':'reflection-work-001'})
  self.assertEqual(coach.snapshot(self.c,1)['reflection_work'],saved['id'])
  self.assertEqual(self.send(self.raw(),'coach-reflect-'+str(saved['id']),message='请复盘训练')[0][1],200)
  self.assertIsNone(coach.snapshot(self.c,1)['reflection_work'])
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM coach_memories').fetchone()[0],1)
 def test_twenty_two_coach_turns_continue_without_personal_ceiling(self):
  self.assess();raw=self.raw()
  with patch.dict(os.environ,{'FLOW_AI_DAILY_LIMIT':'0'}),patch.object(lab,'ai_enabled',return_value=True),patch('chat_service.request_model',return_value=(json.dumps(raw),'stop')) as model:
   for i in range(22):
    result,status=coach.chat(self.c,1,{'message':'我想练旅行英语','request_id':'long-coach-request-'+str(i).zfill(4)})
    self.assertEqual(status,200)
   self.assertEqual(model.call_count,22)
  self.assertEqual(len(coach.snapshot(self.c,1)['turns']),22)
  self.assertLess(sum(len(m['content']) for m in coach.prompt_context(self.c,1,'继续练习')),8000)
 def test_restart_preserves_dialogue_memory_and_profile(self):
  self.assess();self.send();self.c.close();app.init();self.c=app.db();d=coach.snapshot(self.c,1);self.assertEqual(len(d['turns']),1);self.assertEqual(len(d['memories']),1);self.assertEqual(d['profile']['goal'],'旅行英语与大学阅读')
if __name__=='__main__':unittest.main()
