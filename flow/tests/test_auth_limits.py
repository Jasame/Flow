"""Ceilings on sign-in that asking again does not get round (2026-11-25, 语流 A5): codes an email gets a day, wrong codes
an email may type a day, sign-up codes the site sends an hour, answers that tell an address whether an email or a
username is taken, the account's own password typed again, JSON-only sign-in routes, the address a guest is counted
by, and the page's CSP. Mail goes to FLOW_MAIL_OUTBOX (files), never to a real address."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: E402
import auth_service  # noqa: E402

PW = 'correct horse battery'


class AuthLimitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_MAIL_OUTBOX': str(Path(self.tmp.name) / 'outbox')}); self.env.start()
        os.environ.pop('FLOW_TRUST_CF', None); os.environ.pop('FLOW_REGISTER_CODES_PER_HOUR', None)
        app.SECURE = False
        app.RATE.clear()
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password,email,storage_ok,terms_version) VALUES(?,?,?,1,?)', ('learner', app.password(PW), 'learner@example.com', __import__('privacy_service').CONSENT_VERSION))
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.cookie = ''; self.csrf = ''

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def call(self, path, data=None, ip='198.51.100.7', headers=None, raw=None):
        h = {'Content-Type': 'application/json', 'Cookie': self.cookie, 'X-Real-IP': ip, **(headers or {})}
        if self.csrf: h['X-CSRF-Token'] = self.csrf
        body = raw if raw is not None else json.dumps(data).encode() if data is not None else None
        req = urllib.request.Request(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', data=body, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b'{}'), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}'), dict(e.headers)

    def codes(self, email, purpose, n, tries=0, ago=60):
        """n earlier codes for this email and purpose, each with this many wrong tries, made ago seconds back."""
        now = time.time()
        with app.db() as c:
            for _ in range(n):
                c.execute('INSERT INTO email_codes(email,purpose,salt,digest,expires,created,ip,tries,used) VALUES(?,?,?,?,?,?,?,?,1)',
                          (email, purpose, 'x', 'y', now - ago + auth_service.TTL, now - ago, '203.0.113.1', tries))

    # ---- codes an email gets a day
    def test_an_email_gets_at_most_ten_codes_for_one_purpose_a_day(self):
        self.codes('learner@example.com', 'login', auth_service.CODES_PER_DAY - 1)
        st, body, _ = self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'login'})
        self.assertEqual(st, 200, body)
        with app.db() as c:
            c.execute('DELETE FROM mail_limits')  # past the 60-second wait between codes
        st, body, _ = self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'login'})
        self.assertEqual((st, body.get('code')), (429, 'codes_today'))
        self.assertIn('密码登录', body['error'])
        # another purpose has its own ceiling, and codes older than a day no longer count
        self.assertEqual(self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'reset'})[0], 200)
        with app.db() as c:
            c.execute('UPDATE email_codes SET created=created-86400'); c.execute('DELETE FROM mail_limits')
        self.assertEqual(self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'login'})[0], 200)

    # ---- wrong codes an email may type a day
    def test_wrong_codes_count_across_codes_and_past_the_ceiling_even_a_right_code_waits(self):
        self.codes('learner@example.com', 'login', 4, tries=auth_service.TRIES)  # 20 wrong in four earlier codes
        st, _, _ = self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'login'})
        self.assertEqual(st, 200)
        mail = sorted((Path(self.tmp.name) / 'outbox').glob('*.txt'))[-1].read_text(encoding='utf-8')
        code = __import__('re').search(r'(\d{6})', [l for l in mail.splitlines() if l.startswith('Subject:')][0]).group(1)
        st, body, _ = self.call('/api/login', {'method': 'code', 'email': 'learner@example.com', 'code': code})
        self.assertEqual(st, 400); self.assertIn('今天先不能再用验证码', body['error'])
        # password login still works
        self.assertEqual(self.call('/api/login', {'username': 'learner', 'password': PW})[0], 200)

    def test_a_few_wrong_codes_do_not_reach_the_ceiling(self):
        self.codes('learner@example.com', 'login', 2, tries=auth_service.TRIES)  # 10 wrong
        with app.db() as c:
            self.assertNotIn('今天先不能', auth_service.check(c, 'learner@example.com', 'login', '000000'))

    # ---- sign-up codes the site sends an hour
    def test_the_site_sends_a_limited_number_of_sign_up_codes_an_hour(self):
        with patch.dict(os.environ, {'FLOW_REGISTER_CODES_PER_HOUR': '3'}):
            for k in range(3):
                st, body, _ = self.call('/api/auth/code', {'email': f'new{k}@example.com', 'purpose': 'register'}, ip=f'198.51.100.{10 + k}')
                self.assertEqual(st, 200, body)
            st, body, _ = self.call('/api/auth/code', {'email': 'new9@example.com', 'purpose': 'register'}, ip='198.51.100.99')
            self.assertEqual((st, body.get('code')), (429, 'busy'))
            # signing in by code is not held up by sign-ups
            self.assertEqual(self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'login'}, ip='198.51.100.99')[0], 200)

    # ---- whether an email or a username is taken
    def test_an_address_told_too_often_whether_an_email_is_taken_is_paused(self):
        with patch.object(auth_service, 'PROBES', 3):
            for _ in range(3):
                st, body, _ = self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'register'})
                self.assertEqual((st, body.get('code')), (409, 'email_taken'))
            # now nothing from this address says whether an email is taken: not the code route, not sign-up, not code login
            for path, data in (('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'register'}),
                               ('/api/auth/code', {'email': 'nobody@example.com', 'purpose': 'login'}),
                               ('/api/login', {'method': 'code', 'email': 'nobody@example.com', 'code': '123456'}),
                               ('/api/auth/reset', {'email': 'nobody@example.com', 'code': '123456', 'password': PW}),
                               ('/api/register', {'username': 'learner', 'password': PW, 'email': 'x@example.com', 'code': '123456'})):
                st, body, _ = self.call(path, data)
                self.assertEqual((st, body.get('code')), (429, 'busy'), path)
            # another address is not affected
            self.assertEqual(self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'register'}, ip='198.51.100.8')[0], 409)

    def test_unknown_emails_and_taken_usernames_count_too(self):
        with patch.object(auth_service, 'PROBES', 2):
            self.assertEqual(self.call('/api/login', {'method': 'code', 'email': 'nobody@example.com', 'code': '123456'})[0], 404)
            self.assertEqual(self.call('/api/register', {'username': 'learner', 'password': PW, 'age': '18+', 'storage': True, 'terms': True})[0], 409)
            self.assertEqual(self.call('/api/auth/code', {'email': 'someone@example.com', 'purpose': 'register'})[1].get('code'), 'busy')

    # ---- the account's own password typed again
    def test_changing_the_password_pauses_after_five_wrong_current_passwords(self):
        st, _, h = self.call('/api/login', {'username': 'learner', 'password': PW})
        self.assertEqual(st, 200)
        self.cookie = h['Set-Cookie'].split(';')[0]; self.csrf = self.call('/api/session')[1]['user']['csrf']
        for k in range(4):
            st, body, _ = self.call('/api/password', {'old_password': 'wrong password %d' % k, 'new_password': 'another long password'})
            self.assertEqual(st, 400); self.assertTrue(body['error'].startswith('原密码不正确'))
        st, body, _ = self.call('/api/password', {'old_password': 'wrong again', 'new_password': 'another long password'})
        self.assertIn('已暂停 15 分钟', body['error'])
        st, body, _ = self.call('/api/password', {'old_password': PW, 'new_password': 'another long password'})
        self.assertEqual(st, 400); self.assertIn('分钟后再试', body['error'])
        # password login has its own lock and is not paused by this one
        self.assertEqual(self.call('/api/login', {'username': 'learner', 'password': PW}, ip='198.51.100.50')[0], 200)

    def test_the_right_current_password_clears_the_count(self):
        st, _, h = self.call('/api/login', {'username': 'learner', 'password': PW})
        self.cookie = h['Set-Cookie'].split(';')[0]; self.csrf = self.call('/api/session')[1]['user']['csrf']
        for _ in range(4):
            self.call('/api/password', {'old_password': 'nope nope nope', 'new_password': 'another long password'})
        st, body, _ = self.call('/api/password', {'old_password': PW, 'new_password': 'another long password'})
        self.assertEqual(st, 200, body)
        with app.db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM login_failures WHERE key LIKE 'pw:%'").fetchone())

    # ---- JSON only on the sign-in routes
    def test_sign_in_routes_take_json_only(self):
        for path in ('/api/login', '/api/register', '/api/auth/code', '/api/auth/reset', '/api/recovery/request', '/api/teacher/check'):
            st, _, _ = self.call(path, raw=b'{"username":"learner","password":"x"}', headers={'Content-Type': 'text/plain'})
            self.assertEqual(st, 415, path)
        self.assertEqual(self.call('/api/login', {'username': 'learner', 'password': PW}, headers={'Content-Type': 'application/json; charset=utf-8'})[0], 200)

    # ---- the address a guest is counted by
    def test_a_guest_cannot_pick_a_new_address_with_a_header(self):
        fb = __import__('feedback_service')
        for k in range(fb.GUEST_DAILY):
            st, body, _ = self.call('/api/feedback', {'kind': 'bug', 'text': '页面打不开了 %d' % k}, headers={'CF-Connecting-IP': f'192.0.2.{k + 1}'})
            self.assertEqual(st, 200, body)
        st, _, _ = self.call('/api/feedback', {'kind': 'bug', 'text': '页面又打不开了'}, headers={'CF-Connecting-IP': '192.0.2.200'})
        self.assertEqual(st, 429)
        # behind Cloudflare's proxy (FLOW_TRUST_CF=1) its header is the visitor's address
        with patch.dict(os.environ, {'FLOW_TRUST_CF': '1'}):
            self.assertEqual(self.call('/api/feedback', {'kind': 'bug', 'text': '页面又打不开了'}, headers={'CF-Connecting-IP': '192.0.2.201'})[0], 200)

    # ---- the page's CSP, and the sign-in ceiling's table
    def test_the_csp_also_closes_base_form_and_object(self):
        csp = self.call('/api/health')[2]['Content-Security-Policy']
        for part in ("script-src 'self'", "base-uri 'none'", "form-action 'self'", "object-src 'none'", "frame-ancestors 'none'"):
            self.assertIn(part, csp)

    def test_the_per_address_table_drops_addresses_it_has_not_seen_for_a_minute(self):
        old = time.time() - 120
        app.RATE.update({f'2001:db8::{k:x}': [old] for k in range(5001)})
        self.call('/api/login', {'username': 'learner', 'password': 'wrong'})
        self.assertLess(len(app.RATE), 10)


if __name__ == '__main__':
    unittest.main()
