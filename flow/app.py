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
def wrong_questions(c,uid):
 return c.execute('''SELECT q.id,q.topic,q.prompt,q.options,q.explanation,q.answer,a.selected FROM questions q
 JOIN attempts a ON a.question_id=q.id WHERE q.status='published' AND a.user_id=? AND a.correct=0
 AND a.id=(SELECT MAX(b.id) FROM attempts b WHERE b.user_id=a.user_id AND b.question_id=a.question_id)
 ORDER BY a.id DESC''',(uid,)).fetchall()
def password(p,salt=None):
 salt=salt or secrets.token_hex(16); return salt+':'+hashlib.pbkdf2_hmac('sha256',p.encode(),bytes.fromhex(salt),260000).hex()
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
  if cookie:self.send_header('Set-Cookie',cookie)
  self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def headers_common(self,mime):
  self.send_header('Permissions-Policy','camera=(), geolocation=(), microphone=(self)')
  self.send_header('Content-Type',mime);self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','same-origin');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; frame-src 'self' about:; frame-ancestors 'none'")
 def visitor_address(self):
  ip=self.client_address[0]
  if ip in ('127.0.0.1','::1'):
   for header in ('CF-Connecting-IP','X-Real-IP'):
    try:return str(ipaddress.ip_address(self.headers.get(header,'').strip()))
    except ValueError:pass
  return ip
 def send_audio(self,path):
  # /audio/<voice>/<material>.(m4a|json): pre-generated narration; /audio/words/<accent>/<sprite>.m4a: word pronunciations.
  # Byte ranges so Safari can seek.
  import next_service
  parts=path.split('/')
  if len(parts)==5 and parts[2]=='words' and parts[4][-4:] in ('.m4a','.mp4'):f=__import__('vocab_service').word_audio_file(parts[3],parts[4][:-4])
  else:f=next_service.audio_file(parts[2],parts[3].rsplit('.',1)[0],parts[3].rsplit('.',1)[-1]) if len(parts)==4 and '.' in parts[3] else None
  if not f:return self.send({'error':'音频不存在'},404)
  data=f.read_bytes();size=len(data);start,end=0,size-1;status=200
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
  self.send_response(status);self.headers_common('audio/mp4' if f.suffix=='.m4a' else 'application/json; charset=utf-8')
  self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','public, max-age=604800')
  if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def user(self,c):
  jar=SimpleCookie()
  try:jar.load(self.headers.get('Cookie',''))
  except Exception:return None
  token=jar['flow_session'].value if 'flow_session' in jar else ''
  return c.execute('SELECT users.id,username,admin,csrf,token FROM sessions JOIN users ON users.id=user_id WHERE token=? AND expires>?',(token,time.time())).fetchone()
 def do_GET(self):
  try:self.get()
  except (BrokenPipeError,ConnectionResetError):pass
  except (ValueError,TypeError):self.send({'error':'材料或请求参数不正确'},400)
  except Exception:self.send({'error':'服务暂时异常，请稍后重试'},500)
 def get(self):
  path=self.path.split('?')[0]
  if path=='/api/health':return self.send({'ok':True,'version':'4.5.0','mail':account.configured()})
  if path=='/api/survey':return self.send(__import__('survey_service').SURVEY)
  if path=='/api/meeting/previews':
   return self.send({'previews':[meeting_path.task(day) for day in meeting_path.PUBLIC.values()]})
  if path=='/api/deploy-status':
   # Written by tools/flow-autodeploy.py: release tag, commit, result, health checks and test counts. Nothing private.
   try:body=(DATA/'deploy-status.json').read_bytes()
   except OSError:body=b'{}'
   self.send_response(200);self.headers_common('application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
   self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path=='/api/next/vocab/reminder.ics':
   # A daily calendar event: a reminder that works on every phone without an app, email or push service.
   hour=parse_qs(urlsplit(self.path).query).get('hour',['20'])[0]
   body=__import__('vocab_service').ics(int(hour) if hour.isdigit() else 20).encode()
   self.send_response(200);self.headers_common('text/calendar; charset=utf-8');self.send_header('Content-Disposition','attachment; filename="flow-review.ics"')
   self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path.startswith('/api/'):
   with db() as c:
    u=self.user(c)
    if path=='/api/session':return self.send({'user':dict(u) if u else None,'ai_enabled':ai_enabled()} if not u else {'user':{k:u[k] for k in ('id','username','admin','csrf')},'ai_enabled':ai_enabled()})
    if path.startswith('/api/next/'):
     result=__import__('next_service').get(c,u['id'] if u else None,path,parse_qs(urlsplit(self.path).query))
     return self.send(*result) if result is not None else self.send({'error':'接口不存在'},404)
    if not u:return self.send({'error':'请先登录'},401)
    result=core_words.get(c,path,parse_qs(urlsplit(self.path).query))
    if result is not None:return self.send(*result)
    result=meeting.get(c,u['id'],u['admin'],path)
    if result is not None:return self.send(*result)
    if path=='/api/ai/status':
     configured=bool(os.getenv('FLOW_AI_MODEL')) and (bool(os.getenv('GOOGLE_CLOUD_PROJECT')) if vertex_enabled() else bool(os.getenv('FLOW_AI_KEY')) and os.getenv('FLOW_AI_URL','').startswith('https://'))
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
    if path=='/api/manage/backup':
     if not u['admin']:return self.send({'error':'需要管理员权限'},403)
     status_file=DATA/'backup-status.json'
     return self.send({'last':json.loads(status_file.read_text()) if status_file.exists() else None})
    if path=='/api/account':
     result=account.private(c,u,path,{},verify);return self.send(*result)
    if path=='/api/dashboard':return self.send(report(c,u['id']))
    if path=='/api/chat/history':
     topic=parse_qs(urlsplit(self.path).query).get('topic',[''])[0];out,status=chat_history(c,u['id'],topic);return self.send(out,status)
    if path=='/api/wrongs':return self.send({'items':[dict(r) for r in wrong_questions(c,u['id'])]})
    if path=='/api/history':return self.send({'items':[dict(r) for r in c.execute('SELECT prompt,selected,correct,questions.explanation,created,options FROM attempts JOIN questions ON questions.id=question_id WHERE user_id=? ORDER BY attempts.id DESC LIMIT 50',(u['id'],))]})
    if path=='/api/admin':
     if not u['admin']:return self.send({'error':'需要管理员权限'},403)
     return self.send({'users':c.execute('SELECT COUNT(*) FROM users').fetchone()[0],'attempts':c.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],'questions':c.execute('SELECT COUNT(*) FROM questions').fetchone()[0],'ai_enabled':ai_enabled(),'ai_provider':'Vertex ADC' if vertex_enabled() else '兼容接口','ai_model':os.getenv('FLOW_AI_MODEL',''),'ai_daily_limit':int(os.getenv('FLOW_AI_DAILY_LIMIT','0'))})
   return self.send({'error':'接口不存在'},404)
  if path.startswith('/practice/') and path.endswith('/'):
   slug=path.removeprefix('/practice/').removesuffix('/')
   if slug in meeting_path.PUBLIC:
    body=meeting_path.public_page(slug)
    self.send_response(200);self.headers_common('text/html; charset=utf-8');self.send_header('Cache-Control','no-cache')
    self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  files={'/sw.js':('sw.js','text/javascript; charset=utf-8'),'/manifest.webmanifest':('manifest.webmanifest','application/manifest+json; charset=utf-8'),
   '/icon-192.png':('icon-192.png','image/png'),'/icon-512.png':('icon-512.png','image/png'),'/apple-touch-icon.png':('apple-touch-icon.png','image/png'),
   '/next':('next.html','text/html; charset=utf-8'),'/next.js':('next.js','text/javascript; charset=utf-8'),'/next.css':('next.css','text/css; charset=utf-8'),'/survey':('survey.html','text/html; charset=utf-8'),'/survey.js':('survey.js','text/javascript; charset=utf-8'),'/survey.css':('survey.css','text/css; charset=utf-8'),'/guest-first.js':('guest-first.js','text/javascript; charset=utf-8'),'/flow4.css':('flow4.css','text/css; charset=utf-8'),'/flow-motion.js':('flow-motion.js','text/javascript; charset=utf-8'),'/flow-mindmap.js':('flow-mindmap.js','text/javascript; charset=utf-8'),'/literata.woff2':('literata.woff2','font/woff2'),'/core-words.js':('core-words.js','text/javascript; charset=utf-8'),'/meeting.js':('meeting.js','text/javascript; charset=utf-8'),'/meeting.css':('meeting.css','text/css; charset=utf-8'),'/flow36.js':('flow36.js','text/javascript; charset=utf-8'),'/flow36.css':('flow36.css','text/css; charset=utf-8'),'/phone.css':('phone.css','text/css; charset=utf-8'),'/pilot.js':('pilot.js','text/javascript; charset=utf-8'),'/pilot.css':('pilot.css','text/css; charset=utf-8'),'/learning35.js':('learning35.js','text/javascript; charset=utf-8'),'/learning35.css':('learning35.css','text/css; charset=utf-8'),'/ai-live.js':('ai-live.js','text/javascript; charset=utf-8'),'/ai-live.css':('ai-live.css','text/css; charset=utf-8'),'/continuity.js':('continuity.js','text/javascript; charset=utf-8'),'/continuity.css':('continuity.css','text/css; charset=utf-8'),'/foundation.js':('foundation.js','text/javascript; charset=utf-8'),'/foundation.css':('foundation.css','text/css; charset=utf-8'),'/mobile.js':('mobile.js','text/javascript; charset=utf-8'),'/mobile.css':('mobile.css','text/css; charset=utf-8'),'/practice.js':('practice.js','text/javascript; charset=utf-8'),'/practice.css':('practice.css','text/css; charset=utf-8'),'/reference.js':('reference.js','text/javascript; charset=utf-8'),'/reference.css':('reference.css','text/css; charset=utf-8'),'/atlas.js':('atlas.js','text/javascript; charset=utf-8'),'/atlas.css':('atlas.css','text/css; charset=utf-8'),'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/tutor.js':('tutor.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/advanced.js':('advanced.js','text/javascript; charset=utf-8'),'/studio.js':('studio.js','text/javascript; charset=utf-8'),'/growth.js':('growth.js','text/javascript; charset=utf-8'),'/growth.css':('growth.css','text/css; charset=utf-8'),'/design-bridge.css':('design-bridge.css','text/css; charset=utf-8'),'/coach.js':('coach.js','text/javascript; charset=utf-8'),'/coach.css':('coach.css','text/css; charset=utf-8'),'/adaptive.js':('adaptive.js','text/javascript; charset=utf-8'),'/adaptive.css':('adaptive.css','text/css; charset=utf-8'),'/knowledge.js':('knowledge.js','text/javascript; charset=utf-8'),'/layout.css':('layout.css','text/css; charset=utf-8')}
  if path.startswith('/audio/'):
   return self.send_audio(path)
  if path=='/classic':
   self.send_response(302);self.send_header('Location','/?classic=1');self.send_header('Content-Length','0');self.end_headers();return
  if path=='/' and not urlsplit(self.path).query:
   # The Flow learning loop (next.html) is the main site; the classic site stays at /?classic=1
   # (any query string, e.g. old /?account=1#login and trial links, still opens the classic page).
   body=(ROOT/'public'/'next.html').read_bytes()
   self.send_response(200);self.headers_common('text/html; charset=utf-8');self.send_header('Cache-Control','no-cache')
   self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
  if path not in files:return self.send({'error':'页面不存在'},404)
  name,mime=files[path];body=(ROOT/'public'/name).read_bytes();self.send_response(200);self.headers_common(mime);self.send_header('Cache-Control','public, max-age=31536000, immutable' if name.endswith('.woff2') else 'no-cache');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def do_POST(self):
  try:self.post()
  except (ValueError,KeyError,TypeError,json.JSONDecodeError):self.send({'error':'请求格式或参数不正确'},400)
  except sqlite3.IntegrityError:self.send({'error':'用户名已存在，或数据关联无效'},409)
  except Exception:self.send({'error':'服务暂时异常，请稍后重试'},500)
  finally:
   import ai_jobs
   ai_jobs.leave(getattr(self,'ai_ticket',None))
   if getattr(self,'ai_transport',None):
    self.ai_transport.stop.set()
    import ai_stream
    ai_stream.LOCAL.callback=None
 def post(self):
  length=int(self.headers.get('Content-Length',0))
  limit=2200000 if self.path in ('/api/lab/audio','/api/next/shadow','/api/next/retell','/api/next/dialog','/api/next/say') else 800000 if self.path=='/api/vocab/import' else 40000 if self.path in ('/api/next/import','/api/next/essay','/api/next/dialog') else 20000
  if length<1 or length>limit:return self.send({'error':'请求大小不正确'},400)
  if self.headers.get('Sec-Fetch-Site')=='cross-site':return self.send({'error':'不允许跨站请求'},403)
  if self.path=='/api/lab/audio':
   with db() as c:
    owner=self.user(c)
    if not owner:return self.send({'error':'请先登录'},401)
    if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),owner['csrf']):return self.send({'error':'安全校验失败'},403)
  data=json.loads(self.rfile.read(length));path=self.path
  if not isinstance(data,dict):return self.send({'error':'请求必须为 JSON 对象'},400)
  if path=='/api/survey':
   # Anonymous: no session lookup; the address is only used for a short-lived hashed rate limit.
   with db() as c:return self.send(*__import__('survey_service').submit(c,data,self.visitor_address()))
  if path.startswith('/api/next/'):
   import next_service
   with db() as c:
    u=self.user(c)
    result=next_service.post_public(c,u['id'] if u else None,path,data)
    if result is not None:return self.send(*result)
    if not u:return self.send({'error':'请先登录'},401)
    if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),u['csrf']):return self.send({'error':'安全校验失败，请刷新页面'},403)
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
  if path in ['/api/login','/api/register','/api/auth/code']:
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
    u,problem=auth_service.register(c,data,password) if path=='/api/register' else auth_service.login(c,data,verify)
    if problem:return self.send(*problem)
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
    c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),));c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token,u['id'],csrf,time.time()+86400*7))
   return self.send({'ok':True},cookie='flow_session='+token+'; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800'+('; Secure' if SECURE else ''))
  with db() as c:
   u=self.user(c)
   if not u:return self.send({'error':'登录已过期'},401)
   if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),u['csrf']):return self.send({'error':'安全校验失败，请刷新页面'},403)
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
   if path=='/api/daily/run':
    if not u['admin']:return self.send({'error':'需要管理员权限'},403)
    def generate_daily():
     with db() as connection:daily.run(connection)
    threading.Thread(target=generate_daily,daemon=True).start()
    return self.send({'ok':True,'message':'已请求生成，稍后刷新查看；同日成功缓存不会重建。'},202)
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
    c.execute('DELETE FROM sessions WHERE token=?',(u['token'],));c.commit();return self.send({'ok':True},cookie='flow_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax')
   if path=='/api/password':
    old=str(data.get('old_password',''));new=str(data.get('new_password',''))
    if not 10<=len(new)<=200:return self.send({'error':'新密码需 10–200 个字符'},400)
    stored=c.execute('SELECT password FROM users WHERE id=?',(u['id'],)).fetchone()[0]
    if not verify(old,stored):return self.send({'error':'原密码不正确'},400)
    if old==new:return self.send({'error':'新密码不能与原密码相同'},400)
    c.execute('UPDATE users SET password=? WHERE id=?',(password(new),u['id']))
    c.execute('UPDATE recovery_tokens SET used=1 WHERE user_id=?',(u['id'],))
    c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],));c.commit()
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
   if path=='/api/admin/question':
    if not u['admin']:return self.send({'error':'需要管理员权限'},403)
    learning.save_question(c,u['id'],{**data,'status':'published'});c.commit();return self.send({'ok':True})
   if path=='/api/chat':
    out,status=tutor_chat(c,u['id'],data);return self.send(out,status)
  self.send({'error':'接口不存在'},404)
if __name__=='__main__':
 init();parser=argparse.ArgumentParser();parser.add_argument('--create-admin',action='store_true');args=parser.parse_args()
 if args.create_admin:
  name=input('管理员用户名: ').strip();p=getpass.getpass('密码（至少10位）: ')
  if not 3<=len(name)<=40 or not 10<=len(p)<=200:raise SystemExit('用户名或密码长度不符合要求')
  with db() as c:c.execute('INSERT INTO users(username,password,admin) VALUES(?,?,1)',(name,password(p)))
  print('管理员已创建')
 else:
  import ai_jobs
  with db() as c:ai_jobs.recover_interrupted(c)
  __import__('flow_admin').start()
  def remind_loop():
   # Daily vocabulary reminder emails, at each learner's chosen hour (Asia/Shanghai).
   while True:
    try:
     with db() as c:
      __import__('vocab_service').send_reminders(c)
      __import__('skills_service').send_weekly(c)
    except Exception as exc:print('reminders failed:',type(exc).__name__,flush=True)
    time.sleep(300)
  threading.Thread(target=remind_loop,daemon=True).start()
  class Server(ThreadingHTTPServer):
   request_queue_size=128  # the default (5) resets connections when a page fires many requests at once
   daemon_threads=True
  server=Server((os.getenv('FLOW_HOST','127.0.0.1'),int(os.getenv('FLOW_PORT','8090'))),Handler);print('Flow listening',server.server_address,flush=True);server.serve_forever()
