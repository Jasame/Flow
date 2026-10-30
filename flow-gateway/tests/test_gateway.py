import unittest,tempfile,sys,base64,threading,urllib.request,urllib.error,json,io,concurrent.futures
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import gateway as g
from nginx_update import update as update_nginx
class GatewayTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory()
  self.env=patch.multiple(g,PROJECT='test-project',MODEL='test-model',SECRET='s'*64,DATA=Path(self.tmp.name),LIMIT=3)
  self.env.start();g.init()
 def tearDown(self):self.env.stop();self.tmp.cleanup()
 def test_validation_and_limits(self):
  d={'model':'test-model','messages':[{'role':'system','content':'Teach English'},{'role':'user','content':'Hello'}],'max_tokens':2048}
  p=g.prepare(d);self.assertEqual(p['generationConfig']['maxOutputTokens'],2048)
  self.assertEqual(p['systemInstruction']['parts'][0]['text'],'Teach English')
  for wrong in [dict(d,model='other-model'),dict(d,stream="true"),dict(d,messages=[{'role':'tool','content':'no'}]),dict(d,messages=[{'role':'user','content':'x'*8001}])]:
   with self.assertRaises(ValueError):g.prepare(wrong)
 def test_grounding_is_opt_in_and_metadata_is_preserved(self):
  data={'model':'test-model','messages':[{'role':'user','content':'Recent science'}],'flow_grounding':True}
  payload=g.prepare(data);self.assertEqual(payload['tools'],[{'googleSearch':{}}])
  self.assertNotIn('tools',g.prepare(dict(data,flow_grounding=False)))
  with self.assertRaises(ValueError):g.prepare(dict(data,flow_grounding='true'))
  class Reply(io.BytesIO):
   def __enter__(self):return self
   def __exit__(self,*a):self.close()
  metadata={'groundingChunks':[{'web':{'uri':'https://example.org','title':'Source'}}],'searchEntryPoint':{'renderedContent':'<a>Google</a>'}}
  result={'candidates':[{'finishReason':'STOP','content':{'parts':[{'text':'A recent report.'}]},'groundingMetadata':metadata}]}
  with patch.object(g,'access_token',return_value='private-token'),patch.object(g.urllib.request,'urlopen',return_value=Reply(json.dumps(result).encode())):
   response=g.invoke(payload)
  self.assertEqual(response['flow_grounding'],metadata);self.assertEqual(response['flow_gateway_version'],'2.2')
 def test_quota_is_atomic_and_persistent(self):
  with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:r=list(pool.map(lambda _:g.reserve(),range(12)))
  self.assertEqual(sum(r),3);g.init();self.assertFalse(g.reserve())
 def test_zero_daily_limit_keeps_usage_without_an_application_ceiling(self):
  with patch.object(g,'LIMIT',0):
   for _ in range(105):self.assertTrue(g.reserve())
  with g.sqlite3.connect(g.DATA/'usage.sqlite3') as c:self.assertEqual(c.execute('SELECT count FROM daily').fetchone()[0],105)
 def test_http_auth_and_openai_contract(self):
  server=g.ThreadingHTTPServer(('127.0.0.1',0),g.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  base='http://127.0.0.1:'+str(server.server_port)
  def request(data=None,key=None,path='/v1/chat/completions'):
   req=urllib.request.Request(base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**({'Authorization':'Bearer '+key} if key else {})})
   try:
    with urllib.request.urlopen(req,timeout=2) as r:return r.status,json.load(r)
   except urllib.error.HTTPError as e:return e.code,json.load(e)
  try:
   with patch.object(g,'invoke',return_value={'choices':[{'message':{'content':'Hello'}}]}) as invoke:
    payload={'model':'test-model','messages':[{'role':'user','content':'Hi'}]}
    self.assertEqual(request(path='/health')[0],200)
    self.assertEqual(request(payload)[0],401);invoke.assert_not_called()
    status,body=request(payload,key='s'*64);self.assertEqual(status,200);self.assertEqual(body['choices'][0]['message']['content'],'Hello')
    self.assertEqual(request(dict(payload,model='other'),key='s'*64)[0],400)
  finally:server.shutdown();server.server_close();thread.join()
 def test_finish_reason_and_thought_filtering(self):
  class Reply(io.BytesIO):
   def __enter__(self):return self
   def __exit__(self,*args):self.close()
  result={'candidates':[{'finishReason':'MAX_TOKENS','content':{'parts':[{'text':'private reasoning','thought':True},{'text':'visible answer'}]}}]}
  with patch.object(g,'access_token',return_value='private-token'),patch.object(g.urllib.request,'urlopen',return_value=Reply(json.dumps(result).encode())):
   response=g.invoke({});self.assertEqual(response['choices'][0]['finish_reason'],'length');self.assertEqual(response['choices'][0]['message']['content'],'visible answer');self.assertNotIn('private',json.dumps(response))
 def test_metadata_cache(self):
  g.TOKEN.update(value=None,until=0)
  class Reply(io.BytesIO):
   def __enter__(self):return self
   def __exit__(self,*args):self.close()
  with patch.object(g.NO_PROXY,'open',return_value=Reply(b'{"access_token":"private-test-token","expires_in":3600}')) as open_:
   self.assertEqual(g.access_token(),'private-test-token');self.assertEqual(g.access_token(),'private-test-token');self.assertEqual(open_.call_count,1)
  g.TOKEN.update(value=None,until=0)
 def test_audio_payload_validation_and_forwarding(self):
  encoded=base64.b64encode(b'\x1aE\xdf\xa3'+b'x'*50000).decode()
  data={'model':'test-model','messages':[{'role':'system','content':'Teach English'},{'role':'user','content':'Transcribe this'}],'max_tokens':2048,'flow_audio':{'mime_type':'audio/webm','data':encoded}}
  payload=g.prepare(data);part=payload['contents'][-1]['parts'][-1]
  self.assertEqual(part['inlineData']['mimeType'],'audio/webm');self.assertEqual(part['inlineData']['data'],encoded)
  with self.assertRaises(ValueError):g.prepare({**data,'flow_audio':{'mime_type':'audio/wav','data':encoded}})
  with self.assertRaises(ValueError):g.prepare({**data,'flow_audio':{'mime_type':'audio/webm','data':'!'*20}})
  server=g.ThreadingHTTPServer(('127.0.0.1',0),g.Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with patch.object(g,'invoke',return_value={'choices':[{'message':{'content':'Transcript'}}]}) as invoke:
    req=urllib.request.Request('http://127.0.0.1:'+str(server.server_port)+'/v1/chat/completions',data=json.dumps(data).encode(),headers={'Authorization':'Bearer '+'s'*64,'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=2) as r:self.assertEqual(r.status,200)
    self.assertIn('inlineData',invoke.call_args.args[0]['contents'][-1]['parts'][-1])
  finally:server.shutdown();server.server_close();thread.join()
 def test_nginx_update_retains_security_and_is_idempotent(self):
  source='server { client_max_body_size 24k; location = /v1/chat/completions { allow 121.40.203.104; deny all; limit_req zone=flow_gateway burst=10 nodelay; proxy_pass http://127.0.0.1:8088; proxy_read_timeout 95s; } }'
  updated=update_nginx(source)
  for value in ('allow 121.40.203.104;','deny all;','limit_req','proxy_request_buffering off;','client_body_buffer_size 3m;'):self.assertIn(value,updated)
  self.assertEqual(update_nginx(updated),updated)
  with self.assertRaises(ValueError):update_nginx('server { location / { return 404; } }')
if __name__=='__main__':unittest.main()
