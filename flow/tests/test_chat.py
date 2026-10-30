import unittest,tempfile,sys,os,time,json,urllib.error,io
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,chat_service as chat
class ChatTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.dbpatch=patch.object(app,'DB',Path(self.tmp.name)/'flow.sqlite3');self.dbpatch.start();app.init();self.c=app.db()
  self.c.execute("INSERT INTO users(username,password) VALUES('learner','hash')");self.c.execute("INSERT INTO users(username,password) VALUES('other','hash')");self.c.commit()
  self.env=patch.dict(os.environ,{'FLOW_AI_PROVIDER':'openai','FLOW_AI_KEY':'fake-private-key','FLOW_AI_MODEL':'test-model','FLOW_AI_DAILY_LIMIT':'100'});self.env.start()
 def tearDown(self):self.c.close();self.env.stop();self.dbpatch.stop();self.tmp.cleanup()
 def data(self,rid='request-0000000001',**extra):return {'message':'如何判断现在完成时？','topic':'tense','request_id':rid,**extra}
 def test_context_persistence_isolation_and_idempotency(self):
  with patch.object(chat,'request_model',return_value=('**第一条回答**','length')) as invoke:
   result,status=chat.chat(self.c,1,self.data());self.assertEqual(status,200);self.assertTrue(result['truncated']);self.assertIsNone(result['remaining'])
   again,status=chat.chat(self.c,1,self.data());self.assertEqual(status,200);self.assertEqual(again['reply'],result['reply']);self.assertEqual(invoke.call_count,1)
  with patch.object(chat,'request_model',return_value=('第二条回答','stop')) as invoke:
   result,status=chat.chat(self.c,1,self.data('request-0000000002',message='请继续'))
   self.assertEqual(status,200);messages=invoke.call_args[0][0];self.assertEqual(messages[-2]['role'],'assistant');self.assertEqual(messages[-2]['content'],'**第一条回答**')
  self.assertEqual(len(chat.history(self.c,1,'tense')[0]['items']),2)
  self.assertEqual(chat.history(self.c,2,'tense')[0]['items'],[])
  self.assertEqual(chat.history(self.c,1,'clause')[0]['items'],[])
 def test_failure_retry_and_pending_protection(self):
  with patch.object(chat,'request_model',side_effect=TimeoutError()):r,status=chat.chat(self.c,1,self.data())
  self.assertEqual(status,504);self.assertEqual(chat.history(self.c,1,'tense')[0]['items'][0]['status'],'failed')
  with patch.object(chat,'request_model',return_value=('重试成功','stop')):r,status=chat.chat(self.c,1,self.data())
  self.assertEqual(status,200);self.assertEqual(len(chat.history(self.c,1,'tense')[0]['items']),1)
  self.c.execute("UPDATE chat_turns SET status='pending',updated=?",(time.time(),));self.c.commit()
  with patch.object(chat,'request_model') as invoke:
   self.assertEqual(chat.chat(self.c,1,self.data())[1],409)
   self.assertEqual(chat.chat(self.c,1,self.data('request-0000000003'))[1],409);invoke.assert_not_called()
 def test_quota_validation_and_offline(self):
  self.assertEqual(chat.chat(self.c,1,self.data(message='x'*1001))[1],400)
  day=time.strftime('%Y-%m-%d',time.gmtime());self.c.execute('INSERT INTO ai_usage VALUES(?,?,20)',(1,day));self.c.commit()
  with patch.object(chat,'request_model',return_value=('不设个人上限','stop')) as invoke:self.assertEqual(chat.chat(self.c,1,self.data())[1],200);self.assertEqual(invoke.call_count,1)
  with patch.dict(os.environ,{'FLOW_AI_KEY':''}):
   r,status=chat.chat(self.c,1,self.data('offline-request-0001'));self.assertEqual(status,200);self.assertEqual(r['mode'],'lesson')
 def test_unicode_wire_and_long_context(self):
  now=time.time()
  self.c.execute("INSERT INTO chat_turns(user_id,topic,request_id,message,reply,status,created,updated) VALUES(1,'tense','long-request-0001','用中文解释',?,'complete',?,?)",('中'*6000,now,now));self.c.commit()
  topic=self.c.execute("SELECT * FROM topics WHERE id='tense'").fetchone()
  messages=chat.context(self.c,1,topic,'再举一个例子')
  self.assertTrue(any(m['role']=='assistant' for m in messages))
  self.assertLess(len(json.dumps({'model':'test','messages':messages,'max_tokens':4096},ensure_ascii=False).encode()),24000)
  class Reply(io.BytesIO):
   def __enter__(self):return self
   def __exit__(self,*args):self.close()
  data={'choices':[{'message':{'content':'完整回答'},'finish_reason':'stop'}]}
  with patch.dict(os.environ,{'FLOW_AI_URL':'https://ai.flowlang.cn/v1/chat/completions'}),patch.object(chat.urllib.request,'urlopen',return_value=Reply(json.dumps(data).encode())) as call:
   self.assertEqual(chat.request_model(messages)[0],'完整回答')
   self.assertIn('再举一个例子',call.call_args[0][0].data.decode())
 def test_stale_requests_can_retry(self):
  self.c.execute("INSERT INTO chat_turns(user_id,topic,request_id,message,status,created,updated) VALUES(1,'tense',?,?,'pending',0,0)",('request-0000000001',self.data()['message']));self.c.commit()
  self.assertEqual(chat.history(self.c,1,'tense')[0]['items'][0]['status'],'failed')
  with patch.object(chat,'request_model',return_value=('恢复成功','stop')):self.assertEqual(chat.chat(self.c,1,self.data())[1],200)
