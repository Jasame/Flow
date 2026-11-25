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
 any reason, Gemini searches instead (the main service), so a bad day at one vendor costs no news.
 A recording goes first to the task's audio route when FLOW_AUDIO_ROUTES names one (ai_routes.audio_route: Qwen-Omni on
 百炼 through the gateway, _request_audio_service); if that fails for any reason, Gemini hears it, as before."""
 import ai_routes
 text_model=ai_routes.route()
 search=search_provider() if grounding and not audio else None
 hearing=ai_routes.audio_route() if audio and not grounding and audio_provider() else ''
 main=main_on();backup=backup_model()
 order=[]
 if search:order.append('search')
 elif hearing:order.append('audio')
 elif not audio and not grounding and text_provider(text_model):order.append('text')
 if main:order.append('main')
 elif order[:1]==['text'] and backup and backup!=text_model:order.append('backup')  # 百炼's other model, not Gemini
 elif order[:1]==['audio'] and backup and asr_model() and ai_routes.current() in HEARD_ONLY:order.append('asr')
 elif not order and backup and not audio and not grounding:order.append('backup')
 if getattr(MAIN_ONLY,'on',False):  # run_job's last try after answers it could not take (e.g. Omni twice with nothing heard): another model
  if main:order=['main']
  elif backup and not audio and not grounding:order=['backup']
  elif hearing and backup and asr_model() and ai_routes.current() in HEARD_ONLY:order=['asr']  # r30 e2e: Omni's heard empty twice
 if not order:
  from vertex_auth import AIConfigurationError
  raise AIConfigurationError('No AI service for this request')
 if len(order)==1:order.append(order[0])  # one retry on the only service
 ai_routes.CTX.route=text_model if order[0]=='text' else search[2] if order[0]=='search' else hearing if order[0]=='audio' else ''
 last=None
 for i,which in enumerate(order):
  started=time.monotonic();INFO.__dict__.clear()
  model=(text_model if which=='text' else search[2] if which=='search' else hearing if which=='audio' else backup if which in ('backup','asr')
         else os.getenv('FLOW_AI_MODEL',''))
  try:
   out=(_request_text_service(messages,text_model,ai_routes.extra_body(text_model)) if which=='text' else
        _request_search_service(messages) if which=='search' else _request_audio_service(messages,audio,hearing) if which=='audio' else
        _request_text_service(messages,backup,ai_routes.extra_body(backup)) if which=='backup' else
        _request_heard_then_text(messages,audio,backup) if which=='asr' else
        _request_main(messages,audio,grounding))
   LAST['provider']=which
   ai_routes.record('backup' if which=='asr' else which,model,started,messages,out[0],dict(INFO.__dict__),fallback=i>0)
   return out
  except Exception as exc:
   last=exc
   ai_routes.record('backup' if which=='asr' else which,model,started,messages,None,dict(INFO.__dict__),exc,fallback=i>0)
   if which in ('search','audio') and i<len(order)-1 and order[i+1]!=which:continue  # the next service searches / hears it instead
   if which=='text' and order[i+1:i+2]!=['text'] and i<len(order)-1 and time.monotonic()-started<=60 and (not refused(exc) or (ai_routes.is_bailian(text_model) and getattr(exc,'code',None)!=413)):continue  # the main service takes over
   if i==len(order)-1 or not transient(exc) or time.monotonic()-started>60:raise
   if order[i+1]==which:
    if isinstance(exc,urllib.error.HTTPError) and exc.code==429:raise  # rate-limited: asking the same service again at once will not help
    time.sleep(1.5)
 raise last


# 2026-11-25 (user: 「换成国内已备案模型」; Gemini has no filing in China and a recording sent to it leaves the country):
# FLOW_MAIN_AI=off keeps the main model (Gemini) out of every learner request. Then a text task that fails on its route
# goes to FLOW_BACKUP_AI_MODEL (another 百炼 model, e.g. flow-text-qwen-plus), a recording whose audio route fails is
# written down by FLOW_ASR_AI_MODEL (qwen3-asr-flash) and answered by that backup model (only tasks in HEARD_ONLY: what
# was said matters, not how it sounded), and run_job's last try asks the backup model. 跟读 and 发音 have no text backup
# (a score of how it sounded needs the sound); a search has none either.
HEARD_ONLY={'next-dialog','next-retell','next-ielts'}


def main_on():
 return os.getenv('FLOW_MAIN_AI','on').strip().lower()!='off'


def backup_model():
 m=os.getenv('FLOW_BACKUP_AI_MODEL','').strip()
 return m if m and text_provider(m) else ''


def asr_model():
 m=os.getenv('FLOW_ASR_AI_MODEL','').strip()
 return m if m and audio_provider() else ''


INFO=__import__('threading').local()  # the last call's usage and answering model (ai_routes.record)
MAIN_ONLY=__import__('threading').local()


@__import__('contextlib').contextmanager
def main_only():
 """Inside, request_model asks the main service (Gemini) only: after the task's own model twice answered in a shape the
 converter could not take (lab_service.run_job), another vendor gets the last word."""
 old=getattr(MAIN_ONLY,'on',False);MAIN_ONLY.on=True
 try:yield
 finally:MAIN_ONLY.on=old


def _request_text_service(messages,model=None,extra=None):
 url,key,model=text_provider(model) or ('','','')
 return _openai_compatible(url,key,model,messages,None,False,extra,timeout=text_timeout())


def text_timeout():
 """Seconds the text service (DeepSeek on 百炼) may take before the main model takes over (FLOW_TEXT_TIMEOUT, 15–85;
 default 45). 2026-11-25: on 内测版 its 321 answered text calls took at most 28 s (P99 20 s), but one import enrichment
 got nothing back for 85 s and failed, as request_model hands a failure to Gemini only within 60 s. At 45 s it still does."""
 try:
  v=int(os.getenv('FLOW_TEXT_TIMEOUT','45'))
 except ValueError:
  return 45
 return v if 15<=v<=85 else 45


AUDIO_FORMATS={'audio/webm':'webm','audio/ogg':'ogg','audio/wav':'wav','audio/mpeg':'mp3','audio/mp3':'mp3','audio/mp4':'mp4','audio/m4a':'mp4','audio/flac':'flac'}


def audio_provider():
 """The gateway that hears recordings on an audio route (the main gateway address and key), or None (Vertex direct)."""
 url,key=os.getenv('FLOW_AI_URL',''),os.getenv('FLOW_AI_KEY','')
 return (url,key) if not vertex_enabled() and endpoint_ok(url) and key and url.endswith('/chat/completions') else None


def _request_audio_service(messages,audio,model):
 """A recording to an audio route (Qwen-Omni on 百炼): the same system and user text, the recording as an OpenAI
 input_audio part before the user's text, streamed (Omni answers only streamed), thinking off. (reply, reason).
 Measured 2026-11-25 (voice_eval.py): browser webm/opus and iPhone mp4/AAC are taken as they are."""
 from audio_validation import validate_audio
 from vertex_auth import AIConfigurationError
 found=audio_provider()
 if not found or not model:raise AIConfigurationError('Audio route configuration incomplete')
 validate_audio(audio)
 url,key=found
 fmt=AUDIO_FORMATS.get(audio['mime_type'],'')
 if not fmt:raise ValueError('Audio format not for this route')
 msgs=[dict(m) for m in messages]
 last=next(i for i in range(len(msgs)-1,-1,-1) if msgs[i].get('role')=='user')
 msgs[last]={'role':'user','content':[{'type':'input_audio','input_audio':{'data':f"data:{audio['mime_type']};base64,{audio['data']}",'format':fmt}},
                                      {'type':'text','text':msgs[last]['content']}]}
 payload={'model':model,'messages':msgs,'modalities':['text'],'enable_thinking':False,'max_tokens':4096,'stream':True,'stream_options':{'include_usage':True}}
 req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'User-Agent':'jasa-flow/1.0','Authorization':'Bearer '+key,'Content-Type':'application/json'})
 import ai_routes
 reply='';reason=None;started=time.monotonic()
 with urllib.request.urlopen(req,timeout=25) as r:  # Omni answers in ~3 s (P90 ~5); give up early so Gemini still has time
  for frame in ai_stream.events(r):
   if time.monotonic()-started>30:raise TimeoutError('Audio route deadline exceeded')
   if frame=='[DONE]':break
   chunk=json.loads(frame)
   if chunk.get('model'):INFO.served=str(chunk['model'])[:80]
   if ai_routes.usage_of(chunk):INFO.usage=ai_routes.usage_of(chunk)
   if chunk.get('error'):raise urllib.error.HTTPError(url,502,'Audio route stream failed',None,None)
   for choice in chunk.get('choices') or []:
    delta=(choice.get('delta') or {}).get('content') or ''
    if delta:
     if not isinstance(delta,str):raise ValueError('Invalid model delta')
     reply+=delta
     if len(reply)>20000:raise ValueError('Model response too long')
     if ai_stream.active():ai_stream.emit({'type':'preview','text':ai_stream.preview(reply,getattr(ai_stream.LOCAL,'structured',True)),'characters':len(reply)})
    if choice.get('finish_reason') is not None:reason=choice['finish_reason']
 if not reply.strip():raise ValueError('Empty model reply')
 if reason not in (None,'stop'):raise ValueError('Model stream not complete')
 return reply,'stop'


SAID=[{'role':'user','content':'[recording]'}]  # what ai_calls counts for a transcription (the audio is not text)
WORD_PROMPT='You write down English speech. The recording is one English word. Output only that word, as you hear it.'


def word_model():
 """The audio route that writes down one read word: 发音's own (next-say) or, without one, 情景对话's (both Qwen-Omni)."""
 import ai_routes
 return ai_routes.audio_route('next-say') or ai_routes.audio_route('next-dialog')


def hear_word(audio):
 """One read word written down by Qwen-Omni (filed under 通义千问), told nothing of the word expected; '' = nothing.
 2026-11-25 omni_word_eval (24 pairs of 发音入门, synthetic voices, 192 judgements): a correct reading heard as the pair
 word 1 in 48 (English voice) and 3 in 48 (Chinese voice), a wrong one caught 36 and 35 of 48, 0.9 s; told the two
 words it did worse (5 and 10 in 48), and qwen3-asr told them (1 and 6) has no filing (Aliyun ticket, 13:58)."""
 import ai_routes
 from vertex_auth import AIConfigurationError
 model=word_model()
 if not model:raise AIConfigurationError('No audio route to write down a word')
 msgs=[{'role':'system','content':WORD_PROMPT},{'role':'user','content':'Write down the word.'}]
 started=time.monotonic();INFO.__dict__.clear()
 try:
  reply,_=_request_audio_service(msgs,audio,model)
 except ValueError as exc:
  if str(exc)!='Empty model reply':
   ai_routes.record('word',model,started,SAID,None,dict(INFO.__dict__),exc);raise
  reply=''
 except Exception as exc:
  ai_routes.record('word',model,started,SAID,None,dict(INFO.__dict__),exc);raise
 ai_routes.record('word',model,started,SAID,reply,dict(INFO.__dict__))
 return reply.strip()[:200]


def transcribe(audio,words=None):
 """A recording written down by 百炼's speech recognition (FLOW_ASR_AI_MODEL) through the gateway: the text, or ''.
 words: what the speaker is expected to say (a word and its pair word), given as context so the recogniser hears the
 likely word (2026-11-25 say_pairs_eval: 1 of 48 correct English-voice readings heard as the other word, 0.6 s)."""
 from audio_validation import validate_audio
 from vertex_auth import AIConfigurationError
 found,model=audio_provider(),asr_model()
 if not found or not model:raise AIConfigurationError('Speech recognition configuration incomplete')
 validate_audio(audio)
 url,key=found
 msgs=[{'role':'user','content':[{'type':'input_audio','input_audio':{'data':f"data:{audio['mime_type']};base64,{audio['data']}"}}]}]
 if words:
  ws=[w for w in words if w]
  msgs.insert(0,{'role':'system','content':[{'text':'English pronunciation practice. The speaker reads one word: '+' or '.join('"'+w+'"' for w in ws)+'.'}]})
 payload={'model':model,'messages':msgs,'stream':True,'stream_options':{'include_usage':True},'asr_options':{'language':'en','enable_itn':False}}
 req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'User-Agent':'jasa-flow/1.0','Authorization':'Bearer '+key,'Content-Type':'application/json'})
 import ai_routes
 text='';started=time.monotonic();INFO.__dict__.clear()
 try:
  with urllib.request.urlopen(req,timeout=20) as r:
   for frame in ai_stream.events(r):
    if time.monotonic()-started>25:raise TimeoutError('Speech recognition deadline exceeded')
    if frame=='[DONE]':break
    chunk=json.loads(frame)
    if chunk.get('model'):INFO.served=str(chunk['model'])[:80]
    if ai_routes.usage_of(chunk):INFO.usage=ai_routes.usage_of(chunk)
    for choice in chunk.get('choices') or []:
     d=(choice.get('delta') or {}).get('content') or ''
     if isinstance(d,str):text+=d
     if len(text)>4000:raise ValueError('Transcript too long')
 except Exception as exc:
  ai_routes.record('asr',model,started,SAID,None,dict(INFO.__dict__),exc)
  raise
 ai_routes.record('asr',model,started,SAID,text,dict(INFO.__dict__))
 return text.strip()


def _request_heard_then_text(messages,audio,model):
 """The audio route failed: write the recording down (transcribe), then ask the text model with what was said in
 place of the recording. The task's prompt asks for what was heard; the transcript is that."""
 heard=transcribe(audio)
 msgs=[dict(m) for m in messages]
 last=next(i for i in range(len(msgs)-1,-1,-1) if msgs[i].get('role')=='user')
 msgs[last]['content']=str(msgs[last]['content'])+'\n\n（录音已由语音识别转成文字，下面就是学习者说的话；把它当作你听到的内容，照原样转写，不要猜测发音。）\n学习者说：'+(heard or '[听不清]')
 import ai_routes
 return _request_text_service(msgs,model,ai_routes.extra_body(model))


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


def audio_timeout():
 """Seconds a recording may take on the main service before the learner is told (FLOW_AUDIO_TIMEOUT, 15–85; default
 85, as before). 2026-11-25: Vertex was slow on recordings and every one waited the relay's full 65 s; a site can answer
 sooner with e.g. 40. Normal Gemini turns took up to ~37 s in voice_eval, so not much lower."""
 try:
  v=int(os.getenv('FLOW_AUDIO_TIMEOUT','85'))
 except ValueError:
  return 85
 return v if 15<=v<=85 else 85


def _openai_compatible(endpoint,key,model,messages,audio,grounding,extra=None,timeout=None):
 from vertex_auth import AIConfigurationError
 if not endpoint_ok(endpoint) or not model or not key:raise AIConfigurationError('AI configuration incomplete')
 payload={**(extra or {}),'model':model,'messages':messages,'max_tokens':4096}
 if ai_stream.active():payload['stream']=True
 if grounding:payload['flow_grounding']=True
 if audio:
  from audio_validation import validate_audio
  validate_audio(audio);payload['flow_audio']=audio
 req=urllib.request.Request(endpoint,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'User-Agent':'jasa-flow/1.0','Authorization':'Bearer '+key,'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=timeout or (audio_timeout() if audio else 85)) as r:
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
