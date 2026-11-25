import unittest,tempfile,sys,json,os,time
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

 def used(self,uid,*days_ago):
  for d in days_ago:self.c.execute('INSERT OR REPLACE INTO ai_usage VALUES(?,?,3)',(uid,time.strftime('%Y-%m-%d',time.gmtime(time.time()-d*86400))))
  self.c.commit()

 def test_site_ceiling_grows_with_learners_who_come_back(self):  # the owner 2026-11-25: 「按照人数动态设置」 → 「两层都做」
  with patch.dict(os.environ,{'FLOW_AI_DAILY_LIMIT':'50'}),patch.object(chat,'SITE_MAX',90):
   self.assertEqual(chat.site_limit(self.c),50)  # nobody yet: the configured value is the floor
   self.used(1,0,1);self.used(2,3,5)  # two learners on two days of the last seven
   self.used(3,0);self.used(4,0)  # one day only (an account opened today): not counted
   self.used(5,8,9)  # older than a week: not counted
   self.assertEqual(chat.regulars(self.c),2);self.assertEqual(chat.site_limit(self.c),80)
   self.used(6,1,2)
   self.assertEqual(chat.site_limit(self.c),90)  # 120, but never above SITE_MAX
  with patch.dict(os.environ,{'FLOW_AI_DAILY_LIMIT':'0'}):self.assertEqual(chat.site_limit(self.c),0)  # 0 = no ceiling, as before
  with patch.dict(os.environ,{'FLOW_AI_DAILY_LIMIT':'50'}),patch('console_ops.limit_override',lambda name:7 if name=='FLOW_AI_DAILY_LIMIT' else None):
   self.assertEqual(chat.site_limit(self.c),7)  # a value set in the console wins as it is
  self.assertEqual((chat.SITE_PER_LEARNER,chat.SITE_MAX),(40,15000))

 def test_the_grown_ceiling_is_the_one_a_call_meets(self):
  self.used(2,1,2)  # one regular: 40 calls today, above the floor of 1
  with patch.dict(os.environ,{'FLOW_AI_DAILY_LIMIT':'1','FLOW_AI_USER_DAILY_LIMIT':'0'}):
   self.assertEqual(self.feedback(1,1)[1],200);self.assertEqual(self.feedback(1,2)[1],200)

 def test_the_day_stop_holds_every_learner_before_calling_the_model(self):  # the owner: 「¥5 提醒，¥10 硬停」
  import ai_routes
  with patch.object(ai_routes,'day_full',lambda c=None,now=None:True):
   out,status=self.feedback(1,1)
   self.assertEqual((status,out.get('code')),(429,'ai_day_full'));self.assertIn('北京时间早上 8 点恢复',out['error'])
   self.assertEqual(self.feedback(3,1)[1],429)  # admins too: it is about money, not one account
  self.assertEqual(self.called.call_count,0)
  self.assertEqual(self.c.execute('SELECT COALESCE(SUM(count),0) FROM ai_usage').fetchone()[0],0)  # nothing counted
  self.assertEqual(self.feedback(1,2)[1],200)

 def test_the_stop_line_its_day_and_what_it_counts(self):
  import ai_routes
  with patch.object(ai_routes,'_settings',lambda:{}):self.assertEqual(ai_routes.stop_line(),10.0)
  with patch.object(ai_routes,'_settings',lambda:{'ai_stop':15}):self.assertEqual(ai_routes.stop_line(),15.0)
  with patch.object(ai_routes,'_settings',lambda:{'ai_stop':0}):
   self.assertEqual(ai_routes.stop_line(),0.0);self.assertFalse(ai_routes.day_full(self.c))
  t=1795600000.0  # 2026-11-25 08:26 UTC
  self.assertEqual(ai_routes.learner_day_start(t),1795564800.0)  # 00:00 UTC = 08:00 Beijing, as the call counts
  ai_routes.schema(self.c)
  rows=[(t-60,200,1),(t-50,200,0),(t-40,500,0),(t-10*3600,200,1)]  # paid, paid but unusable, failed, yesterday's learner day
  for ts,status,ok in rows:
   self.c.execute("INSERT INTO ai_calls(ts,kind,service,model,ok,status) VALUES(?,?,?,?,?,?)",(ts,'next-rewrite','text','m',ok,status))
  self.c.commit()
  with patch.object(ai_routes,'cost',lambda *a:3.0):
   self.assertEqual(ai_routes.spent_since(self.c,ai_routes.learner_day_start(t)),6.0)
   ai_routes._FULL.update(key=None)
   with patch.object(ai_routes,'_settings',lambda:{'ai_stop':6}):self.assertTrue(ai_routes.day_full(self.c,now=t))
   ai_routes._FULL.update(key=None)
   with patch.object(ai_routes,'_settings',lambda:{'ai_stop':7}):self.assertFalse(ai_routes.day_full(self.c,now=t))
  ai_routes._FULL.update(key=None)

if __name__=='__main__':unittest.main()
