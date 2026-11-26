"""切换账号 (2026-11-26, the owner in A0: 「按推荐定」; plan in the shared notes account-switch/plan.md, D2 and B9 read it).

One device remembers up to MAX accounts: the one in use (cookie flow_session, as before) and the others in a second
HttpOnly cookie, flow_more (their own session tokens, '.'-joined). A tap switches without a password: the two cookies
trade places. Nothing new is kept on the server: each account's session is its own row in sessions, ends on its own
SESSION_DAYS after its last use, and goes with 退出所有设备, a new password, 停用 or 注销 as before; a token that no
longer opens an account is dropped the next time the list is read. Never in the list (D2): a 员工账号 (admin=1: each
time with the password) and an account paused for 数据存放在香港 (it signs in as usual to agree again, export or
delete). Tokens never reach the page's scripts or any JSON; the list says names and roles only, never an email.
Switching into an account that has not agreed is as signing in: the consent page first (the router, 81-privacy.js).
"""
import re, time

MAX = 3
COOKIE = 'flow_more'
TOKEN = re.compile(r'[A-Za-z0-9_-]{20,80}')
FULL = {'error': '这台设备最多记住 3 个账号，先移除一个', 'code': 'switch_full'}
STAFF = {'error': '员工账号请每次用密码登录，不能加进切换账号', 'code': 'switch_staff'}


def tokens(raw):
    """The remembered tokens from the flow_more cookie's value: well-formed, no repeats, at most MAX - 1."""
    out = []
    for t in str(raw or '').split('.'):
        if TOKEN.fullmatch(t) and t not in out:
            out.append(t)
    return out[:MAX - 1]


def cookie(toks, days, secure):
    """Set-Cookie for flow_more: the tokens, or the cookie gone when there are none."""
    if not toks:
        return f'{COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax' + ('; Secure' if secure else '')
    return f'{COOKIE}={".".join(toks)}; HttpOnly; SameSite=Lax; Path=/; Max-Age={days * 86400}' + ('; Secure' if secure else '')


def _account(c, token, now):
    """The account a token opens, if it may be remembered: a live session, not stopped, not staff, not paused."""
    r = c.execute('SELECT u.*, s.token, s.expires FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token=? AND s.expires>?',
                  (token, now)).fetchone()
    if not r or r['admin'] or ('disabled' in r.keys() and r['disabled']):
        return None
    if __import__('privacy_service').storage(r) == 'no':
        return None
    return r


def _row(u, current):
    return {'id': u['id'], 'username': u['username'], 'teacher': (u['role'] if 'role' in u.keys() else '') == 'teacher', 'current': current}


def remembered(c, current, raw, now=None):
    """[(token, account row)] this device remembers besides the account in use, in order; what no longer may is left
    out (the caller writes the cookie again when the list shrank)."""
    now = now or time.time()
    out, seen = [], {current['id']} if current else set()
    for t in tokens(raw):
        u = _account(c, t, now)
        if u and u['id'] not in seen:
            seen.add(u['id'])
            out.append((t, u))
    return out


def listing(c, current, raw, now=None):
    """GET /api/account/list: {items: [the account in use first, then the others], max, full, staff}, and the tokens
    still good (to write back when some went)."""
    others = remembered(c, current, raw, now)
    items = ([_row(current, True)] if current else []) + [_row(u, False) for _, u in others]
    staff = bool(current and current['admin'])
    return {'items': items, 'max': MAX, 'full': len(items) >= MAX, 'staff': staff}, [t for t, _ in others]


def switch(c, current, raw, target, now=None):
    """POST /api/account/switch {id}: (body, status, new flow_session token or None, new flow_more tokens or None).
    The account in use goes into the list (a 员工账号 is signed out instead: never remembered)."""
    others = remembered(c, current, raw, now)
    hit = next(((t, u) for t, u in others if str(u['id']) == str(target)), None)
    if not hit:
        return {'error': '这个账号已经不在这台设备上了，请重新登录', 'code': 'switch_gone'}, 404, None, [t for t, _ in others]
    keep = [t for t, u in others if t != hit[0]]
    if current:
        if current['admin']:
            c.execute('DELETE FROM sessions WHERE token=?', (current['token'],)); c.commit()
        else:
            keep = [current['token']] + keep
    return {'ok': True, 'username': hit[1]['username'], 'teacher': _row(hit[1], True)['teacher']}, 200, hit[0], keep[:MAX - 1]


def forget(c, current, raw, target, now=None):
    """POST /api/account/forget {id}: this device forgets an account it remembers (its session here ends; the account and
    its records stay). (body, status, flow_more tokens)."""
    others = remembered(c, current, raw, now)
    hit = next(((t, u) for t, u in others if str(u['id']) == str(target)), None)
    if hit:
        c.execute('DELETE FROM sessions WHERE token=?', (hit[0],)); c.commit()
    return {'ok': True}, 200, [t for t, u in others if not hit or t != hit[0]]


def adding(c, current, raw, new_user, now=None):
    """Signing in with add: true while an account is in use: None when it may be added, else the refusal (body, status).
    The new account may not be staff; the device may not remember more than MAX (the one signing in again replaces
    itself). new_user None: an account about to be made (注册), checked before it is."""
    if new_user is not None and new_user['admin']:
        return STAFF, 409
    others = remembered(c, current, raw, now)
    ids = {u['id'] for _, u in others} | ({current['id']} if current and not current['admin'] else set())
    if (new_user is None or new_user['id'] not in ids) and len(ids) + 1 > MAX:
        return FULL, 409
    return None


def after_add(c, current, raw, new_user, now=None):
    """The flow_more tokens once new_user is the account in use: the one used before goes in (a 员工账号 is signed out
    instead), the new account's older token here goes (it has a new one)."""
    others = remembered(c, current, raw, now)
    keep = []
    if current and current['id'] != new_user['id']:
        if current['admin']:
            c.execute('DELETE FROM sessions WHERE token=?', (current['token'],))
        else:
            keep.append(current['token'])
    elif current:  # the same account signing in again: its new token replaces the one in use here
        c.execute('DELETE FROM sessions WHERE token=?', (current['token'],))
    for t, u in others:
        if u['id'] == new_user['id']:
            c.execute('DELETE FROM sessions WHERE token=?', (t,))
        else:
            keep.append(t)
    c.commit()
    return keep[:MAX - 1]
