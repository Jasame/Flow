"""切换账号 (account_switch.py; the owner, 2026-11-26: 「按推荐定」): a device remembers up to 3 accounts, the one in use
in flow_session and the others in the HttpOnly flow_more; a tap switches without a password; adding one keeps the one in
use; 从这台设备移除 ends that account's session here. Never in the list: a 员工账号, an account paused for 数据存放在
香港, one whose sessions ended elsewhere (退出所有设备, a new password). No token in any answer; no email in the list."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, privacy_service as pv  # noqa: E402

PW = 'a long password here'


class Device:
    """One browser: its cookie jar, as the site sets it."""
    def __init__(self, test):
        self.t, self.jar = test, {}

    def call(self, path, data=None, csrf=True, header=True):
        h = {'Content-Type': 'application/json'}
        if self.jar:
            h['Cookie'] = '; '.join(f'{k}={v}' for k, v in self.jar.items())
        if data is not None and header:
            h['X-Requested-With'] = 'flow'
        if data is not None and csrf and 'flow_session' in self.jar:
            s = self._get('/api/session')
            if s.get('user'):
                h['X-CSRF-Token'] = s['user']['csrf']
        req = urllib.request.Request(f'http://127.0.0.1:{self.t.site.server_address[1]}{path}',
                                     data=json.dumps(data).encode() if data is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                st, body, hd = r.status, r.read(), r.headers
        except urllib.error.HTTPError as e:
            st, body, hd = e.code, e.read(), e.headers
        for line in hd.get_all('Set-Cookie') or []:
            jar = SimpleCookie(); jar.load(line)
            for k, m in jar.items():
                if m['max-age'] == '0' or not m.value:
                    self.jar.pop(k, None)
                else:
                    self.jar[k] = m.value
        self.t.seen.append(body.decode('utf-8', 'replace'))
        return st, json.loads(body or b'{}')

    def _get(self, path):
        h = {'Cookie': '; '.join(f'{k}={v}' for k, v in self.jar.items())}
        req = urllib.request.Request(f'http://127.0.0.1:{self.t.site.server_address[1]}{path}', headers=h)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read() or b'{}')

    def login(self, name, add=False):
        return self.call('/api/login', {'username': name, 'password': PW, **({'add': True} if add else {})})

    def names(self):
        st, d = self.call('/api/account/list')
        return [(x['username'], x['current']) for x in d['items']]


class AccountSwitch(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for p in (patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0'})):
            p.start(); self.addCleanup(p.stop)
        app.SECURE = False
        app.RATE.clear()
        app.init()
        self.ids = {}
        with app.db() as c:
            for name, admin, role in (('lin', 0, None), ('wang', 0, 'teacher'), ('zhao', 0, None), ('qian', 0, None), ('boss', 1, None)):
                self.ids[name] = c.execute('INSERT INTO users(username,password,email,admin,role,storage_ok,terms_ok,terms_version,age_band) '
                                           'VALUES(?,?,?,?,?,?,?,?,?)', (name, app.password(PW), f'{name}@example.com', admin, role, time.time(),
                                                                         time.time(), pv.CONSENT_VERSION, '18+')).lastrowid
            c.commit()
        self.site = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.site.serve_forever, daemon=True).start()
        self.addCleanup(lambda: (self.site.shutdown(), self.site.server_close()))
        self.seen = []

    def tokens(self):
        with app.db() as c:
            return [r[0] for r in c.execute('SELECT token FROM sessions')]

    def test_add_switch_and_forget(self):
        d = Device(self)
        self.assertEqual(d.login('lin')[0], 200)
        self.assertNotIn('flow_more', d.jar)
        self.assertEqual(d.login('wang', add=True)[0], 200)  # the student stays on this device
        self.assertEqual(d.names(), [('wang', True), ('lin', False)])
        st, body = d.call('/api/account/list')
        self.assertTrue(body['items'][0]['teacher']); self.assertNotIn('email', json.dumps(body))
        st, body = d.call('/api/account/switch', {'id': self.ids['lin']})
        self.assertEqual((st, body['username']), (200, 'lin'))
        self.assertEqual(d.names(), [('lin', True), ('wang', False)])
        self.assertEqual(d._get('/api/session')['user']['username'], 'lin')
        self.assertEqual(d.call('/api/account/forget', {'id': self.ids['wang']})[0], 200)
        self.assertEqual(d.names(), [('lin', True)])
        with app.db() as c:  # the teacher's session here has ended; the account stays
            self.assertIsNone(c.execute('SELECT 1 FROM sessions WHERE user_id=?', (self.ids['wang'],)).fetchone())
            self.assertIsNotNone(c.execute('SELECT 1 FROM users WHERE id=?', (self.ids['wang'],)).fetchone())
        for t in self.tokens():  # no answer ever carries a token
            self.assertFalse(any(t in b for b in self.seen))

    def test_three_at_most_and_never_staff(self):
        d = Device(self)
        d.login('lin'); d.login('wang', add=True); d.login('zhao', add=True)
        st, body = d.login('qian', add=True)
        self.assertEqual((st, body['code']), (409, 'switch_full'))
        self.assertEqual(d.names()[0], ('zhao', True))
        with app.db() as c:
            n = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
        st, body = d.call('/api/register', {'add': True, 'username': 'new1', 'password': PW, 'email': 'n@example.com', 'code': '000000',
                                            'age': '18+', 'storage': True, 'terms': True})
        self.assertEqual((st, body['code']), (409, 'switch_full'))  # refused before any account is made
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM users').fetchone()[0], n)
        self.assertEqual(d.login('lin', add=True)[0], 200)  # one already here: signs in again, no fourth
        self.assertEqual([x for x, _ in d.names()], ['lin', 'zhao', 'wang'])
        e = Device(self); e.login('lin')
        st, body = e.login('boss', add=True)
        self.assertEqual((st, body['code']), (409, 'switch_staff'))

    def test_what_ended_elsewhere_or_paused_leaves_the_list(self):
        d = Device(self)
        d.login('lin'); d.login('wang', add=True); d.login('zhao', add=True)
        other = Device(self); other.login('lin')
        other.call('/api/logout', {'all': True})  # 退出所有设备 on another phone
        self.assertEqual([x for x, _ in d.names()], ['zhao', 'wang'])
        with app.db() as c:
            c.execute('UPDATE users SET storage_ok=NULL, storage_no=? WHERE id=?', (time.time(), self.ids['wang'])); c.commit()
        self.assertEqual(d.names(), [('zhao', True)])
        self.assertNotIn('flow_more', d.jar)  # the cookie is written again without them

    def test_signed_out_the_others_stay_and_the_guards_hold(self):
        d = Device(self)
        d.login('lin'); d.login('wang', add=True)
        self.assertEqual(d.call('/api/account/switch', {'id': self.ids['lin']}, header=False)[0], 403)  # another site's form
        self.assertEqual(d.call('/api/account/switch', {'id': self.ids['lin']}, csrf=False)[0], 403)  # no CSRF while signed in
        d.call('/api/logout', {})
        self.assertEqual(d.names(), [('lin', False)])  # signed out: the one remembered is offered
        st, body = d.call('/api/account/switch', {'id': self.ids['lin']})
        self.assertEqual((st, d._get('/api/session')['user']['username']), (200, 'lin'))
        self.assertEqual(d.call('/api/account/switch', {'id': 99999})[0], 404)

    def test_switching_into_an_account_that_has_not_agreed_asks_first(self):
        d = Device(self)
        d.login('lin'); d.login('wang', add=True)
        with app.db() as c:  # the teacher's agreement is to an older 用户协议 now
            c.execute("UPDATE users SET terms_version='2026-01-01/2026-01-01' WHERE id=?", (self.ids['lin'],)); c.commit()
        self.assertEqual(d.call('/api/account/switch', {'id': self.ids['lin']})[0], 200)
        st, body = d.call('/api/next/profile', {'level': 'B1'})
        self.assertEqual((st, body.get('code'), body.get('need')), (403, 'storage', 'terms'))  # the consent page first (81-privacy.js)
        self.assertNotEqual(d._get('/api/session')['user']['terms'], 'ok')  # the router's test (S.user.terms !== 'ok')


if __name__ == '__main__':
    unittest.main()
