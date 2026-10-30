import unittest,tempfile,sys,time,json,os,base64,sqlite3,io
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,lab_service as lab,chat_service as chat,studio_setup
from audio_validation import validate_audio
from content_v06 import material,PACKS
FEEDBACK={'strength':'You made your request clear.','priorities':[{'issue':'Use a polite request','evidence':'give me','suggestion':'Try could you ...'}],'revision':'Could you tell me when breakfast starts?','next_question':'What else would you like to ask?'}
class LabTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'lab.db');self.p.start();app.init();self.c=app.db()
  for name in ['learner','other']:self.c.execute('INSERT INTO users(username,password) VALUES(?,?)',(name,'hash'))
  self.c.commit();self.env=patch.dict(os.environ,{'FLOW_AI_PROVIDER':'openai','FLOW_AI_KEY':'fake-test-key','FLOW_AI_MODEL':'test-model','FLOW_AI_DAILY_LIMIT':'100','FLOW_AI_AUDIO':'1'});self.env.start()
 def tearDown(self):self.c.close();self.env.stop();self.p.stop();self.tmp.cleanup()
 def post(self,path,data,uid=1):return lab.post(self.c,uid,'/api/lab/'+path,data)
 def get(self,path='',query=None,uid=1):return lab.get(self.c,uid,'/api/lab'+path,query or {})
 def feedback(self,**extra):return {'pack':'travel-a2','skill':'speaking','answer':'give me a room','request_id':'lab-feedback-001',**extra}
 def test_original_materials_and_answer_hiding(self):
  d,status=self.get();self.assertEqual(status,200);self.assertEqual(len(d['packs']),154)
  for row in PACKS:
   p=material(row);lab.validate_pack(p)
   for q in p['questions']:self.assertIn(q['evidence'],p['body'])
   d,status=self.get('/pack',{'id':[p['id']]});self.assertEqual(status,200)
   self.assertNotIn('answer',d['pack']['questions'][0]);self.assertTrue(d['pack']['sentences'])
  self.assertEqual(self.post('profile',{'level':'B2','theme':'travel','focus':'writing'})[1],200)
  self.assertEqual(self.get()[0]['profile']['level'],'B2')
 def test_comprehension_dictation_and_request_replay(self):
  p=lab.pack_for(self.c,1,'travel-a2');data={'pack':p['id'],'skill':'reading','choices':[q['answer'] for q in p['questions']],'save_id':'lab-reading-001'}
  a,status=self.post('comprehension',data);self.assertEqual(status,200);self.assertTrue(all(q['correct'] for q in a['details']['results']))
  b,status=self.post('comprehension',data);self.assertEqual(a,b)
  self.assertEqual(self.post('comprehension',{**data,'choices':[0,0]})[1],409)
  target=lab.sentences(p['body'])[p['dictation_index']]
  d,status=self.post('dictation',{'pack':p['id'],'skill':'listening','answer':target.upper(),'save_id':'lab-listening-001'});self.assertEqual(status,200);self.assertEqual(d['details']['accuracy'],100)
  self.assertIn('不代表听力',d['details']['note'])
  self.assertEqual(self.get('/history',uid=2)[0]['items'],[])
 def test_draft_feedback_idempotence_and_versions(self):
  d=self.feedback();self.post('draft',{'pack':d['pack'],'skill':d['skill'],'answer':d['answer']})
  self.assertEqual(self.get('/pack',{'id':[d['pack']]})[0]['drafts'][0]['answer'],d['answer'])
  self.assertEqual(self.get('/pack',{'id':[d['pack']]},uid=2)[0]['drafts'],[])
  with patch.object(lab,'request_model',return_value=(json.dumps(FEEDBACK),'stop')) as model:
   out,status=self.post('feedback',d);self.assertEqual(status,200)
   self.assertEqual(self.post('feedback',d)[0],out);self.assertEqual(model.call_count,1)
  saved,status=self.post('save',{'pack':d['pack'],'skill':d['skill'],'answer':d['answer'],'feedback_request':d['request_id'],'save_id':'lab-save-original'});self.assertEqual(status,200)
  with self.assertRaises(ValueError):self.post('save',{'pack':d['pack'],'skill':d['skill'],'answer':'changed','feedback_request':d['request_id'],'save_id':'lab-save-bad-001'})
  revised,status=self.post('save',{'pack':d['pack'],'skill':d['skill'],'answer':'Could you give me a room?','parent':saved['id'],'save_id':'lab-save-revision'});self.assertEqual(status,200)
  self.assertEqual(self.get('/history')[0]['report']['revisions'],1)
  with self.assertRaises(ValueError):self.post('save',{'pack':d['pack'],'skill':d['skill'],'answer':'other','parent':saved['id'],'save_id':'lab-save-cross-01'},uid=2)
 def test_private_generation_and_history_redaction(self):
  raw=material(PACKS[0]);data={'level':'A2','theme':'campus','request_id':'lab-generated-001'}
  with patch.object(lab,'request_model',return_value=(json.dumps(raw),'stop')) as model:
   out,status=self.post('generate',data);self.assertEqual(status,200);self.assertNotIn('answer',out['result']['questions'][0]);pid=out['result']['id']
   self.assertEqual(self.post('generate',data)[0]['result']['id'],pid);self.assertEqual(model.call_count,1)
  self.assertNotIn(pid,[p['id'] for p in self.get(uid=2)[0]['packs']])
  with self.assertRaises(ValueError):self.get('/pack',{'id':[pid]},uid=2)
  self.assertNotIn('answer',self.get('/history')[0]['jobs'][0]['result']['questions'][0])
 def test_shared_quota_pending_failure_and_retry(self):
  d=self.feedback();day=time.strftime('%Y-%m-%d',time.gmtime());self.c.execute('INSERT INTO ai_usage VALUES(?,?,100)',(1,day));self.c.commit()
  with patch.object(lab,'request_model') as model:self.assertEqual(self.post('feedback',d)[1],429);model.assert_not_called()
  self.c.execute('UPDATE ai_usage SET count=0');self.c.commit()
  with patch.object(lab,'request_model',return_value=('not-json','stop')):self.assertEqual(self.post('feedback',d)[1],502)
  self.assertEqual(self.get('/history')[0]['jobs'][0]['status'],'failed')
  with patch.object(lab,'request_model',return_value=(json.dumps(FEEDBACK),'stop')):self.assertEqual(self.post('feedback',d)[1],200)
  self.assertIsNone(chat.remaining(self.c,1))
  self.c.execute("UPDATE lab_jobs SET status='pending',updated=?",(time.time(),));self.c.commit()
  with patch.object(chat,'request_model') as model:
   self.assertEqual(chat.chat(self.c,1,{'topic':'tense','message':'hello','request_id':'chat-during-lab-01'})[1],409);model.assert_not_called()
  with patch.dict(os.environ,{'FLOW_AI_KEY':''}):self.assertEqual(self.post('feedback',self.feedback(request_id='lab-offline-0001'))[1],503)
 def test_audio_in_memory_and_binding(self):
  audio={'mime_type':'audio/webm','data':base64.b64encode(b'\x1aE\xdf\xa3'+b'x'*40).decode()};result={**FEEDBACK,'transcript':'Could you tell me when breakfast starts?'}
  with patch.object(lab,'request_model',return_value=(json.dumps(result),'stop')) as model:
   out,status=self.post('audio',self.feedback(audio=audio));self.assertEqual(status,200);self.assertEqual(model.call_args.kwargs['audio'],audio)
  row=dict(self.c.execute('SELECT * FROM lab_jobs').fetchone());self.assertNotIn(audio['data'],json.dumps(row))
  self.assertEqual(self.post('save',{'pack':'travel-a2','skill':'speaking','answer':result['transcript'],'feedback_request':'lab-feedback-001','save_id':'lab-audio-save-001'})[1],200)
  for bad in [{'mime_type':'audio/wav','data':audio['data']},{'mime_type':'audio/webm','data':'!'*24},{'mime_type':'audio/webm','data':'x'*2000004}]:
   with self.assertRaises(ValueError):validate_audio(bad)
  with patch.dict(os.environ,{'FLOW_AI_AUDIO':'0'}):self.assertEqual(self.post('audio',self.feedback(audio=audio,request_id='audio-offline-01'))[1],503)
 def test_word_review_ownership_and_early_repetition(self):
  item={'term':'reliable','meaning':'可靠的','example':'A reliable plan helps.'};self.assertEqual(self.post('word',item)[1],200)
  self.post('word',item);words=self.get('/words')[0]['items'];self.assertEqual(len(words),1);word=words[0]
  self.assertEqual(self.post('word/review',{'id':word['id'],'rating':'remembered'},uid=2)[1],404)
  self.post('word/review',{'id':word['id'],'rating':'remembered'});self.assertEqual(self.get('/words')[0]['items'][0]['stage'],0)
  self.c.execute('UPDATE wordbook SET due=0');self.c.commit();self.post('word/review',{'id':word['id'],'rating':'remembered'});self.assertEqual(self.get('/words')[0]['items'][0]['stage'],1)
  self.post('word/review',{'id':word['id'],'rating':'again'});self.assertEqual(self.get('/words')[0]['items'][0]['stage'],0)
 def test_proxy_configuration_scope(self):
  source='server { server_name flowlang.cn www.flowlang.cn; location / { proxy_pass http://127.0.0.1:8090; } }'
  modified=studio_setup.update_vhost(source);self.assertIn(str(studio_setup.EXTENSION),modified);self.assertEqual(studio_setup.update_vhost(modified),modified)
  self.assertIn('proxy_request_buffering off;',studio_setup.ROUTE);self.assertIn('client_body_buffer_size 3m;',studio_setup.ROUTE)
  with self.assertRaises(ValueError):studio_setup.update_vhost(source.replace('flowlang.cn','other.example'))
if __name__=='__main__':unittest.main()
