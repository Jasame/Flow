"""Verified email binding and one-use recovery tokens. Secrets never leave the server."""
import os,time,secrets,hashlib,re,smtplib,ssl
from email.message import EmailMessage

def configured():
 return bool(os.getenv('FLOW_SMTP_HOST') and os.getenv('FLOW_SMTP_FROM') and os.getenv('FLOW_SMTP_USER') and os.getenv('FLOW_SMTP_PASSWORD'))

def schema(c):
 if 'email' not in {r[1] for r in c.execute('PRAGMA table_info(users)')}:c.execute('ALTER TABLE users ADD COLUMN email TEXT')
 c.executescript('''CREATE UNIQUE INDEX IF NOT EXISTS verified_email ON users(email) WHERE email IS NOT NULL;
 CREATE TABLE IF NOT EXISTS recovery_tokens(digest TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),email TEXT,purpose TEXT,expires REAL,used INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS mail_limits(key TEXT PRIMARY KEY,last REAL);
 CREATE TABLE IF NOT EXISTS mail_events(id INTEGER PRIMARY KEY,status TEXT,created REAL);''')

def digest(token):return hashlib.sha256(token.encode()).hexdigest()

def mail(to,subject,text):
 msg=EmailMessage();msg['From']=os.environ['FLOW_SMTP_FROM'];msg['To']=to;msg['Subject']=subject;msg.set_content(text)
 host=os.environ['FLOW_SMTP_HOST'];port=int(os.getenv('FLOW_SMTP_PORT','465'));ctx=ssl.create_default_context()
 if port==465:connection=smtplib.SMTP_SSL(host,port,timeout=12,context=ctx)
 else:
  connection=smtplib.SMTP(host,port,timeout=12);connection.ehlo();connection.starttls(context=ctx);connection.ehlo()
 with connection as s:
  s.login(os.environ['FLOW_SMTP_USER'],os.environ['FLOW_SMTP_PASSWORD']);s.send_message(msg)

def issue(c,uid,email,purpose):
 token=secrets.token_urlsafe(32);c.execute('UPDATE recovery_tokens SET used=1 WHERE user_id=? AND purpose=?',(uid,purpose))
 c.execute('DELETE FROM recovery_tokens WHERE expires<?',(time.time(),));c.execute('INSERT INTO recovery_tokens VALUES(?,?,?,?,?,0)',(digest(token),uid,email,purpose,time.time()+1800));c.commit()
 origin=os.getenv('FLOW_PUBLIC_URL','https://flowlang.cn').rstrip('/')
 url=origin+'/#reset='+token if purpose=='reset' else None
 text=('请在 30 分钟内打开此链接设置新密码：\n'+url) if url else '请在 Flow 账号设置中输入以下验证令牌（30 分钟内有效）：\n'+token
 try:mail(email,'Flow 密码找回' if purpose=='reset' else 'Flow 邮箱验证',text+'\n\n如非本人操作，请忽略。');state='sent'
 except Exception:
  state='failed';c.execute('UPDATE recovery_tokens SET used=1 WHERE digest=?',(digest(token),))
 c.execute('INSERT INTO mail_events(status,created) VALUES(?,?)',(state,time.time()));c.commit()
 return state=='sent'

def limited(c,key,seconds=120):
 c.execute('BEGIN IMMEDIATE');c.execute('DELETE FROM mail_limits WHERE last<?',(time.time()-86400,));row=c.execute('SELECT last FROM mail_limits WHERE key=?',(key,)).fetchone()
 if row and row[0]>time.time()-seconds:c.rollback();return True
 c.execute('INSERT OR REPLACE INTO mail_limits VALUES(?,?)',(key,time.time()));c.commit();return False

def public(c,path,data,password,ip):
 if path=='/api/recovery/request':
  # The same response is used for unknown emails, rate limits and mail delivery failures.
  response=({'ok':True,'message':'如该邮箱已绑定账号且邮件服务可用，将收到重置链接。请检查收件箱和垃圾邮件。'},200)
  email=str(data.get('email','')).strip().lower()
  if not configured() or limited(c,'reset-ip:'+ip,120):return response
  if limited(c,'reset-email:'+digest(email),120):return response
  row=c.execute('SELECT id FROM users WHERE email=?',(email,)).fetchone()
  if row:issue(c,row[0],email,'reset')
  return response
 if path=='/api/recovery/reset':
  token=data.get('token','');new=data.get('password','')
  if not isinstance(token,str) or not isinstance(new,str) or not 10<=len(new)<=200 or len(token)>100:return {'error':'重置链接或密码不正确'},400
  c.execute('BEGIN IMMEDIATE');row=c.execute("SELECT * FROM recovery_tokens WHERE digest=? AND purpose='reset' AND used=0 AND expires>?",(digest(token),time.time())).fetchone()
  if not row:c.rollback();return {'error':'重置链接已过期或已使用，请重新申请'},400
  # Only a currently bound email can recover an account.
  if not c.execute('SELECT 1 FROM users WHERE id=? AND email=?',(row['user_id'],row['email'])).fetchone():c.rollback();return {'error':'绑定邮箱已变更，请重新申请'},400
  c.execute('UPDATE users SET password=? WHERE id=?',(password(new),row['user_id']));c.execute('UPDATE recovery_tokens SET used=1 WHERE user_id=?',(row['user_id'],));c.execute('DELETE FROM sessions WHERE user_id=?',(row['user_id'],));c.commit();return {'ok':True},200
 return None

def private(c,u,path,data,verify):
 if path=='/api/account':return {'email':c.execute('SELECT email FROM users WHERE id=?',(u['id'],)).fetchone()[0],'mail_enabled':configured()},200
 if path=='/api/account/email/request':
  if not configured():return {'error':'管理员尚未配置邮件服务'},503
  email=str(data.get('email','')).strip().lower()
  if len(email)>254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',email):return {'error':'邮箱格式不正确'},400
  stored=c.execute('SELECT password FROM users WHERE id=?',(u['id'],)).fetchone()[0]
  if not verify(str(data.get('password','')),stored):return {'error':'当前密码不正确'},400
  if c.execute('SELECT 1 FROM users WHERE email=? AND id!=?',(email,u['id'])).fetchone():return {'error':'该邮箱无法绑定'},400
  if limited(c,'bind:'+str(u['id'])):return {'error':'请两分钟后再发送'},429
  ok=issue(c,u['id'],email,'bind');return ({'ok':True} if ok else {'error':'验证邮件发送失败，请联系管理员检查邮件服务'}),200 if ok else 502
 if path=='/api/account/email/confirm':
  token=str(data.get('token',''))
  if len(token)>100:return {'error':'验证令牌不正确'},400
  c.execute('BEGIN IMMEDIATE');row=c.execute("SELECT * FROM recovery_tokens WHERE digest=? AND user_id=? AND purpose='bind' AND used=0 AND expires>?",(digest(token),u['id'],time.time())).fetchone()
  if not row:c.rollback();return {'error':'验证令牌无效或已过期'},400
  c.execute('UPDATE users SET email=? WHERE id=?',(row['email'],u['id']));c.execute('UPDATE recovery_tokens SET used=1 WHERE user_id=?',(u['id'],));c.commit();return {'ok':True},200
 return None
