"""A whole class signs up from one school network (the user's choices, 2026-11-25): a sign-up code asked for from a class
invite link counts against its class (CLASS_CODES_PER_HOUR), not the network's PER_IP_HOUR; one network makes at most
SIGNUPS_PER_IP_DAY accounts a day, class invites not counted; sign-in calls per address a minute are LOGIN_PER_MINUTE.
Mail goes to FLOW_MAIL_OUTBOX (files), never to a real address."""
import json, os, re, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app  # noqa: E402
import auth_service  # noqa: E402

PW = 'correct horse battery'
SCHOOL = '198.51.100.20'


class ClassSignupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = Path(self.tmp.name) / 'outbox'
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_MAIL_OUTBOX': str(self.outbox)}); self.env.start()
        os.environ.pop('FLOW_TRUST_CF', None); os.environ.pop('FLOW_REGISTER_CODES_PER_HOUR', None)
        app.SECURE = False
        app.RATE.clear()
        app.init()
        now = time.time()
        with app.db() as c:
            t = c.execute("INSERT INTO users(username,password,role,storage_ok) VALUES('teacher',?,'teacher',1)", (app.password(PW),)).lastrowid
            c.execute("INSERT INTO classes(name,code,teacher,created,updated) VALUES('初二（3）班','K3ABCD',?,?,?)", (t, now, now))
            c.execute("INSERT INTO classes(name,code,teacher,active,created,updated) VALUES('旧班','OLD123',?,0,?,?)", (t, now, now))
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def call(self, path, data, ip=SCHOOL):
        req = urllib.request.Request(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', data=json.dumps(data).encode(),
                                     headers={'Content-Type': 'application/json', 'X-Real-IP': ip})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def ask(self, email, ip=SCHOOL, **extra):
        return self.call('/api/auth/code', {'email': email, 'purpose': 'register', **extra}, ip)

    def mailed_code(self, email):
        for f in sorted(self.outbox.glob('*.txt'), reverse=True):
            text = f.read_text(encoding='utf-8')
            if email in text:
                return re.search(r'(\d{6})', [l for l in text.splitlines() if l.startswith('Subject:')][0]).group(1)
        self.fail('no code mailed to ' + email)

    def sign_up(self, k, ip=SCHOOL, **extra):
        email = f'student{k}@example.com'
        st, body = self.ask(email, ip, **extra)
        self.assertEqual(st, 200, body)
        return self.call('/api/register', {'username': f'student{k}', 'password': PW, 'email': email, 'code': self.mailed_code(email),
                                           'age': '14-17', 'storage': True, 'terms': True}, ip)

    def past_the_minute(self):
        with app.db() as c:
            c.execute('DELETE FROM mail_limits')

    # ---- sign-up codes from a class invite
    def test_codes_from_a_class_invite_do_not_use_up_the_school_networks_hour(self):
        with patch.object(auth_service, 'PER_IP_HOUR', 2):
            for k in range(2):
                self.assertEqual(self.ask(f'a{k}@example.com')[0], 200)
            st, body = self.ask('a9@example.com')
            self.assertEqual(st, 429, body); self.assertIn('一小时后', body['error'])
            # the same network, from the class's invite link: the class's own allowance (code in any case, spaces kept out)
            for k, code in enumerate(('K3ABCD', 'k3abcd', ' K3ABCD ')):
                st, body = self.ask(f'b{k}@example.com', **{'class': code})
                self.assertEqual(st, 200, body)
            # a stopped class or a made-up code is no invite
            for code in ('OLD123', 'NOPE99'):
                self.assertEqual(self.ask(f'c{code}@example.com', **{'class': code})[0], 429, code)
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM email_codes WHERE class_id IS NOT NULL').fetchone()[0], 3)

    def test_a_class_has_its_own_hourly_allowance(self):
        with patch.object(auth_service, 'CLASS_CODES_PER_HOUR', 2):
            for k in range(2):
                self.assertEqual(self.ask(f'd{k}@example.com', ip=f'198.51.100.{30 + k}', **{'class': 'K3ABCD'})[0], 200)
            st, body = self.ask('d9@example.com', ip='198.51.100.39', **{'class': 'K3ABCD'})
            self.assertEqual((st, body.get('code')), (429, 'busy')); self.assertIn('这个班', body['error'])
            # without the invite the network's own hour still has room
            self.assertEqual(self.ask('d9@example.com', ip='198.51.100.39')[0], 200)

    def test_the_per_email_limits_still_hold_from_an_invite(self):
        self.assertEqual(self.ask('e@example.com', **{'class': 'K3ABCD'})[0], 200)
        self.assertEqual(self.ask('e@example.com', **{'class': 'K3ABCD'})[0], 429)  # one code a minute

    def test_sign_in_codes_ignore_the_class(self):
        with app.db() as c:
            c.execute("INSERT INTO users(username,password,email,storage_ok) VALUES('old',?,'old@example.com',1)", (app.password(PW),))
        st, body = self.call('/api/auth/code', {'email': 'old@example.com', 'purpose': 'login', 'class': 'K3ABCD'})
        self.assertEqual(st, 200, body)
        with app.db() as c:
            self.assertIsNone(c.execute("SELECT class_id FROM email_codes WHERE email='old@example.com'").fetchone()[0])

    # ---- accounts a network makes a day
    def test_one_network_makes_a_limited_number_of_accounts_a_day(self):
        with patch.object(auth_service, 'SIGNUPS_PER_IP_DAY', 2):
            for k in range(2):
                st, body = self.sign_up(k); self.past_the_minute()
                self.assertEqual(st, 200, body)
            st, body = self.sign_up(2)
            self.assertEqual((st, body.get('code')), (429, 'busy')); self.assertIn('邀请链接', body['error'])
            # another network is not affected, and a day later this one has room again
            self.past_the_minute()
            self.assertEqual(self.sign_up(3, ip='198.51.100.77')[0], 200)
            with app.db() as c:
                c.execute('UPDATE signup_ips SET created=created-86401')
            self.past_the_minute()
            self.assertEqual(self.sign_up(4)[0], 200)
        with app.db() as c:
            # kept: the address and when, no account; older than a day is gone
            self.assertEqual([r[1] for r in c.execute('PRAGMA table_info(signup_ips)')], ['ip', 'created'])
            self.assertEqual(c.execute('SELECT COUNT(*) FROM signup_ips').fetchone()[0], 1)

    def test_sign_ups_from_a_class_invite_are_not_counted(self):
        with patch.object(auth_service, 'SIGNUPS_PER_IP_DAY', 1):
            self.assertEqual(self.sign_up(0)[0], 200); self.past_the_minute()
            self.assertEqual(self.sign_up(1)[0], 429); self.past_the_minute()
            # the code was asked for from the invite link: the sign-up is the class's
            for k in range(2, 5):
                st, body = self.sign_up(k, **{'class': 'K3ABCD'}); self.past_the_minute()
                self.assertEqual(st, 200, body)
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM signup_ips').fetchone()[0], 1)

    # ---- sign-in calls per address a minute
    def test_a_class_signing_in_together_is_not_cut_off_at_thirty(self):
        with app.db() as c:
            c.execute("INSERT INTO users(username,password,storage_ok) VALUES('pupil',?,1)", (app.password(PW),))
        for _ in range(40):
            self.assertEqual(self.call('/api/login', {'username': 'pupil', 'password': PW})[0], 200)
        with patch.object(app, 'LOGIN_PER_MINUTE', 3):
            app.RATE.clear()
            for _ in range(3):
                self.call('/api/login', {'username': 'pupil', 'password': PW})
            self.assertEqual(self.call('/api/login', {'username': 'pupil', 'password': PW})[0], 429)


if __name__ == '__main__':
    unittest.main()
