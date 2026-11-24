"""What learners' browsers report about the site (field_service): page errors counted per day and kind of page, and
opening times with where the time went. Nothing about who: no account, no address, only the browser's family."""
import json, os, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, field_service as fs, flow_admin  # noqa: E402

IPHONE = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1'
WECHAT = 'Mozilla/5.0 (Linux; Android 13; V2241A) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/116.0 Mobile Safari/537.36 MicroMessenger/8.0.47'


class Servers(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_ADMIN_EMAILS': 'boss@example.com'})]
        for p in self.patches:
            p.start()
        app.SECURE = False
        app.init()
        (Path(self.tmp.name) / 'deploy-status.json').write_text(json.dumps({'tag': 'r21'}))
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

    def post(self, path, data, ua=IPHONE, ctype='text/plain;charset=UTF-8'):  # sendBeacon sends a string as text/plain
        req = urllib.request.Request(f'http://127.0.0.1:{self.site.server_address[1]}{path}', data=json.dumps(data).encode(),
                                     headers={'Content-Type': ctype, 'User-Agent': ua})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read() or b'{}')
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def console(self, path, email='boss@example.com'):
        req = urllib.request.Request(f'http://127.0.0.1:{self.admin.server_address[1]}/flow/api{path}', headers={'Cf-Access-Authenticated-User-Email': email})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b'{}')

    def rows(self, table):
        with app.db() as c:
            return [dict(r) for r in c.execute(f'SELECT * FROM {table}')]


class IssueTests(Servers):
    def test_a_problem_is_counted_by_kind_of_page_without_who(self):
        item = {'kind': 'js', 'page': '#/m/v5-campus-a2-budget-cooking/read', 'message': "TypeError: x is null", 'source': 'next.js:1'}
        for ua in (IPHONE, IPHONE, WECHAT):
            self.assertEqual(self.post('/api/next/issues', {'items': [item], 'asset': 'abc'}, ua)[0], 200)
        rows = sorted(self.rows('client_issues'), key=lambda r: r['platform'])
        self.assertEqual([(r['page'], r['platform'], r['n'], r['release']) for r in rows],
                         [('#/m/*/read', 'Android · 微信', 1, 'r21'), ('#/m/*/read', 'iPhone · Safari', 2, 'r21')])
        cols = set(rows[0])
        self.assertFalse(cols & {'user_id', 'ip', 'address', 'ua', 'account'})

    def test_messages_lose_addresses_queries_and_long_numbers(self):
        self.assertEqual(fs.clean_message('img 没加载出来：https://flow.jasa.hk/audio/us-f/v5-x.mp4?v=1795344292'), 'img 没加载出来：/audio/us-f/v5-x.mp4')
        self.assertEqual(fs.clean_message('bad input from lin@example.com at 1795344292'), 'bad input from <email> at #')
        self.assertEqual(fs.page_of('#/graph/tense-past?x=1'), '#/graph/*')
        self.assertEqual(fs.page_of('#/radar/test/writing'), '#/radar/test/writing')  # a fixed page, not an id
        self.assertEqual(fs.page_of('#/series/lighthouse-ledger'), '#/series/*')
        self.assertEqual(fs.page_of('javascript:alert(1)'), '#/')

    def test_what_is_refused_and_the_daily_caps(self):
        self.assertEqual(self.post('/api/next/issues', {'items': []})[0], 400)
        self.assertEqual(self.post('/api/next/issues', {'items': [{'kind': 'js', 'message': 'x'}] * 21})[0], 400)
        self.assertEqual(self.post('/api/next/issues', {'items': [{'kind': 'nonsense', 'message': 'x'}]})[1]['kept'], 0)
        with patch.object(fs, 'MAX_ISSUE_ROWS', 2):
            for k in range(4):
                self.post('/api/next/issues', {'items': [{'kind': 'js', 'message': f'error {k}'}]})
            self.assertEqual(len(self.rows('client_issues')), 2)  # new problems stop at the cap; known ones still count
            self.post('/api/next/issues', {'items': [{'kind': 'js', 'message': 'error 0'}]})
            self.assertEqual(sum(r['n'] for r in self.rows('client_issues')), 3)

    def test_platforms(self):
        self.assertEqual(fs.platform(IPHONE), ('iPhone', 'Safari'))
        self.assertEqual(fs.platform(WECHAT), ('Android', '微信'))
        self.assertEqual(fs.platform('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1'), ('iPad', 'Safari'))
        self.assertEqual(fs.platform('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 Edg/124.0'), ('Windows', 'Edge'))


class OpenTimeTests(Servers):
    def test_an_opening_is_kept_with_where_the_time_went(self):
        body = {'domain': 'flowlang.cn', 'first_view': 1830.4, 'waited': 2100, 'dns': 40, 'connect': 120, 'tls': 90, 'ttfb': 310, 'html': 25,
                'scripts': 600, 'home_api': 420, 'render': 60, 'repeat': False, 'standalone': True, 'net': '4g', 'tz': 'Asia/Shanghai'}
        self.assertEqual(self.post('/api/next/opentime', body, WECHAT)[0], 200)
        r = self.rows('open_times')[0]
        self.assertEqual((r['domain'], r['platform'], r['browser'], r['first_view'], r['ttfb'], r['net'], r['tz'], r['standalone']),
                         ('flowlang.cn', 'Android', '微信', 1830, 310, '4g', 'Asia/Shanghai', 1))
        self.assertFalse(set(r) & {'user_id', 'ip', 'address', 'ua'})

    def test_odd_values_are_dropped_and_a_visit_that_left_early_counts(self):
        self.post('/api/next/opentime', {'domain': 'evil.example', 'first_view': None, 'waited': 9000, 'dns': -5, 'ttfb': 10 ** 9, 'net': 'fiber'})
        r = self.rows('open_times')[0]
        self.assertEqual((r['domain'], r['first_view'], r['waited'], r['dns'], r['ttfb'], r['net']), ('其他', None, 9000, None, None, ''))

    def test_the_console_shows_the_spread_and_where_time_goes(self):
        for v, ua, repeat in ((1000, IPHONE, True), (2000, IPHONE, False), (3000, WECHAT, False), (None, WECHAT, False)):
            self.post('/api/next/opentime', {'domain': 'flow.jasa.hk', 'first_view': v, 'ttfb': 300, 'repeat': repeat}, ua)
        st, d = self.console('/speed', email='intern@example.com')  # numbers only: open to 只看数据 too
        self.assertEqual(st, 200)
        self.assertEqual((d['overall']['visits'], d['overall']['p50'], d['overall']['p90'], d['overall']['left']), (4, 2000, 3000, 1))
        self.assertEqual(d['phases']['ttfb'], 300)
        by = {g['group']: g for g in d['by']['browser']}
        self.assertEqual((by['Safari']['visits'], by['微信']['left_pct']), (2, 50.0))
        self.assertEqual({g['group'] for g in d['by']['repeat']}, {'再次打开（有缓存）', '第一次打开'})

    def test_the_slowest_quarter_shows_where_it_waits(self):
        # quick visits wait on nothing in particular; the slow ones wait for the home data
        quick = [(v, v // 6) for v in range(300, 1000, 100)]  # 7 visits, the home data a sixth of the time
        for v, api in quick + [(6000, 4800), (7000, 5600)]:
            self.post('/api/next/opentime', {'domain': 'flowlang.cn', 'first_view': v, 'home_api': api, 'scripts': 20}, WECHAT)
        d = self.console('/speed', email='intern@example.com')[1]
        self.assertEqual(d['slow_visits'], 3)  # from the 75th percentile up: 900, 6000 and 7000
        self.assertEqual((d['phases']['home_api'], d['phases_slow']['home_api'], d['phases_slow']['scripts']), (116, 4800, 20))


    def test_startup_boot_and_the_first_page_are_kept(self):
        body = {'domain': 'flowlang.cn', 'first_view': 900, 'startup': 420, 'boot': 130, 'scripts': 200, 'page': 'material', 'hidden': False}
        self.post('/api/next/opentime', body, WECHAT)
        self.post('/api/next/opentime', {'domain': 'flowlang.cn', 'first_view': 300, 'page': 'admin', 'hidden': 'yes'}, WECHAT)
        a, b = sorted(self.rows('open_times'), key=lambda r: r['id'])
        self.assertEqual((a['startup'], a['boot'], a['page'], a['hidden']), (420, 130, 'material', 0))
        self.assertEqual((b['startup'], b['boot'], b['page'], b['hidden']), (None, None, '', 0))  # only known pages, only true

    def test_a_page_opened_out_of_sight_is_left_out_and_counted_apart(self):
        for v, hidden, page in ((400, False, 'today'), (600, False, 'today'), (800, False, 'material'), (11000, True, 'today')):
            self.post('/api/next/opentime', {'domain': 'flowlang.cn', 'first_view': v, 'startup': 50, 'hidden': hidden, 'page': page}, WECHAT)
        d = self.console('/speed', email='intern@example.com')[1]
        self.assertEqual((d['overall']['visits'], d['overall']['p90'], d['hidden_visits']), (3, 800, 1))
        self.assertEqual(d['phases']['startup'], 50)
        self.assertEqual(list(d['phases']), list(fs.PHASES))
        self.assertEqual(fs.PHASES[0], 'startup'); self.assertEqual(fs.PHASES.index('boot'), fs.PHASES.index('scripts') + 1)
        by = {g['group']: g['visits'] for g in d['by']['page']}
        self.assertEqual(by, {'今日': 2, '从链接打开的材料页': 1})

    def test_a_table_from_before_r27_gets_the_new_columns(self):
        import sqlite3
        c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
        c.execute('CREATE TABLE open_times(id INTEGER PRIMARY KEY, created REAL NOT NULL, day TEXT NOT NULL, domain TEXT NOT NULL, '
                  'platform TEXT NOT NULL, browser TEXT NOT NULL, net TEXT NOT NULL, tz TEXT NOT NULL, repeat INTEGER NOT NULL, standalone INTEGER NOT NULL, '
                  'first_view INTEGER, waited INTEGER NOT NULL DEFAULT 0, dns INTEGER, connect INTEGER, tls INTEGER, ttfb INTEGER, html INTEGER, '
                  'scripts INTEGER, home_api INTEGER, render INTEGER)')  # as r20 made it: no snap either
        c.execute("INSERT INTO open_times(created, day, domain, platform, browser, net, tz, repeat, standalone, first_view) "
                  "VALUES(1, ?, 'flowlang.cn', 'iPhone', '微信', '', '', 0, 0, 700)", (fs._today(),))
        fs.schema(c); fs.schema(c)  # twice: the second run finds every column there
        cols = {r[1] for r in c.execute('PRAGMA table_info(open_times)')}
        self.assertTrue({'snap', 'startup', 'boot', 'hidden', 'page'} <= cols)
        d = fs.speed(c)
        self.assertEqual((d['overall']['visits'], d['hidden_visits'], d['by']['page'][0]['group']), (1, 0, 'r26 以前（没有记录）'))

class ConsoleTests(Servers):
    def test_page_errors_sit_with_the_server_errors_for_administrators(self):
        self.post('/api/next/issues', {'items': [{'kind': 'audio', 'page': '#/m/v5-x/listen', 'message': '没有放出声音（微信）'}]}, WECHAT)
        st, d = self.console('/errors')
        self.assertEqual(st, 200)
        g = d['client']['groups'][0]
        self.assertEqual((g['kind_label'], g['page'], g['count'], g['platforms']), ('声音放不出来', '#/m/*/listen', 1, [['Android · 微信', 1]]))
        self.assertEqual(self.console('/errors', email='intern@example.com')[0], 403)

    def test_the_page_reports_and_the_console_has_the_tabs(self):
        js = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8')
        for s in ("beacon('/api/next/issues'", "beacon('/api/next/opentime'", 'firstViewDrawn(); prefetchTabs();', "noteIssue('api'", "noteIssue('audio'", '}, true);'):
            self.assertIn(s, js)
        root = Path(app.ROOT).parent / 'xmc-admin'
        self.assertIn('data-tab="speed"', (root / 'index.html').read_text(encoding='utf-8'))
        self.assertIn('function speedView', (root / 'admin.js').read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
