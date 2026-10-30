#!/usr/bin/env python3
"""Dedicated Gemini gateway for Flow, behind Nginx. Uses attached GCE identity."""
import os,json,time,hmac,sqlite3,threading,urllib.request,urllib.error,socket,re
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from audio_validation import validate_audio
PROJECT=os.environ.get('GOOGLE_CLOUD_PROJECT','')
MODEL=os.environ.get('GATEWAY_MODEL','gemini-3.8-flash')
SECRET=os.environ.get('GATEWAY_SECRET','')
DATA=Path(os.environ.get('GATEWAY_DATA','/var/lib/flow-gateway'))
LIMIT=int(os.environ.get('GATEWAY_DAILY_LIMIT','0'))
TOKEN_LOCK=threading.Lock();TOKEN={'value':None,'until':0};SLOTS=threading.BoundedSemaphore(2)
NO_PROXY=urllib.request.build_opener(urllib.request.ProxyHandler({}))

def init():
 if len(SECRET)<40:raise RuntimeError('Gateway secret missing or too short')
 if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]',PROJECT):raise RuntimeError('Invalid project ID')
 if not re.fullmatch(r'[a-z0-9.-]+',MODEL):raise RuntimeError('Invalid model ID')
 DATA.mkdir(parents=True,exist_ok=True)
 with sqlite3.connect(DATA/'usage.sqlite3') as c:c.execute('CREATE TABLE IF NOT EXISTS daily(day TEXT PRIMARY KEY,count INTEGER NOT NULL)')

def reserve():
 day=time.strftime('%Y-%m-%d',time.gmtime())
 with sqlite3.connect(DATA/'usage.sqlite3',timeout=10) as c:
  c.execute('BEGIN IMMEDIATE');c.execute('INSERT OR IGNORE INTO daily VALUES(?,0)',(day,))
  if LIMIT>0 and c.execute('SELECT count FROM daily WHERE day=?',(day,)).fetchone()[0]>=LIMIT:return False
  c.execute('UPDATE daily SET count=count+1 WHERE day=?',(day,));return True

def access_token():
 with TOKEN_LOCK:
  if TOKEN['value'] and TOKEN['until']>time.time():return TOKEN['value']
  req=urllib.request.Request('http://169.254.169.254/computeMetadata/v1/instance/service-accounts/default/token',headers={'Metadata-Flavor':'Google'})
  with NO_PROXY.open(req,timeout=10) as r:d=json.load(r)
  TOKEN.update(value=d['access_token'],until=time.time()+max(0,int(d['expires_in'])-60))
  return TOKEN['value']

def prepare(data):
 if not isinstance(data,dict):raise ValueError('JSON object required')
 if 'stream' in data and type(data['stream'])!=bool:raise ValueError('stream must be boolean')
 if data.get('model') not in (MODEL,'google/'+MODEL):raise ValueError('Model does not match gateway configuration')
 messages=data.get('messages')
 if not isinstance(messages,list) or not 1<=len(messages)<=12:raise ValueError('1 to 12 text messages required')
 system=[];contents=[];total=0
 for m in messages:
  if not isinstance(m,dict) or m.get('role') not in ('system','user','assistant') or not isinstance(m.get('content'),str):raise ValueError('Only text system/user/assistant messages supported')
  text=m['content'];total+=len(text)
  if m['role']=='system':system.append(text)
  else:contents.append({'role':'model' if m['role']=='assistant' else 'user','parts':[{'text':text}]})
 if total>8000 or not any(c['role']=='user' for c in contents):raise ValueError('Prompt too long or missing user message')
 n=data.get('max_tokens',1024)
 if type(n)!=int or not 1<=n<=4096:raise ValueError('max_tokens must be an integer between 1 and 4096')
 payload={'contents':contents,'generationConfig':{'maxOutputTokens':min(n,4096)}}
 if data.get('flow_audio') is not None:
  audio=data['flow_audio'];validate_audio(audio)
  user_parts=next(c['parts'] for c in reversed(contents) if c['role']=='user')
  user_parts.append({'inlineData':{'mimeType':audio['mime_type'],'data':audio['data']}})
 if data.get('flow_grounding') is not None:
  if type(data['flow_grounding'])!=bool or data.get('flow_audio'):raise ValueError('Invalid grounding request')
  if data['flow_grounding']:payload['tools']=[{'googleSearch':{}}]
 if system:payload['systemInstruction']={'parts':[{'text':'\n\n'.join(system)}]}
 return payload

def invoke(payload):
 url=f'https://aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/global/publishers/google/models/{MODEL}:generateContent'
 req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+access_token(),'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=65) as r:d=json.load(r)
 candidates=d.get('candidates',[])
 candidate=candidates[0] if candidates else {}
 parts=[p['text'] for p in candidate.get('content',{}).get('parts',[]) if p.get('text') and not p.get('thought')]
 if not parts:raise ValueError('Model returned no visible text')
 upstream_reason=candidate.get('finishReason','UNKNOWN')
 reason='length' if upstream_reason=='MAX_TOKENS' else 'content_filter' if upstream_reason in ('SAFETY','RECITATION','PROHIBITED_CONTENT','BLOCKLIST') else 'stop' if upstream_reason=='STOP' else 'unknown'
 result={'id':'flow-'+str(time.time_ns()),'object':'chat.completion','created':int(time.time()),'model':MODEL,'flow_gateway_version':'2.2','upstream_finish_reason':upstream_reason,'choices':[{'index':0,'message':{'role':'assistant','content':'\n'.join(parts)},'finish_reason':reason}]}

 if payload.get('tools'):result['flow_grounding']=candidate.get('groundingMetadata',{})
 return result

def invoke_stream(payload):
 """Forward visible Gemini deltas as OpenAI SSE; never forward thought parts."""
 url=f'https://aiplatform.googleapis.com/v1/projects/{PROJECT}/locations/global/publishers/google/models/{MODEL}:streamGenerateContent?alt=sse'
 req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+access_token(),'Content-Type':'application/json'})
 seen=False;finished=False;start=time.monotonic();lines=[];size=0
 with urllib.request.urlopen(req,timeout=65) as response:
  if 'text/event-stream' not in response.headers.get('Content-Type',''):raise ValueError('Expected Google SSE')
  for raw in response:
   if time.monotonic()-start>100 or len(raw)>262144:raise ValueError('Stream deadline or frame limit')
   line=raw.decode('utf-8').rstrip('\r\n')
   if line.startswith('data:'):
    lines.append(line[5:].lstrip(' '));size+=len(line)
    if size>262144:raise ValueError('Stream frame limit')
   elif not line and lines:
    chunk=json.loads('\n'.join(lines));lines=[];size=0
    if chunk.get('error'):raise ValueError('Google stream failed')
    candidates=chunk.get('candidates',[])
    if not candidates:continue
    candidate=candidates[0];text=''.join(p['text'] for p in candidate.get('content',{}).get('parts',[]) if p.get('text') and not p.get('thought'))
    upstream=candidate.get('finishReason');reason=None
    if upstream:
     finished=True;reason='stop' if upstream=='STOP' else 'length' if upstream=='MAX_TOKENS' else 'content_filter' if upstream in ('SAFETY','RECITATION','PROHIBITED_CONTENT','BLOCKLIST') else 'unknown'
    if text:seen=True
    event={'object':'chat.completion.chunk','model':MODEL,'choices':[{'index':0,'delta':{'content':text} if text else {},'finish_reason':reason}]}
    if payload.get('tools') and candidate.get('groundingMetadata'):event['flow_grounding']=candidate['groundingMetadata']
    yield event
    if upstream:break
 if not seen or not finished:raise ValueError('Incomplete Google stream')

class Handler(BaseHTTPRequestHandler):
 def setup(self):super().setup();self.connection.settimeout(15)
 def log_message(self,*args):pass
 def send(self,data,status=200):
  body=json.dumps(data,ensure_ascii=False).encode();self.send_response(status)
  self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_GET(self):
  if self.path=='/health':self.send({'ok':True,'service':'flow-gateway','version':'2.2','audio_input':True,'search_grounding':True,'streaming':True})
  else:self.send({'error':'Not found'},404)
 def do_POST(self):
  if self.path!='/v1/chat/completions':return self.send({'error':'Not found'},404)
  if not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+SECRET):return self.send({'error':'Unauthorized'},401)
  try:
   length=int(self.headers.get('Content-Length','0'))
   if not 1<=length<=2200000:raise ValueError('Request size is invalid')
   data=json.loads(self.rfile.read(length));payload=prepare(data)
  except (ValueError,TypeError,KeyError):return self.send({'error':'Invalid request: text messages and configured model required'},400)
  if not SLOTS.acquire(timeout=25):return self.send({'error':'Gateway queue timed out, retry later'},503)
  try:
   if not reserve():return self.send({'error':'Gateway daily request ceiling reached'},429)
   if data.get('stream'):return self.stream(payload)
   return self.send(invoke(payload))
  except urllib.error.HTTPError as e:
   # Neither Google response bodies nor credentials are logged or forwarded.
   status=429 if e.code==429 else 502
   return self.send({'error':'Google model request failed','upstream_status':e.code},status)
  except (TimeoutError,socket.timeout):return self.send({'error':'Google model request timed out'},504)
  except Exception:return self.send({'error':'Model unavailable or no text returned'},502)
  finally:SLOTS.release()

 def stream(self,payload):
  self.send_response(200);self.send_header('Content-Type','text/event-stream; charset=utf-8')
  self.send_header('Cache-Control','no-store');self.send_header('X-Accel-Buffering','no');self.send_header('Connection','close');self.end_headers();self.close_connection=True
  def write(data):
   self.wfile.write(('data: '+data+'\n\n').encode());self.wfile.flush()
  try:
   for event in invoke_stream(payload):write(json.dumps(event,ensure_ascii=False))
   write('[DONE]')
  except (BrokenPipeError,ConnectionResetError):pass
  except Exception as exc:
   status=exc.code if isinstance(exc,urllib.error.HTTPError) else 504 if isinstance(exc,(TimeoutError,socket.timeout)) else 502
   try:write(json.dumps({'error':'Google stream unavailable or interrupted','status':status}))
   except (OSError,ValueError):pass

if __name__=='__main__':
 init();server=ThreadingHTTPServer(('127.0.0.1',8088),Handler);server.daemon_threads=True;print('Flow gateway ready',flush=True);server.serve_forever()
