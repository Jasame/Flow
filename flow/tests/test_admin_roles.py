"""r20: the classic site is archived (the learner site serves only the learning site, the survey, sign-in and the
account), operator functions live only in the xmc.hk console, the console has two roles (管理员, 只看数据) by the
email Cloudflare Access signed in, what a 管理员 changes is logged, and the console compares the weeks before and after
a release (with anonymous tap counts from a few entry points)."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, flow_admin, next_service as nx  # noqa: E402

DAY = 86400


class Servers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_ADMIN_EMAILS': ''})]
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

    def call(self, srv, path, data=None, headers=None, raw=False):
        h = {'Content-Type': 'application/json', **(headers or {})}
        req = urllib.request.Request(f'http://127.0.0.1:{srv.server_address[1]}{path}', data=json.dumps(data).encode() if data is not None else None, headers=h)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        try:
            with urllib.request.build_opener(NoRedirect).open(req, timeout=10) as r:
                body = r.read()
                return r.status, (body if raw else json.loads(body or b'{}')), dict(r.headers)
        except urllib.error.HTTPError as e:
            body = e.read()
            return e.code, (body if raw else json.loads(body or b'{}')), dict(e.headers)

    def console(self, path, email='', data=None):
        h = {'Cf-Access-Authenticated-User-Email': email} if email else {}
        if data is not None:
            h['X-Requested-With'] = 'xmc'
        return self.call(self.admin, '/flow/api' + path, data, h, raw=path.endswith('.csv'))


class ClassicArchivedTests(Servers):
    def test_old_addresses_open_the_learning_site(self):
        for path in ('/', '/?classic=1', '/?account=1'):
            st, body, h = self.call(self.site, path, raw=True)
            self.assertEqual(st, 200, path); self.assertIn(b'/next.js?v=', body)
        for path in ('/classic', '/practice/first-meeting/'):
            st, _, h = self.call(self.site, path, raw=True)
            self.assertEqual((st, h.get('Location')), (302, '/'), path)
        for path in ('/app.js', '/style.css', '/tutor.js', '/index.html', '/atlas.js'):
            self.assertEqual(self.call(self.site, path, raw=True)[0], 404, path)
        for path in ('/next.js', '/next.css', '/survey', '/sw.js', '/literata.woff2'):
            self.assertEqual(self.call(self.site, path, raw=True)[0], 200, path)

    def test_the_introduction_page_and_its_files(self):
        """认识语流 (/about): its own page, script and styles under a content version, real screenshots, the CSP."""
        import re
        v = app.asset_version(app.ABOUT_ASSETS)
        st, body, h = self.call(self.site, '/about', raw=True)
        self.assertEqual(st, 200); self.assertTrue(h['Content-Type'].startswith('text/html'))
        self.assertIn(f'/about.js?v={v}'.encode(), body); self.assertIn(f'/about.css?v={v}'.encode(), body)
        self.assertIn(b'data-channel="prod"', body); self.assertIn("script-src 'self'", h['Content-Security-Policy'])
        self.assertNotIn(b'<script>', body); self.assertNotIn(b' style="', body)  # nothing inline: the CSP would refuse it
        for name in app.ABOUT_ASSETS:
            st, _, h = self.call(self.site, f'/{name}?v={v}', raw=True)
            self.assertEqual((st, h['Cache-Control']), (200, 'public, max-age=31536000, immutable'), name)
            self.assertEqual(self.call(self.site, f'/{name}?v=old', raw=True)[2]['Cache-Control'], 'no-cache', name)
        pictures = set(re.findall(rb'/about/([\w-]+\.jpg)', body))
        self.assertGreaterEqual(len(pictures), 10)
        for name in pictures:
            st, img, h = self.call(self.site, '/about/' + name.decode(), raw=True)
            self.assertEqual((st, h['Content-Type'], img[:2]), (200, 'image/jpeg', b'\xff\xd8'), name)
        for path in ('/about/nothing.jpg', '/about/..%2fapp.py', '/about/today.png', '/about.html'):
            self.assertEqual(self.call(self.site, path, raw=True)[0], 404, path)
        st, _, h = self.call(self.site, '/about/', raw=True)
        self.assertEqual((st, h.get('Location')), (301, '/about'))
        with patch.object(app, 'CHANNEL', 'beta'):  # the 内测版 says so on this page too and stays out of search results
            st, body, h = self.call(self.site, '/about', raw=True)
            self.assertIn(b'data-channel="beta"', body); self.assertEqual(h.get('X-Robots-Tag'), 'noindex, nofollow')

    def test_the_introduction_page_says_what_the_data_says(self):
        """认识语流 shows the word books with their sizes and a tap-a-word demo with dictionary entries, copied into
        about.js. When a word book or the dictionary changes, this says which figure on the page to update."""
        import re
        import vocab_service
        src = (Path(app.ROOT) / 'public' / 'about.js').read_text(encoding='utf-8')
        shown = {title: int(n) for title, n in re.findall(r"\['([^']+)', (\d+), '", src)}
        real = {b['title']: b['count'] for b in vocab_service.registry()}
        self.assertEqual(shown, real, 'update SHELF in flow/public/about.js')
        words = json.loads(re.search(r'const DICT = (\{.*?\});\n', src).group(1))
        self.assertGreaterEqual(len(words), 15)
        for k, e in words.items():
            hit = nx.lookup(k)
            self.assertEqual((e['w'], e['p'], e['m'], e['t']), (hit['word'], hit.get('phonetic', ''), hit['meaning'], hit.get('tags', [])),
                             f'update DICT["{k}"] in flow/public/about.js')

    def test_no_file_of_the_server_is_exposed_and_the_page_keeps_its_csp(self):
        # (kept from the archived classic tests, test_flow.py)
        for path in ('/../data/flow.sqlite3', '/data/flow.sqlite3', '/.env', '/app.py', '/flow_admin.py'):
            self.assertEqual(self.call(self.site, path, raw=True)[0], 404, path)
        st, _, h = self.call(self.site, '/', raw=True)
        self.assertIn("script-src 'self'", h['Content-Security-Policy'])

    def test_only_the_learning_site_apis_answer(self):
        for path in ('/api/health', '/api/session', '/api/next/home', '/api/survey', '/api/deploy-status'):
            self.assertEqual(self.call(self.site, path)[0], 200, path)
        for path in ('/api/admin', '/api/manage/backup', '/api/lab', '/api/meeting/previews', '/api/dashboard', '/api/graph', '/api/daily'):
            self.assertEqual(self.call(self.site, path)[:2], (404, {'error': '接口不存在'}), path)
        for path in ('/api/daily/run', '/api/admin/question', '/api/chat', '/api/lab/pack', '/api/quiz'):
            self.assertEqual(self.call(self.site, path, {})[0], 404, path)
        self.assertNotEqual(self.call(self.site, '/api/login', {'username': 'x', 'password': 'y'})[0], 404)  # still there

    def test_the_admin_flag_opens_nothing_on_the_learner_site(self):
        with app.db() as c:
            c.execute('INSERT INTO users(username,password,admin) VALUES(?,?,1)', ('boss', app.password('a long password here')))
        st, body, h = self.call(self.site, '/api/login', {'username': 'boss', 'password': 'a long password here'})
        cookie = h['Set-Cookie'].split(';')[0]
        for path in ('/api/admin', '/api/manage/backup'):
            self.assertEqual(self.call(self.site, path, headers={'Cookie': cookie})[0], 404)


class ConsoleRoleTests(Servers):
    def test_without_a_list_of_admins_everyone_through_access_is_admin(self):
        st, me, _ = self.console('/me', 'anyone@example.com')
        self.assertEqual((st, me['role'], me['roles_set']), (200, 'admin', False))
        self.assertEqual(self.console('/users', 'anyone@example.com')[0], 200)

    def test_a_viewer_sees_the_numbers_but_not_people_and_changes_nothing(self):
        with patch.dict(os.environ, {'FLOW_ADMIN_EMAILS': 'Boss@Example.com, ops@example.com'}):
            st, me, _ = self.console('/me', 'teacher@example.com')
            self.assertEqual((me['role'], me['label']), ('viewer', '只看数据'))
            for path in ('/overview', '/learning', '/survey/summary', '/survey/definition', '/releases'):
                self.assertEqual(self.console(path, 'teacher@example.com')[0], 200, path)
            for path in ('/users', '/survey/responses', '/survey/export.csv', '/errors', '/log'):
                self.assertEqual(self.console(path, 'teacher@example.com')[0], 403, path)
            for path, data in (('/users/reset-link', {'user': 'x'}), ('/survey/hide', {'id': 1}), ('/daily/run', {})):
                self.assertEqual(self.console(path, 'teacher@example.com', data)[0], 403, path)
            self.assertEqual(self.console('/users', '')[0], 403)  # no email from Access: the smaller role
            self.assertEqual(self.console('/me', 'boss@example.com')[1]['role'], 'admin')  # emails compare case-blind
            self.assertEqual(self.console('/users', 'boss@example.com')[0], 200)

    def test_what_an_admin_changes_is_logged_without_the_secret(self):
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('nomail', app.password('a long password here')))
        with patch.dict(os.environ, {'FLOW_ADMIN_EMAILS': 'boss@example.com'}):
            st, body, _ = self.console('/users/reset-link', 'boss@example.com', {'user': 'nomail'})
            self.assertEqual(st, 200); token = body['link'].split('#reset=')[1]
            self.assertEqual(self.console('/users/reset-link', 'boss@example.com', {'user': 'nobody-here'})[0], 404)
            with patch('daily_service.run', lambda c: None):
                self.assertEqual(self.console('/daily/run', 'boss@example.com', {})[0], 202)
            st, csv, h = self.console('/survey/export.csv', 'boss@example.com')
            self.assertEqual(st, 200)
            st, log, _ = self.console('/log', 'boss@example.com')
        rows = log['items']
        self.assertEqual([r['action'] for r in rows], ['survey-export', 'daily-run', 'reset-link', 'reset-link'])
        self.assertEqual({r['email'] for r in rows}, {'boss@example.com'})
        self.assertEqual((rows[3]['target'], rows[3]['detail']), ('nomail', '已生成'))
        self.assertEqual(rows[2]['target'], 'nobody-here'); self.assertNotEqual(rows[2]['detail'], '已生成')
        self.assertNotIn(token, json.dumps(rows))
        self.assertEqual(rows[1]['action_label'], '生成今日热点')

    def test_the_overview_shows_the_last_backup_and_todays_news_material(self):
        (Path(self.tmp.name) / 'backup-status.json').write_text(json.dumps({'ok': True, 'at': '2026-11-23T03:00:00+08:00'}))
        st, ov, _ = self.console('/overview', 'anyone@example.com')
        self.assertEqual(ov['backup'], {'ok': True, 'at': '2026-11-23T03:00:00+08:00'})
        self.assertIn(ov['daily']['status'], ('waiting', 'complete', 'running', 'failed', 'interrupted'))


class ReleaseCompareTests(Servers):
    def test_a_release_is_noted_once_when_it_is_live(self):
        with app.db() as c:
            flow_admin.note_release(c, {'tag': 'r20', 'state': 'running', 'started': '2026-11-24T10:00:00+08:00'})
            flow_admin.note_release(c, {'tag': 'r20', 'result': 'DEPLOYED', 'commit': 'a' * 40, 'finished': '2026-11-24T10:05:00+08:00'})
            flow_admin.note_release(c, {'tag': 'r20', 'result': 'DEPLOYED', 'commit': 'a' * 40, 'finished': '2026-11-25T10:05:00+08:00'})
            flow_admin.note_release(c, {'tag': 'r21', 'result': 'ROLLED_BACK', 'finished': '2026-11-26T10:05:00+08:00'})
            items = flow_admin.releases(c)['items']
        self.assertEqual([(r['tag'], r['commit_sha'][:3]) for r in items], [('r20', 'aaa')])
        self.assertEqual(items[0]['at'], __import__('datetime').datetime.fromisoformat('2026-11-24T10:05:00+08:00').timestamp())  # when it went live
        (Path(self.tmp.name) / 'deploy-status.json').write_text(json.dumps({'tag': 'r21', 'result': 'DEPLOYED', 'finished': '2026-11-27T09:00:00+08:00'}))
        self.call(self.site, '/api/deploy-status')  # the deploy monitor asks this after every release
        with app.db() as c:
            self.assertEqual([r['tag'] for r in flow_admin.releases(c)['items']], ['r21', 'r20'])

    def test_the_weeks_before_and_after_a_release_as_daily_averages(self):
        at = time.time() - 4 * DAY
        day = lambda t: __import__('datetime').datetime.fromtimestamp(t, nx.TZ).date().isoformat()
        with app.db() as c:
            for uid in (1, 2, 3):
                c.execute('INSERT INTO users(id,username,password) VALUES(?,?,?)', (uid, f'u{uid}', 'x'))
            for k, uid in enumerate((1, 2)):  # before: two learners, one day each; one profile
                c.execute('INSERT INTO next_progress(user_id,pack,step,created) VALUES(?,?,?,?)', (uid, 'p', 'read', at - (k + 2) * DAY))
            c.execute('INSERT INTO next_profiles(user_id,level,goal,themes,minutes,created) VALUES(1,"B1","work","[]",15,?)', (at - 3 * DAY,))
            for d in range(4):  # after: one learner every day, an output step and two reviews a day
                c.execute('INSERT INTO next_progress(user_id,pack,step,created) VALUES(3,?,?,?)', (f'p{d}', 'output', at + d * DAY + 60))
                for r in range(2):
                    c.execute("INSERT INTO next_reviews(user_id,card,rating,created) VALUES(3,1,'good',?)", (at + d * DAY + 120 + r,))
            c.execute('INSERT INTO next_profiles(user_id,level,goal,themes,minutes,created) VALUES(3,"B1","work","[]",15,?)', (at + 30,))
            for key, t, n in (('home-more', at - 2 * DAY, 3), ('home-more', at + DAY, 9), ('practice-map', at + DAY, 5), ('words-plan', at, 4)):
                c.execute('INSERT INTO ui_taps(day,key,n) VALUES(?,?,?)', (day(t), key, n))
        st, cmp, _ = self.console(f'/compare?at={at}&days=7', 'anyone@example.com')
        self.assertEqual(st, 200)
        m = {x['key']: x for x in cmp['metrics']}
        self.assertEqual((m['active']['before'], m['active']['after']), (round(2 / 7, 1), 1.0))
        self.assertEqual((m['reviews']['before'], m['reviews']['after']), (0.0, 2.0))
        self.assertEqual((m['step-output']['before'], m['step-output']['after']), (0.0, 1.0))
        self.assertEqual(m['back7']['after'], 100)  # the learner who started after the release came back the next days
        self.assertEqual(cmp['after_days'], 4.0)
        taps = {t['key']: t for t in cmp['taps']}
        self.assertEqual((taps['home-more']['before'], taps['home-more']['after'], taps['practice-map']['after']), (3, 9, 5))
        self.assertEqual(taps['home-more']['label'], '今日 · 更多材料')
        self.assertEqual((taps['words-plan']['before'], taps['words-plan']['after']), (0, 0))  # the release day is on neither side


class TapTests(Servers):
    def test_a_tap_is_counted_per_day_and_key_only(self):
        for _ in range(3):
            self.assertEqual(self.call(self.site, '/api/next/tap', {'k': 'practice-map'})[0], 200)
        self.assertEqual(self.call(self.site, '/api/next/tap', {'k': 'anything-else'})[0], 400)
        with app.db() as c:
            rows = [tuple(r) for r in c.execute('SELECT key, n FROM ui_taps')]
            cols = [r[1] for r in c.execute('PRAGMA table_info(ui_taps)')]
        self.assertEqual(rows, [('practice-map', 3)])
        self.assertEqual(cols, ['day', 'key', 'n'])  # nothing about who

    def test_every_counted_entry_point_is_on_the_page_and_known_to_the_console(self):
        js = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8') + (Path(app.ROOT) / 'public' / 'about.html').read_text(encoding='utf-8')  # 认识语流 counts its buttons too
        import re
        used = set(re.findall(r'data-tap="([a-z-]+)"', js)) | set(re.findall(r"'([a-z]+-[a-z-]+)'", js)) & set(flow_admin.TAP_LABEL)
        self.assertEqual(set(flow_admin.TAP_LABEL) - used, set())


if __name__ == '__main__':
    unittest.main()
