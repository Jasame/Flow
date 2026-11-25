"""Email verification codes for sign-up and code login (3.6).

- New accounts must verify an email with a 6-digit code before the account is created.
- Login works with username-or-email + password, or with a bound email + code.
- Older accounts without an email keep password login and can bind an email in settings.
- Until mail is configured (FLOW_SMTP_*), all of this stays off: sign-up is username + password
  and the login page offers password only. It turns on by itself once mail is configured.
Codes are stored only as salted hashes, expire after 10 minutes, allow 5 tries and are single use.
Mail delivery reuses account_service (FLOW_SMTP_* in the service environment).

r19: the same codes reset a forgotten password (purpose reset, signs the learner in and ends every other session)
and bind an email from 我的 (purpose bind). Password login locks an account for 15 minutes after 5 wrong
passwords in 15 minutes (code login and reset still work), and new usernames cannot contain spaces or @, so a
username never reads as an email address.

2026-11-25 (语流 A5): ceilings a stranger cannot get round by asking again. One email gets at most CODES_PER_DAY codes
for one purpose a day and may type CODE_FAILS_PER_DAY wrong codes for it a day, across all its codes (one code allowing
5 tries is no ceiling when a new one can be asked for every minute). The site sends at most FLOW_REGISTER_CODES_PER_HOUR
sign-up codes an hour, so its mail address cannot be used to flood other people's inboxes. An address that is told
PROBES times an hour that an email or a username is taken (or unknown) is paused for the rest of that hour. Typing the
account's own password again (改密码, 绑定邮箱) pauses after 5 wrong ones, as password login does.
"""
import os,time,secrets,hashlib,hmac,re
import account_service as account
TTL=600
TRIES=5
RESEND=60
PER_IP_HOUR=30
# 班级试用 (the user's choices 2026-11-25): a whole class signs up from one school network. A code asked for from a
# class invite link (data.class: an active class's code) skips PER_IP_HOUR and counts against its class instead
# (CLASS_CODES_PER_HOUR); the per-email, site-wide and one-minute limits still hold. One network makes at most
# SIGNUPS_PER_IP_DAY accounts a day, class invites not counted (signup_ips: the address and when, no account,
# kept one day).
CLASS_CODES_PER_HOUR=120
SIGNUPS_PER_IP_DAY=60
# A class code travels (it is posted in class chats): the accounts one class's invite makes in 24 hours are capped at
# CLASS_SIGNUPS_PER_DAY, or twice the class's settled members (in the class a day and studied there) when that is more; at the cap the console's 管理员 get one mail
# (a class, a day). class_signups keeps the class and when only (no account, no address), CLASS_SIGNUPS_KEEP_DAYS,
# for the console's count (语流 A5, 2026-11-25).
CLASS_SIGNUPS_PER_DAY=80
CLASS_SIGNUPS_KEEP_DAYS=30
EMAIL=re.compile(r'[^\s@<>"\'(),;:]+@[^\s@<>"\'(),;:]+\.[A-Za-z]{2,}')
PURPOSES={'register':'注册','login':'登录','reset':'重设密码','bind':'绑定邮箱'}
FOR={'register':'注册语流 Flow','login':'登录语流 Flow','reset':'重设语流 Flow 密码','bind':'给语流 Flow 账号绑定这个邮箱'}
USERNAME=re.compile(r'[^\s@<>"\'\\/]{2,40}')
LOCK_TRIES=5
LOCK_WINDOW=900
CODES_PER_DAY=10
CODE_FAILS_PER_DAY=20
PROBES,PROBE_WINDOW=60,3600

def register_per_hour():
 try:return max(1,int(os.getenv('FLOW_REGISTER_CODES_PER_HOUR','') or 300))
 except ValueError:return 300

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS email_codes(id INTEGER PRIMARY KEY,email TEXT NOT NULL,purpose TEXT NOT NULL,salt TEXT NOT NULL,digest TEXT NOT NULL,expires REAL NOT NULL,tries INTEGER NOT NULL DEFAULT 0,used INTEGER NOT NULL DEFAULT 0,created REAL NOT NULL);
 CREATE INDEX IF NOT EXISTS email_codes_lookup ON email_codes(email,purpose,used);
 CREATE TABLE IF NOT EXISTS login_failures(key TEXT PRIMARY KEY,count INTEGER NOT NULL,first REAL NOT NULL,until REAL NOT NULL DEFAULT 0);''')
 cols={r[1] for r in c.execute('PRAGMA table_info(email_codes)')}
 if 'ip' not in cols:c.execute('ALTER TABLE email_codes ADD COLUMN ip TEXT')
 if 'class_id' not in cols:c.execute('ALTER TABLE email_codes ADD COLUMN class_id INTEGER')  # asked for from a class invite
 c.execute('CREATE TABLE IF NOT EXISTS signup_ips(ip TEXT NOT NULL,created REAL NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS class_signups(class_id INTEGER NOT NULL,created REAL NOT NULL)')
 c.execute('CREATE TABLE IF NOT EXISTS class_signup_alerts(class_id INTEGER NOT NULL,day TEXT NOT NULL,PRIMARY KEY(class_id,day))')

def invited_class(c,code):
 """The id of the active class whose invite code this is, else None (班级试用's sign-up allowance)."""
 code=str(code or '').strip().upper()[:16]
 if not code:return None
 r=c.execute('SELECT id FROM classes WHERE code=? AND active=1',(code,)).fetchone() if c.execute("SELECT 1 FROM sqlite_master WHERE name='classes'").fetchone() else None
 return r[0] if r else None

def class_signups(c,cid,now=None):
 """(accounts this class's invite made in the last 24 hours, the cap for it)."""
 now=now or time.time()
 # members who have been in the class a day and studied there (class_service.settled), so a batch of accounts made
 # from a passed-round code does not double tomorrow's cap
 members=__import__('class_service').settled(c,cid,now) if c.execute("SELECT 1 FROM sqlite_master WHERE name='class_members'").fetchone() else 0
 made=c.execute('SELECT COUNT(*) FROM class_signups WHERE class_id=? AND created>?',(cid,now-86400)).fetchone()[0] if c.execute("SELECT 1 FROM sqlite_master WHERE name='class_signups'").fetchone() else 0
 return made,max(CLASS_SIGNUPS_PER_DAY,2*members)

def _class_full(c,cid):
 """The class's invite reached the cap: one mail a class a day (Beijing) to the console's 管理员."""
 day=time.strftime('%Y-%m-%d',time.gmtime(time.time()+8*3600))
 c.execute('DELETE FROM class_signup_alerts WHERE day<?',(time.strftime('%Y-%m-%d',time.gmtime(time.time()-CLASS_SIGNUPS_KEEP_DAYS*86400)),))
 fresh=c.execute('INSERT OR IGNORE INTO class_signup_alerts(class_id,day) VALUES(?,?)',(cid,day)).rowcount;c.commit()
 to=[e.strip() for e in os.getenv('FLOW_ADMIN_EMAILS','').split(',') if e.strip()]
 if not fresh or not to or not account.configured():return
 k=c.execute('SELECT name,code FROM classes WHERE id=?',(cid,)).fetchone();n,cap=class_signups(c,cid)
 subject=f'班级「{k["name"]}」的邀请链接今天注册的人数到上限了'
 text,page=__import__('mail_layout').message(
  [f'「{k["name"]}」（邀请码 {k["code"]}）近 24 小时通过邀请链接注册了 {n} 个账号，到了上限 {cap} 个，之后从这个班的邀请链接来的注册先拦下了，页面上请他们联系老师。',
   '如果这不像是这个班的同学在注册，邀请码可能传出去了：在后台这个班的页面换一个邀请码，旧的马上失效，再请老师把新的发给学生。'],
  title=subject,button=('查看这个班','https://xmc.hk/flow#classes/%d'%cid))
 for addr in to:
  try:account.mail(addr,subject,text,html=page)
  except Exception:continue  # noqa: BLE001 - a mail failure must not fail the answer

def normalize(value):
 email=str(value or '').strip().lower()
 return email if len(email)<=254 and EMAIL.fullmatch(email) else None

def _hash(salt,code):return hashlib.sha256((salt+':'+code).encode()).hexdigest()

def owner(c,email):return c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone()

def request(c,data,ip):
 """POST /api/auth/code {email, purpose}: register, login or reset. Returns (body, status)."""
 purpose=data.get('purpose');email=normalize(data.get('email'))
 if purpose not in ('register','login','reset'):return {'error':'请求类型不正确'},400
 if not email:return {'error':'请输入有效的邮箱地址'},400
 if not account.configured():return {'error':'邮件服务暂未开启。'+('请稍后再注册。' if purpose=='register' else '请先用密码登录。')},503
 held=probing(c,ip)
 if held:return held
 exists=owner(c,email)
 if purpose=='register' and exists:probed(c,ip);return {'error':'这个邮箱已经注册，可以直接用验证码登录。','code':'email_taken'},409
 if purpose=='login' and not exists:probed(c,ip);return {'error':'这个邮箱还没有绑定账号。老账号请先用密码登录，再到「我的」里绑定邮箱。','code':'email_unknown'},404
 if purpose=='reset' and not exists:probed(c,ip);return {'error':'没有找到绑定这个邮箱的账号。注册时没有填邮箱的话，请联系老师或管理员，在后台为你生成一个重设密码的链接。','code':'email_unknown','field':'email'},404
 return send(c,email,purpose,ip,invited_class(c,data.get('class')) if purpose=='register' else None)

def probing(c,ip):
 """(body, 429) while this address is paused for asking too often whether an email or a username is taken, else None."""
 if not ip:return None
 row=c.execute('SELECT until FROM login_failures WHERE key=?',('probe:'+ip,)).fetchone()
 if row and row['until']>time.time():return {'error':'操作过于频繁，请一小时后再试','code':'busy'},429
 return None

def probed(c,ip):
 """One more answer that told this address whether an email or a username is taken (PROBES an hour, then a pause)."""
 if not ip:return
 key='probe:'+ip;now=time.time()
 strike(c,key,c.execute('SELECT * FROM login_failures WHERE key=?',(key,)).fetchone(),now,PROBE_WINDOW,PROBES)

def send(c,email,purpose,ip,class_id=None):
 """Mail a fresh code for this email and purpose (the caller has checked who may ask). class_id: asked for from that
 class's invite link (CLASS_CODES_PER_HOUR instead of PER_IP_HOUR)."""
 # Per address: at most PER_IP_HOUR codes an hour (a class invite: its class's own allowance); per email: one a minute.
 if class_id:
  if c.execute('SELECT COUNT(*) FROM email_codes WHERE class_id=? AND created>?',(class_id,time.time()-3600)).fetchone()[0]>=CLASS_CODES_PER_HOUR:return {'error':'这个班这一小时获取验证码的人太多了，请过一会儿再试','code':'busy'},429
 elif c.execute('SELECT COUNT(*) FROM email_codes WHERE ip=? AND created>? AND class_id IS NULL',(ip,time.time()-3600)).fetchone()[0]>=PER_IP_HOUR:return {'error':'这台设备获取验证码太频繁，请一小时后再试'},429
 if c.execute('SELECT COUNT(*) FROM email_codes WHERE email=? AND purpose=? AND created>?',(email,purpose,time.time()-86400)).fetchone()[0]>=CODES_PER_DAY:
  return {'error':f'这个邮箱今天已经收到 {CODES_PER_DAY} 封验证码了。为了这个邮箱的安全，请明天再试'+('，或者先用密码登录。' if purpose in ('login','reset') else '。'),'code':'codes_today'},429
 if purpose=='register' and c.execute("SELECT COUNT(*) FROM email_codes WHERE purpose='register' AND created>?",(time.time()-3600,)).fetchone()[0]>=register_per_hour():
  return {'error':'现在注册的人很多，请过几分钟再试','code':'busy'},429
 if account.limited(c,'code:'+purpose+':'+account.digest(email),RESEND):return {'error':'验证码已发送，请 60 秒后再重新获取'},429
 code=f'{secrets.randbelow(10**6):06d}';salt=secrets.token_hex(8);now=time.time()
 # The same address and purpose asked again within account.AGAIN (the learner's 「重新发送」): this one goes by the
 # fallback channel first, in case the first was refused later, went to junk or is late (account_service).
 again=c.execute('SELECT 1 FROM email_codes WHERE email=? AND purpose=? AND created>?',(email,purpose,now-account.AGAIN)).fetchone()
 c.execute('UPDATE email_codes SET used=1 WHERE email=? AND purpose=? AND used=0',(email,purpose))
 c.execute('DELETE FROM email_codes WHERE expires<?',(now-86400,))
 c.execute('INSERT INTO email_codes(email,purpose,salt,digest,expires,created,ip,class_id) VALUES(?,?,?,?,?,?,?,?)',(email,purpose,salt,_hash(salt,code),now+TTL,now,ip,class_id));c.commit()
 # So that phones and password managers pick the code up (mail_layout): the code in the subject, 「验证码：123456」 as
 # the first line, the code as one run of digits; how long it lasts and not to pass it on.
 paras=[f'这是你{FOR[purpose]}的验证码，{TTL//60} 分钟内有效，只能用一次。',
        '请勿把验证码转发或告诉任何人，语流不会向你索要验证码。如果不是你本人操作，忽略这封邮件即可。']
 if purpose=='reset':  # a learner who forgot the password often forgot the username too
  u=owner(c,email)
  if u:paras.append(f'你的用户名是：{u["username"]}（登录时用户名和这个邮箱都可以用）。')
 text,page=__import__('mail_layout').message(paras,code=code)
 channel=None
 try:channel=account.mail(email,f'语流 Flow {PURPOSES[purpose]}验证码：{code}',text,html=page,prefer='fallback' if again else None);state='sent'
 except Exception:state='failed';c.execute('UPDATE email_codes SET used=1 WHERE email=? AND purpose=? AND used=0',(email,purpose))
 account.mail_event(c,state,channel)
 if state!='sent':return {'error':'验证码邮件发送失败，请稍后再试'},502
 return {'ok':True,'message':'验证码已发送到 '+mask(email)+'，10 分钟内有效。','resend_after':RESEND},200

def mask(email):
 name,_,domain=email.partition('@')
 return (name[:2]+'***' if len(name)>2 else name[:1]+'***')+'@'+domain

def check(c,email,purpose,code):
 """Consume a code. Returns None when valid, otherwise an error message. Commits its own changes."""
 code=str(code or '').strip()
 if not re.fullmatch(r'\d{6}',code):return '请输入邮件里的 6 位验证码'
 # wrong codes for this email and purpose in the last day, across all its codes: past the ceiling even a right one waits
 if c.execute('SELECT COALESCE(SUM(tries),0) FROM email_codes WHERE email=? AND purpose=? AND created>?',(email,purpose,time.time()-86400)).fetchone()[0]>=CODE_FAILS_PER_DAY:
  return '验证码输错的次数太多了，这个邮箱今天先不能再用验证码'+('，可以先用密码登录' if purpose=='login' else '')+'，明天再试'
 row=c.execute('SELECT * FROM email_codes WHERE email=? AND purpose=? AND used=0 ORDER BY id DESC LIMIT 1',(email,purpose)).fetchone()
 if not row or row['expires']<time.time():return '验证码已过期，请重新获取'
 if row['tries']>=TRIES:return '尝试次数过多，请重新获取验证码'
 if not hmac.compare_digest(row['digest'],_hash(row['salt'],code)):
  c.execute('UPDATE email_codes SET tries=tries+1 WHERE id=?',(row['id'],));c.commit()
  left=TRIES-row['tries']-1
  return '验证码不正确'+('，还可以再试 '+str(left)+' 次' if left>0 else '，请重新获取')
 c.execute('UPDATE email_codes SET used=1 WHERE id=?',(row['id'],));c.commit()
 return None

def _signed_up(c,ip,invited):
 """Count this sign-up toward its class's invite (class_signups: the class and when) or else its network's day
 (SIGNUPS_PER_IP_DAY: the address and when only, kept one day)."""
 now=time.time()
 if invited:
  c.execute('DELETE FROM class_signups WHERE created<?',(now-CLASS_SIGNUPS_KEEP_DAYS*86400,))
  c.execute('INSERT INTO class_signups(class_id,created) VALUES(?,?)',(invited,now));return
 if not ip:return
 c.execute('DELETE FROM signup_ips WHERE created<?',(now-86400,));c.execute('INSERT INTO signup_ips(ip,created) VALUES(?,?)',(ip,now))

def register(c,data,hash_password,ip=''):
 """Returns (user_row, None) or (None, (body, status)).
 Without mail configured, sign-up stays username + password (as in 3.5) and any email is ignored,
 because an unverified address must not be bound to an account.
 data.teacher: the token of a 老师注册链接 (teacher_service): the account is a 老师账号, the link is used up, and no
 年龄段 is asked (a teacher is an adult: 18 岁及以上). Without it, every sign-up is a 学生账号."""
 ts=__import__('teacher_service');link=None
 if data.get('teacher'):
  link,problem=ts.usable(c,data.get('teacher'),ip)
  if problem:return None,problem
 name=str(data.get('username','')).strip();p=str(data.get('password',''));email=normalize(data.get('email'))
 held=probing(c,ip)
 if held:return None,held
 # 班级试用: a sign-up from a class invite (its email code was asked for from the invite link, or data.class) does not
 # count toward SIGNUPS_PER_IP_DAY
 row=c.execute("SELECT class_id FROM email_codes WHERE email=? AND purpose='register' AND used=0 AND expires>? ORDER BY id DESC LIMIT 1",(email,time.time())).fetchone() if email else None
 invited=invited_class(c,data.get('class')) or (row['class_id'] if row and row['class_id'] and c.execute('SELECT 1 FROM classes WHERE id=? AND active=1',(row['class_id'],)).fetchone() else None)
 if ip and not invited and c.execute('SELECT COUNT(*) FROM signup_ips WHERE ip=? AND created>?',(ip,time.time()-86400)).fetchone()[0]>=SIGNUPS_PER_IP_DAY:
  return None,({'error':'这个网络今天注册的账号已经很多了，请明天再试。班级的同学请用老师发的邀请链接注册。','code':'busy'},429)
 if invited:
  n,cap=class_signups(c,invited)
  if n>=cap:_class_full(c,invited);return None,({'error':'这个班今天通过邀请链接注册的人太多了，请联系老师。','code':'busy'},429)
 if not USERNAME.fullmatch(name):return None,({'error':'用户名需 2–40 个字符，不能有空格、@ 和 < > " \' / \\','field':'username'},400)
 if not 10<=len(p)<=200:return None,({'error':'密码需 10–200 个字符','field':'password'},400)
 if c.execute('SELECT 1 FROM users WHERE username=?',(name,)).fetchone():probed(c,ip);return None,({'error':'这个用户名已被使用，换一个试试'},409)
 pv=__import__('privacy_service');problem=None if link else pv.check_signup(data)  # 年龄段; 不满 14 岁 needs the guardian ticked
 if problem:return None,problem
 problem=pv.check_storage(data)  # 数据存放在香港: its own tick, teachers too
 if problem:return None,problem
 taken=({'error':'这个老师注册链接刚刚被用掉了。需要的话，请联系语流重新发一个。','code':'teacher_link'},410)
 if not account.configured():
  if link and not ts.claim(c,link['id']):return None,taken
  c.execute('INSERT INTO users(username,password,created) VALUES(?,?,?)',(name,hash_password(p),time.time()))
  u=c.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone()
  if link:ts.made(c,link['id'],u['id'])
  pv.agreed(c,u['id']);_signed_up(c,ip,invited);c.commit()
  if not link:pv.store(c,u['id'],data)
  return c.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone(),None
 if not email:return None,({'error':'请输入有效的邮箱地址'},400)
 if owner(c,email):probed(c,ip);return None,({'error':'这个邮箱已经注册，可以直接用验证码登录。','code':'email_taken'},409)
 problem=check(c,email,'register',data.get('code'))
 if problem:return None,({'error':problem,'field':'code'},400)
 if link and not ts.claim(c,link['id']):return None,taken
 c.execute('INSERT INTO users(username,password,email,created) VALUES(?,?,?,?)',(name,hash_password(p),email,time.time()))
 u=c.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone()
 if link:ts.made(c,link['id'],u['id'])
 pv.agreed(c,u['id']);_signed_up(c,ip,invited);c.commit()
 if not link:pv.store(c,u['id'],data)
 return c.execute('SELECT * FROM users WHERE id=?',(u['id'],)).fetchone(),None

def strike(c,key,row,now,window,tries):
 """One more strike for key within window seconds (row: its login_failures row or None); at tries strikes it is paused
 for window seconds. Returns the strikes so far."""
 if row and row['first']>now-window:
  n=row['count']+1;c.execute('UPDATE login_failures SET count=?,until=? WHERE key=?',(n,now+window if n>=tries else 0,key))
 else:
  n=1;c.execute('INSERT OR REPLACE INTO login_failures(key,count,first,until) VALUES(?,1,?,0)',(key,now))
 c.execute('DELETE FROM login_failures WHERE first<? AND until<?',(now-86400,now));c.commit()
 return n

def failed(c,key,row,now):
 """One more wrong password for this account (key u:<id>): 5 in 15 minutes pause password login, and 注销账号
 (account_data.erase), for 15 minutes. Returns the count so far."""
 return strike(c,key,row,now,LOCK_WINDOW,LOCK_TRIES)

def own_password(c,uid,given,verify,wrong):
 """The account's own password typed again (改密码, 绑定邮箱): None when right, else the message (wrong + how many
 tries are left). 5 wrong in 15 minutes pause this check for 15 minutes; password login has its own lock."""
 key='pw:%d'%uid;now=time.time();row=c.execute('SELECT * FROM login_failures WHERE key=?',(key,)).fetchone()
 if row and row['until']>now:return '当前密码错了太多次，请 %d 分钟后再试'%max(1,round((row['until']-now)/60))
 stored=c.execute('SELECT password FROM users WHERE id=?',(uid,)).fetchone()[0]
 if verify(str(given or ''),stored):
  if row:c.execute('DELETE FROM login_failures WHERE key=?',(key,));c.commit()
  return None
 left=LOCK_TRIES-failed(c,key,row,now)
 return wrong+('，再错 %d 次会暂停 15 分钟'%left if 0<left<=2 else '，已暂停 15 分钟' if left<=0 else '')

def login(c,data,verify,ip=''):
 """Password login by username or email, or code login by email."""
 if data.get('method')=='code':
  email=normalize(data.get('email'))
  if not email:return None,({'error':'请输入有效的邮箱地址'},400)
  held=probing(c,ip)
  if held:return None,held
  u=owner(c,email)
  if not u:probed(c,ip);return None,({'error':'这个邮箱还没有绑定账号','code':'email_unknown'},404)
  problem=check(c,email,'login',data.get('code'))
  if problem:return None,({'error':problem,'field':'code'},400)
  return u,None
 name=str(data.get('username','')).strip();p=str(data.get('password',''))
 if not name or not 1<=len(p)<=200:return None,({'error':'请输入用户名或邮箱，以及密码'},400)
 u=owner(c,normalize(name)) if '@' in name and normalize(name) else c.execute('SELECT * FROM users WHERE username=?',(name,)).fetchone()
 # One lock per account (or per name tried, when there is no such account, so both read the same).
 key='u:%d'%u['id'] if u else 'n:'+hashlib.sha256(name.lower().encode()).hexdigest()
 now=time.time();row=c.execute('SELECT * FROM login_failures WHERE key=?',(key,)).fetchone()
 if row and row['until']>now:
  return None,({'error':'密码错了太多次，这个账号的密码登录暂停 %d 分钟。可以用「验证码登录」或「忘记密码」。'%max(1,round((row['until']-now)/60)),'code':'locked'},429)
 if not u or not verify(p,u['password']):
  left=LOCK_TRIES-failed(c,key,row,now)
  return None,({'error':'用户名、邮箱或密码不正确'+('，再错 %d 次会暂停 15 分钟'%left if 0<left<=2 else '，密码登录已暂停 15 分钟' if left<=0 else '')},401)
 if row:c.execute('DELETE FROM login_failures WHERE key=?',(key,));c.commit()
 return u,None

def reset(c,data,hash_password,ip=''):
 """POST /api/auth/reset {email, code, password}: a forgotten password, reset with an emailed code.
 Ends every session of the account and clears its lock; the caller signs the learner in."""
 email=normalize(data.get('email'));p=str(data.get('password',''))
 if not email:return None,({'error':'请输入有效的邮箱地址','field':'email'},400)
 if not 10<=len(p)<=200:return None,({'error':'新密码需 10–200 个字符','field':'password'},400)
 held=probing(c,ip)
 if held:return None,held
 u=owner(c,email)
 if not u:probed(c,ip);return None,({'error':'这个邮箱还没有绑定账号','code':'email_unknown'},404)
 problem=check(c,email,'reset',data.get('code'))
 if problem:return None,({'error':problem,'field':'code'},400)
 c.execute('UPDATE users SET password=? WHERE id=?',(hash_password(p),u['id']))
 c.execute('DELETE FROM sessions WHERE user_id=?',(u['id'],))
 c.execute('UPDATE recovery_tokens SET used=1 WHERE user_id=?',(u['id'],))
 c.execute('DELETE FROM login_failures WHERE key=?',('u:%d'%u['id'],));c.commit()
 account.password_changed(c,u['id'],'通过邮箱验证码重设')
 return u,None
