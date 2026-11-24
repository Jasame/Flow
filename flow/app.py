#!/usr/bin/env python3
"""Flow pilot: standard-library HTTP service. Run behind Nginx HTTPS."""
import os,json,sqlite3,ipaddress,secrets,hashlib,hmac,time,threading,argparse,getpass,urllib.request,urllib.error
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from chat_service import schema as chat_schema,history as chat_history,chat as tutor_chat
import lab_service as lab
import daily_service as daily
import knowledge_service as knowledge
import adaptive_service as adaptive
import coach_service as coach
import growth_service as growth
import graph_service as graph_engine
import reference_service as reference
import practice_service as practice
import foundation_service as foundation
import learning_service as learning
import account_service as account
import guest_first
import attempt_service as attempts
import settings_service as settings_store
import core_words
import meeting_path
import meeting_service as meeting
from seed import TOPICS,QUESTIONS
from content_v03 import EXTRA_QUESTIONS,LESSONS
from vertex_auth import vertex_enabled, ai_enabled, vertex_connection
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('FLOW_DATA_DIR',str(ROOT/'data'))); DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'flow.sqlite3'
SECURE=os.getenv('FLOW_COOKIE_SECURE','1')=='1'
RATE={}; LOCK=threading.Lock()
REVISION_TAG=__import__('re').compile(r' · (?:A2|B1|B2) · 修订题组')
def public_text(s):
 """Internal edition tags stay in the data; learners see the plain title (level is shown on its own)."""
 return REVISION_TAG.sub('',s)

def ai_model_label():
 # Readable name of the configured model (FLOW_AI_MODEL is not a secret), e.g. gemini-3.8-flash -> Gemini 3.8 Flash.
 raw=os.getenv('FLOW_AI_MODEL','').strip().lower().removeprefix('google/')
 if not raw or len(raw)>80 or not all(ch.isalnum() or ch in '.-' for ch in raw):return ''
 return ' '.join(p if any(ch.isdigit() for ch in p) else p.capitalize() for p in raw.split('-') if p)
def db():
 c=sqlite3.connect(DB,timeout=15); c.row_factory=sqlite3.Row; c.execute('PRAGMA foreign_keys=ON'); return c
def init():
 with db() as c:
  c.executescript('''PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,admin INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),csrf TEXT,expires REAL);
CREATE TABLE IF NOT EXISTS topics(id TEXT PRIMARY KEY,title TEXT,summary TEXT,lesson TEXT,example TEXT,explanation TEXT,prereqs TEXT);
CREATE TABLE IF NOT EXISTS questions(id INTEGER PRIMARY KEY,topic TEXT REFERENCES topics(id),prompt TEXT,options TEXT,answer INTEGER,explanation TEXT);
CREATE TABLE IF NOT EXISTS attempts(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),question_id INTEGER REFERENCES questions(id),selected INTEGER,correct INTEGER,created REAL);
CREATE TABLE IF NOT EXISTS quizzes(token TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),ids TEXT,expires REAL,used INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS migrations(version TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS completed_lessons(user_id INTEGER REFERENCES users(id),topic TEXT REFERENCES topics(id),created REAL,PRIMARY KEY(user_id,topic));
CREATE INDEX IF NOT EXISTS attempts_user_question ON attempts(user_id,question_id,id);
CREATE INDEX IF NOT EXISTS attempts_user_time ON attempts(user_id,created);
CREATE TABLE IF NOT EXISTS ai_usage(user_id INTEGER,day TEXT,count INTEGER,PRIMARY KEY(user_id,day));''')
  if not c.execute('SELECT 1 FROM topics').fetchone():
   c.executemany('INSERT INTO topics VALUES(?,?,?,?,?,?,?)',[(*t[:6],json.dumps(t[6])) for t in TOPICS])
   c.executemany('INSERT INTO questions(topic,prompt,options,answer,explanation) VALUES(?,?,?,?,?)',[(t,p,json.dumps(o),a,e) for t,p,o,a,e in QUESTIONS])
  if not c.execute("SELECT 1 FROM migrations WHERE version='0.3'").fetchone():
   for t,prompt,opts,a,e in EXTRA_QUESTIONS:
    if not c.execute('SELECT 1 FROM questions WHERE topic=? AND prompt=?',(t,prompt)).fetchone():
     c.execute('INSERT INTO questions(topic,prompt,options,answer,explanation) VALUES(?,?,?,?,?)',(t,prompt,json.dumps(opts),a,e))
   c.execute("INSERT INTO migrations VALUES('0.3')")
  chat_schema(c)
  learning.schema(c)
  account.schema(c)
  __import__('auth_service').schema(c)
  lab.schema(c)
  daily.schema(c)
  adaptive.schema(c)
  coach.schema(c)
  growth.schema(c)
  reference.schema(c)
  __import__('ops_errors').schema(c)
  __import__('feedback_service').schema(c)
  __import__('field_service').schema(c)
  core_words.schema(c)
  practice.schema(c)
  foundation.schema(c)
  import migration_35
  migration_35.run(c)
  __import__('corpus_import').schema(c)
  __import__('pilot_service').schema(c)
  meeting.schema(c)
  __import__('survey_service').schema(c)
  __import__('next_service').schema(c)
  __import__('relisten_service').schema(c)
  __import__('tts_service').schema(c)
  __import__('tts_service').CONNECT=db  # 声音接力: a sentence made in a thread while the reply travels needs its own connection
  __import__('class_service').schema(c)
  __import__('flow_admin').schema(c)
  __import__('ai_routes').schema(c)
def wrong_questions(c,uid):
 return c.execute('''SELECT q.id,q.topic,q.prompt,q.options,q.explanation,q.answer,a.selected FROM questions q
 JOIN attempts a ON a.question_id=q.id WHERE q.status='published' AND a.user_id=? AND a.correct=0
 AND a.id=(SELECT MAX(b.id) FROM attempts b WHERE b.user_id=a.user_id AND b.question_id=a.question_id)
 ORDER BY a.id DESC''',(uid,)).fetchall()
def password(p,salt=None):
 salt=salt or secrets.token_hex(16); return salt+':'+hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(salt),260000).hex()
STARTED=time.time()
def live_status():
 """What the monitor reads every few minutes: process memory (Linux), uptime, threads, server errors in the last day."""
 out={'uptime_min':round((time.time()-STARTED)/60),'threads':threading.active_count(),'malloc_arenas':os.getenv('MALLOC_ARENA_MAX','')}
 try:
  for line in Path('/proc/self/status').read_text().splitlines():
   k,_,v=line.partition(':')
   if k in ('VmRSS','VmHWM'):out[{'VmRSS':'rss_mb','VmHWM':'peak_rss_mb'}[k]]=round(int(v.split()[0])/1024)
 except OSError:pass
 try:
  with db() as c:out['errors_24h']=__import__('ops_errors').count_since(c,86400)
 except Exception:pass
 return out
SESSION_DAYS=30
# r20: the classic site is archived (archive/classic/). The learner site serves only what the learning site (next.html),
# the survey, sign-in and the account need, and the operations checks; every other /api/ path answers 404. Operator
# functions live in the xmc.hk console (flow_admin.py, port FLOW_ADMIN_PORT), never on the learner site.
OPEN_API={'GET':('/api/health','/api/version','/api/survey','/api/deploy-status','/api/session','/api/account','/api/next/'),
 'POST':('/api/survey','/api/feedback','/api/next/','/api/recovery/','/api/login','/api/register','/api/auth/code','/api/auth/reset','/api/logout','/api/password','/api/account/')}
def api_open(method,path):return any(path==p or (p.endswith('/') and path.startswith(p)) for p in OPEN_API[method])
def session_cookie(token):
 return 'flow_session='+token+'; HttpOnly; SameSite=Lax; Path=/; Max-Age='+str(SESSION_DAYS*86400)+('; Secure' if SECURE else '')
_ASSET={}
# Two sites from one code base (2026-11-24): flowlang.cn is 语流's site (FLOW_CHANNEL unset, "prod"); flow.jasa.hk is
# the 内测版 (FLOW_CHANNEL=beta), a second instance with its own data, where versions waiting for release run first.
# The 内测版 says so on every page, sends its mail marked 【内测版】 and asks search engines to stay away.
CHANNEL='beta' if os.getenv('FLOW_CHANNEL','').strip().lower()=='beta' else 'prod'
_SLIM={}
def shell_file(name):
 """A public file; the page shell and the service worker get the asset version filled in (__ASSET__): a hash of
 next.js and next.css, so any change to them gives new URLs and a changed service worker, and phones update.
 next.js and next.css are sent slimmed (slim.py: no comments or indentation, the same lines), once per change.
 The page shell also says which site it is (__CHANNEL__), and the 内测版's home-screen app is named as such."""
 f=ROOT/'public'/name;body=f.read_bytes()
 if name in ('next.js','next.css','about.js','about.css'):
  key=f.stat().st_mtime_ns
  if _SLIM.get(name,(None,))[0]!=key:_SLIM[name]=(key,__import__('slim').slim(name,body))
  return _SLIM[name][1]
 if name=='manifest.webmanifest' and CHANNEL=='beta':
  m=json.loads(body);m.update(name='语流 Flow 内测版',short_name='语流内测');return json.dumps(m,ensure_ascii=False,indent=1).encode()
 if name=='about.html':return body.replace(b'__ABOUT__',asset_version(ABOUT_ASSETS).encode()).replace(b'__CHANNEL__',CHANNEL.encode())
 if name not in ('next.html','sw.js'):return body
 return body.replace(b'__ASSET__',asset_version().encode()).replace(b'__CHANNEL__',CHANNEL.encode())

PAGE_CACHE='max-age=0, stale-while-revalidate=2592000'  # the learning page: see do_GET '/'

# 认识语流 (/about): the introduction page for people who have not used Flow yet; its own small files, so it opens fast
# and never loads the learning site. Its pictures are real screenshots (tools/about_shots.py) in public/about/.
ABOUT_ASSETS=('about.js','about.css')
def asset_version(names=('next.js','next.css')):
 """The content version of next.js and next.css (10 hex digits), or of the files named; recomputed when one changes."""
 key=tuple((ROOT/'public'/n).stat().st_mtime_ns for n in names)
 got=_ASSET.get(names)
 if not got or got[0]!=key:
  h=hashlib.sha256()
  for n in names:h.update((ROOT/'public'/n).read_bytes())
  got=_ASSET[names]=(key,h.hexdigest()[:10])
 return got[1]
def csp():
 # The media domain (R2, media.py) is the second line for audio and its timings, when FLOW_MEDIA_BASE is set.
 m=__import__('media').origin();extra=' '+m if m else ''
 return "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'"+extra+"; media-src 'self' blob:"+extra+"; frame-src 'self' about:; frame-ancestors 'none'"
def session_info(u):
 """What /api/session answers; /api/next/home carries the same, so the page needs one request to start."""
 # email_bound: the page reminds an account without one that a forgotten password could not be reset by itself.
 # media: where audio can also be fetched when this server cannot answer (None unless R2 is in use).
 # age/guardian: 年龄段 and a guardian's agreement under 14 (privacy_service): an account without a band is asked once.
 return {'user':{**{k:u[k] for k in ('id','username','admin','csrf')},'email_bound':bool(u['email']),**__import__('privacy_service').info(u)} if u else None,'ai_enabled':ai_enabled(),'mail':account.configured(),'media':__import__('media').info(),'tts':__import__('tts_service').enabled()}
def verify(p,stored): return hmac.compare_digest(password(p,stored.split(':')[0]),stored)
def topics(c):
 out=[]
 for r in c.execute('SELECT * FROM topics'):
  t=dict(r);t['prereqs']=json.loads(t['prereqs']);t['details']=LESSONS.get(t['id'],[]);out.append(t)
 return out
def report(c,uid):
 ts=topics(c)
 completed={r[0] for r in c.execute('SELECT topic FROM completed_lessons WHERE user_id=?',(uid,))}
 for t in ts:
  t['completed']=t['id'] in completed
  rows=c.execute('SELECT correct FROM attempts JOIN questions ON questions.id=question_id WHERE user_id=? AND topic=? ORDER BY attempts.id DESC LIMIT 10',(uid,t['id'])).fetchall()
  t.update(attempts=len(rows),mastery=round(sum(r[0] for r in rows)/len(rows)*100) if rows else None)
 ordered=sorted(ts,key=lambda t:(t['mastery'] if t['mastery'] is not None else 50,-t['attempts']))
 target=ordered[0] if ordered else None
 if target:
  lookup={t['id']:t for t in ts};weak=[lookup[p] for p in target['prereqs'] if lookup[p]['mastery'] is None or lookup[p]['mastery']<70]
  chosen=weak[0] if weak else target
  reason=('先巩固「'+target['title']+'」的前置知识。') if weak else ('根据最近答题记录，优先练习这一知识点。' if chosen['attempts'] else '当前证据不足，先测评以建立学习起点。')
 else: chosen=None;reason='暂无内容'
 stats=c.execute('SELECT COUNT(*),COALESCE(SUM(correct),0) FROM attempts WHERE user_id=?',(uid,)).fetchone()
 days=[dict(r) for r in c.execute("SELECT date(created,'unixepoch','+8 hours') AS day,COUNT(*) AS total,SUM(correct) AS correct FROM attempts WHERE user_id=? AND created>=? GROUP BY day ORDER BY day",(uid,time.time()-86400*7))]
 # 3.6.3: the review badge shows what is due now (same count as the review page), not the wrong-answer total.
 try:
  import adaptive_service;rs=adaptive_service.review_status(c,uid);due=rs['due_grammar']+rs['due_words']
 except Exception:due=None
 return {'topics':ts,'recommended':chosen,'reason':reason,'total':stats[0],'correct':stats[1],'wrong_count':len(wrong_questions(c,uid)),'due_review':due,'completed':len(completed),'days':days}
class Handler(BaseHTTPRequestHandler):
 def setup(self):
  super().setup();self.connection.settimeout(45)
 def log_message(self,*args): pass
 def send(self,obj,status=200,cookie=None):
  if getattr(self,'ai_transport',None):return self.ai_transport.finish(obj,status)
  body=public_text(json.dumps(obj,ensure_ascii=False)).encode(); self.send_response(status);self.headers_common('application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
  renew,self.renew=getattr(self,'renew',None),None
  if cookie:self.send_header('Set-Cookie',cookie)
  elif renew:self.send_header('Set-Cookie',session_cookie(renew))  # a session in use stays signed in (user())
  self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def headers_common(self,mime):
  self.send_header('Permissions-Policy','camera=(), geolocation=(), microphone=(self)')
  self.send_header('Content-Type',mime);self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','same-origin');self.send_header('Content-Security-Policy',csp())
  if CHANNEL=='beta':self.send_header('X-Robots-Tag','noindex, nofollow')  # the 内测版 stays out of search results
 def visitor_address(self):
  ip=self.client_address[0]
  if ip in ('127.0.0.1','::1'):
   for header in ('CF-Connecting-IP','X-Real-IP'):
    try:return str(ipaddress.ip_address(self.headers.get(header,'').strip()))
    except ValueError:pass
  return ip
 def send_audio(self,path):
  # /audio/<voice>/<material>.(m4a|json): pre-generated narration; /audio/words/<accent>/<sprite>.m4a: word pronunciations;
  # /audio/tts/<voice>/<hash>.mp3: a sentence the server voice made (tts_service).
  # Byte ranges so Safari can seek.
  # /audio/words/<accent>/<sprite>.aac?s=<start>&e=<end>: one word cut from its sprite with silence in front (word_clip:
  # an iPhone waking its audio lost the start of a word played from the middle of the sprite).
  import next_service
  parts=path.split('/');data=None;mime=None
  if len(parts)==5 and parts[2]=='words' and parts[4][-4:] in ('.m4a','.mp4'):f=__import__('vocab_service').word_audio_file(parts[3],parts[4][:-4])
  elif len(parts)==5 and parts[2]=='words' and parts[4].endswith('.aac'):
   f=__import__('vocab_service').word_audio_file(parts[3],parts[4][:-4]);q=parse_qs(urlsplit(self.path).query)
   try:data=__import__('word_clip').clip(f,float(q.get('s',[''])[0]),float(q.get('e',[''])[0])) if f and f.is_file() else None
   except (ValueError,OSError,IndexError,KeyError,StopIteration,TypeError,__import__('struct').error):data=None
   f=f if data else None;mime='audio/aac'
  elif len(parts)==4 and parts[3].endswith('.aac'):
   # /audio/<voice>/<material>.aac?v=&s=&e=: one sentence of a narration, cut the same way (played by Web Audio on iPhones)
   f=next_service.audio_file(parts[2],parts[3][:-4],'m4a');q=parse_qs(urlsplit(self.path).query);wc=__import__('word_clip')
   try:data=wc.clip(f,float(q.get('s',[''])[0]),float(q.get('e',[''])[0]),wc.SENTENCE) if f and f.is_file() else None
   except (ValueError,OSError,IndexError,KeyError,StopIteration,TypeError,__import__('struct').error):data=None
   f=f if data else None;mime='audio/aac'
  elif len(parts)==5 and parts[2]=='tts':f=__import__('tts_service').file(parts[3],parts[4])
  else:f=next_service.audio_file(parts[2],parts[3].rsplit('.',1)[0],parts[3].rsplit('.',1)[-1]) if len(parts)==4 and '.' in parts[3] else None
  if not f:return self.send({'error':'音频不存在'},404)
  data=data if data is not None else f.read_bytes();size=len(data);start,end=0,size-1;status=200
  rng=self.headers.get('Range','')
  if rng.startswith('bytes='):
   a,_,b=rng[6:].split(',')[0].partition('-')
   try:
    if a:start=int(a);end=int(b) if b else size-1
    else:start=max(0,size-int(b))
    end=min(end,size-1)
    if start>end or start>=size:raise ValueError
    status=206
   except ValueError:
    self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.send_header('Content-Length','0');self.end_headers();return
  body=data[start:end+1]
  self.send_response(status);self.headers_common(mime or {'.m4a':'audio/mp4','.mp3':'audio/mpeg'}.get(f.suffix,'application/json; charset=utf-8'))
  self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','public, max-age=604800')
  if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def user(self,c):
  self.renew=None
  jar=SimpleCookie()
  try:jar.load(self.headers.get('Cookie',''))
  except Exception:return None
  token=jar['flow_session'].value if 'flow_session' in jar else ''
  now=time.time()
  # an account an operator stopped (xmc.hk console) has no session: its sessions are deleted and none is read
  u=c.execute('SELECT users.id,username,admin,csrf,token,expires,email,age_band,guardian_ok FROM sessions JOIN users ON users.id=user_id WHERE token=? AND expires>? AND NOT COALESCE(users.disabled,0)',(token,now)).fetchone()
  # Sliding sessions: a learner who keeps coming back stays signed in; SESSION_DAYS after the last visit it ends.
  # At most one write a day per session; the cookie is renewed with the same answer (send()).
  if u and u['expires']<now+(SESSION_DAYS-1)*86400:
   c.execute('UPDATE sessions SET expires=? WHERE token=?',(now+SESSION_DAYS*86400,token));c.commit();self.renew=token
  return u
 def do_GET(self):
  try:self.get()
  except (BrokenPipeError,ConnectionResetError):pass
  except (ValueError,TypeError):self.send({'error':'材料或请求参数不正确'},400)
  except Exception as exc:__import__('ops_errors').record(db,'GET',self.path,exc);self.send({'error':'服务暂时异常，请稍后重试'},500)
 def get(self):
  path=self.path.split('?')[0]
  if path.startswith('/api/') and not api_open('GET',path):return self.send({'error':'接口不存在'},404)
  if path=='/api/health':return self.send({'ok':True,'version':'4.5.0','mail':account.configured(),'channel':CHANNEL})
  # The version of next.js/next.css the server sends now: a home-screen app asleep for days asks it when it wakes
  # (04-home-app.js) and takes a new one when it is safe to. No database, nothing about anyone.
  if path=='/api/version':return self.send({'asset':asset_version()})
  if path=='/robots.txt':
   body=('User-agent: *\nDisallow: /\n' if CHANNEL=='beta' else 'User-agent: *\nDisallow: /api/\nAllow: /\n').encode()
   self.send_response(200);self.headers_common('text/plain; charset=utf-8');self.send_header('Cache-Control','public, max-age=3600')
   self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path=='/api/survey':sv=__import__('survey_service');return self.send(sv.definition(parse_qs(urlsplit(self.path).query).get('s',[''])[0]))  # ?s=trial: the class trial survey
  if path=='/api/deploy-status':
   # Written by tools/flow-autodeploy.py: release tag, commit, result, health checks and test counts. Nothing private.
   try:st=json.loads((DATA/'deploy-status.json').read_text())
   except (OSError,ValueError):st={}
   try:st['daily']=json.loads((DATA/'e2e-daily.json').read_text())  # the daily end-to-end test (flow-autodeploy.py)
   except (OSError,ValueError):pass
   st['live']=live_status()
   try:
    with db() as c:__import__('flow_admin').note_release(c,st)
   except Exception:pass
   body=json.dumps(st,ensure_ascii=False).encode()
   self.send_response(200);self.headers_common('application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
   self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path=='/api/next/vocab/reminder.ics':
   # A daily calendar event: a reminder that works on every phone without an app, email or push service.
   q=parse_qs(urlsplit(self.path).query);hour=q.get('hour',['20'])[0];kind=q.get('kind',['vocab'])[0];mins=q.get('minutes',['10'])[0]
   body=__import__('vocab_service').ics(int(hour) if hour.isdigit() else 20,'plan' if kind=='plan' else 'vocab',int(mins) if mins.isdigit() else 10).encode()
   self.send_response(200);self.headers_common('text/calendar; charset=utf-8');self.send_header('Content-Disposition','attachment; filename="flow-'+('plan' if kind=='plan' else 'review')+'.ics"')
   self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path.startswith('/api/'):
   with db() as c:
    u=self.user(c)
    if path=='/api/session':return self.send(session_info(u))
    if path.startswith('/api/next/export/'):
     # 我的 → 我的数据: the word book for Excel or Anki, or every record of the account (account_data.py)
     if not u:return self.send({'error':'请先登录'},401)
     ad=__import__('account_data');out=ad.export(c,u,path)
     if out is None:return self.send({'error':'接口不存在'},404)
     body,mime,ascii_name,name=out
     self.send_response(200);self.headers_common(mime);self.send_header('Content-Disposition',ad.disposition(ascii_name,name))
     self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
    if path.startswith('/api/next/'):
     q=parse_qs(urlsplit(self.path).query)
     if path=='/api/next/home' and u:q={k:v for k,v in q.items() if k not in ('level','themes')}  # a guest's choices; signed in, the profile decides
     result=__import__('next_service').get(c,u['id'] if u else None,path,q)
     if path=='/api/next/home' and result and result[1]==200:result[0]['session']=session_info(u)
     return self.send(*result) if result is not None else self.send({'error':'接口不存在'},404)
    if not u:return self.send({'error':'请先登录'},401)
    result=core_words.get(c,path,parse_qs(urlsplit(self.path).query))
    if result is not None:return self.send(*result)
    result=meeting.get(c,u['id'],u['admin'],path)
    if result is not None:return self.send(*result)
    if path=='/api/ai/status':
     configured=bool(os.getenv('FLOW_AI_MODEL')) and (bool(os.getenv('GOOGLE_CLOUD_PROJECT')) if vertex_enabled() else bool(os.getenv('FLOW_AI_KEY')) and __import__('chat_service').endpoint_ok(os.getenv('FLOW_AI_URL','')))
     last=c.execute("SELECT MAX(updated) FROM lab_jobs WHERE user_id=? AND status='complete'",(u['id'],)).fetchone()[0]
     chat_last=c.execute("SELECT MAX(updated) FROM chat_turns WHERE user_id=? AND status='complete' AND finish_reason!='lesson'",(u['id'],)).fetchone()[0]
     last=max(last or 0,chat_last or 0) or None
     return self.send({'configured':configured,'last_success':last,'model':ai_model_label() if configured else '','provider':'Vertex ADC' if vertex_enabled() else '兼容网关','message':'当前账号有成功记录；不代表此刻所有能力可用，音频与检索仍需分别实测。' if last else '配置字段齐全，但当前账号尚无成功记录，请运行部署实测。' if configured else '配置字段不完整，请管理员检查接口、模型与凭据。'})
    if path=='/api/daily/suggestions':
     pack_id=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
     row=c.execute("SELECT content FROM lab_packs WHERE id=? AND owner IS NULL AND origin='daily'",(pack_id,)).fetchone()
     if not row:return self.send({'error':'来源不存在'},404)
     html=json.loads(row['content']).get('provenance',{}).get('suggestions','').encode()
     self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Cache-Control','no-store')
     self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
     self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; img-src https: data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'; sandbox allow-popups allow-popups-to-escape-sandbox")
     self.send_header('Content-Length',str(len(html)));self.end_headers();self.wfile.write(html);return
    if path=='/api/graph':return self.send(graph_engine.network(c,u['id']))
    if path=='/api/graph/node':return self.send(graph_engine.detail(c,u['id'],parse_qs(urlsplit(self.path).query).get('id',[''])[0]))
    result=settings_store.get_route(c,u['id'],path)
    if result is not None:return self.send(*result)
    result=foundation.get(c,u['id'],path,parse_qs(urlsplit(self.path).query))
    if result is not None:return self.send(*result)
    result=practice.get(c,u['id'],path,parse_qs(urlsplit(self.path).query))
    if result is not None:return self.send(*result)
    result=reference.get(c,u['id'],path,parse_qs(urlsplit(self.path).query))
    if result is not None:return self.send(*result)
    result=growth.get(c,u['id'],u['admin'],path,parse_qs(urlsplit(self.path).query))
    if result is not None:return self.send(*result)
    result=coach.get(c,u['id'],path,parse_qs(urlsplit(self.path).query))
    if result is not None:return self.send(*result)
    result=adaptive.get(c,u['id'],u['admin'],path,parse_qs(urlsplit(self.path).query))
    if result is not None:return self.send(*result)
    if path=='/api/pilot/audio':
     body=__import__('pilot_service').audio(c,u['id'],parse_qs(urlsplit(self.path).query))
     if body is None:return self.send({'error':'音频不存在或未开放'},404)
     self.send_response(200);self.headers_common('audio/mp4');self.send_header('Cache-Control','private, max-age=3600');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
    result=__import__('pilot_service').get(c,u['id'],u['admin'],path,parse_qs(urlsplit(self.path).query))
    if result is not None:return self.send(*result)
    if path=='/api/knowledge':return self.send(knowledge.graph(c,u['id']))
    if path=='/api/daily':return self.send(daily.status(c))
    result=lab.get(c,u['id'],path,parse_qs(urlsplit(self.path).query))
    if result is not None:return self.send(*result)
    result=learning.get(c,u['id'],u['admin'],path,parse_qs(urlsplit(self.path).query))
    if result is not None:return self.send(*result)
    if path=='/api/account':
     result=account.private(c,u,path,{},verify);return self.send(*result)
    if path=='/api/dashboard':return self.send(report(c,u['id']))
    if path=='/api/chat/history':
     topic=parse_qs(urlsplit(self.path).query).get('topic',[''])[0];out,status=chat_history(c,u['id'],topic);return self.send(out,status)
    if path=='/api/wrongs':return self.send({'items':[dict(r) for r in wrong_questions(c,u['id'])]})
    if path=='/api/history':return self.send({'items':[dict(r) for r in c.execute('SELECT prompt,selected,correct,questions.explanation,created,options FROM attempts JOIN questions ON questions.id=question_id WHERE user_id=? ORDER BY attempts.id DESC LIMIT 50',(u['id'],))]})
   return self.send({'error':'接口不存在'},404)
  if path=='/classic' or (path.startswith('/practice/') and path.endswith('/')):
   # archived classic pages: an old bookmark lands on the learning site
   self.send_response(302);self.send_header('Location','/');self.send_header('Content-Length','0');self.end_headers();return
  files={'/sw.js':('sw.js','text/javascript; charset=utf-8'),
   '/manifest.webmanifest':('manifest.webmanifest','application/manifest+json; charset=utf-8'),
   '/icon-192.png':('icon-192.png','image/png'),
   '/icon-512.png':('icon-512.png','image/png'),
   '/apple-touch-icon.png':('apple-touch-icon.png','image/png'),
   '/next':('next.html','text/html; charset=utf-8'),
   '/next.js':('next.js','text/javascript; charset=utf-8'),
   '/next.css':('next.css','text/css; charset=utf-8'),
   '/survey':('survey.html','text/html; charset=utf-8'),
   '/about':('about.html','text/html; charset=utf-8'),
   '/about.js':('about.js','text/javascript; charset=utf-8'),
   '/about.css':('about.css','text/css; charset=utf-8'),
   '/survey.js':('survey.js','text/javascript; charset=utf-8'),
   '/survey.css':('survey.css','text/css; charset=utf-8'),
   '/literata.woff2':('literata.woff2','font/woff2')}
  if path=='/guide.pdf' or (path.startswith('/guide/') and path.endswith('.jpg') and path[7:-4].replace('-','').isalnum() and path[7:-4].isascii()):
   # the 操作指南: its screenshots and the PDF made from the same source (user_guide.py)
   f=ROOT/'public'/'guide'/('flow-guide.pdf' if path=='/guide.pdf' else path[7:])
   if not f.is_file():return self.send({'error':'页面不存在'},404)
   body=f.read_bytes();self.send_response(200);self.headers_common('application/pdf' if path=='/guide.pdf' else 'image/jpeg')
   if path=='/guide.pdf':self.send_header('Content-Disposition',"inline; filename=\"flow-guide.pdf\"; filename*=UTF-8''%E8%AF%AD%E6%B5%81%E6%93%8D%E4%BD%9C%E6%8C%87%E5%8D%97.pdf")
   self.send_header('Cache-Control','public, max-age=3600');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path.startswith('/about/') and path.endswith('.jpg') and path[7:-4].replace('-','').isalnum() and path[7:-4].isascii():
   # 认识语流's screenshots
   f=ROOT/'public'/'about'/path[7:]
   if not f.is_file():return self.send({'error':'页面不存在'},404)
   body=f.read_bytes();self.send_response(200);self.headers_common('image/jpeg')
   self.send_header('Cache-Control','public, max-age=86400');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path=='/about/':
   self.send_response(301);self.send_header('Location','/about');self.send_header('Content-Length','0');self.end_headers();return
  if path.startswith('/audio/'):
   return self.send_audio(path)
  if path=='/':
   # The learning site is the only site: any query string (old /?classic=1, /?account=1#login, trial links) opens it too.
   # The page opens from the browser's own copy at once and is fetched again in the background for next time
   # (stale-while-revalidate): iPhone WeChat has no service worker, so without this every opening first waited for a
   # round trip to the server (0.1-0.7 s from the mainland, r26 data). The copy names its own next.js/next.css version,
   # so an old copy runs the release it came with, once; sw.js fetches this page with cache 'no-cache', so phones with
   # the service worker get a new release exactly as before.
   body=shell_file('next.html')
   self.send_response(200);self.headers_common('text/html; charset=utf-8');self.send_header('Cache-Control',PAGE_CACHE)
   self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path not in files:return self.send({'error':'页面不存在'},404)
  name,mime=files[path];body=shell_file(name);self.send_response(200);self.headers_common(mime)
  # next.js and next.css under their current ?v= never change, so browsers and Cloudflare may keep them for a year;
  # any other version asked for (an old page) gets today's file and must check again.
  v=parse_qs(urlsplit(self.path).query).get('v',[''])[0]
  versioned=(name in ('next.js','next.css') and v==asset_version()) or (name in ABOUT_ASSETS and v==asset_version(ABOUT_ASSETS))
  self.send_header('Cache-Control','public, max-age=31536000, immutable' if name.endswith('.woff2') or versioned else 'no-cache');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_POST(self):
  try:self.post()
  except (ValueError,KeyError,TypeError,json.JSONDecodeError):self.send({'error':'请求格式或参数不正确'},400)
  except sqlite3.IntegrityError:self.send({'error':'用户名已存在，或数据关联无效'},409)
  except Exception as exc:__import__('ops_errors').record(db,'POST',self.path,exc);self.send({'error':'服务暂时异常，请稍后重试'},500)
  finally:
   import ai_jobs
   ai_jobs.leave(getattr(self,'ai_ticket',None))
   if getattr(self,'ai_transport',None):
    self.ai_transport.stop.set()
    import ai_stream
    ai_stream.LOCAL.callback=None
 def post(self):
  length=int(self.headers.get('Content-Length',0))
  # /api/feedback: up to three screenshots shrunk on the phone, sent as base64; under nginx's 3 MB (client_max_body_size 3m)
  limit=2900000 if self.path=='/api/feedback' else 2200000 if self.path in ('/api/lab/audio','/api/next/shadow','/api/next/retell','/api/next/dialog','/api/next/say','/api/next/ielts') else 800000 if self.path=='/api/vocab/import' else 40000 if self.path in ('/api/next/import','/api/next/essay','/api/next/dialog') else 20000
  if length<1 or length>limit:return self.send({'error':'请求大小不正确'},400)
  if self.headers.get('Sec-Fetch-Site')=='cross-site':return self.send({'error':'不允许跨站请求'},403)
  if not api_open('POST',self.path.split('?')[0]):return self.send({'error':'接口不存在'},404)
  if self.path=='/api/lab/audio':
   with db() as c:
    owner=self.user(c)
    if not owner:return self.send({'error':'请先登录'},401)
    if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),owner['csrf']):return self.send({'error':'安全校验失败'},403)
  if self.path.startswith('/api/next/weekly-mail/off?'):
   # RFC 8058 one-click unsubscribe from a mail app's own button: a form post to the List-Unsubscribe address
   body=self.rfile.read(length).decode('utf-8','replace')
   if body.strip()!='List-Unsubscribe=One-Click':return self.send({'error':'请求格式不正确'},400)
   with db() as c:return self.send(*__import__('progress_service').unsubscribe(c,parse_qs(urlsplit(self.path).query).get('t',[''])[0]))
  data=json.loads(self.rfile.read(length));path=self.path
  if not isinstance(data,dict):return self.send({'error':'请求必须为 JSON 对象'},400)
  if path=='/api/survey':
   # Anonymous: no session lookup; the address is only used for a short-lived hashed rate limit.
   with db() as c:return self.send(*__import__('survey_service').submit(c,data,self.visitor_address()))
  if path=='/api/feedback':
   # Signed in or not: the account is attached only with the session's CSRF token; a guest is limited by a hashed address.
   with db() as c:
    u=self.user(c);signed=bool(u) and hmac.compare_digest(self.headers.get('X-CSRF-Token',''),u['csrf'])
    return self.send(*__import__('feedback_service').submit(c,data,self.visitor_address(),u['id'] if signed else None))
  if path in ('/api/next/issues','/api/next/opentime'):
   # What the browser reports about the site itself (field_service): no session, no address; the User-Agent only for
   # its family (iPhone · Safari, Android · 微信 …).
   with db() as c:
    f=__import__('field_service')
    return self.send(*(f.issues if path=='/api/next/issues' else f.open_time)(c,data,self.headers.get('User-Agent','')))
  if path.startswith('/api/next/'):
   import next_service
   with db() as c:
    u=self.user(c)
    # Open routes still record progress for a signed-in learner: only with the session's CSRF token (else as a guest).
    signed=bool(u) and hmac.compare_digest(self.headers.get('X-CSRF-Token',''),u['csrf'])
    result=next_service.post_public(c,u['id'] if signed else None,path,data)
    if result is not None:return self.send(*result)
    if not u:return self.send({'error':'请先登录'},401)
    if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),u['csrf']):return self.send({'error':'安全校验失败，请刷新页面'},403)
    held=__import__('privacy_service').gate(u,path)  # under 14 without a guardian's agreement: no AI on the learner's own words
    if held:return self.send(*held)
    if path in next_service.AI_PATHS:
     import ai_jobs
     try:self.ai_ticket=ai_jobs.enter(u['id'])
     except TimeoutError:return self.send({'error':'排队较久，本次未调用模型，请稍后重试。'},503)
    result=next_service.post(c,u['id'],path,data)
    return self.send(*result) if result is not None else self.send({'error':'接口不存在'},404)
  if path==meeting.FIRST_TASK:
   if not meeting.valid_id(data.get('visitor')) or data.get('action')=='hint':
    return self.send(*meeting.preview(data))
   with db() as c:
    result=meeting.preview(data,c)
    c.commit();return self.send(*result)
  if path.startswith('/api/recovery/'):
   with db() as c:
    ip=self.client_address[0]
    if ip in ('127.0.0.1','::1'):
     try:ip=str(ipaddress.ip_address(self.headers.get('X-Real-IP',ip)))
     except ValueError:pass
    result=account.public(c,path,data,password,ip)
    if result is not None:return self.send(*result)
  if path in ['/api/login','/api/register','/api/auth/code','/api/auth/reset']:
   # Rate-limit by directly connected address; loopback proxy intentionally shares a ceiling.
   key=self.client_address[0]
   if key in ('127.0.0.1','::1'):
    try:key=str(ipaddress.ip_address(self.headers.get('X-Real-IP',key)))
    except ValueError:pass
   # Code requests have their own per-email and per-address caps (auth_service).
   if path!='/api/auth/code':
    with LOCK:
     now=time.time();times=[t for t in RATE.get(key,[]) if t>now-60];RATE[key]=times
     if len(times)>=30:return self.send({'error':'操作过于频繁，请稍后再试'},429)
     times.append(now)
   import auth_service
   with db() as c:
    if path=='/api/auth/code':return self.send(*auth_service.request(c,data,key))
    # 3.6: sign-up needs a verified email code; login accepts username/email + password or email + code.
    # r19: a forgotten password is reset with an emailed code, which also signs the learner in.
    u,problem=auth_service.register(c,data,password) if path=='/api/register' else auth_service.reset(c,data,password) if path=='/api/auth/reset' else auth_service.login(c,data,verify)
    if problem:return self.send(*problem)
    if 'disabled' in u.keys() and u['disabled']:return self.send({'error':'这个账号已停用。如有疑问，请联系语流。','code':'disabled'},403)
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
    c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),));c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token,u['id'],csrf,time.time()+SESSION_DAYS*86400))
   return self.send({'ok':True,'username':u['username']},cookie=session_cookie(token))
  with db() as c:
   u=self.user(c)
   if not u:return self.send({'error':'登录已过期'},401)
   if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),u['csrf']):return self.send({'error':'安全校验失败，请刷新页面'},403)
   if path=='/api/account/age':return self.send(*__import__('privacy_service').set_age(c,u['id'],data))  # 年龄段, asked later
   held=__import__('privacy_service').gate(u,path)
   if held:return self.send(*held)
   if path=='/api/account/delete':
    # 注销账号: the password once more, then everything the account has is deleted (account_data.py)
    result=__import__('account_data').erase(c,u,data,verify)
    return self.send(*result,cookie='flow_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax' if result[1]==200 else None)
   result=meeting.post(c,u['id'],path,data)
   if result is not None:
    c.commit();return self.send(*result)
   import ai_stream
   if path in ai_stream.PATHS and self.headers.get('Accept')=='text/event-stream':
    self.ai_transport=ai_stream.Transport(self,path)
    ai_stream.LOCAL.callback=self.ai_transport.write
    ai_stream.LOCAL.structured=path!='/api/chat'
    import ai_jobs
    try:self.ai_ticket=ai_jobs.enter(u['id'],cancelled=lambda:self.ai_transport.closed)
    except ConnectionAbortedError:return
    except TimeoutError:return self.send({'error':'排队较久，本次未调用模型。草稿保留，可稍后重试。'},503)
    current=self.user(c)
    if not current or not hmac.compare_digest(current['csrf'],u['csrf']):return self.send({'error':'登录已过期，请重新登录'},401)
   if path=='/api/ai/help':
    import ai_help_service
    return self.send(*ai_help_service.help(c,u['id'],data))
   result=settings_store.post_route(c,u['id'],path,data)
   if result is not None:return self.send(*result)
   result=attempts.post(c,u['id'],path,data)
   if result is not None:return self.send(*result)
   result=foundation.post(c,u['id'],path,data)
   if result is not None:return self.send(*result)
   result=practice.post(c,u['id'],path,data)
   if result is not None:return self.send(*result)
   result=reference.post(c,u['id'],path,data)
   if result is not None:return self.send(*result)
   result=growth.post(c,u['id'],u['admin'],path,data)
   if result is not None:return self.send(*result)
   result=coach.post(c,u['id'],path,data)
   if result is not None:return self.send(*result)
   result=__import__('pilot_service').post(c,u['id'],u['admin'],path,data)
   if result is not None:return self.send(*result)
   result=adaptive.post(c,u['id'],u['admin'],path,data)
   if result is not None:return self.send(*result)
   result=lab.post(c,u['id'],path,data)
   if result is not None:return self.send(*result)
   result=account.private(c,u,path,data,verify)
   if result is not None:return self.send(*result)
   result=learning.post(c,u['id'],u['admin'],path,data,tutor_chat)
   if result is not None:return self.send(*result)
   if path=='/api/logout':
    # {"all": true} signs this account out on every device (a lost phone, a shared computer).
    if data.get('all') is True:c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
    else:c.execute('DELETE FROM sessions WHERE token=?',(u['token'],))
    c.commit();return self.send({'ok':True},cookie='flow_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax')
   if path=='/api/password':
    old=str(data.get('old_password',''));new=str(data.get('new_password',''))
    if not 10<=len(new)<=200:return self.send({'error':'新密码需 10–200 个字符'},400)
    stored=c.execute('SELECT password FROM users WHERE id=?',(u['id'],)).fetchone()[0]
    if not verify(old,stored):return self.send({'error':'原密码不正确'},400)
    if old==new:return self.send({'error':'新密码不能与原密码相同'},400)
    c.execute('UPDATE users SET password=? WHERE id=?',(password(new),u['id']))
    c.execute('UPDATE recovery_tokens SET used=1 WHERE user_id=?',(u['id'],))
    c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],));c.commit()
    account.password_changed(c,u['id'],'在「我的」里修改')
    return self.send({'ok':True},cookie='flow_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax')
   if path=='/api/lesson/complete':
    topic=data.get('topic')
    if not c.execute('SELECT 1 FROM topics WHERE id=?',(topic,)).fetchone():raise ValueError()
    c.execute('INSERT OR IGNORE INTO completed_lessons VALUES(?,?,?)',(u['id'],topic,time.time()));c.commit()
    return self.send({'ok':True})
   if path=='/api/quiz':
    topic=data.get('topic')
    rows=learning.quiz_rows(c,u['id'],data)
    entry='node' if data.get('node') else 'review' if data.get('mode')=='review' else 'wrongs' if data.get('mode')=='wrongs' else 'topic' if topic else 'diagnostic'
    if rows is not None:pass
    elif data.get('mode')=='wrongs':
     rows=wrong_questions(c,u['id'])[:12]
    elif topic:
     rows=c.execute('SELECT id,topic,prompt,options FROM questions WHERE status="published" AND topic=? ORDER BY RANDOM() LIMIT 10',(topic,)).fetchall()
    else:
     rows=[]
     for t in c.execute('SELECT id FROM topics ORDER BY id'):
      rows.extend(c.execute('SELECT id,topic,prompt,options FROM questions WHERE status="published" AND topic=? ORDER BY RANDOM() LIMIT 2',(t[0],)).fetchall())
     rows=rows[:12]
    if not rows:
     if entry=='review':return self.send({'error':'现在没有到期的语法复习。','empty':True,'status':'none_due'},200)
     return self.send({'error':'暂无可用题目'},400)
    qs=[{k:r[k] for k in ('id','topic','prompt','options')} for r in rows]
    for q in qs:q['options']=json.loads(q['options'])
    c.execute('DELETE FROM quizzes WHERE expires<?',(time.time(),))
    token,items=attempts.open_session(c,u['id'],entry,[q['id'] for q in qs],data.get('node') or topic or '')
    familiar={i['question'] for i in items if i['familiar']}
    for q in qs:q['familiar']=q['id'] in familiar
    c.execute('INSERT INTO quizzes VALUES(?,?,?,?,0)',(token,u['id'],json.dumps([q['id'] for q in qs]),time.time()+3600));c.commit()
    return self.send({'token':token,'entry':entry,'questions':qs,'policy':attempts.POLICY,'hint_levels':attempts.HINT_LEVELS,'note':'近24小时做过的题会标为“熟悉题”，做对记为有支持的练习；看提示同样如此。' if familiar else '没看提示独立做对，才计入独立证据。'})
   if path=='/api/submit':
    c.execute('BEGIN IMMEDIATE')
    token=data['token'];answers=data['answers']
    quiz=c.execute('SELECT * FROM quizzes WHERE token=? AND user_id=? AND expires>?',(token,u['id'],time.time()-86400)).fetchone()
    session=attempts.get(c,u['id'],token)
    if quiz and quiz['used']:
     # Idempotent replay: the same answers return the stored result; different answers are refused.
     if session and session['status']=='complete' and session['signature']==attempts.signature(answers):c.rollback();return self.send({**json.loads(session['result']),'replayed':True})
     c.rollback();return self.send({'error':'这次测评已经提交过，答案不同的重复提交不会记录。'},409)
    if not quiz or quiz['expires']<time.time():c.rollback();return self.send({'error':'测评已过期，请重新开始'},400)
    ids=json.loads(quiz['ids'])
    if not isinstance(answers,dict) or set(answers)!=set(map(str,ids)):c.rollback();return self.send({'error':'请完成所有题目'},400)
    result=[]
    for qid in ids:
     q=c.execute('SELECT * FROM questions WHERE id=?',(qid,)).fetchone();a=answers[str(qid)]
     if type(a)!=int or not 0<=a<len(json.loads(q['options'])):raise ValueError()
     correct=a==q['answer'];result.append({'id':qid,'topic':q['topic'],'prompt':q['prompt'],'correct':correct,'answer':q['answer'],'selected':a,'options':json.loads(q['options']),'explanation':q['explanation']})
    # Recheck exposure now, in the same transaction as the write: another tab or entry may have shown an answer since this test opened.
    session=attempts.recheck(c,u['id'],session)
    support={qid:attempts.support(session,qid) for qid in ids} if session else None
    for q in result:
     q['attempt']=c.execute('INSERT INTO attempts(user_id,question_id,selected,correct,created) VALUES(?,?,?,?,?)',(u['id'],q['id'],q['selected'],q['correct'],time.time())).lastrowid
     if support:q['support']=support[q['id']]['support'];q['assisted']=support[q['id']]['assisted']
    learning.observe(c,u['id'],ids,support=support)
    from pedagogy_service import next_step
    out={'results':result,'score':round(sum(q['correct'] for q in result)/len(result)*100),'independent':sum(1 for q in result if q['correct'] and not q.get('assisted',True)),'policy':attempts.POLICY,'next_step':next_step(c,u['id'],return_to=data.get('return_to'))}
    if session and session.get('rechecked'):out['familiar_note']='有 '+str(len(session['rechecked']))+' 道题在你打开这次测评后，已在别处看过答案；这些题记为有支持的练习，不计独立通过。'
    c.execute('UPDATE quizzes SET used=1 WHERE token=?',(token,))
    if session:attempts.complete(c,token,answers,out)
    c.commit();return self.send(out)
   if path=='/api/chat':
    out,status=tutor_chat(c,u['id'],data);return self.send(out,status)
  self.send({'error':'接口不存在'},404)
if __name__=='__main__':
 init();parser=argparse.ArgumentParser();parser.add_argument('--create-admin',action='store_true')
 parser.add_argument('--reset-link',metavar='用户名或邮箱',help='给忘了密码、又没绑定邮箱的账号生成一次性重设链接（24 小时内有效）')
 args=parser.parse_args()
 if args.reset_link:
  with db() as c:body,status=account.admin_link(c,args.reset_link)
  if status!=200:raise SystemExit(body['error'])
  print(f"账号：{body['username']}\n重设链接（{body['hours']} 小时内有效，只能用一次；当面或私信发给本人，不要发到群里）：\n{body['link']}")
 elif args.create_admin:
  name=input('管理员用户名: ').strip();p=getpass.getpass('密码（至少10位）: ')
  if not 3<=len(name)<=40 or not 10<=len(p)<=200:raise SystemExit('用户名或密码长度不符合要求')
  with db() as c:c.execute('INSERT INTO users(username,password,admin,created) VALUES(?,?,1,?)',(name,password(p),time.time()))
  print('管理员已创建')
 else:
  import ai_jobs
  with db() as c:ai_jobs.recover_interrupted(c)
  __import__('flow_admin').start()
  def remind_loop():
   # Daily vocabulary reminder emails, at each learner's chosen hour (Asia/Shanghai), and the Sunday progress mail.
   while True:
    try:
     with db() as c:
      __import__('progress_service').send_weekly(c)  # Sunday evening, before the daily reminder: it says the words due too
      __import__('vocab_service').send_reminders(c)
    except Exception as exc:print('reminders failed:',type(exc).__name__,flush=True)
    try:
     with db() as c:__import__('ai_routes').tick(c)  # AI budget mails, the nightly marking check, old call rows pruned
    except Exception as exc:print('ai budget/check failed:',type(exc).__name__,flush=True)
    try:__import__('tts_service').tick(db)  # 03:00–05:00: the fixed sentences the server voice says, made while idle
    except Exception as exc:print('tts prewarm failed:',type(exc).__name__,flush=True)
    time.sleep(300)
  threading.Thread(target=remind_loop,daemon=True).start()
  class Server(ThreadingHTTPServer):
   request_queue_size=128  # the default (5) resets connections when a page fires many requests at once
   daemon_threads=True
  server=Server((os.getenv('FLOW_HOST','127.0.0.1'),int(os.getenv('FLOW_PORT','8090'))),Handler);print('Flow listening',server.server_address,flush=True);server.serve_forever()
