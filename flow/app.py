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
from seed import TOPICS,QUESTIONS
from content_v03 import EXTRA_QUESTIONS,LESSONS
from vertex_auth import vertex_enabled, ai_enabled, vertex_connection
ROOT=Path(__file__).resolve().parent
DATA=Path(os.environ.get('FLOW_DATA_DIR',str(ROOT/'data'))); DATA.mkdir(parents=True,exist_ok=True)
DB=DATA/'flow.sqlite3'
SECURE=os.getenv('FLOW_COOKIE_SECURE','1')=='1'
RATE={}; LOCK=threading.Lock()
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
  lab.schema(c)
  daily.schema(c)
  adaptive.schema(c)
  coach.schema(c)
  growth.schema(c)
  reference.schema(c)
  practice.schema(c)
  foundation.schema(c)
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
 return {'topics':ts,'recommended':chosen,'reason':reason,'total':stats[0],'correct':stats[1],'wrong_count':len(wrong_questions(c,uid)),'completed':len(completed),'days':days}
class Handler(BaseHTTPRequestHandler):
 def setup(self):
  super().setup();self.connection.settimeout(45)
 def log_message(self,*args): pass
 def send(self,obj,status=200,cookie=None):
  if getattr(self,'ai_transport',None):return self.ai_transport.finish(obj,status)
  body=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status);self.headers_common('application/json; charset=utf-8');self.send_header('Cache-Control','no-store')
  if cookie:self.send_header('Set-Cookie',cookie)
  self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
 def headers_common(self,mime):
  self.send_header('Permissions-Policy','camera=(), geolocation=(), microphone=(self)')
  self.send_header('Content-Type',mime);self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY');self.send_header('Referrer-Policy','same-origin');self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; media-src 'self' blob:; frame-src 'self' about:; frame-ancestors 'none'")
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
  if path=='/api/health':return self.send({'ok':True,'version':'3.4'})
  if path.startswith('/api/'):
   with db() as c:
    u=self.user(c)
    if path=='/api/session':return self.send({'user':dict(u) if u else None,'ai_enabled':ai_enabled()} if not u else {'user':{k:u[k] for k in ('id','username','admin','csrf')},'ai_enabled':ai_enabled()})
    if not u:return self.send({'error':'请先登录'},401)
    if path=='/api/ai/status':
     configured=bool(os.getenv('FLOW_AI_MODEL')) and (bool(os.getenv('GOOGLE_CLOUD_PROJECT')) if vertex_enabled() else bool(os.getenv('FLOW_AI_KEY')) and os.getenv('FLOW_AI_URL','').startswith('https://'))
     last=c.execute("SELECT MAX(updated) FROM lab_jobs WHERE user_id=? AND status='complete'",(u['id'],)).fetchone()[0]
     chat_last=c.execute("SELECT MAX(updated) FROM chat_turns WHERE user_id=? AND status='complete' AND finish_reason!='lesson'",(u['id'],)).fetchone()[0]
     last=max(last or 0,chat_last or 0) or None
     return self.send({'configured':configured,'last_success':last,'provider':'Vertex ADC' if vertex_enabled() else '兼容网关','message':'当前账号有成功记录；不代表此刻所有能力可用，音频与检索仍需分别实测。' if last else '配置字段齐全，但当前账号尚无成功记录，请运行部署实测。' if configured else '配置字段不完整，请管理员检查接口、模型与凭据。'})
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
  files={'/ai-live.js':('ai-live.js','text/javascript; charset=utf-8'),'/ai-live.css':('ai-live.css','text/css; charset=utf-8'),'/continuity.js':('continuity.js','text/javascript; charset=utf-8'),'/continuity.css':('continuity.css','text/css; charset=utf-8'),'/foundation.js':('foundation.js','text/javascript; charset=utf-8'),'/foundation.css':('foundation.css','text/css; charset=utf-8'),'/mobile.js':('mobile.js','text/javascript; charset=utf-8'),'/mobile.css':('mobile.css','text/css; charset=utf-8'),'/practice.js':('practice.js','text/javascript; charset=utf-8'),'/practice.css':('practice.css','text/css; charset=utf-8'),'/reference.js':('reference.js','text/javascript; charset=utf-8'),'/reference.css':('reference.css','text/css; charset=utf-8'),'/atlas.js':('atlas.js','text/javascript; charset=utf-8'),'/atlas.css':('atlas.css','text/css; charset=utf-8'),'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/tutor.js':('tutor.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8'),'/advanced.js':('advanced.js','text/javascript; charset=utf-8'),'/studio.js':('studio.js','text/javascript; charset=utf-8'),'/growth.js':('growth.js','text/javascript; charset=utf-8'),'/growth.css':('growth.css','text/css; charset=utf-8'),'/design-bridge.css':('design-bridge.css','text/css; charset=utf-8'),'/coach.js':('coach.js','text/javascript; charset=utf-8'),'/coach.css':('coach.css','text/css; charset=utf-8'),'/adaptive.js':('adaptive.js','text/javascript; charset=utf-8'),'/adaptive.css':('adaptive.css','text/css; charset=utf-8'),'/knowledge.js':('knowledge.js','text/javascript; charset=utf-8'),'/layout.css':('layout.css','text/css; charset=utf-8')}
  if path not in files:return self.send({'error':'页面不存在'},404)
  name,mime=files[path];body=(ROOT/'public'/name).read_bytes();self.send_response(200);self.headers_common(mime);self.send_header('Cache-Control','no-cache');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
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
  limit=2200000 if self.path=='/api/lab/audio' else 800000 if self.path=='/api/vocab/import' else 20000
  if length<1 or length>limit:return self.send({'error':'请求大小不正确'},400)
  if self.headers.get('Sec-Fetch-Site')=='cross-site':return self.send({'error':'不允许跨站请求'},403)
  if self.path=='/api/lab/audio':
   with db() as c:
    owner=self.user(c)
    if not owner:return self.send({'error':'请先登录'},401)
    if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),owner['csrf']):return self.send({'error':'安全校验失败'},403)
  data=json.loads(self.rfile.read(length));path=self.path
  if not isinstance(data,dict):return self.send({'error':'请求必须为 JSON 对象'},400)
  if path.startswith('/api/recovery/'):
   with db() as c:
    ip=self.client_address[0]
    if ip in ('127.0.0.1','::1'):
     try:ip=str(ipaddress.ip_address(self.headers.get('X-Real-IP',ip)))
     except ValueError:pass
    result=account.public(c,path,data,password,ip)
    if result is not None:return self.send(*result)
  if path in ['/api/login','/api/register']:
   # Rate-limit by directly connected address; loopback proxy intentionally shares a ceiling.
   key=self.client_address[0]
   if key in ('127.0.0.1','::1'):
    try:key=str(ipaddress.ip_address(self.headers.get('X-Real-IP',key)))
    except ValueError:pass
   with LOCK:
    now=time.time();times=[t for t in RATE.get(key,[]) if t>now-60];RATE[key]=times
    if len(times)>=30:return self.send({'error':'操作过于频繁，请稍后再试'},429)
    times.append(now)
   name=str(data.get('username','')).strip();p=str(data.get('password',''))
   if not 3<=len(name)<=40 or not 10<=len(p)<=200:return self.send({'error':'用户名需 3–40 个字符，密码需 10–200 个字符'},400)
   with db() as c:
    if path=='/api/register':c.execute('INSERT INTO users(username,password) VALUES(?,?)',(name,password(p)))
    u=c.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone()
    if not u or not verify(p,u['password']):return self.send({'error':'用户名或密码错误'},401)
    token=secrets.token_urlsafe(32);csrf=secrets.token_urlsafe(24)
    c.execute('DELETE FROM sessions WHERE expires<?',(time.time(),));c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(token,u['id'],csrf,time.time()+86400*7))
   return self.send({'ok':True},cookie='flow_session='+token+'; HttpOnly; SameSite=Lax; Path=/; Max-Age=604800'+('; Secure' if SECURE else ''))
  with db() as c:
   u=self.user(c)
   if not u:return self.send({'error':'登录已过期'},401)
   if not hmac.compare_digest(self.headers.get('X-CSRF-Token',''),u['csrf']):return self.send({'error':'安全校验失败，请刷新页面'},403)
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
    if not rows:return self.send({'error':'暂无可用题目或当前没有到期复习'},400)
    qs=[{k:r[k] for k in ('id','topic','prompt','options')} for r in rows]
    for q in qs:q['options']=json.loads(q['options'])
    token=secrets.token_urlsafe(24);c.execute('DELETE FROM quizzes WHERE expires<?',(time.time(),));c.execute('INSERT INTO quizzes VALUES(?,?,?,?,0)',(token,u['id'],json.dumps([q['id'] for q in qs]),time.time()+3600));c.commit();return self.send({'token':token,'questions':qs})
   if path=='/api/submit':
    c.execute('BEGIN IMMEDIATE')
    quiz=c.execute('SELECT * FROM quizzes WHERE token=? AND user_id=? AND used=0 AND expires>?',(data['token'],u['id'],time.time())).fetchone()
    if not quiz:return self.send({'error':'测评已提交或已过期，请重新开始'},400)
    ids=json.loads(quiz['ids']);answers=data['answers']
    if not isinstance(answers,dict) or set(answers)!=set(map(str,ids)):return self.send({'error':'请完成所有题目'},400)
    result=[]
    for qid in ids:
     q=c.execute('SELECT * FROM questions WHERE id=?',(qid,)).fetchone();a=answers[str(qid)]
     if type(a)!=int or not 0<=a<len(json.loads(q['options'])):raise ValueError()
     correct=a==q['answer'];result.append({'id':qid,'topic':q['topic'],'prompt':q['prompt'],'correct':correct,'answer':q['answer'],'selected':a,'options':json.loads(q['options']),'explanation':q['explanation']})
    for q in result:c.execute('INSERT INTO attempts(user_id,question_id,selected,correct,created) VALUES(?,?,?,?,?)',(u['id'],q['id'],q['selected'],q['correct'],time.time()))
    learning.observe(c,u['id'],ids)
    c.execute('UPDATE quizzes SET used=1 WHERE token=?',(data['token'],));c.commit();return self.send({'results':result,'score':round(sum(q['correct'] for q in result)/len(result)*100)})
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
  server=ThreadingHTTPServer((os.getenv('FLOW_HOST','127.0.0.1'),int(os.getenv('FLOW_PORT','8090'))),Handler);server.daemon_threads=True;print('Flow listening',server.server_address,flush=True);server.serve_forever()
