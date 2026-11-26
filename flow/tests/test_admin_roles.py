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
        # the one-minute film talks about the server voice and quick typed replies only where the server has them on
        with patch.object(app, '_FILM', {'at': 0.0, 'v': ''}), patch.dict(os.environ, {'FLOW_TTS_MODEL': '', 'FLOW_TEXT_AI_MODEL': 'flow-text'}):
            body = self.call(self.site, '/about', raw=True)[1]
            self.assertIn(b'data-film=""', body); self.assertNotIn(b'__FILM__', body)
        with patch.object(app, '_FILM', {'at': 0.0, 'v': ''}), patch('tts_service.enabled', return_value=True), \
                patch('ai_routes.route', return_value='flow-text-deepseek'), patch.dict(os.environ, {'FLOW_TEXT_AI_MODEL': 'flow-text'}):
            self.assertIn(b'data-film="voice fast"', self.call(self.site, '/about', raw=True)[1])

    def test_the_installers_come_from_their_own_folder_and_the_page_waits_for_them(self):
        """下载安装 (/about#download): /download/ serves plain files of a few types from DOWNLOADS (outside the release),
        installers as attachments and the list afresh; with no list it answers an empty one (no failed request on the page)
        and the page keeps 即将开放 on its buttons (Linux: one per package, named)."""
        import hashlib, re
        body = self.call(self.site, '/about', raw=True)[1].decode()
        sec = body[body.index('id="download"'):body.index('<!-- ============ who')]
        self.assertEqual(re.findall(r'data-app="([\w-]+)"', sec), ['web', 'android', 'windows', 'mac', 'linux', 'harmony', 'ios'])
        self.assertEqual(re.findall(r'data-dl="([\w-]+)"', sec),  # iPhone and iPad: 开发中, no button
                         ['android', 'windows', 'mac', 'linux-appimage', 'linux-deb'])
        self.assertEqual(re.findall(r'aria-disabled="true">([^<]*)</a>', sec),
                         ['即将开放'] * 3 + ['AppImage（即将开放）', 'deb（即将开放）'])
        with tempfile.TemporaryDirectory() as d, patch.object(app, 'DOWNLOADS', Path(d)):
            self.assertEqual(self.call(self.site, '/download/latest.json')[:2], (200, {}))  # nothing yet: 即将开放
            apk = Path(d) / 'flow-android-1.2.3.apk'; apk.write_bytes(b'PK\x03\x04 an installer')
            (Path(d) / 'latest.json').write_text(json.dumps({'android': {
                'file': apk.name, 'version': '1.2.3', 'size': apk.stat().st_size, 'sha256': hashlib.sha256(apk.read_bytes()).hexdigest()}}))
            (Path(d) / 'notes.txt').write_text('not served'); (Path(d) / '.flow.apk').write_bytes(b'hidden')
            st, got, h = self.call(self.site, '/download/latest.json', raw=True)
            self.assertEqual((st, h['Content-Type'], h['Cache-Control']), (200, 'application/json; charset=utf-8', 'no-cache'))
            self.assertEqual(json.loads(got)['android']['file'], apk.name)
            st, got, h = self.call(self.site, '/download/' + apk.name, raw=True)
            self.assertEqual((st, got, h['Content-Type']), (200, apk.read_bytes(), 'application/vnd.android.package-archive'))
            self.assertEqual(h['Content-Disposition'], f'attachment; filename="{apk.name}"')
            deb = Path(d) / 'flow-linux-1.2.3-amd64.deb'; deb.write_bytes(b'!<arch> a package')
            img = Path(d) / 'flow-linux-1.2.3-x86_64.AppImage'; img.write_bytes(b'ELF an image')
            self.assertEqual(self.call(self.site, '/download/' + deb.name, raw=True)[2]['Content-Type'], 'application/vnd.debian.binary-package')
            self.assertEqual(self.call(self.site, '/download/' + img.name, raw=True)[2]['Content-Type'], 'application/octet-stream')
            for path in ('/download/', '/download/notes.txt', '/download/.flow.apk', '/download/..%2fapp.py',
                         '/download/sub/flow.apk', '/download/flow-9.apk', '/download/' + 'a' * 101 + '.apk'):
                self.assertEqual(self.call(self.site, path, raw=True)[0], 404, path)

    def test_the_harmony_card_shows_each_site_its_own_part(self):
        """鸿蒙 (/about#download), the owner 2026-11-26: 语流 says the app is in 内测 and how to ask to join (问题反馈), with
        nothing about AppTest; the 内测版 has the install steps, and its box asks /api/next/harmony-test for the invite code
        (or a link) saved in its console. The page itself never carries either, and the endpoint gives them only to
        someone signed in to the 内测版 (只发同学); 语流 has no such endpoint."""
        import console_ops, time
        code, link = 'TEST1234', 'https://appgallery.huawei.com/link/invite-test-wap?taskId=1&invitationCode=ab'  # made up
        with tempfile.TemporaryDirectory() as d, patch.object(console_ops, 'data_dir', return_value=Path(d)):
            def card(channel):
                with patch.object(app, 'CHANNEL', channel):
                    body = self.call(self.site, '/about', raw=True)[1].decode()
                self.assertNotIn('<!--channel', body); self.assertNotIn('__HARMONY_TEST__', body)
                return body[body.index('data-app="harmony"'):body.index('data-app="ios"')]
            def ask(channel, signed_in):
                h = {'Cookie': 'flow_session=tok-harmony'} if signed_in else {}
                with patch.object(app, 'CHANNEL', channel):
                    return self.call(self.site, '/api/next/harmony-test', headers=h)[:2]
            with app.db() as c:
                uid = c.execute("INSERT INTO users(username,password,admin,created) VALUES('hm-learner','x',0,?)", (time.time(),)).lastrowid
                c.execute("INSERT INTO sessions VALUES('tok-harmony',?,'csrf',?)", (uid, time.time() + 3600)); c.commit()
            beta = card('beta')
            self.assertIn('AppTest', beta); self.assertIn('邀请码每月更新', beta); self.assertIn('未成年模式', beta)
            self.assertIn('没有的话在 App 里注册一个', beta)
            self.assertNotIn('申请鸿蒙内测', beta)
            self.assertIn('<div class="dl" data-harmony><p class="hm-code" hidden>', beta)
            self.assertIn('data-tap="about-harmony-join" aria-disabled="true">即将开放</a>', beta)
            self.assertEqual(ask('beta', True), (200, {'url': '', 'code': ''}))  # signed in, nothing saved: 即将开放 stays
            console_ops.set_harmony_test(' ' + code + ' ', 'op')  # an invite code, what Huawei's console gives now
            self.assertEqual((console_ops.harmony_test_value(), console_ops.harmony_test_code(), console_ops.harmony_test_url()), (code, code, ''))
            self.assertEqual(console_ops.harmony_test_host(), '')
            self.assertNotIn(code, card('beta'))  # never in the page, even with it saved
            self.assertEqual(ask('beta', True), (200, {'url': '', 'code': code}))
            self.assertEqual(ask('beta', False)[0], 401)  # whoever opens /about without signing in gets 「登录内测版后显示」
            self.assertEqual(ask('prod', True)[0], 404)  # 语流: no such endpoint, whatever is saved
            prod = card('prod')
            self.assertIn('申请鸿蒙内测', prod); self.assertIn('href="/#/feedback"', prod)
            for word in ('AppTest', 'data-harmony', 'hm-code', code, '加入内测', '邀请码'):
                self.assertNotIn(word, prod)
            console_ops.set_harmony_test_url(link, 'op')  # a link still works, should one appear
            self.assertEqual(console_ops.harmony_test_host(), 'appgallery.huawei.com')
            self.assertNotIn('huawei.com', card('beta'))
            self.assertEqual(ask('beta', True), (200, {'url': link, 'code': ''}))
            for bad in ('ab', 'AB 12', 'AB12"<', '-AB12', 'AB-12', 'AB_12', 'A' * 33, 'http://appgallery.huawei.com/x', 'javascript:alert(1)',
                        'https://appgallery.huawei.com/x"><script>', 'https:///x'):
                with self.assertRaises(ValueError):
                    console_ops.set_harmony_test(bad, 'op')
            self.assertEqual(console_ops.harmony_test_value(), link)  # a refused one leaves the saved one as it was
            console_ops.save_settings({'harmony_test_url': 'javascript:alert(1)'}, 'op')  # even if the file is edited by hand
            self.assertEqual(ask('beta', True), (200, {'url': '', 'code': ''}))
            console_ops.set_harmony_test('', 'op')  # emptied: back to 即将开放
            self.assertNotIn('harmony_test_url', console_ops.settings()); self.assertEqual(ask('beta', True), (200, {'url': '', 'code': ''}))

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
            with patch('daily_service.PAUSED', True):  # switched off: the console says so instead of starting it
                self.assertEqual(self.console('/daily/run', 'boss@example.com', {})[0], 409)
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
        self.assertEqual(rows[1]['action_label'], '生成今日一读')

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
            for key, t, n in (('home-more', at - 2 * DAY, 3), ('home-more', at + DAY, 9), ('practice-tip', at + DAY, 5), ('words-plan', at, 4)):
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
        self.assertEqual((taps['home-more']['before'], taps['home-more']['after'], taps['practice-tip']['after']), (3, 9, 5))
        self.assertEqual(taps['home-more']['label'], '今日 · 更多材料')
        self.assertEqual((taps['words-plan']['before'], taps['words-plan']['after']), (0, 0))  # the release day is on neither side


class TapTests(Servers):
    def test_a_tap_is_counted_per_day_and_key_only(self):
        for _ in range(3):
            self.assertEqual(self.call(self.site, '/api/next/tap', {'k': 'practice-tip'})[0], 200)
        self.assertEqual(self.call(self.site, '/api/next/tap', {'k': 'anything-else'})[0], 400)
        with app.db() as c:
            rows = [tuple(r) for r in c.execute('SELECT key, n FROM ui_taps')]
            cols = [r[1] for r in c.execute('PRAGMA table_info(ui_taps)')]
        self.assertEqual(rows, [('practice-tip', 3)])
        self.assertEqual(cols, ['day', 'key', 'n'])  # nothing about who

    def test_every_counted_entry_point_is_on_the_page_and_known_to_the_console(self):
        js = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8') + (Path(app.ROOT) / 'public' / 'about.html').read_text(encoding='utf-8')  # 认识语流 counts its buttons too
        import re
        used = set(re.findall(r'data-tap="([a-z-]+)"', js)) | set(re.findall(r"'([a-z]+-[a-z-]+)'", js)) & set(flow_admin.TAP_LABEL)
        self.assertEqual(set(flow_admin.TAP_LABEL) - used, set())


if __name__ == '__main__':
    unittest.main()
