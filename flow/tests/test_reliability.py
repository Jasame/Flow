import unittest,tempfile,sys,json,time,threading,os,base64,io
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,ai_jobs,ai_stream,ai_help_service as help_service,lab_service as lab,coach_service as coach,learning_insights as insights,chat_service
from test_ai_stream import Reply

class ReliabilityTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'test.db');self.p.start();app.init();self.c=app.db()
  self.c.executemany('INSERT INTO users(username,password) VALUES(?,?)',[('one','hash'),('two','hash')]);self.c.commit()
 def tearDown(self):self.c.close();self.p.stop();self.tmp.cleanup()
 def profile(self):
  self.c.execute('INSERT INTO coach_profiles VALUES(?,?,?,?,?,?,?)',(1,'工作邮件','旅行',10,json.dumps({'band':'A2','scores':{},'label':'建议起步'}),time.time(),time.time()));self.c.commit()
 def test_fifo_queue_has_no_cross_user_blocking(self):
  first=ai_jobs.enter(8001);other=ai_jobs.enter(8002);order=[]
  def worker(label):
   ticket=ai_jobs.enter(8001);order.append(label);ai_jobs.leave(ticket)
  a=threading.Thread(target=worker,args=('a',));b=threading.Thread(target=worker,args=('b',));a.start()
  until=time.monotonic()+2
  while len(ai_jobs.QUEUES[8001])<2 and time.monotonic()<until:time.sleep(.005)
  b.start()
  while len(ai_jobs.QUEUES[8001])<3 and time.monotonic()<until:time.sleep(.005)
  ai_jobs.leave(first);ai_jobs.leave(other);a.join(2);b.join(2)
  self.assertEqual(order,['a','b']);self.assertNotIn(8001,ai_jobs.QUEUES)
 def test_queue_timeout_cleans_its_ticket(self):
  handle=ai_jobs.enter(8003)
  try:
   with self.assertRaises(TimeoutError):ai_jobs.enter(8003,timeout=.02)
   self.assertEqual(len(ai_jobs.QUEUES[8003]),1)
  finally:ai_jobs.leave(handle)
 def test_lease_fences_stale_result(self):
  def invoke():
   self.c.execute("UPDATE lab_jobs SET lease='replacement' WHERE request_id='lease-fence-0001'");self.c.commit();return '{"reply":"old"}','stop'
  with patch.object(lab,'ai_enabled',return_value=True):out,status=lab.run_job(self.c,1,'lease-fence-0001','test','','',{},invoke,lambda x:x)
  self.assertEqual(status,409);self.assertEqual(self.c.execute("SELECT result FROM lab_jobs WHERE request_id='lease-fence-0001'").fetchone()[0],'')
 def test_lease_renews_only_matching_attempt(self):
  self.c.execute("INSERT INTO lab_jobs(user_id,request_id,status,updated,lease) VALUES(1,'lease-renew-0001','pending',0,'mine')");self.c.commit()
  with ai_jobs.renewing(self.c,'lab_jobs',1,'lease-renew-0001','mine',interval=.01):
   until=time.monotonic()+1
   while self.c.execute("SELECT updated FROM lab_jobs WHERE request_id='lease-renew-0001'").fetchone()[0]==0 and time.monotonic()<until:time.sleep(.01)
  self.assertGreater(self.c.execute("SELECT updated FROM lab_jobs WHERE request_id='lease-renew-0001'").fetchone()[0],0)
 def test_failed_hint_does_not_mark_support_and_context_is_specific(self):
  self.profile();pack=lab.pack_for(self.c,1,'campus-a2');selected=pack['body'].split('.')[0]
  data={'kind':'material','target':'campus-a2','skill':'writing','question':'这个短句怎么表达？','selected':selected,'answer':'I like a book.','request_id':'hint-failure-0001'}
  with patch.object(lab,'ai_enabled',return_value=True),patch.object(help_service,'request_model',side_effect=TimeoutError()) as model:
   out,status=help_service.help(self.c,1,data)
  self.assertEqual(status,504);self.assertIsNone(self.c.execute('SELECT * FROM studio_support').fetchone())
  sent=json.loads(model.call_args.args[0][1]['content']);self.assertEqual(sent['answer'],'I like a book.');self.assertEqual(sent['learner']['goal'],'工作邮件');self.assertEqual(sent['selected'],selected)
  with self.assertRaises(ValueError):help_service.help(self.c,1,dict(data,selected='not in this material'))
 def test_delivered_partial_hint_marks_support_even_if_json_later_invalid(self):
  def invoke(messages):ai_stream.emit({'type':'preview','text':'试着先想主语。'});return 'bad json','stop'
  with patch.object(lab,'ai_enabled',return_value=True),patch.object(help_service,'request_model',side_effect=invoke),ai_stream.observe(lambda e:None):
   out,status=help_service.help(self.c,1,{'kind':'material','target':'campus-a2','skill':'reading','request_id':'hint-partial-0001'})
  self.assertEqual(status,502);self.assertEqual(self.c.execute('SELECT assisted FROM studio_support').fetchone()[0],1)
 def test_progressive_priorities_hide_answers_and_memories(self):
  raw='{"strength":"Good","priorities":[{"issue":"Verb","evidence":"I goes","suggestion":"Use go'
  visible=ai_stream.preview(raw);self.assertIn('Verb',visible);self.assertIn('Use go',visible)
  self.assertNotIn('SECRET',ai_stream.preview('{"memory_updates":[{"suggestion":"SECRET"}],"questions":[{"answer":"SECRET"}]}'))
 def test_pinned_old_memory_survives_newer_memories_and_context_pruning(self):
  self.profile()
  for i in range(16):self.c.execute('INSERT INTO coach_memories(user_id,kind,text,evidence,pinned,created) VALUES(1,?,?,?,?,?)',('preference','旧偏好-'+str(i),'用户原文',int(i==0),time.time()))
  self.c.commit();memories=coach.select_memories(self.c,1,'继续学习');self.assertEqual(memories[0]['text'],'旧偏好-0')
  context=coach.prompt_context(self.c,1,'请继续');self.assertIn('旧偏好-0',context[0]['content']);self.assertLess(sum(len(m['content']) for m in context),8000)
  old=memories[0]['id']
  with self.assertRaises(ValueError):coach.post(self.c,2,'/api/coach/memory/pin',{'id':old,'pinned':False})
 def test_five_word_chat_does_not_complete_writing_mission(self):
  self.profile();self.c.execute("INSERT INTO coach_missions(id,user_id,chapter,skill,title,instruction,pack,minutes,created) VALUES('writing-m',1,1,'writing','写工作邮件','Write a polite work request.','campus-a2',5,?)",(time.time(),));self.c.commit()
  raw={'reply':'请写出自己的请求。','turn_summary':'讨论任务','memory_updates':[],'observations':[],'missions':[]}
  with patch.object(lab,'ai_enabled',return_value=True),patch('chat_service.request_model',return_value=(json.dumps(raw),'stop')):
   out,status=coach.chat(self.c,1,{'message':'one two three four five six','request_id':'writing-chat-0001','mission':'writing-m'})
  self.assertEqual(status,200);self.assertEqual(self.c.execute("SELECT status FROM coach_missions WHERE id='writing-m'").fetchone()[0],'active')
 def test_calibration_requires_distinct_learners_and_is_not_ai_grading(self):
  from event_service import record
  for i in range(1,22):
   if i>2:self.c.execute('INSERT INTO users(id,username,password) VALUES(?,?,?)',(i,'u'+str(i),'hash'))
   record(self.c,i,'skill:reading','calibration-'+str(i),'comprehension','campus-a2','campus-a2',i%2,False,'rule')
  self.c.commit();stats=insights.material(self.c,1,'campus-a2');self.assertTrue(stats['calibrated']);self.assertEqual(stats['learners'],21);self.assertNotIn('user_id',stats)
  self.assertEqual(insights.expression(self.c,2)['writing']['works'],0)
 def test_vertex_audio_uses_native_inline_data_and_adc_token(self):
  audio={'mime_type':'audio/webm','data':base64.b64encode(b'\x1aE\xdf\xa3'+b'x'*40).decode()}
  payload={'candidates':[{'content':{'parts':[{'text':'Hello'}]},'finishReason':'STOP'}]}
  with patch.dict(os.environ,{'FLOW_AI_PROVIDER':'vertex','FLOW_AI_MODEL':'google/test-model','GOOGLE_CLOUD_PROJECT':'test-project'}),patch.object(chat_service,'vertex_connection',return_value=('https://not-used.invalid','private-token')),patch('vertex_native.urllib.request.urlopen',return_value=io.BytesIO(json.dumps(payload).encode())) as request:
   out=chat_service.request_model([{'role':'user','content':'Transcribe'}],audio=audio)
  self.assertEqual(out,('Hello','stop'));req=request.call_args.args[0];self.assertIn('/publishers/google/models/test-model:generateContent',req.full_url);self.assertEqual(json.loads(req.data)['contents'][0]['parts'][1]['inlineData']['data'],audio['data'])
 def test_config_error_is_actionable_not_output_format_failure(self):
  from vertex_auth import AIConfigurationError
  with patch.object(lab,'ai_enabled',return_value=True):out,status=lab.run_job(self.c,1,'configuration-error-01','test','','',{},lambda:(_ for _ in ()).throw(AIConfigurationError()),lambda x:x)
  self.assertEqual(status,503);self.assertIn('配置',out['error']);self.assertNotIn('输出不完整',out['error'])
 def test_task_review_rejects_invented_quote_and_disputes_are_owner_scoped(self):
  raw={'strength':'Clear','priorities':[],'revision':'I like books.','next_question':'Why?','links':[],'task_check':{'on_task':True,'evidence':'invented quotation','reason':'判断'}}
  data={'pack':'campus-a2','skill':'writing','answer':'I like books.','request_id':'quoted-review-0001'}
  with patch.object(lab,'ai_enabled',return_value=True),patch.object(lab,'request_model',return_value=(json.dumps(raw),'stop')):
   out,status=lab.feedback(self.c,1,data)
  self.assertEqual(status,502)
  raw['task_check']['evidence']='I like books.'
  with patch.object(lab,'ai_enabled',return_value=True),patch.object(lab,'request_model',return_value=(json.dumps(raw),'stop')):
   out,status=lab.feedback(self.c,1,data)
  self.assertEqual(status,200)
  with self.assertRaises(ValueError):lab.post(self.c,2,'/api/lab/feedback/dispute',{'request_id':data['request_id'],'correction':'我不是这个意思'})
  self.assertEqual(lab.post(self.c,1,'/api/lab/feedback/dispute',{'request_id':data['request_id'],'correction':'我不是这个意思'})[1],200)
  self.assertEqual(self.c.execute("SELECT kind FROM teaching_corrections WHERE user_id=1").fetchone()[0],'feedback')
 def test_cancelled_queued_request_never_gets_a_model_turn(self):
  with self.assertRaises(ConnectionAbortedError):ai_jobs.enter(8004,cancelled=lambda:True)
  self.assertNotIn(8004,ai_jobs.QUEUES)
 def test_vertex_audio_stream_stops_on_finish_and_never_emits_thoughts(self):
  audio={'mime_type':'audio/webm','data':base64.b64encode(b'\x1aE\xdf\xa3'+b'x'*40).decode()}
  class Stream(Reply):
   def __iter__(self):
    yield ('data: '+json.dumps({'candidates':[{'content':{'parts':[{'text':'SECRET','thought':True},{'text':'{"reply":"Hello"}'}]},'finishReason':'STOP'}]})+'\n').encode();yield b'\n'
    raise AssertionError('Must stop at terminal candidate, not wait for EOF')
  events=[]
  with patch.dict(os.environ,{'FLOW_AI_PROVIDER':'vertex','FLOW_AI_MODEL':'google/test-model','GOOGLE_CLOUD_PROJECT':'test-project','FLOW_AI_AUDIO':'1'}),patch.object(chat_service,'vertex_connection',return_value=('https://not-used.invalid','private-token')),patch('vertex_native.urllib.request.urlopen',return_value=Stream(b'')),ai_stream.observe(events.append):
   out=chat_service.request_model([{'role':'user','content':'Transcribe'}],audio=audio);self.assertTrue(lab.audio_enabled())
  self.assertEqual(out,('{"reply":"Hello"}','stop'));self.assertNotIn('SECRET',str(events))
 def test_restart_clears_orphan_pending_and_fences_previous_attempt(self):
  self.c.execute("INSERT INTO lab_jobs(user_id,request_id,status,lease) VALUES(1,'restart-request-01','pending','old')")
  self.c.commit();ai_jobs.recover_interrupted(self.c)
  row=self.c.execute("SELECT status,lease,error FROM lab_jobs WHERE request_id='restart-request-01'").fetchone()
  self.assertEqual(row['status'],'failed');self.assertNotEqual(row['lease'],'old');self.assertIn('重试同一次',row['error'])

if __name__=='__main__':unittest.main()
