"""Persistent tutor conversations, bounded context and idempotent chat requests."""
import json,os,re,secrets,time,urllib.request,urllib.error,socket
import ai_stream
import ai_jobs
from content_v05 import PRACTICES
from vertex_auth import ai_enabled,vertex_enabled,vertex_connection
PENDING_TTL=120

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS chat_turns(
 id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),topic TEXT NOT NULL REFERENCES topics(id),
 request_id TEXT NOT NULL,message TEXT NOT NULL,reply TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,
 finish_reason TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',created REAL NOT NULL,updated REAL NOT NULL,
 UNIQUE(user_id,request_id));
 CREATE INDEX IF NOT EXISTS chat_user_topic ON chat_turns(user_id,topic,id);''')
 ai_jobs.schema(c,'chat_turns')

def daily_limit(name):
 # r26: a value set in the xmc.hk console (console-settings.json) wins over /etc/flow.env, at once
 v=__import__('console_ops').limit_override(name)
 if v is not None:return v
 try:return max(0,int(os.getenv(name,'0') or 0))
 except ValueError:return 0

def _today():return time.strftime('%Y-%m-%d',time.gmtime())

def _exempt(c,uid):
 row=c.execute('SELECT admin FROM users WHERE id=?',(uid,)).fetchone()
 return bool(row and row[0])

def remaining(c,uid):
 """Calls left today for this learner, or None when no per-account ceiling applies."""
 limit=daily_limit('FLOW_AI_USER_DAILY_LIMIT')
 if not limit or _exempt(c,uid):return None
 row=c.execute('SELECT count FROM ai_usage WHERE user_id=? AND day=?',(uid,_today())).fetchone()
 return max(0,limit-(row[0] if row else 0))

def reserve(c,uid):
 """Count one model call inside the caller's write transaction.

 Returns an error message (and counts nothing) when the site-wide
 FLOW_AI_DAILY_LIMIT or the per-account FLOW_AI_USER_DAILY_LIMIT is reached.
 Both reset at 00:00 UTC; 0 disables a ceiling; admins skip the per-account one.
 """
 day=_today();c.execute('INSERT OR IGNORE INTO ai_usage VALUES(?,?,0)',(uid,day))
 site=daily_limit('FLOW_AI_DAILY_LIMIT')
 if site and c.execute('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE day=?',(day,)).fetchone()[0]>=site:
  return '本站今日 AI 调用额度已用完，请明天再来。'
 if remaining(c,uid)==0:
  return f"你今天的 {daily_limit('FLOW_AI_USER_DAILY_LIMIT')} 次 AI 调用已用完，北京时间早上 8 点重置。"
 c.execute('UPDATE ai_usage SET count=count+1 WHERE user_id=? AND day=?',(uid,day))
 return None

def history(c,uid,topic):
 if not c.execute('SELECT 1 FROM topics WHERE id=?',(topic,)).fetchone():return {'error':'知识点不存在'},404
 rows=c.execute('SELECT request_id,message,reply,status,finish_reason,error,created,updated FROM chat_turns WHERE user_id=? AND topic=? ORDER BY id DESC LIMIT 20',(uid,topic)).fetchall()
 out=[dict(r) for r in reversed(rows)]
 for row in out:
  if row['status']=='pending' and row['updated']<time.time()-PENDING_TTL:
   row.update(status='failed',error='上次请求未完成，可以重试。')
 return {'items':out,'remaining':remaining(c,uid),'enabled':ai_enabled(),'reset_timezone':'UTC'},200

def context(c,uid,topic,question):
 rows=c.execute("SELECT message,reply FROM chat_turns WHERE user_id=? AND topic=? AND status='complete' ORDER BY id DESC LIMIT 4",(uid,topic['id'])).fetchall()
 pairs=[];size=0
 # Recent exchanges take priority and are kept in chronological order.
 for row in rows:
  q=row['message'];a=row['reply']
  budget=4200-size-len(q)
  if budget<150:break
  if len(a)>budget:a='[较早内容省略] '+a[-max(1,budget-20):]
  pairs.append((q,a));size+=len(q)+len(a)
 system=('你是 Flow 英语学习导师。用简洁、完整的中文讲解，适当保留英文例句，优先用短段落和列表。'
         '先回答用户的具体问题，一次讲清一到三个要点，通常控制在400字内；不确定时明确说明。'
         '支持追问，结合之前的对话；仅讨论英语学习。教学参考：'+topic['title']+'；'+topic['lesson']+'；'+topic['example'])
 task=next((t for t in PRACTICES if question.startswith('【训练任务:'+t['id']+'】')),None)
 if task:system+='。当前训练要求：'+task['prompt']+'。反馈标准：先指出具体优点，再给最多三条修改建议与一句示范；不提供考试分数或发音评价。'
 messages=[{'role':'system','content':system}]
 for q,a in reversed(pairs):messages.extend([{'role':'user','content':q},{'role':'assistant','content':a}])
 messages.append({'role':'user','content':question})
 return messages

TRANSIENT_HTTP=(408,429,500,502,503,504)
LAST={'provider':None}  # which service answered the last call in this process (diagnostics only)


def transient(exc):
 """A failure worth trying again or elsewhere: timeouts, network trouble, rate limits and server errors; never a refusal or a configuration error."""
 from vertex_auth import AIConfigurationError
 if isinstance(exc,AIConfigurationError):return False
 if isinstance(exc,urllib.error.HTTPError):return exc.code in TRANSIENT_HTTP
 return isinstance(exc,(urllib.error.URLError,TimeoutError,socket.timeout,ConnectionError)) or (isinstance(exc,ValueError) and 'Incomplete' in str(exc))


LOOPBACK=re.compile(r'http://(127\.0\.0\.1|localhost|\[::1\])(:\d{1,5})?/')


def endpoint_ok(url):
 """https anywhere; plain http only to this machine (a model service on 127.0.0.1)."""
 return url.startswith('https://') or bool(LOOPBACK.match(url))


def text_provider(model=None):
 """Where text-only requests go first, or None (then everything goes to the main service).
 FLOW_TEXT_AI_MODEL alone: the same gateway and key as the main service (FLOW_AI_URL / FLOW_AI_KEY), another model
 name, e.g. flow-text on api.xmc.hk, whose console points it at DeepSeek, Qwen or Gemini (tools/ai-gateway/README.md).
 With FLOW_TEXT_AI_URL too: a separate service, which then needs its own FLOW_TEXT_AI_KEY; the main key is never
 sent to another address. model: another model name on that same service (a task's route, ai_routes.model_name)."""
 url,key,model=os.getenv('FLOW_TEXT_AI_URL',''),os.getenv('FLOW_TEXT_AI_KEY',''),model or os.getenv('FLOW_TEXT_AI_MODEL','')
 if model and not url and not vertex_enabled():
  url,key=os.getenv('FLOW_AI_URL',''),os.getenv('FLOW_AI_KEY','')
 return (url,key,model) if endpoint_ok(url) and key and model else None


SEARCH_STRATEGIES=('turbo','max')


def search_provider():
 """Where a grounded request (今日热点's news search) goes first, or None (then Gemini searches on the main service).
 FLOW_SEARCH_AI_MODEL: a gateway model name on a 百炼 upstream, e.g. flow-search-ds-flash, asked through the gateway's
 POST /v1/search/completions (百炼's own search, which names its sources; tools/ai-gateway/README.md) with the main
 gateway address and key. FLOW_SEARCH_STRATEGY: turbo (default) or max."""
 model=os.getenv('FLOW_SEARCH_AI_MODEL','').strip();url,key=os.getenv('FLOW_AI_URL',''),os.getenv('FLOW_AI_KEY','')
 if not model or vertex_enabled() or not endpoint_ok(url) or not key or not url.endswith('/chat/completions'):return None
 return url[:-len('/chat/completions')]+'/search/completions',key,model


def refused(exc):
 """The request itself was refused (malformed, too large): the main service would refuse it too."""
 return isinstance(exc,urllib.error.HTTPError) and exc.code in (400,413,422)


def request_model(messages,audio=None,grounding=False):
 """One model call. Text goes to the text service when one is configured, else to the main one; audio and grounded
 requests only to the main one, which can hear and search. When the text service fails for any reason but a refused
 request (down, model disabled in the gateway's console, key rejected, rate-limited), the main service answers; with
 only one service, a transient failure is retried once after a short pause (not after a rate limit), so a single
 hiccup does not cost the learner their answer.
 Which text model: the calling task's route (ai_routes: a gateway model name; FLOW_TEXT_AI_MODEL by default, a 百炼
 line such as flow-qwen-plus when the console says so). On a 百炼 line even a refused request goes to the main service
 once, which is another vendor. Every attempt is written to ai_calls (tokens, the model that answered, failures and
 fallbacks) for the console.
 A grounded request goes first to 百炼's search when FLOW_SEARCH_AI_MODEL names one (search_provider); if that fails for
 any reason, Gemini searches instead (the main service), so a bad day at one vendor costs no news."""
 import ai_routes
 text_model=ai_routes.route()
 search=search_provider() if grounding and not audio else None
 order=[]
 if search:order.append('search')
 elif not audio and not grounding and text_provider(text_model):order.append('text')
 order.append('main')
 if len(order)==1:order.append('main')  # one retry on the only service
 ai_routes.CTX.route=text_model if order[0]=='text' else search[2] if order[0]=='search' else ''
 last=None
 for i,which in enumerate(order):
  started=time.monotonic();INFO.__dict__.clear()
  model=text_model if which=='text' else search[2] if which=='search' else os.getenv('FLOW_AI_MODEL','')
  try:
   out=(_request_text_service(messages,text_model,ai_routes.extra_body(text_model)) if which=='text' else
        _request_search_service(messages) if which=='search' else _request_main(messages,audio,grounding))
   LAST['provider']=which
   ai_routes.record(which,model,started,messages,out[0],dict(INFO.__dict__),fallback=i>0)
   return out
  except Exception as exc:
   last=exc
   ai_routes.record(which,model,started,messages,None,dict(INFO.__dict__),exc,fallback=i>0)
   if which=='search':continue  # Gemini searches instead
   if which=='text' and time.monotonic()-started<=60 and (not refused(exc) or (ai_routes.is_bailian(text_model) and getattr(exc,'code',None)!=413)):continue  # the main service takes over
   if i==len(order)-1 or not transient(exc) or time.monotonic()-started>60:raise
   if order[i+1]==which:
    if isinstance(exc,urllib.error.HTTPError) and exc.code==429:raise  # rate-limited: asking the same service again at once will not help
    time.sleep(1.5)
 raise last


INFO=__import__('threading').local()  # the last call's usage and answering model (ai_routes.record)


def _request_text_service(messages,model=None,extra=None):
 url,key,model=text_provider(model) or ('','','')
 return _openai_compatible(url,key,model,messages,None,False,extra)


def _request_search_service(messages):
 """百炼's search through the gateway: (reply, reason, metadata). The reply cites its sources as [ref_N]; metadata is
 {'engine': 'bailian', 'search_results': [{index, url, title, site_name}], 'searches': n} (daily_service.provenance)."""
 from vertex_auth import AIConfigurationError
 found=search_provider()
 if not found:raise AIConfigurationError('Search configuration incomplete')
 url,key,model=found
 strategy=os.getenv('FLOW_SEARCH_STRATEGY','turbo').strip() or 'turbo'
 payload={'model':model,'messages':[{'role':m['role'],'content':m['content']} for m in messages],'max_tokens':2048,
          'search':{'strategy':strategy if strategy in SEARCH_STRATEGIES else 'turbo','freshness':7}}
 req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'User-Agent':'jasa-flow/1.0','Authorization':'Bearer '+key,'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=120) as r:d=json.load(r)
 import ai_routes
 INFO.usage=ai_routes.usage_of(d);INFO.served=str(d.get('model') or '')[:80]
 choice=d['choices'][0];reply=choice['message']['content'];reason=choice.get('finish_reason','stop')
 if not isinstance(reply,str) or not reply.strip():raise ValueError('Empty model reply')
 info=d.get('search_info') if isinstance(d.get('search_info'),dict) else {}
 results=info.get('search_results') if isinstance(info.get('search_results'),list) else []
 return reply[:20000],reason,{'engine':'bailian','search_results':results[:50],'searches':(d.get('search_usage') or {}).get('count')}


def _request_main(messages,audio=None,grounding=False):
 endpoint=os.getenv('FLOW_AI_URL','');key=os.getenv('FLOW_AI_KEY','');model=os.getenv('FLOW_AI_MODEL','')
 from vertex_auth import AIConfigurationError
 if vertex_enabled():
  try:endpoint,key=vertex_connection()
  except (ValueError,ImportError) as exc:raise AIConfigurationError('Vertex configuration incomplete') from exc
  if audio or grounding:
   from vertex_native import request_native
   return request_native(messages,model,key,audio,grounding)
 return _openai_compatible(endpoint,key,model,messages,audio,grounding)


def _openai_compatible(endpoint,key,model,messages,audio,grounding,extra=None):
 from vertex_auth import AIConfigurationError
 if not endpoint_ok(endpoint) or not model or not key:raise AIConfigurationError('AI configuration incomplete')
 payload={**(extra or {}),'model':model,'messages':messages,'max_tokens':4096}
 if ai_stream.active():payload['stream']=True
 if grounding:payload['flow_grounding']=True
 if audio:
  from audio_validation import validate_audio
  validate_audio(audio);payload['flow_audio']=audio
 req=urllib.request.Request(endpoint,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'User-Agent':'jasa-flow/1.0','Authorization':'Bearer '+key,'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=85) as r:
  if ai_stream.active():
   if 'text/event-stream' not in r.headers.get('Content-Type',''):raise AIConfigurationError('Gateway streaming upgrade required')
   reply='';reason=None;metadata={};started=time.monotonic()
   for frame in ai_stream.events(r):
    if time.monotonic()-started>100:raise TimeoutError('AI stream deadline exceeded')
    if frame=='[DONE]':break
    chunk=json.loads(frame)
    if chunk.get('model'):INFO.served=str(chunk['model'])[:80]
    if __import__('ai_routes').usage_of(chunk):INFO.usage=__import__('ai_routes').usage_of(chunk)
    if chunk.get('error'):
     status=chunk.get('status',502)
     raise urllib.error.HTTPError(endpoint,status if type(status)==int and status in (400,401,403,413,429,502,503,504) else 502,'Model stream failed',None,None)
    choices=chunk.get('choices',[])
    if chunk.get('flow_grounding'):metadata=chunk['flow_grounding']
    if not choices:continue
    choice=choices[0];delta=choice.get('delta',{}).get('content','')
    if delta:
     if not isinstance(delta,str):raise ValueError('Invalid model delta')
     reply+=delta
     if len(reply)>20000:raise ValueError('Model response too long')
     ai_stream.emit({'type':'preview','text':ai_stream.preview(reply,getattr(ai_stream.LOCAL,'structured',True)),'characters':len(reply)})
    if choice.get('finish_reason') is not None:
     reason=choice['finish_reason'];break
   if not reason or reason not in ('stop','length','max_tokens','content_filter') or not reply.strip():raise ValueError('Incomplete model stream')
   if reason!='stop':raise ValueError('Model stream not complete')
   return (reply,reason,metadata) if grounding else (reply,reason)
  d=json.load(r)
 import ai_routes
 INFO.usage=ai_routes.usage_of(d);INFO.served=str(d.get('model') or '')[:80]
 choice=d['choices'][0];reply=choice['message']['content'];reason=choice.get('finish_reason','stop')
 if not isinstance(reply,str) or not reply.strip():raise ValueError('Empty model reply')
 if grounding:return reply[:20000],reason,d.get('flow_grounding',{})
 return reply[:20000],('length' if len(reply)>20000 else reason)

def result(row,quota):
 return {'reply':row['reply'],'request_id':row['request_id'],'finish_reason':row['finish_reason'],'truncated':row['finish_reason'] in ('length','max_tokens'),'remaining':quota,'mode':'ai' if row['finish_reason']!='lesson' else 'lesson'}

def chat(c,uid,data):
 question=data.get('message','');topic_id=data.get('topic','');rid=data.get('request_id') or secrets.token_hex(16)
 if not isinstance(question,str) or not 1<=len(question.strip())<=1000 or not isinstance(rid,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{12,80}',rid):return {'error':'问题需为1–1000字，请求标识不正确。'},400
 question=question.strip();topic=c.execute('SELECT * FROM topics WHERE id=?',(topic_id,)).fetchone()
 if not topic:return {'error':'知识点不存在'},400
 c.execute('BEGIN IMMEDIATE')
 row=c.execute('SELECT * FROM chat_turns WHERE user_id=? AND request_id=?',(uid,rid)).fetchone()
 if row:
  if row['topic']!=topic_id or row['message']!=question:c.rollback();return {'error':'请求标识已被使用，请重新提问。'},409
  if row['status']=='complete':c.rollback();return result(row,remaining(c,uid)),200
  if row['status']=='pending' and row['updated']>time.time()-PENDING_TTL:c.rollback();return {'error':'导师还在回答，请稍候。'},409
 if c.execute("SELECT 1 FROM lab_jobs WHERE user_id=? AND status='pending' AND updated>?",(uid,time.time()-PENDING_TTL)).fetchone():
  c.rollback();return {'error':'已有训练请求正在处理，请稍候。'},409
 if c.execute("SELECT 1 FROM chat_turns WHERE user_id=? AND status='pending' AND updated>? AND request_id!=?",(uid,time.time()-PENDING_TTL,rid)).fetchone():
  c.rollback();return {'error':'已有提问正在处理，请稍候再试。'},409
 enabled=ai_enabled()
 if enabled:
  problem=reserve(c,uid)
  if problem:c.rollback();return {'error':problem,'remaining':remaining(c,uid)},429
 now=time.time()
 if row:c.execute("UPDATE chat_turns SET status='pending',error='',updated=? WHERE id=?",(now,row['id']))
 else:c.execute("INSERT INTO chat_turns(user_id,topic,request_id,message,status,created,updated) VALUES(?,?,?,?,'pending',?,?)",(uid,topic_id,rid,question,now,now))
 lease=ai_jobs.reserve(c,'chat_turns',uid,rid);c.commit()
 try:
  if enabled:
   with ai_jobs.renewing(c,'chat_turns',uid,rid,lease),__import__('ai_routes').task('chat'):reply,reason=request_model(context(c,uid,topic,question))
  else:reply='当前未接入 AI。以下是本知识点的固定学习提示：\n\n'+topic['lesson']+'\n\n**例句**\n'+topic['example']+'\n\n'+topic['explanation'];reason='lesson'
  changed=c.execute("UPDATE chat_turns SET reply=?,finish_reason=?,status='complete',error='',updated=? WHERE user_id=? AND request_id=? AND lease=?",(reply,reason,time.time(),uid,rid,lease)).rowcount;c.commit()
  if not changed:return {'error':'旧请求已被新请求接替，请刷新记录。'},409
  row=c.execute('SELECT * FROM chat_turns WHERE user_id=? AND request_id=?',(uid,rid)).fetchone()
  return result(row,remaining(c,uid)),200
 except Exception as exc:
  error='AI 暂时无法回答，请稍后重试。';status=502
  if isinstance(exc,__import__('vertex_auth').AIConfigurationError):status=503;error='AI 配置不完整或网关不支持实时输出，请管理员检查，草稿仍保留。'
  elif isinstance(exc,urllib.error.HTTPError):
   error={401:'网关认证失败，请管理员检查连接配置。',403:'访问权限受限，请管理员检查网关白名单。',429:'模型或网关配额不足，请稍后再试。',504:'模型回答超时，请重试。'}.get(exc.code,error)
  elif isinstance(exc,(TimeoutError,socket.timeout)):error='导师回答超时，你的问题已保留，可以重试。';status=504
  c.execute("UPDATE chat_turns SET status='failed',error=?,updated=? WHERE user_id=? AND request_id=? AND lease=?",(error,time.time(),uid,rid,lease));c.commit()
  return {'error':error,'request_id':rid,'remaining':remaining(c,uid)},status
