"""Verified email binding and one-use recovery tokens. Secrets never leave the server."""
import os,time,secrets,hashlib,re,smtplib,ssl
from email.message import EmailMessage

def configured():
 # FLOW_MAIL_OUTBOX is for local development and tests only: messages are written to files instead of sent.
 if os.getenv('FLOW_MAIL_OUTBOX'):return True
 return bool(os.getenv('FLOW_SMTP_HOST') and os.getenv('FLOW_SMTP_FROM') and os.getenv('FLOW_SMTP_USER') and os.getenv('FLOW_SMTP_PASSWORD'))

def schema(c):
 cols={r[1] for r in c.execute('PRAGMA table_info(users)')}
 if 'email' not in cols:c.execute('ALTER TABLE users ADD COLUMN email TEXT')
 # r26: when an account signed up (older accounts: unknown), and an account an operator stopped (xmc.hk console)
 if 'created' not in cols:c.execute('ALTER TABLE users ADD COLUMN created REAL')
 if 'disabled' not in cols:c.execute('ALTER TABLE users ADD COLUMN disabled INTEGER NOT NULL DEFAULT 0')
 __import__('privacy_service').schema(c)  # 年龄段, a guardian's agreement under 14
 c.executescript('''CREATE UNIQUE INDEX IF NOT EXISTS verified_email ON users(email) WHERE email IS NOT NULL;
 CREATE TABLE IF NOT EXISTS recovery_tokens(digest TEXT PRIMARY KEY,user_id INTEGER REFERENCES users(id),email TEXT,purpose TEXT,expires REAL,used INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS mail_limits(key TEXT PRIMARY KEY,last REAL);
 CREATE TABLE IF NOT EXISTS mail_events(id INTEGER PRIMARY KEY,status TEXT,created REAL);''')

def digest(token):return hashlib.sha256(token.encode()).hexdigest()

def ehlo_name():
 # The name given to the mail server (EHLO/HELO): the site's own domain (FLOW_PUBLIC_URL; flowlang.cn by default).
 # smtplib's default is the machine's internal name (socket.getfqdn()), which every mail would then carry in its
 # Received header, and which counts against delivery.
 # A local address (localhost, 127.0.0.1) is no domain to give, so it falls back too.
 import ipaddress;from urllib.parse import urlsplit
 name=urlsplit(os.getenv('FLOW_PUBLIC_URL','').strip()).hostname or ''
 try:ipaddress.ip_address(name);name=''
 except ValueError:pass
 return name if '.' in name else 'flowlang.cn'

def mail(to,subject,text,headers=None):
 # the 内测版 (FLOW_CHANNEL=beta, flow.jasa.hk) marks every mail it sends, so nobody takes it for 语流's own
 if os.getenv('FLOW_CHANNEL','').strip().lower()=='beta' and not subject.startswith('【内测版】'):subject='【内测版】'+subject
 outbox=os.getenv('FLOW_MAIL_OUTBOX')
 if outbox:
  os.makedirs(outbox,exist_ok=True)
  name=os.path.join(outbox,f'{time.time():.6f}-{secrets.token_hex(3)}.txt')
  with open(name,'w',encoding='utf-8') as f:f.write('To: '+to+'\nSubject: '+subject+'\n'+''.join(k+': '+v+'\n' for k,v in (headers or {}).items())+'\n'+text)
  return
 msg=EmailMessage();msg['From']=os.environ['FLOW_SMTP_FROM'];msg['To']=to;msg['Subject']=subject;msg.set_content(text)
 for k,v in (headers or {}).items():msg[k]=v  # List-Unsubscribe on the Sunday mail (progress_service)
 host=os.environ['FLOW_SMTP_HOST'];port=int(os.getenv('FLOW_SMTP_PORT','465'));ctx=ssl.create_default_context()
 if port==465:connection=smtplib.SMTP_SSL(host,port,local_hostname=ehlo_name(),timeout=12,context=ctx)
 else:
  connection=smtplib.SMTP(host,port,local_hostname=ehlo_name(),timeout=12);connection.ehlo();connection.starttls(context=ctx);connection.ehlo()
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

ADMIN_TTL=86400

def password_changed(c,uid,how):
 """A notice to the bound email after any password change: if it was not the owner, they reset it at once.
 Sent on a background thread (the learner does not wait for the mail server); failures are only counted."""
 row=c.execute('SELECT username,email FROM users WHERE id=?',(uid,)).fetchone()
 if not row or not row['email'] or not configured():return False
 origin=os.getenv('FLOW_PUBLIC_URL','https://flowlang.cn').rstrip('/')
 text=(f'你的语流 Flow 账号（用户名：{row["username"]}）的密码刚刚{how}了，所有手机和电脑上的登录都已退出。\n\n'
       f'如果是你本人操作，不用理会这封邮件。\n如果不是你，请马上打开 {origin} ，在登录框点「忘记密码？」用这个邮箱重设密码。')
 def go():
  try:mail(row['email'],'Flow 密码已修改',text)
  except Exception:pass
 __import__('threading').Thread(target=go,daemon=True).start()
 return True

def admin_link(c,who):
 """An operator's one-time link to set a new password, for an account that cannot reset by itself (no email
 bound). Valid 24 hours and once; shown to the operator only, never mailed. The learner opens it: /#reset=<token>."""
 who=str(who or '').strip()[:254]
 if not who:return {'error':'请输入用户名或邮箱'},400
 u=c.execute('SELECT id,username FROM users WHERE username=? OR email=?',(who,who.lower())).fetchone()
 if not u:return {'error':'没有找到这个账号'},404
 token=secrets.token_urlsafe(32);now=time.time()
 c.execute("UPDATE recovery_tokens SET used=1 WHERE user_id=? AND purpose='admin_reset'",(u['id'],))
 c.execute('DELETE FROM recovery_tokens WHERE expires<?',(now,))
 c.execute('INSERT INTO recovery_tokens VALUES(?,?,?,?,?,0)',(digest(token),u['id'],None,'admin_reset',now+ADMIN_TTL));c.commit()
 origin=os.getenv('FLOW_PUBLIC_URL','https://flowlang.cn').rstrip('/')
 return {'ok':True,'username':u['username'],'link':origin+'/#reset='+token,'hours':ADMIN_TTL//3600},200

def admin_users(c,q=''):
 """Accounts for the operator's 账号 tab: name, a masked email, whether one is bound (newest first, 30 at most)."""
 import auth_service
 q=str(q or '').strip()[:60];like='%'+q.replace('%','').replace('_','')+'%'
 rows=c.execute("SELECT id,username,email FROM users WHERE ?='' OR username LIKE ? OR email LIKE ? ORDER BY id DESC LIMIT 30",(q,like,like.lower())).fetchall()
 total,bound=c.execute('SELECT COUNT(*),COUNT(email) FROM users').fetchone()
 return {'users':[{'id':r['id'],'username':r['username'],'email':auth_service.mask(r['email']) if r['email'] else '','has_email':bool(r['email'])} for r in rows],
         'total':total,'without_email':total-bound}

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
  c.execute('BEGIN IMMEDIATE');row=c.execute("SELECT * FROM recovery_tokens WHERE digest=? AND purpose IN ('reset','admin_reset') AND used=0 AND expires>?",(digest(token),time.time())).fetchone()
  if not row:c.rollback();return {'error':'重置链接已过期或已使用，请重新申请'},400
  # A mailed link works only while that email is still bound; an operator's link (admin_reset) has no email.
  if row['purpose']=='reset' and not c.execute('SELECT 1 FROM users WHERE id=? AND email=?',(row['user_id'],row['email'])).fetchone():c.rollback();return {'error':'绑定邮箱已变更，请重新申请'},400
  c.execute('UPDATE users SET password=? WHERE id=?',(password(new),row['user_id']));c.execute('UPDATE recovery_tokens SET used=1 WHERE user_id=?',(row['user_id'],));c.execute('DELETE FROM sessions WHERE user_id=?',(row['user_id'],))
  c.execute('DELETE FROM login_failures WHERE key=?',('u:%d'%row['user_id'],));c.commit()
  password_changed(c,row['user_id'],'由管理员发的链接重设' if row['purpose']=='admin_reset' else '通过邮件里的链接重设')
  return {'ok':True},200
 return None

def private(c,u,path,data,verify):
 if path=='/api/account':return {'email':c.execute('SELECT email FROM users WHERE id=?',(u['id'],)).fetchone()[0],'mail_enabled':configured()},200
 if path=='/api/account/email/request':
  if not configured():return {'error':'管理员尚未配置邮件服务'},503
  email=str(data.get('email','')).strip().lower()
  if len(email)>254 or not re.fullmatch(r'[^\s@<>]+@[^\s@<>]+\.[^\s@<>]+',email):return {'error':'邮箱格式不正确'},400
  stored=c.execute('SELECT password FROM users WHERE id=?',(u['id'],)).fetchone()[0]
  if not verify(str(data.get('password','')),stored):return {'error':'当前密码不正确','field':'password'},400
  if c.execute('SELECT 1 FROM users WHERE email=? AND id!=?',(email,u['id'])).fetchone():return {'error':'该邮箱无法绑定'},400
  if data.get('mode')=='code':
   # r19: a 6-digit code, as at sign-up, instead of a long token to copy out of the mail.
   import auth_service
   email=auth_service.normalize(email)
   if not email:return {'error':'邮箱格式不正确'},400
   return auth_service.send(c,email,'bind','user:'+str(u['id']))
  if limited(c,'bind:'+str(u['id'])):return {'error':'请两分钟后再发送'},429
  ok=issue(c,u['id'],email,'bind');return ({'ok':True} if ok else {'error':'验证邮件发送失败，请联系管理员检查邮件服务'}),200 if ok else 502
 if path=='/api/account/email/confirm' and 'code' in data:
  import auth_service
  email=auth_service.normalize(data.get('email'))
  if not email:return {'error':'邮箱格式不正确'},400
  if c.execute('SELECT 1 FROM users WHERE email=? AND id!=?',(email,u['id'])).fetchone():return {'error':'该邮箱无法绑定'},400
  problem=auth_service.check(c,email,'bind',data.get('code'))
  if problem:return {'error':problem,'field':'code'},400
  c.execute('UPDATE users SET email=? WHERE id=?',(email,u['id']));c.execute('UPDATE recovery_tokens SET used=1 WHERE user_id=?',(u['id'],));c.commit()
  return {'ok':True,'email':email},200
 if path=='/api/account/email/confirm':
  token=str(data.get('token',''))
  if len(token)>100:return {'error':'验证令牌不正确'},400
  c.execute('BEGIN IMMEDIATE');row=c.execute("SELECT * FROM recovery_tokens WHERE digest=? AND user_id=? AND purpose='bind' AND used=0 AND expires>?",(digest(token),u['id'],time.time())).fetchone()
  if not row:c.rollback();return {'error':'验证令牌无效或已过期'},400
  c.execute('UPDATE users SET email=? WHERE id=?',(row['email'],u['id']));c.execute('UPDATE recovery_tokens SET used=1 WHERE user_id=?',(u['id'],));c.commit();return {'ok':True},200
 return None
