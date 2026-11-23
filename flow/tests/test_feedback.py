"""问题反馈: learners (signed in or not) send what happened, the page and up to three screenshots; administrators read
them in the xmc.hk console and mark them handled. Nothing in a guest's report points back to them."""
import base64, json, os, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, feedback_service as fb, flow_admin  # noqa: E402

JPEG = b'\xff\xd8\xff\xe0' + b'\x00\x10JFIF' + b'0' * 200
PNG = b'\x89PNG\r\n\x1a\n' + b'0' * 120
url = lambda blob, kind='jpeg': f'data:image/{kind};base64,' + base64.b64encode(blob).decode()


class Servers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        self.patches = [patch.object(app, 'DB', self.data / 'a.db'), patch.object(app, 'DATA', self.data),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_ADMIN_EMAILS': 'boss@example.com', 'FLOW_SURVEY_SALT': 'test-salt',
                                                'FLOW_DATA_DIR': str(self.data)})]
        for p in self.patches:
            p.start()
        app.SECURE = False
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

    def call(self, srv, path, data=None, headers=None, raw=False, body=None):
        h = {'Content-Type': 'application/json', **(headers or {})}
        payload = body if body is not None else (json.dumps(data).encode() if data is not None else None)
        req = urllib.request.Request(f'http://127.0.0.1:{srv.server_address[1]}{path}', data=payload, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                b = r.read()
                return r.status, (b if raw else json.loads(b or b'{}')), dict(r.headers)
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, (b if raw else json.loads(b or b'{}')), dict(e.headers)

    def report(self, headers=None, **kw):
        body = {'kind': 'display', 'text': '单词页往下滑，底部按钮跑到中间了', 'page': '#/cards',
                'device': {'ua': 'Mozilla/5.0 (iPhone)', 'w': 390, 'h': 844, 'dpr': 3, 'theme': 'dark', 'standalone': True, 'errors': ['TypeError: x @ next.js:1']}, **kw}
        return self.call(self.site, '/api/feedback', body, headers)

    def console(self, path, email='boss@example.com', data=None, raw=False):
        h = {'Cf-Access-Authenticated-User-Email': email}
        if data is not None:
            h['X-Requested-With'] = 'xmc'
        return self.call(self.admin, '/flow/api' + path, data, h, raw=raw)

    def rows(self):
        with app.db() as c:
            return [dict(r) for r in c.execute('SELECT * FROM feedback ORDER BY id')]


class SendingTests(Servers):
    def test_a_guest_reports_with_screenshots_and_nothing_points_back(self):
        st, body, _ = self.report(images=[url(JPEG), url(PNG, 'png')], contact='teacher@example.com')
        self.assertEqual((st, body['ok'], body['images']), (200, True, 2))
        r = self.rows()[0]
        self.assertIsNone(r['user_id'])
        self.assertEqual((r['kind'], r['page'], r['contact'], json.loads(r['images'])), ('display', '#/cards', 'teacher@example.com', ['1.jpg', '2.png']))
        self.assertEqual(json.loads(r['device'])['w'], 390)
        self.assertTrue(json.loads(r['device'])['standalone'])
        self.assertEqual((self.data / 'feedback' / str(r['id']) / '1.jpg').read_bytes(), JPEG)
        self.assertEqual((self.data / 'feedback' / str(r['id']) / '2.png').read_bytes(), PNG)
        # the report has no address; the limit keeps only a salted, day-scoped hash, in its own table
        self.assertNotIn('127.0.0.1', json.dumps(r))
        with app.db() as c:
            keys = [k for (k,) in c.execute('SELECT key FROM feedback_limits')]
        self.assertEqual(len(keys), 1); self.assertNotIn('127.0.0.1', keys[0])

    def test_a_signed_in_report_names_the_account_only_with_the_session_token(self):
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('lin', app.password('a long password here')))
        st, body, h = self.call(self.site, '/api/login', {'username': 'lin', 'password': 'a long password here'})
        cookie = h['Set-Cookie'].split(';')[0]
        csrf = self.call(self.site, '/api/session', headers={'Cookie': cookie})[1]['user']['csrf']
        self.assertEqual(self.report(headers={'Cookie': cookie, 'X-CSRF-Token': csrf})[0], 200)
        self.assertEqual(self.report(headers={'Cookie': cookie})[0], 200)  # no token: kept, but as a guest's
        users = [r['user_id'] for r in self.rows()]
        self.assertIsNotNone(users[0]); self.assertIsNone(users[1])

    def test_what_is_refused(self):
        self.assertEqual(self.report(text='坏了')[0], 400)
        self.assertEqual(self.report(text='字' * 1001)[0], 400)
        self.assertEqual(self.report(images=[url(JPEG)] * 4)[0], 400)
        self.assertEqual(self.report(images=['data:image/gif;base64,R0lGODlh'])[0], 400)
        self.assertEqual(self.report(images=[url(b'not an image at all')])[0], 400)
        self.assertEqual(self.report(images=[url(JPEG + b'0' * 700_001)])[0], 400)
        self.assertEqual(self.report(page='https://elsewhere.example/')[0], 200)  # kept, without a page that is not ours
        self.assertEqual(self.rows()[-1]['page'], '')
        # more than nginx lets through (3 MB) is refused from the length alone, before anything is read
        import http.client
        conn = http.client.HTTPConnection('127.0.0.1', self.site.server_address[1], timeout=10)
        conn.putrequest('POST', '/api/feedback'); conn.putheader('Content-Type', 'application/json'); conn.putheader('Content-Length', '2900001'); conn.endheaders()
        self.assertEqual(conn.getresponse().status, 400); conn.close()
        n = len(self.rows())
        self.assertEqual(self.report(website='http://spam.example')[0], 200)  # the hidden field: a bot; nothing kept
        self.assertEqual(len(self.rows()), n)

    def test_limits_per_guest_per_account_and_per_day(self):
        for _ in range(fb.GUEST_DAILY):
            self.assertEqual(self.report()[0], 200)
        st, body, _ = self.report()
        self.assertEqual(st, 429); self.assertIn('登录', body['error'])
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('lin', 'x'))
            uid = c.execute("SELECT id FROM users WHERE username='lin'").fetchone()[0]
            c.commit()
            for _ in range(fb.USER_DAILY):
                self.assertEqual(fb.submit(c, {'text': '还是有问题的那一页'}, '10.0.0.9', uid)[1], 200)
            self.assertEqual(fb.submit(c, {'text': '还是有问题的那一页'}, '10.0.0.9', uid)[1], 429)
        with patch.object(fb, 'DAILY_TOTAL', len(self.rows())), app.db() as c:
            self.assertEqual(fb.submit(c, {'text': '今天的第一条'}, '10.0.0.10')[1], 429)

    def test_the_release_running_is_kept_with_the_report(self):
        (self.data / 'deploy-status.json').write_text(json.dumps({'tag': 'r21', 'result': 'DEPLOYED'}))
        self.report()
        self.assertEqual(self.rows()[0]['release'], 'r21')


class ConsoleTests(Servers):
    def test_administrators_read_look_at_screenshots_and_close_reports(self):
        rid = self.report(images=[url(JPEG)])[1]['id']
        st, d, _ = self.console('/feedback')
        self.assertEqual((st, d['counts']), (200, {'new': 1, 'done': 0}))
        x = d['items'][0]
        self.assertEqual((x['id'], x['who'], x['kind_label'], x['status_label'], x['images']), (rid, '游客', '页面显示不对', '待处理', ['1.jpg']))
        self.assertEqual(x['device']['errors'], ['TypeError: x @ next.js:1'])
        st, blob, h = self.console(f'/feedback/image?id={rid}&n=1.jpg', raw=True)
        self.assertEqual((st, blob, h['Content-Type']), (200, JPEG, 'image/jpeg'))
        for bad in (f'?id={rid}&n=2.jpg', f'?id={rid}&n=../a.db', '?id=x&n=1.jpg', f'?id={rid}&n=1.gif'):
            self.assertEqual(self.console('/feedback/image' + bad, raw=True)[0], 404, bad)
        self.assertEqual(self.console('/overview')[1]['feedback_open'], 1)
        st, body, _ = self.console('/feedback/status', data={'id': rid, 'status': 'done'})
        self.assertEqual(st, 200)
        d = self.console('/feedback?status=done')[1]
        self.assertEqual((d['counts'], d['items'][0]['handled_by']), ({'new': 0, 'done': 1}, 'boss@example.com'))
        log = self.console('/log')[1]['items'][0]
        self.assertEqual((log['action'], log['target']), ('feedback-done', f'#{rid}'))
        self.assertEqual(self.console('/feedback/status', data={'id': rid, 'status': 'new'})[0], 200)
        self.assertEqual(self.console('/feedback/status', data={'id': 999, 'status': 'done'})[0], 404)

    def test_viewers_see_no_reports_or_screenshots(self):
        rid = self.report(images=[url(JPEG)])[1]['id']
        self.assertEqual(self.console('/feedback', email='intern@example.com')[0], 403)
        self.assertEqual(self.console(f'/feedback/image?id={rid}&n=1.jpg', email='intern@example.com', raw=True)[0], 403)
        self.assertEqual(self.console('/feedback/status', email='intern@example.com', data={'id': rid, 'status': 'done'})[0], 403)


class PageTests(unittest.TestCase):
    def test_the_learning_site_offers_it_and_the_console_has_its_tab(self):
        js = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8')
        for s in ('async function feedbackView', "name === 'feedback'", "'#/feedback', '问题反馈'", 'href="#/feedback">反馈这个问题', 'shrinkShot'):
            self.assertIn(s, js)
        self.assertTrue(app.api_open('POST', '/api/feedback'))
        root = Path(app.ROOT).parent / 'xmc-admin'
        self.assertIn('data-tab="feedback" data-admin', (root / 'index.html').read_text(encoding='utf-8'))
        self.assertIn('function feedbackView', (root / 'admin.js').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
