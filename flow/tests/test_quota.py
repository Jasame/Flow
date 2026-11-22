import unittest,tempfile,sys,json,os
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,lab_service as lab,chat_service as chat

FEEDBACK={'strength':'Clear.','priorities':[{'issue':'Politeness','evidence':'give me','suggestion':'Try could you ...'}],'revision':'Could you give me a room?','next_question':'Anything else?'}

class QuotaTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'quota.db');self.p.start();app.init();self.c=app.db()
  for name,admin in [('learner',0),('other',0),('teacher',1)]:self.c.execute('INSERT INTO users(username,password,admin) VALUES(?,?,?)',(name,'hash',admin))
  self.c.commit()
  self.env=patch.dict(os.environ,{'FLOW_AI_PROVIDER':'openai','FLOW_AI_KEY':'fake-test-key','FLOW_AI_MODEL':'test-model','FLOW_AI_DAILY_LIMIT':'0','FLOW_AI_USER_DAILY_LIMIT':'2'});self.env.start()
  self.model=patch.object(lab,'request_model',return_value=(json.dumps(FEEDBACK),'stop'));self.called=self.model.start()
 def tearDown(self):self.model.stop();self.c.close();self.env.stop();self.p.stop();self.tmp.cleanup()
 def feedback(self,uid,n):return lab.post(self.c,uid,'/api/lab/feedback',{'pack':'travel-a2','skill':'writing','answer':'give me a room','request_id':f'quota-{uid}-{n:04d}'})

 def test_per_account_ceiling_blocks_before_calling_the_model(self):
  first,s1=self.feedback(1,1);second,s2=self.feedback(1,2)
  self.assertEqual((s1,s2),(200,200));self.assertEqual((first['remaining'],second['remaining']),(1,0))
  out,status=self.feedback(1,3)
  self.assertEqual(status,429);self.assertIn('2 次',out['error']);self.assertEqual(out['remaining'],0)
  self.assertEqual(self.called.call_count,2)
  self.assertEqual(self.c.execute('SELECT SUM(count) FROM ai_usage WHERE user_id=1').fetchone()[0],2)

 def test_ceiling_is_per_account_and_admins_are_exempt(self):
  for n in range(2):self.feedback(1,n)
  self.assertEqual(self.feedback(2,1)[1],200)
  for n in range(4):self.assertEqual(self.feedback(3,n)[1],200)
  self.assertIsNone(chat.remaining(self.c,3))

 def test_replaying_a_finished_request_is_free(self):
  self.feedback(1,1);self.feedback(1,2)
  out,status=self.feedback(1,1)
  self.assertEqual(status,200);self.assertEqual(self.called.call_count,2)

 def test_site_ceiling_still_applies_and_zero_disables_both(self):
  with patch.dict(os.environ,{'FLOW_AI_DAILY_LIMIT':'1','FLOW_AI_USER_DAILY_LIMIT':'0'}):
   self.assertEqual(self.feedback(1,1)[1],200);out,status=self.feedback(2,1)
   self.assertEqual(status,429);self.assertIn('本站',out['error'])
  with patch.dict(os.environ,{'FLOW_AI_DAILY_LIMIT':'0','FLOW_AI_USER_DAILY_LIMIT':'0'}):
   for n in range(2,6):self.assertEqual(self.feedback(1,n)[1],200)
   self.assertIsNone(chat.remaining(self.c,1))

 def test_bad_values_fall_back_to_no_ceiling(self):
  with patch.dict(os.environ,{'FLOW_AI_USER_DAILY_LIMIT':'lots'}):self.assertIsNone(chat.remaining(self.c,1))
  with patch.dict(os.environ,{'FLOW_AI_USER_DAILY_LIMIT':'-5'}):self.assertIsNone(chat.remaining(self.c,1))

 def test_tutor_chat_shares_the_same_account_ceiling(self):
  for n in range(2):self.feedback(1,n)
  with patch('chat_service.request_model',return_value=('Hi','stop')) as model:
   out,status=chat.chat(self.c,1,{'topic':self.c.execute('SELECT id FROM topics LIMIT 1').fetchone()[0],'message':'What is a gerund?','request_id':'quota-chat-0001'})
  self.assertEqual(status,429);model.assert_not_called()

if __name__=='__main__':unittest.main()
