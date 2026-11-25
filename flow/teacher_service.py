"""老师模式 (2026-11-26, the owner: 「分老师模式和学生模式（常规学习用户模式，可不加入班级），然后给老师写操作说明，老师账号注册需要我发链接，链接注册单次有效」).

- 学生账号: every ordinary sign-up, as before. A learner may join a class with an invite code, of their own accord, or
  never join one.
- 老师账号 (users.role = 'teacher'): made only through a 老师注册链接. Its home page (#/teach) lists its classes and makes
  new ones; each class page shows the invite code and the whole class's numbers only (class_service.teach: no names, no
  ids, nothing about one learner, nothing under 5 members). A teacher account never joins a class, so it is never
  counted; it may use the rest of 语流 like anyone.
- 老师注册链接: made by a 管理员 in the xmc.hk console (or with the command below on the server), each good for one
  sign-up and LINK_DAYS days (1–MAX_DAYS, the operator's choice). Only a hash of the token is kept, so the console shows
  the link once, when it is made. The console lists every link (unused, used by whom, revoked, expired) and revokes an
  unused one. Wrong tokens from one address: TRIES in WINDOW pause checking for WINDOW.

    python3 teacher_service.py link [--days 7] [--note 备注]    # on the server: a link, printed once
"""
import datetime, hashlib, os, re, secrets, sys, time

LINK_DAYS, MAX_DAYS = 7, 30
TRIES, WINDOW = 10, 900          # wrong tokens: 10 in 15 minutes from one address pause checking for 15 minutes
CLASSES_MAX = 10                 # classes a teacher account may have in use at once
TZ = datetime.timezone(datetime.timedelta(hours=8))
ROUTE = '/#/teacher/'


def schema(c):
    if 'role' not in {r[1] for r in c.execute('PRAGMA table_info(users)')}:
        c.execute('ALTER TABLE users ADD COLUMN role TEXT')
    c.execute('''CREATE TABLE IF NOT EXISTS teacher_links(id INTEGER PRIMARY KEY, digest TEXT NOT NULL UNIQUE,
      note TEXT NOT NULL DEFAULT '', by TEXT NOT NULL DEFAULT '', created REAL NOT NULL, expires REAL NOT NULL,
      used_at REAL, used_by INTEGER REFERENCES users(id), revoked_at REAL)''')


def is_teacher(u):
    return bool(u is not None and 'role' in u.keys() and u['role'] == 'teacher')


def _digest(token):
    return hashlib.sha256(str(token).encode()).hexdigest()


def _day(t):
    return datetime.datetime.fromtimestamp(t, TZ).strftime('%Y-%m-%d %H:%M') if t else ''


def origin():
    return os.getenv('FLOW_PUBLIC_URL', 'https://flowlang.cn').strip().rstrip('/') or 'https://flowlang.cn'


# ---------------------------------------------------------------- the links (管理员)

def make_link(c, data, by):
    """POST /teacher-link/create {days, note}: (body, status, log target). The link is in the answer only this once."""
    days = data.get('days')
    try:
        days = LINK_DAYS if days in (None, '') else int(days)
    except (TypeError, ValueError):
        days = 0
    if not 1 <= days <= MAX_DAYS:
        return {'error': f'有效期写 1–{MAX_DAYS} 天', 'field': 'days'}, 400, ''
    note = re.sub(r'\s+', ' ', str(data.get('note') or '')).strip()[:40]
    token, now = secrets.token_urlsafe(32), time.time()
    lid = c.execute('INSERT INTO teacher_links(digest, note, by, created, expires) VALUES(?,?,?,?,?)',
                    (_digest(token), note, str(by or '')[:200], now, now + days * 86400)).lastrowid
    c.commit()
    return ({'ok': True, 'id': lid, 'link': origin() + ROUTE + token, 'expires': _day(now + days * 86400), 'days': days},
            200, f'#t{lid}' + (f' · {note}' if note else ''))


def _status(r, now):
    if r['used_at']:
        return 'used'
    if r['revoked_at']:
        return 'revoked'
    return 'expired' if r['expires'] <= now else 'open'


STATUS_LABEL = {'open': '未使用', 'used': '已注册', 'revoked': '已作废', 'expired': '已过期'}


def links(c, now=None):
    """GET /teacher-links: every link, newest first, and the teacher accounts there are."""
    now = now or time.time()
    out = []
    for r in c.execute('SELECT l.*, u.username FROM teacher_links l LEFT JOIN users u ON u.id=l.used_by ORDER BY l.id DESC LIMIT 200'):
        s = _status(r, now)
        out.append({'id': r['id'], 'note': r['note'], 'by': r['by'], 'created': _day(r['created']), 'expires': _day(r['expires']),
                    'status': s, 'status_label': STATUS_LABEL[s], 'used': _day(r['used_at']),
                    'teacher': {'id': r['used_by'], 'username': r['username']} if r['used_by'] and r['username'] else None})
    teachers = c.execute("SELECT COUNT(*) FROM users WHERE role='teacher'").fetchone()[0]
    return {'items': out, 'teachers': teachers, 'days': LINK_DAYS, 'max_days': MAX_DAYS}


def revoke(c, data):
    """POST /teacher-link/revoke {id}: an unused link stops working at once. (body, status, log target)."""
    r = c.execute('SELECT * FROM teacher_links WHERE id=?', (data.get('id'),)).fetchone()
    if not r:
        return {'error': '没有找到这个链接'}, 404, ''
    if r['used_at']:
        return {'error': '这个链接已经注册过老师账号，不能作废'}, 409, ''
    if not r['revoked_at']:
        c.execute('UPDATE teacher_links SET revoked_at=? WHERE id=?', (time.time(), r['id']))
        c.commit()
    return {'ok': True}, 200, f"#t{r['id']}" + (f" · {r['note']}" if r['note'] else '')


# ---------------------------------------------------------------- using a link (the sign-up page)

def _paused(c, ip, now):
    r = c.execute('SELECT * FROM login_failures WHERE key=?', ('tlink:' + ip,)).fetchone()
    return r if r and r['until'] > now else None


def _wrong(c, ip, now):
    key = 'tlink:' + ip
    r = c.execute('SELECT * FROM login_failures WHERE key=?', (key,)).fetchone()
    if r and r['first'] > now - WINDOW:
        n = r['count'] + 1
        c.execute('UPDATE login_failures SET count=?, until=? WHERE key=?', (n, now + WINDOW if n >= TRIES else 0, key))
    else:
        c.execute('INSERT OR REPLACE INTO login_failures(key, count, first, until) VALUES(?, 1, ?, 0)', (key, now))
    c.commit()


def usable(c, token, ip):
    """(link row, None) or (None, (error body, status)). An unknown token counts toward the pause; one that was real
    but is used, revoked or out of date says so (the teacher asks for a new one)."""
    now, ip = time.time(), str(ip or '')
    p = _paused(c, ip, now)
    if p:
        return None, ({'error': '试错太多次了，请 %d 分钟后再打开链接' % max(1, round((p['until'] - now) / 60)), 'code': 'teacher_link'}, 429)
    token = str(token or '').strip()
    r = c.execute('SELECT * FROM teacher_links WHERE digest=?', (_digest(token),)).fetchone() if re.fullmatch(r'[A-Za-z0-9_-]{30,100}', token) else None
    if not r:
        _wrong(c, ip, now)
        return None, ({'error': '这个老师注册链接不对。请把语流发给你的链接完整地复制到浏览器里打开。', 'code': 'teacher_link'}, 404)
    s = _status(r, now)
    if s != 'open':
        why = {'used': '已经用来注册过一个老师账号了', 'revoked': '已经作废了', 'expired': '已经过期了'}[s]
        return None, ({'error': f'这个老师注册链接{why}。需要的话，请联系语流重新发一个。', 'code': 'teacher_link'}, 410)
    return r, None


def check(c, data, ip):
    """POST /api/teacher/check {token}: whether the sign-up page may offer a teacher sign-up."""
    r, err = usable(c, data.get('token'), ip)
    if err:
        return err
    return {'ok': True, 'expires': _day(r['expires'])}, 200


def claim(c, link_id, now=None):
    """Take the link for the account about to be made: True once, False if someone else just did (no commit here)."""
    now = now or time.time()
    return c.execute('UPDATE teacher_links SET used_at=? WHERE id=? AND used_at IS NULL AND revoked_at IS NULL AND expires>?',
                     (now, link_id, now)).rowcount == 1


def made(c, link_id, uid):
    """The account the link made is a teacher account (in the sign-up's transaction)."""
    c.execute("UPDATE users SET role='teacher', age_band=COALESCE(age_band, '18+'), age_set=COALESCE(age_set, ?) WHERE id=?", (time.time(), uid))
    c.execute('UPDATE teacher_links SET used_by=? WHERE id=?', (uid, link_id))


def set_teacher(c, uid, on):
    """POST /learner/teacher {id, teacher} (管理员, the user's rule 2026-11-26): an existing account becomes a 老师账号, or
    back. Only an account in no class now: a teacher never sits in one. (body, status, user row or None)."""
    u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone() if str(uid or '').isdigit() else None
    if not u:
        return {'error': '没有找到这个学员'}, 404, None
    if on:
        k = c.execute('SELECT k.name FROM class_members m JOIN classes k ON k.id=m.class_id WHERE m.user_id=? AND m.left_at IS NULL', (u['id'],)).fetchone()
        if k:
            return {'error': f"这个账号现在在班级「{k['name']}」里。老师账号不能在班里：请他先退出班级，再设为老师账号"}, 409, u
    c.execute('UPDATE users SET role=? WHERE id=?', ('teacher' if on else None, u['id']))
    c.commit()
    return {'ok': True, 'username': u['username'], 'teacher': bool(on)}, 200, u


# ---------------------------------------------------------------- a teacher's own classes

def _teacher_row(c, uid):
    u = c.execute('SELECT * FROM users WHERE id=?', (uid,)).fetchone()
    return u if is_teacher(u) else None


def create_class(c, uid, data):
    """POST /api/next/class/create {name}: a teacher account makes a class of its own (with a new invite code)."""
    cs = __import__('class_service')
    u = _teacher_row(c, uid)
    if not u:
        return {'error': '只有老师账号能建班。老师账号要用语流发的老师注册链接注册。'}, 403
    name, err = cs._name(data.get('name'))
    if err:
        return err
    if c.execute('SELECT COUNT(*) FROM classes WHERE teacher=? AND active=1', (uid,)).fetchone()[0] >= CLASSES_MAX:
        return {'error': f'一个老师账号最多同时有 {CLASSES_MAX} 个在用的班级。需要更多，请联系语流。', 'field': 'name'}, 409
    now = time.time()
    cid = c.execute('INSERT INTO classes(name, code, teacher, by, created, updated) VALUES(?,?,?,?,?,?)',
                    (name, cs.new_code(c), uid, '老师 ' + u['username'], now, now)).lastrowid
    c.commit()
    body, status = cs.mine(c, uid)
    return {**body, 'created': cid}, status


def rename_class(c, uid, data):
    """POST /api/next/class/rename {id, name}: the teacher renames a class of their own."""
    cs = __import__('class_service')
    k = cs._class(c, data.get('id'))
    if not k or k['teacher'] != uid:
        return {'error': '没有找到这个班级'}, 404
    name, err = cs._name(data.get('name'))
    if err:
        return err
    c.execute('UPDATE classes SET name=?, updated=? WHERE id=?', (name, time.time(), k['id']))
    c.commit()
    return cs.mine(c, uid)


# ---------------------------------------------------------------- on the server

def main(argv):
    """python3 teacher_service.py link [--days N] [--note 备注]: a teacher sign-up link for this site, printed once (for a
    site without the console, such as the 内测版). The data folder is the service's (FLOW_DATA_DIR, as app.py)."""
    if not argv or argv[0] != 'link':
        print(__doc__.split('\n\n')[-1].strip())
        return 2
    days, note = LINK_DAYS, ''
    if '--days' in argv:
        days = argv[argv.index('--days') + 1]
    if '--note' in argv:
        note = argv[argv.index('--note') + 1]
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import app
    app.init()
    with app.db() as c:
        body, status, _ = make_link(c, {'days': days, 'note': note}, 'server')
    if status != 200:
        print(body['error'])
        return 1
    print(f"{body['link']}\n有效到 {body['expires']}（北京时间），只能注册一个老师账号。")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
