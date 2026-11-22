"""Email verification codes for sign-up and code login (3.6).

- New accounts must verify an email with a 6-digit code before the account is created.
- Login works with username-or-email + password, or with a bound email + code.
- Older accounts without an email keep password login and can bind an email in settings.
- Until mail is configured (FLOW_SMTP_*), all of this stays off: sign-up is username + password
  and the login page offers password only. It turns on by itself once mail is configured.
Codes are stored only as salted hashes, expire after 10 minutes, allow 5 tries and are single use.
Mail delivery reuses account_service (FLOW_SMTP_* in the service environment).
"""
import time,secrets,hashlib,hmac,re
import account_service as account
TTL=600
TRIES=5
RESEND=60
PER_IP_HOUR=30
EMAIL=re.compile(r'[^\s@<>"\'(),;:]+@[^\s@<>"\'(),;:]+\.[A-Za-z]{2,}')
PURPOSES={'register':'注册','login':'登录'}

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS email_codes(id INTEGER PRIMARY KEY,email TEXT NOT NULL,purpose TEXT NOT NULL,salt TEXT NOT NULL,digest TEXT NOT NULL,expires REAL NOT NULL,tries INTEGER NOT NULL DEFAULT 0,used INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
 CREATE INDEX IF NOT EXISTS email_codes_lookup ON email_codes(email,purpose,used);''')
 if 'ip' not in {r[1] for r in c.execute('PRAGMA table_info(email_codes)')}:c.execute('ALTER TABLE email_codes ADD COLUMN ip TEXT')

def normalize(value):
 email=str(value or '').strip().lower()
 return email if len(email)<=254 and EMAIL.fullmatch(email) else None

def _hash(salt,code):return hashlib.sha256((salt+':'+code).encode()).hexdigest()

def owner(c,email):return c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()

def request(c,data,ip):
 """POST /api/auth/code {email, purpose}. Returns (body, status)."""
 purpose=data.get('purpose');email=normalize(data.get('email'))
 if purpose not in PURPOSES:return {'error':'请求类型不正确'},400
 if not email:return {'error':'请输入有效的邮箱地址'},400
 if not account.configured():return {'error':'邮件服务暂未开启。'+('请稍后再注册。' if purpose=='register' else '请先用密码登录。')},503
 exists=owner(c,email)
 if purpose=='register' and exists:return {'error':'这个邮箱已经注册，可以直接用验证码登录。','code':'email_taken'},409
 if purpose=='login' and not exists:return {'error':'这个邮箱还没有绑定账号。老账号请先用密码登录，再到设置里绑定邮箱。','code':'email_unknown'},404
 # Per address: at most PER_IP_HOUR codes an hour; per email: one code a minute.
 if c.execute('SELECT COUNT(*) FROM email_codes WHERE ip=? AND created>?',(ip,time.time()-3600)).fetchone()[0]>=PER_IP_HOUR:return {'error':'这台设备获取验证码太频繁，请一小时后再试'},429
 if account.limited(c,'code:'+purpose+':'+account.digest(email),RESEND):return {'error':'验证码已发送，请 60 秒后再重新获取'},429
 code=f'{secrets.randbelow(10**6):06d}';salt=secrets.token_hex(8);now=time.time()
 c.execute('UPDATE email_codes SET used=1 WHERE email=? AND purpose=? AND used=0',(email,purpose))
 c.execute('DELETE FROM email_codes WHERE expires<?',(now-86400,))
 c.execute('INSERT INTO email_codes(email,purpose,salt,digest,expires,created,ip) VALUES(?,?,?,?,?,?,?)',(email,purpose,salt,_hash(salt,code),now+TTL,now,ip));c.commit()
 text=f'你的语流 Flow {PURPOSES[purpose]}验证码是：{code}\n\n10 分钟内有效，只能使用一次。如果不是你本人操作，请忽略这封邮件。'
 try:account.mail(email,f'Flow {PURPOSES[purpose]}验证码 {code}',text);state='sent'
 except Exception:state='failed';c.execute('UPDATE email_codes SET used=1 WHERE email=? AND purpose=? AND used=0',(email,purpose))
 c.execute('INSERT INTO mail_events(status,created) VALUES(?,?)',(state,time.time()));c.commit()
 if state!='sent':return {'error':'验证码邮件发送失败，请稍后再试'},502
 return {'ok':True,'message':'验证码已发送到 '+mask(email)+'，10 分钟内有效。','resend_after':RESEND},200

def mask(email):
 name,_,domain=email.partition('@')
 return (name[:2]+'***' if len(name)>2 else name[:1]+'***')+'@'+domain

def check(c,email,purpose,code):
 """Consume a code. Returns None when valid, otherwise an error message. Commits its own changes."""
 code=str(code or '').strip()
 if not re.fullmatch(r'\d{6}',code):return '请输入邮件里的 6 位验证码'
 row=c.execute('SELECT * FROM email_codes WHERE email=? AND purpose=? AND used=0 ORDER BY id DESC LIMIT 1',(email,purpose)).fetchone()
 if not row or row['expires']<time.time():return '验证码已过期，请重新获取'
 if row['tries']>=TRIES:return '尝试次数过多，请重新获取验证码'
 if not hmac.compare_digest(row['digest'],_hash(row['salt'],code)):
  c.execute('UPDATE email_codes SET tries=tries+1 WHERE id=?',(row['id'],));c.commit()
  left=TRIES-row['tries']-1
  return '验证码不正确'+('，还可以再试 '+str(left)+' 次' if left>0 else '，请重新获取')
 c.execute('UPDATE email_codes SET used=1 WHERE id=?',(row['id'],));c.commit()
 return None

def register(c,data,hash_password):
 """Returns (user_row, None) or (None, (body, status)).
 Without mail configured, sign-up stays username + password (as in 3.5) and any email is ignored,
 because an unverified address must not be bound to an account."""
 name=str(data.get('username','')).strip();p=str(data.get('password',''));email=normalize(data.get('email'))
 if not 3<=len(name)<=40 or not 10<=len(p)<=200:return None,({'error':'用户名需 3–40 个字符，密码需 10–200 个字符'},400)
 if c.execute('SELECT 1 FROM users WHERE username=?',(name,)).fetchone():return None,({'error':'这个用户名已被使用，换一个试试'},409)
 if not account.configured():
  c.execute('INSERT INTO users(username,password) VALUES(?,?)',(name,hash_password(p)));c.commit()
  return c.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone(),None
 if not email:return None,({'error':'请输入有效的邮箱地址'},400)
 if owner(c,email):return None,({'error':'这个邮箱已经注册，可以直接用验证码登录。','code':'email_taken'},409)
 problem=check(c,email,'register',data.get('code'))
 if problem:return None,({'error':problem,'field':'code'},400)
 c.execute('INSERT INTO users(username,password,email) VALUES(?,?,?)',(name,hash_password(p),email));c.commit()
 return c.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone(),None

def login(c,data,verify):
 """Password login by username or email, or code login by email."""
 if data.get('method')=='code':
  email=normalize(data.get('email'))
  if not email:return None,({'error':'请输入有效的邮箱地址'},400)
  u=owner(c,email)
  if not u:return None,({'error':'这个邮箱还没有绑定账号','code':'email_unknown'},404)
  problem=check(c,email,'login',data.get('code'))
  if problem:return None,({'error':problem,'field':'code'},400)
  return u,None
 name=str(data.get('username','')).strip();p=str(data.get('password',''))
 if not name or not 1<=len(p)<=200:return None,({'error':'请输入用户名或邮箱，以及密码'},400)
 u=owner(c,normalize(name)) if '@' in name and normalize(name) else c.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone()
 if not u or not verify(p,u['password']):return None,({'error':'用户名、邮箱或密码不正确'},401)
 return u,None
