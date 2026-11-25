"""The console's sign-in token (access_check.py): with FLOW_ACCESS_AUD and FLOW_ACCESS_TEAM set, the console takes
the operator from Cloudflare Access's signed token and refuses a request whose token is missing, forged, for another
application, from another team or out of date; without them it reads the header as before. The keys here are made
for the test (small, never used anywhere else)."""
import base64, hashlib, json, os, random, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import access_check as at, app, flow_admin  # noqa: E402

TEAM, AUD = 'flowtest.cloudflareaccess.com', 'aud-1234'


def _prime(bits, rnd):
    while True:
        n = rnd.getrandbits(bits) | (1 << bits - 1) | 1
        if all(n % p for p in (3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37)) and all(pow(a, n - 1, n) == 1 for a in (2, 3, 5, 7, 11, 13)):
            return n


def make_key(seed):
    rnd, e = random.Random(seed), 65537
    while True:
        p, q = _prime(512, rnd), _prime(512, rnd)
        phi = (p - 1) * (q - 1)
        if p != q and phi % e:
            return p * q, e, pow(e, -1, phi)


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b'=').decode()


def sign(key, kid, claims, alg='RS256'):
    n, e, d = key
    head = b64(json.dumps({'alg': alg, 'kid': kid}).encode()) + '.' + b64(json.dumps(claims).encode())
    k = (n.bit_length() + 7) // 8
    t = at.SHA256_INFO + hashlib.sha256(head.encode()).digest()
    em = b'\x00\x01' + b'\xff' * (k - len(t) - 3) + b'\x00' + t
    return head + '.' + b64(pow(int.from_bytes(em, 'big'), d, n).to_bytes(k, 'big'))


KEY, OTHER = make_key(1), make_key(2)


def claims(**more):
    now = time.time()
    return {'aud': [AUD], 'iss': f'https://{TEAM}', 'email': 'Boss@Example.com', 'exp': now + 600, 'nbf': now - 10, **more}


class VerifyTests(unittest.TestCase):
    def setUp(self):
        at._cache.update(keys={}, at=0.0, tried=0.0)
        self.fetched = []
        self.fetch = lambda team: (self.fetched.append(team), {'k1': KEY[:2]})[1]

    def check(self, token):
        return at.verify(token, AUD, TEAM, fetch=self.fetch)

    def test_a_valid_token_gives_its_email(self):
        self.assertEqual(self.check(sign(KEY, 'k1', claims())), 'boss@example.com')
        self.assertEqual(self.fetched, [TEAM])
        self.check(sign(KEY, 'k1', claims()))
        self.assertEqual(len(self.fetched), 1)  # the keys are kept

    def test_anything_else_gives_nothing(self):
        now = time.time()
        bad = {
            'forged (another key)': sign(OTHER, 'k1', claims()),
            'unknown key id': sign(KEY, 'k9', claims()),
            'another application': sign(KEY, 'k1', claims(aud=['aud-other'])),
            'another team': sign(KEY, 'k1', claims(iss='https://evil.cloudflareaccess.com')),
            'expired': sign(KEY, 'k1', claims(exp=now - 3600)),
            'not yet valid': sign(KEY, 'k1', claims(nbf=now + 3600)),
            'no email': sign(KEY, 'k1', claims(email='')),
            'alg none': sign(KEY, 'k1', claims(), alg='none'),
            'missing': None, 'garbage': 'a.b.c',
        }
        for what, token in bad.items():
            with self.subTest(what):
                self.assertIsNone(self.check(token))
        tampered = sign(KEY, 'k1', claims()).split('.')
        tampered[1] = b64(json.dumps(claims(email='intruder@example.com')).encode())
        self.assertIsNone(self.check('.'.join(tampered)))

    def test_an_unknown_key_is_fetched_again_but_not_on_every_request(self):
        self.check(sign(KEY, 'k1', claims()))
        for _ in range(3):
            self.check(sign(KEY, 'k9', claims()))
        self.assertLessEqual(len(self.fetched), 2)


class ConsoleTests(unittest.TestCase):
    def setUp(self):
        at._cache.update(keys={}, at=0.0, tried=0.0)
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'flow.sqlite3'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_ADMIN_EMAILS': 'boss@example.com'}),
                        patch.object(at, 'fetch_keys', lambda team: {'k1': KEY[:2]})]
        for p in self.patches:
            p.start()
        app.init()
        self.admin = ThreadingHTTPServer(('127.0.0.1', 0), flow_admin.AdminHandler)
        threading.Thread(target=self.admin.serve_forever, daemon=True).start()

    def tearDown(self):
        self.admin.shutdown(); self.admin.server_close()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def me(self, headers):
        req = urllib.request.Request(f'http://127.0.0.1:{self.admin.server_address[1]}/flow/api/me', headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def test_without_the_settings_the_header_is_read_as_before(self):
        st, body = self.me({'Cf-Access-Authenticated-User-Email': 'boss@example.com'})
        self.assertEqual((st, body.get('role')), (200, 'admin'))

    def test_with_the_settings_only_a_signed_token_counts(self):
        with patch.dict(os.environ, {'FLOW_ACCESS_AUD': AUD, 'FLOW_ACCESS_TEAM': TEAM}):
            st, _ = self.me({'Cf-Access-Authenticated-User-Email': 'boss@example.com'})  # the header alone
            self.assertEqual(st, 403)
            st, body = self.me({'Cf-Access-Jwt-Assertion': sign(KEY, 'k1', claims()), 'Cf-Access-Authenticated-User-Email': 'other@example.com'})
            self.assertEqual((st, body.get('role'), body.get('email')), (200, 'admin', 'boss@example.com'))  # the token's email wins
            st, _ = self.me({'Cf-Access-Jwt-Assertion': sign(OTHER, 'k1', claims())})
            self.assertEqual(st, 403)


if __name__ == '__main__':
    unittest.main()
