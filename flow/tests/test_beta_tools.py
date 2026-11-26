"""内测版的测试账号 (beta_tools.py, 2026-11-26): made in one click in each state that is slow to reach by hand, signed in
with the password shown once; 重置测试数据 deletes exactly those (never someone who really tests the 内测版), and only
when the page's count is the current one; 语流's console makes and deletes none."""
import json, os, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, beta_tools as bt, flow_admin, next_service as nx  # noqa: E402

BOSS = 'boss@example.com'


class TestAccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'CHANNEL', 'beta'),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_ADMIN_EMAILS': BOSS})]
        for p in self.patches:
            p.start()
        app.SECURE = False
        app.RATE.clear()
        app.init()
        self.site = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        self.admin = ThreadingHTTPServer(('127.0.0.1', 0), flow_admin.AdminHandler)
        for s in (self.site, self.admin):
            threading.Thread(target=s.serve_forever, daemon=True).start()

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

    def make(self, kind):
        st, body = self.console('/beta-test/create', {'kind': kind})
        self.assertEqual(st, 200, body)
        return body

    def test_each_kind_is_in_its_state_and_signs_in(self):
        got = {k: self.make(k) for k in bt.KINDS}
        with app.db() as c:
            u = {k: c.execute('SELECT * FROM users WHERE id=?', (v['id'],)).fetchone() for k, v in got.items()}
            prof = lambda k: nx.profile(c, got[k]['id'])
            self.assertEqual((u['adult']['age_band'], bool(u['adult']['storage_ok']), u['adult']['terms_version'] is not None), ('18+', True, True))
            self.assertEqual(u['teen']['age_band'], '14-17')
            self.assertEqual((u['child']['age_band'], u['child']['guardian_ok']), ('u14', None))
            self.assertEqual((u['teacher']['role'], prof('teacher')), ('teacher', None))
            self.assertEqual((u['paused']['storage_ok'], bool(u['paused']['storage_no'])), (None, True))
            self.assertIsNone(prof('new'))
            self.assertTrue(prof('adult'))
            week = got['week']['id']
            self.assertGreaterEqual(c.execute('SELECT COUNT(DISTINCT pack) FROM next_progress WHERE user_id=?', (week,)).fetchone()[0], 3)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM next_cards WHERE user_id=?', (week,)).fetchone()[0], 5)
        for k, v in got.items():
            self.assertTrue(v['username'].startswith('测试-'))
            self.assertEqual(self.call(self.site, '/api/login', {'username': v['username'], 'password': v['password']})[0], 200, k)
        listed = self.console('/beta-tests')[1]
        self.assertEqual(len(listed['items']), len(bt.KINDS))
        self.assertEqual([k['key'] for k in listed['kinds']], list(bt.KINDS))

    def test_reset_deletes_the_test_accounts_only_and_checks_the_count(self):
        with app.db() as c:
            real = c.execute("INSERT INTO users(username,password,storage_ok) VALUES('真人内测',?,1)", (app.password('correct horse 1'),)).lastrowid
            c.commit()
        a, b = self.make('adult'), self.make('week')
        st, body = self.console('/beta-test/reset', {'count': 5})
        self.assertEqual((st, body['count']), (409, 2))  # the page showed another number: nothing deleted
        st, body = self.console('/beta-test/reset', {'count': 2})
        self.assertEqual((st, body['deleted']), (200, 2))
        with app.db() as c:
            self.assertIsNone(c.execute('SELECT 1 FROM users WHERE id IN (?,?)', (a['id'], b['id'])).fetchone())
            self.assertIsNone(c.execute('SELECT 1 FROM next_progress WHERE user_id=?', (b['id'],)).fetchone())
            self.assertIsNotNone(c.execute('SELECT 1 FROM users WHERE id=?', (real,)).fetchone())
            self.assertEqual(c.execute('SELECT COUNT(*) FROM beta_test_accounts').fetchone()[0], 0)
        actions = [r['action'] for r in self.call(self.admin, '/flow-beta/api/log', None, {'Cf-Access-Authenticated-User-Email': BOSS})[1]['items']]
        self.assertIn('test-reset', actions); self.assertIn('test-account', actions)

    def test_the_prod_console_makes_and_deletes_none(self):
        with patch.object(app, 'CHANNEL', 'prod'):
            self.assertEqual(self.console('/beta-test/create', {'kind': 'adult'})[0], 409)
            self.assertEqual(self.console('/beta-test/reset', {'count': 0})[0], 409)
        self.assertEqual(self.console('/beta-test/create', {'kind': 'nope'})[0], 400)


if __name__ == '__main__':
    unittest.main()
