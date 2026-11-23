"""r19 sign-in: sessions that last while a learner keeps coming back, a lock after repeated wrong passwords, a
forgotten password reset with an emailed code, an email bound with a code, signing out everywhere, and usernames
that never read as an email. Mail goes to FLOW_MAIL_OUTBOX (files), never to a real address."""
import json, os, re, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: E402

PW = 'correct horse battery'
DAY = 86400


class LoginTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = Path(self.tmp.name) / 'outbox'
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'l.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_MAIL_OUTBOX': str(self.outbox)}); self.env.start()
        app.SECURE = False
        app.RATE.clear()  # the per-address ceiling on sign-in attempts (30 a minute) is shared by every test here
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password,email) VALUES(?,?,?)', ('learner', app.password(PW), 'learner@example.com'))
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.cookie = ''; self.csrf = ''

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def call(self, path, data=None, cookie=None):
        h = {'Content-Type': 'application/json', 'Cookie': self.cookie if cookie is None else cookie}
        if self.csrf: h['X-CSRF-Token'] = self.csrf
        req = urllib.request.Request(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', data=json.dumps(data).encode() if data is not None else None, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b'{}'), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}'), dict(e.headers)

    def sign_in(self, username='learner', password=PW):
        st, body, h = self.call('/api/login', {'username': username, 'password': password}, cookie='')
        if st == 200:
            self.cookie = h['Set-Cookie'].split(';')[0]
            self.csrf = self.call('/api/next/home')[1]['session']['user']['csrf']
        return st, body, h

    def code(self, purpose_word):
        """The latest code mailed for this purpose (the outbox file's subject is 'Flow <purpose>验证码 123456')."""
        mails = sorted(self.outbox.glob('*.txt'))
        subject = [l for l in mails[-1].read_text(encoding='utf-8').splitlines() if l.startswith('Subject:')][0]
        self.assertIn(purpose_word, subject)
        return re.search(r'(\d{6})', subject).group(1)

    def session_expires(self):
        with app.db() as c:
            return c.execute('SELECT expires FROM sessions WHERE token=?', (self.cookie.split('=', 1)[1],)).fetchone()[0]

    # ---- sessions
    def test_a_session_lasts_30_days_and_slides_while_the_learner_keeps_coming_back(self):
        st, body, h = self.sign_in()
        self.assertEqual(st, 200); self.assertEqual(body['username'], 'learner')
        self.assertIn('Max-Age=%d' % (30 * DAY), h['Set-Cookie'])
        self.assertAlmostEqual(self.session_expires(), time.time() + 30 * DAY, delta=60)
        # a fresh session is not rewritten on every request
        self.assertNotIn('Set-Cookie', self.call('/api/next/home')[2])
        with app.db() as c:
            c.execute('UPDATE sessions SET expires=? WHERE token=?', (time.time() + 3 * DAY, self.cookie.split('=', 1)[1]))
        st, _, h = self.call('/api/next/home')
        self.assertEqual(st, 200); self.assertIn('Max-Age=%d' % (30 * DAY), h.get('Set-Cookie', ''))
        self.assertAlmostEqual(self.session_expires(), time.time() + 30 * DAY, delta=60)

    def test_signing_out_everywhere_ends_every_session_of_the_account(self):
        self.sign_in(); first, first_csrf = self.cookie, self.csrf
        self.sign_in(); second = self.cookie
        self.assertNotEqual(first, second)
        st, _, h = self.call('/api/logout', {'all': True})
        self.assertEqual(st, 200); self.assertIn('Max-Age=0', h['Set-Cookie'])
        self.csrf = first_csrf
        self.assertIsNone(self.call('/api/next/home', cookie=first)[1]['session']['user'])
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)

    def test_plain_sign_out_ends_only_this_device(self):
        self.sign_in(); first = self.cookie
        self.sign_in()
        self.call('/api/logout', {})
        self.assertEqual(self.call('/api/next/home', cookie=first)[1]['session']['user']['username'], 'learner')

    # ---- wrong passwords
    def test_five_wrong_passwords_lock_password_login_for_15_minutes(self):
        for k in range(4):
            st, body, _ = self.sign_in(password='wrong password %d' % k)
            self.assertEqual(st, 401)
        self.assertIn('再错 1 次', body['error'])
        st, body, _ = self.sign_in(password='wrong again')
        self.assertEqual(st, 401); self.assertIn('暂停 15 分钟', body['error'])
        st, body, _ = self.sign_in()  # even the right password waits
        self.assertEqual(st, 429); self.assertEqual(body['code'], 'locked'); self.assertIn('验证码登录', body['error'])
        with app.db() as c:
            c.execute('UPDATE login_failures SET until=?', (time.time() - 1,))
        self.assertEqual(self.sign_in()[0], 200)
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM login_failures').fetchone()[0], 0)

    def test_an_unknown_name_is_answered_and_locked_like_a_real_one(self):
        for _ in range(5):
            st, body, _ = self.sign_in(username='nobody-here', password='whatever123')
            self.assertEqual(st, 401); self.assertTrue(body['error'].startswith('用户名、邮箱或密码不正确'))
        self.assertEqual(self.sign_in(username='nobody-here', password='whatever123')[0], 429)
        self.assertEqual(self.sign_in()[0], 200)  # the real account is not affected

    def test_a_code_login_still_works_while_password_login_is_locked(self):
        for _ in range(5):
            self.sign_in(password='nope nope nope')
        self.assertEqual(self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'login'}, cookie='')[0], 200)
        st, _, _ = self.call('/api/login', {'method': 'code', 'email': 'learner@example.com', 'code': self.code('登录')}, cookie='')
        self.assertEqual(st, 200)

    # ---- forgotten password
    def test_a_forgotten_password_is_reset_with_a_code_which_signs_in_and_ends_other_sessions(self):
        self.sign_in(); old = self.cookie
        self.cookie = ''; self.csrf = ''
        self.assertEqual(self.call('/api/auth/code', {'email': 'unknown@example.com', 'purpose': 'reset'})[0], 404)
        self.assertEqual(self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'reset'})[0], 200)
        code = self.code('重设密码')
        st, body, _ = self.call('/api/auth/reset', {'email': 'learner@example.com', 'code': code, 'password': 'short'})
        self.assertEqual((st, body['field']), (400, 'password'))
        wrong = '000000' if code != '000000' else '111111'
        st, body, _ = self.call('/api/auth/reset', {'email': 'learner@example.com', 'code': wrong, 'password': 'a brand new password'})
        self.assertEqual((st, body['field']), (400, 'code'))
        st, body, h = self.call('/api/auth/reset', {'email': 'learner@example.com', 'code': code, 'password': 'a brand new password'})
        self.assertEqual(st, 200); self.assertIn('flow_session=', h['Set-Cookie'])
        self.assertIsNone(self.call('/api/next/home', cookie=old)[1]['session']['user'])  # the old device is signed out
        self.assertEqual(self.call('/api/auth/reset', {'email': 'learner@example.com', 'code': code, 'password': 'another new password'})[0], 400)  # single use
        self.assertEqual(self.sign_in()[0], 401)
        self.assertEqual(self.sign_in(password='a brand new password')[0], 200)

    def test_a_reset_clears_the_wrong_password_lock(self):
        for _ in range(5):
            self.sign_in(password='nope nope nope')
        self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'reset'}, cookie='')
        self.call('/api/auth/reset', {'email': 'learner@example.com', 'code': self.code('重设密码'), 'password': 'a brand new password'}, cookie='')
        self.assertEqual(self.sign_in(password='a brand new password')[0], 200)

    # ---- binding an email
    def test_an_email_is_bound_with_a_code_after_the_password(self):
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('nomail', app.password(PW)))
        self.sign_in('nomail')
        st, body, _ = self.call('/api/account/email/request', {'email': 'new@example.com', 'password': 'wrong', 'mode': 'code'})
        self.assertEqual((st, body.get('field')), (400, 'password'))
        st, _, _ = self.call('/api/account/email/request', {'email': 'learner@example.com', 'password': PW, 'mode': 'code'})
        self.assertEqual(st, 400)  # someone else's address
        st, body, _ = self.call('/api/account/email/request', {'email': 'New@Example.com', 'password': PW, 'mode': 'code'})
        self.assertEqual(st, 200); self.assertIn('ne***@example.com', body['message'])
        code = self.code('绑定邮箱')
        self.assertEqual(self.call('/api/account/email/confirm', {'email': 'new@example.com', 'code': '12345'})[0], 400)
        st, body, _ = self.call('/api/account/email/confirm', {'email': 'new@example.com', 'code': code})
        self.assertEqual(st, 200); self.assertEqual(body['email'], 'new@example.com')
        self.assertEqual(self.call('/api/account')[1]['email'], 'new@example.com')
        # and the new address now works for a code login
        self.assertEqual(self.call('/api/auth/code', {'email': 'new@example.com', 'purpose': 'login'}, cookie='')[0], 200)

    # ---- sign-up
    def test_usernames_may_be_two_chinese_characters_but_never_look_like_an_email(self):
        def register(name, email):
            self.call('/api/auth/code', {'email': email, 'purpose': 'register'}, cookie='')
            return self.call('/api/register', {'username': name, 'password': 'long enough pw', 'email': email, 'code': self.code('注册')}, cookie='')
        for bad in ('a@b.com', 'two words', 'x', '<b>bold</b>'):
            st, body, _ = self.call('/api/register', {'username': bad, 'password': 'long enough pw', 'email': 'z@example.com', 'code': '123456'}, cookie='')
            self.assertEqual((st, body.get('field')), (400, 'username'), bad)
        st, body, _ = register('小林', 'lin@example.com')
        self.assertEqual(st, 200); self.assertEqual(body['username'], '小林')

    def test_the_change_password_route_still_signs_out_everywhere(self):
        self.sign_in()
        st, _, h = self.call('/api/password', {'old_password': PW, 'new_password': 'a brand new password'})
        self.assertEqual(st, 200); self.assertIn('Max-Age=0', h['Set-Cookie'])
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0], 0)


    # ---- a forgotten password without an email: the operator's one-time link
    def test_an_operator_link_resets_an_account_without_email_once(self):
        import account_service as account
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('nomail', app.password(PW)))
            self.assertEqual(account.admin_link(c, 'nobody')[1], 404)
            first = account.admin_link(c, 'nomail')[0]['link']
            body, st = account.admin_link(c, 'nomail')  # a new link voids the old one
        self.assertEqual(st, 200); self.assertEqual(body['hours'], 24)
        token, old = body['link'].split('#reset=')[1], first.split('#reset=')[1]
        for _ in range(5):
            self.sign_in('nomail', 'wrong wrong wrong')
        self.assertEqual(self.call('/api/recovery/reset', {'token': old, 'password': 'a brand new password'}, cookie='')[0], 400)
        self.assertEqual(self.call('/api/recovery/reset', {'token': token, 'password': 'a brand new password'}, cookie='')[0], 200)
        self.assertEqual(self.call('/api/recovery/reset', {'token': token, 'password': 'another new password'}, cookie='')[0], 400)
        self.assertEqual(self.sign_in('nomail', 'a brand new password')[0], 200)  # and the wrong-password lock is gone

    def test_an_operator_link_expires_after_a_day(self):
        import account_service as account
        with app.db() as c:
            token = account.admin_link(c, 'learner')[0]['link'].split('#reset=')[1]
            c.execute("UPDATE recovery_tokens SET expires=? WHERE purpose='admin_reset'", (time.time() - 1,))
        self.assertEqual(self.call('/api/recovery/reset', {'token': token, 'password': 'a brand new password'}, cookie='')[0], 400)

    def test_the_operator_api_lists_accounts_with_masked_emails_and_makes_links_only_with_its_marker(self):
        import flow_admin
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('nomail', app.password(PW)))
        srv = ThreadingHTTPServer(('127.0.0.1', 0), flow_admin.AdminHandler); threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f'http://127.0.0.1:{srv.server_address[1]}/flow/api'
        try:
            with urllib.request.urlopen(base + '/users') as r:
                d = json.loads(r.read())
            self.assertEqual((d['total'], d['without_email']), (2, 1))
            row = {u['username']: u for u in d['users']}
            self.assertEqual(row['learner']['email'], 'le***@example.com'); self.assertFalse(row['nomail']['has_email'])
            with urllib.request.urlopen(base + '/users?q=nom') as r:
                self.assertEqual([u['username'] for u in json.loads(r.read())['users']], ['nomail'])
            req = lambda h: urllib.request.Request(base + '/users/reset-link', data=json.dumps({'user': 'nomail'}).encode(), headers={'Content-Type': 'application/json', **h})
            with self.assertRaises(urllib.error.HTTPError) as no:
                urllib.request.urlopen(req({}))
            self.assertEqual(no.exception.code, 403)  # a cross-site form cannot make a link
            with urllib.request.urlopen(req({'X-Requested-With': 'xmc'})) as r:
                self.assertIn('#reset=', json.loads(r.read())['link'])
        finally:
            srv.shutdown(); srv.server_close()

    def test_the_command_line_prints_a_link_for_an_operator_on_the_server(self):
        import subprocess, sqlite3
        data = Path(self.tmp.name) / 'cli'
        env = {**os.environ, 'FLOW_DATA_DIR': str(data)}
        flow = Path(__file__).resolve().parents[1]
        subprocess.run([sys.executable, '-c', 'import app; app.init()'], cwd=flow, env=env, check=True, capture_output=True)
        with sqlite3.connect(data / 'flow.sqlite3') as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('nomail', 'x'))
        out = subprocess.run([sys.executable, 'app.py', '--reset-link', 'nomail'], cwd=flow, env=env, capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 0, out.stderr); self.assertIn('#reset=', out.stdout); self.assertIn('24 小时', out.stdout)
        bad = subprocess.run([sys.executable, 'app.py', '--reset-link', 'nobody'], cwd=flow, env=env, capture_output=True, text=True, timeout=60)
        self.assertNotEqual(bad.returncode, 0); self.assertIn('没有找到', bad.stderr)

    # ---- notices
    def wait_mail(self, subject, timeout=3):
        end = time.time() + timeout
        while time.time() < end:
            for f in self.outbox.glob('*.txt'):
                text = f.read_text(encoding='utf-8')
                if 'Subject: ' + subject in text:
                    return text
            time.sleep(0.05)
        return None

    def test_a_password_change_sends_a_notice_to_the_bound_email(self):
        self.sign_in()
        self.call('/api/password', {'old_password': PW, 'new_password': 'a brand new password'})
        text = self.wait_mail('Flow 密码已修改')
        self.assertIsNotNone(text); self.assertIn('To: learner@example.com', text); self.assertIn('忘记密码', text)

    def test_the_reset_mail_tells_the_username_and_an_unknown_email_says_what_to_do(self):
        self.call('/api/auth/code', {'email': 'learner@example.com', 'purpose': 'reset'}, cookie='')
        mails = sorted(self.outbox.glob('*.txt'))
        self.assertIn('你的用户名是：learner', mails[-1].read_text(encoding='utf-8'))
        st, body, _ = self.call('/api/auth/code', {'email': 'unknown@example.com', 'purpose': 'reset'}, cookie='')
        self.assertEqual((st, body['field']), (404, 'email')); self.assertIn('管理员', body['error'])

    def test_the_session_says_whether_an_email_is_bound_and_whether_mail_is_on(self):
        self.sign_in()
        s = self.call('/api/next/home')[1]['session']
        self.assertTrue(s['mail']); self.assertTrue(s['user']['email_bound'])
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('nomail', app.password(PW)))
        self.sign_in('nomail')
        self.assertFalse(self.call('/api/next/home')[1]['session']['user']['email_bound'])

if __name__ == '__main__':
    unittest.main()
