"""内测版邀请码 (beta_invites.py; the owner, 2026-11-26: 「内测版本能否收紧……我发邀请码才能用」, then 「按你推荐来做」):
with FLOW_SIGNUP_INVITE_ONLY on, a new 学生账号 needs a code, at the email-code step and at sign-up; codes are made and
revoked in the 内测版's console only, for N sign-ups and D days; who used which code is kept with the account; a 老师注册
链接 needs none; 语流's sign-up (the switch off) is unchanged. Mail goes to FLOW_MAIL_OUTBOX (files)."""
import json, os, re, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, beta_invites as bi, flow_admin  # noqa: E402

PW = 'correct horse battery'
BOSS = 'boss@example.com'


class InviteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = Path(self.tmp.name) / 'outbox'
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'CHANNEL', 'beta'),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_MAIL_OUTBOX': str(self.outbox),
                                                'FLOW_SIGNUP_INVITE_ONLY': '1', 'FLOW_ADMIN_EMAILS': BOSS})]
        for p in self.patches:
            p.start()
        app.SECURE = False
        app.RATE.clear()
        app.init()
        self.site = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.admin = ThreadingHTTPServer(('127.0.0.1', 0), flow_admin.AdminHandler)
        for s in (self.site, self.admin):
            threading.Thread(target=s.serve_forever, daemon=True).start()
        self.n = 0

    def tearDown(self):
        for s in (self.site, self.admin):
            s.shutdown(); s.server_close()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def call(self, srv, path, data=None, headers=None):
        req = urllib.request.Request(f'http://127.0.0.1:{srv.server_address[1]}{path}', data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def console(self, path, data=None):
        h = {'Cf-Access-Authenticated-User-Email': BOSS}
        if data is not None:
            h['X-Requested-With'] = 'xmc'
        return self.call(self.admin, '/flow-beta/api' + path, data, h)

    def ask(self, email, invite=None, ip='198.51.100.7'):
        body = {'email': email, 'purpose': 'register', **({'invite': invite} if invite is not None else {})}
        return self.call(self.site, '/api/auth/code', body, {'X-Real-IP': ip})

    def mailed_code(self, email):
        for f in sorted(self.outbox.glob('*.txt'), reverse=True):
            text = f.read_text(encoding='utf-8')
            if email in text:
                return re.search(r'(\d{6})', [l for l in text.splitlines() if l.startswith('Subject:')][0]).group(1)
        self.fail('no code mailed to ' + email)

    def sign_up(self, name, invite, **extra):
        self.n += 1
        ip = f'198.51.100.{10 + self.n}'
        email = f'{name}@example.com'
        st, body = self.ask(email, invite, ip)
        if st != 200:
            return st, body
        return self.call(self.site, '/api/register', {'username': name, 'password': PW, 'email': email, 'code': self.mailed_code(email),
                                                     'age': '18+', 'storage': True, 'terms': True, 'invite': invite, **extra}, {'X-Real-IP': ip})

    def make(self, uses=1, days=14, note=''):
        st, body = self.console('/beta-invite/create', {'uses': uses, 'days': days, 'note': note})
        self.assertEqual(st, 200, body)
        return body

    def test_the_page_is_told_and_a_code_is_needed_before_any_mail(self):
        self.assertTrue(self.call(self.site, '/api/health')[1]['invite'])
        self.assertTrue(self.call(self.site, '/api/session')[1]['invite'])
        st, body = self.ask('a@example.com')
        self.assertEqual((st, body['field'], body['code']), (403, 'invite', 'invite'))
        self.assertEqual(self.ask('a@example.com', 'NOPE-NOPE')[0], 403)
        self.assertFalse(list(self.outbox.glob('*.txt')) if self.outbox.exists() else [])  # nothing mailed

    def test_a_code_makes_its_sign_ups_then_stops_and_who_used_it_shows(self):
        inv = self.make(uses=2, note='小林')
        self.assertRegex(inv['code'], r'^[A-Z2-9]{4}-[A-Z2-9]{4}$')
        typed = inv['code'].lower().replace('-', ' ')  # case, spaces and the dash do not matter
        self.assertEqual(self.sign_up('lin1', typed)[0], 200)
        self.assertEqual(self.sign_up('lin2', inv['code'])[0], 200)
        st, body = self.sign_up('lin3', inv['code'])
        self.assertEqual((st, body['field']), (403, 'invite'))
        self.assertIn('用完', body['error'])
        st, d = self.console('/beta-invites')
        row = next(x for x in d['items'] if x['id'] == inv['id'])
        self.assertEqual((row['used'], row['uses'], row['status'], [p['username'] for p in row['people']]), (2, 2, 'used', ['lin1', 'lin2']))
        log = self.call(self.admin, '/flow-beta/api/log', None, {'Cf-Access-Authenticated-User-Email': BOSS})[1]['items']
        self.assertEqual(log[-1]['action'], 'invite-create')

    def test_a_revoked_or_expired_code_makes_none(self):
        a, b = self.make(), self.make(days=1)
        self.assertEqual(self.console('/beta-invite/revoke', {'id': a['id']})[0], 200)
        self.assertIn('作废', self.sign_up('x1', a['code'])[1]['error'])
        with app.db() as c:
            c.execute('UPDATE beta_invites SET expires=? WHERE id=?', (time.time() - 1, b['id'])); c.commit()
        self.assertIn('过期', self.sign_up('x2', b['code'])[1]['error'])

    def test_wrong_codes_from_one_address_pause_it(self):
        for _ in range(bi.TRIES):
            self.ask('w@example.com', 'WRONGCODE', ip='203.0.113.9')
        st, body = self.ask('w@example.com', 'WRONGCODE', ip='203.0.113.9')
        self.assertEqual((st, body['code']), (429, 'busy'))

    def test_only_the_beta_console_makes_codes(self):
        with patch.object(app, 'CHANNEL', 'prod'):
            self.assertEqual(self.console('/beta-invite/create', {'uses': 1})[0], 409)

    def test_the_uses_go_with_the_account_and_the_filter_lists_the_older_ones(self):
        with app.db() as c:  # an account from before the codes
            c.execute("INSERT INTO users(username,password,created,storage_ok) VALUES('old',?,?,1)", (app.password(PW), time.time() - 86400))
            c.commit()
        inv = self.make()
        self.assertEqual(self.sign_up('newone', inv['code'])[0], 200)
        st, d = self.console('/learners?filter=no_invite')
        self.assertEqual([r['username'] for r in d['items']], ['old'])
        self.assertEqual(self.console('/beta-invites')[1]['before'], 1)
        with app.db() as c:
            uid = c.execute("SELECT id FROM users WHERE username='newone'").fetchone()
            got = json.loads(__import__('account_data').records(c, uid))  # 导出我的数据 carries the code and when (D2)
            self.assertEqual(got['tables']['beta_invite_uses'][0]['code'], inv['code'])
            self.assertIn('beta_invite_uses', got['目录'])
            uid = uid[0]
            __import__('account_data').forget(c, uid)
            self.assertIsNone(c.execute('SELECT 1 FROM beta_invite_uses WHERE user_id=?', (uid,)).fetchone())

    def test_the_switch_off_is_sign_up_as_before(self):
        with patch.dict(os.environ, {'FLOW_SIGNUP_INVITE_ONLY': ''}), patch.object(app, 'CHANNEL', 'prod'):
            self.assertFalse(self.call(self.site, '/api/health')[1]['invite'])
            self.assertEqual(self.sign_up('free', None)[0], 200)
            names = [f['key'] for f in self.console('/learners')[1]['filters']]
            self.assertNotIn('no_invite', names)  # 语流's console has no such filter


if __name__ == '__main__':
    unittest.main()
