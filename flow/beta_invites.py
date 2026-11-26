"""内测版邀请码 (2026-11-26, the owner: 「内测版本能否收紧……我发邀请码才能用」, then 「按你推荐来做」).

With FLOW_SIGNUP_INVITE_ONLY on (the 内测版 only; 语流's sign-up is unchanged), a new 学生账号 needs an invite code, asked
for on the sign-up form both when the email code is requested and at sign-up. A 老师注册链接 (teacher_service) is an
invite of its own and needs none. Accounts made before the switch keep working; the console lists them and can stop
any one of them (账号 → 停用).

- A code is 8 letters and digits people can type (no 0/O, 1/I/L), shown as ABCD-EFGH; spaces, dashes and case do not
  matter. It is made by a 管理员 in the 内测版's console (or with the command below on the server): good for USES
  sign-ups (1–MAX_USES) and DAYS days (1–MAX_DAYS), with a note. The console lists every code (how many used, who signed
  up with it and when, expired, revoked) and revokes one at once.
- Who used which code: beta_invite_uses (invite, account, when). It goes with the account (注销 or the 30-day deletion).
- Wrong codes from one address: TRIES in WINDOW pause checking for WINDOW (the same rule as a 老师注册链接).

    python3 beta_invites.py make [--uses 1] [--days 14] [--note 备注]    # on the 内测版's server: a code, printed
"""
import datetime, os, re, secrets, sys, time

ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
USES, MAX_USES = 1, 200
DAYS, MAX_DAYS = 14, 90
TRIES, WINDOW = 10, 900
TZ = datetime.timezone(datetime.timedelta(hours=8))
NEED = {'error': '内测版要凭邀请码注册，请填写收到的邀请码。', 'field': 'invite', 'code': 'invite'}


def on():
    """FLOW_SIGNUP_INVITE_ONLY: only the 内测版 sets it (the server's environment, A1 with the owner's OK)."""
    return os.getenv('FLOW_SIGNUP_INVITE_ONLY', '').strip().lower() in ('1', 'on', 'yes', 'true')


def schema(c):
    c.execute('''CREATE TABLE IF NOT EXISTS beta_invites(id INTEGER PRIMARY KEY, code TEXT NOT NULL UNIQUE,
      note TEXT NOT NULL DEFAULT '', by TEXT NOT NULL DEFAULT '', created REAL NOT NULL, expires REAL NOT NULL,
      uses INTEGER NOT NULL DEFAULT 1, used INTEGER NOT NULL DEFAULT 0, revoked_at REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS beta_invite_uses(id INTEGER PRIMARY KEY,
      invite_id INTEGER NOT NULL REFERENCES beta_invites(id), user_id INTEGER NOT NULL REFERENCES users(id), used_at REAL NOT NULL)''')


def norm(code):
    """What was typed, as stored: letters and digits only, upper case."""
    return re.sub(r'[^A-Z0-9]', '', str(code or '').upper())[:16]


def shown(code):
    return code[:4] + '-' + code[4:] if len(code) == 8 else code


def _day(t):
    return datetime.datetime.fromtimestamp(t, TZ).strftime('%Y-%m-%d %H:%M') if t else ''


def _int(v, default, lo, hi):
    try:
        v = default if v in (None, '') else int(v)
    except (TypeError, ValueError):
        return None
    return v if lo <= v <= hi else None


# ---------------------------------------------------------------- the codes (管理员, the 内测版's console)

def make(c, data, by):
    """POST /beta-invite/create {uses, days, note}: (body, status, log target)."""
    uses, days = _int(data.get('uses'), USES, 1, MAX_USES), _int(data.get('days'), DAYS, 1, MAX_DAYS)
    if uses is None:
        return {'error': f'能用几次写 1–{MAX_USES}', 'field': 'uses'}, 400, ''
    if days is None:
        return {'error': f'有效期写 1–{MAX_DAYS} 天', 'field': 'days'}, 400, ''
    note = re.sub(r'\s+', ' ', str(data.get('note') or '')).strip()[:40]
    now = time.time()
    for _ in range(20):
        code = ''.join(secrets.choice(ALPHABET) for _ in range(8))
        if not c.execute('SELECT 1 FROM beta_invites WHERE code=?', (code,)).fetchone():
            break
    iid = c.execute('INSERT INTO beta_invites(code, note, by, created, expires, uses) VALUES(?,?,?,?,?,?)',
                    (code, note, str(by or '')[:200], now, now + days * 86400, uses)).lastrowid
    c.commit()
    return ({'ok': True, 'id': iid, 'code': shown(code), 'uses': uses, 'days': days, 'expires': _day(now + days * 86400)},
            200, f'#i{iid}' + (f' · {note}' if note else ''))


def _status(r, now):
    if r['revoked_at']:
        return 'revoked'
    if r['used'] >= r['uses']:
        return 'used'
    return 'expired' if r['expires'] <= now else 'open'


STATUS_LABEL = {'open': '可以用', 'used': '已用完', 'revoked': '已作废', 'expired': '已过期'}


def listing(c, now=None):
    """GET /beta-invites: every code, newest first, with who signed up with it; and the accounts made before codes."""
    now = now or time.time()
    who = {}
    for r in c.execute('SELECT x.invite_id, x.used_at, u.id, u.username FROM beta_invite_uses x JOIN users u ON u.id=x.user_id ORDER BY x.id'):
        who.setdefault(r['invite_id'], []).append({'id': r['id'], 'username': r['username'], 'at': _day(r['used_at'])})
    items = []
    for r in c.execute('SELECT * FROM beta_invites ORDER BY id DESC LIMIT 300'):
        s = _status(r, now)
        items.append({'id': r['id'], 'code': shown(r['code']), 'note': r['note'], 'by': r['by'], 'created': _day(r['created']),
                      'expires': _day(r['expires']), 'uses': r['uses'], 'used': r['used'], 'status': s,
                      'status_label': STATUS_LABEL[s], 'people': who.get(r['id'], [])})
    first = c.execute('SELECT MIN(created) FROM beta_invites').fetchone()[0]
    before = c.execute("SELECT COUNT(*) FROM users u WHERE COALESCE(u.admin,0)=0 AND COALESCE(u.role,'')<>'teacher' "
                       'AND u.id NOT IN (SELECT user_id FROM beta_invite_uses)' + (' AND (u.created IS NULL OR u.created<?)' if first else ''),
                       (first,) if first else ()).fetchone()[0]
    return {'on': on(), 'items': items, 'before': before, 'uses': USES, 'max_uses': MAX_USES, 'days': DAYS, 'max_days': MAX_DAYS}


def revoke(c, data):
    """POST /beta-invite/revoke {id}: the code stops working at once (accounts made with it stay). (body, status, log)."""
    r = c.execute('SELECT * FROM beta_invites WHERE id=?', (data.get('id'),)).fetchone()
    if not r:
        return {'error': '没有找到这个邀请码'}, 404, ''
    if not r['revoked_at']:
        c.execute('UPDATE beta_invites SET revoked_at=? WHERE id=?', (time.time(), r['id']))
        c.commit()
    return {'ok': True}, 200, f"#i{r['id']} {shown(r['code'])}" + (f" · {r['note']}" if r['note'] else '')


# ---------------------------------------------------------------- using a code (the sign-up form)

def _paused(c, ip, now):
    r = c.execute('SELECT * FROM login_failures WHERE key=?', ('binv:' + ip,)).fetchone()
    return r if r and r['until'] > now else None


def _wrong(c, ip, now):
    key = 'binv:' + ip
    r = c.execute('SELECT * FROM login_failures WHERE key=?', (key,)).fetchone()
    if r and r['first'] > now - WINDOW:
        n = r['count'] + 1
        c.execute('UPDATE login_failures SET count=?, until=? WHERE key=?', (n, now + WINDOW if n >= TRIES else 0, key))
    else:
        c.execute('INSERT OR REPLACE INTO login_failures(key, count, first, until) VALUES(?, 1, ?, 0)', (key, now))
    c.commit()


def check(c, code, ip=''):
    """(invite row, None) when code may make an account now, else (None, (body, status)). Nothing is used up here."""
    now = time.time()
    if ip and _paused(c, ip, now):
        return None, ({'error': '邀请码错了太多次，请 15 分钟后再试', 'field': 'invite', 'code': 'busy'}, 429)
    code = norm(code)
    if not code:
        return None, (NEED, 403)
    r = c.execute('SELECT * FROM beta_invites WHERE code=?', (code,)).fetchone()
    if not r:
        if ip:
            _wrong(c, ip, now)
        return None, ({'error': '邀请码不对，请核对一下（字母不分大小写，横线可以不写）', 'field': 'invite', 'code': 'invite'}, 403)
    s = _status(r, now)
    if s != 'open':
        msg = {'used': '这个邀请码的名额已经用完了', 'revoked': '这个邀请码已经作废了', 'expired': '这个邀请码已经过期了'}[s]
        return None, ({'error': msg + '，请向发码的人要一个新的。', 'field': 'invite', 'code': 'invite'}, 403)
    return r, None


def claim(c, invite_id, now=None):
    """Use up one place of the code, if it still has one (one statement: two sign-ups at once cannot both take the last).
    The caller commits, with the account."""
    now = now or time.time()
    return c.execute('UPDATE beta_invites SET used=used+1 WHERE id=? AND used<uses AND revoked_at IS NULL AND expires>?',
                     (invite_id, now)).rowcount == 1


def record(c, invite_id, uid, now=None):
    c.execute('INSERT INTO beta_invite_uses(invite_id, user_id, used_at) VALUES(?,?,?)', (invite_id, uid, now or time.time()))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description='内测版邀请码：在内测版的服务器上生成一个邀请码')
    sub = ap.add_subparsers(dest='cmd', required=True)
    m = sub.add_parser('make')
    m.add_argument('--uses', type=int, default=USES)
    m.add_argument('--days', type=int, default=DAYS)
    m.add_argument('--note', default='')
    a = ap.parse_args(argv)
    import app
    with app.db() as c:
        schema(c)
        body, status, _ = make(c, {'uses': a.uses, 'days': a.days, 'note': a.note}, 'server')
    if status != 200:
        raise SystemExit(body['error'])
    print(f"邀请码：{body['code']}（能用 {body['uses']} 次，{body['expires']} 以前有效）")


if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    main()
