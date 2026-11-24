"""年龄段 and a guardian's agreement under 14 (privacy_service.py), and what the 隐私说明 promises: the band only, never a
birthday; 不满 14 岁 signs up only with the agreement ticked; an older account is asked later and, under 14 without the
agreement, keeps everything but the AI on its own words; joining a class asks the band first; the console shows it;
导出 carries it; deploy-time database copies go after 14 days; nothing shared carries a name."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import app, flow_admin, ops, privacy_service as pv  # noqa: E402

BOSS = 'boss@example.com'
PW = 'correct horse 1'


class Privacy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'flow.sqlite3'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_ADMIN_EMAILS': BOSS})]
        for p in self.patches:
            p.start()
        app.SECURE = False
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

    def call(self, path, data=None, headers=None, srv=None, raw=False):
        srv = srv or self.site
        req = urllib.request.Request(f'http://127.0.0.1:{srv.server_address[1]}{path}', data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read()
                return r.status, (body if raw else json.loads(body or b'{}')), dict(r.headers)
        except urllib.error.HTTPError as e:
            body = e.read()
            return e.code, (body if raw else json.loads(body or b'{}')), dict(e.headers)

    def register(self, name, **extra):
        self.n += 1  # each its own address: sign-ups share a ceiling per address
        return self.call('/api/register', {'username': name, 'password': PW, **extra}, {'X-Real-IP': f'10.8.0.{self.n}'})

    def signed(self, name, **extra):
        st, body, h = self.register(name, **extra)
        self.assertEqual(st, 200, body)
        cookie = h['Set-Cookie'].split(';')[0]
        me = self.call('/api/session', headers={'Cookie': cookie})[1]['user']
        return {'Cookie': cookie, 'X-CSRF-Token': me['csrf']}, me

    def console(self, path):
        return self.call('/flow/api' + path, headers={'Cf-Access-Authenticated-User-Email': BOSS}, srv=self.admin, raw=path.endswith('.csv'))[:2]


class SignUpTests(Privacy):
    def test_the_band_is_kept_and_under_14_needs_the_guardian_ticked(self):
        _, me = self.signed('dawei', age='18+')
        self.assertEqual((me['age'], me['guardian']), ('18+', False))
        st, body, _ = self.register('xiaomei', age='u14')
        self.assertEqual((st, body['field'], body['code']), (400, 'guardian', 'guardian'))
        with app.db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM users WHERE username='xiaomei'").fetchone())  # no account was made
        _, me = self.signed('xiaomei', age='u14', guardian=True)
        self.assertEqual((me['age'], me['guardian']), ('u14', True))
        self.assertEqual(self.register('xiaoming', age='13')[0], 400)  # a band, never an age or a birthday

    def test_an_account_without_a_band_is_asked_later_and_can_answer_under_14_without_the_tick(self):
        h, me = self.signed('laozhang')  # an older page, or an account made before the band was asked
        self.assertIsNone(me['age'])
        self.assertEqual(self.call('/api/account/age', {'age': 'u14'}, {'Cookie': h['Cookie']})[0], 403)  # the CSRF token is needed
        st, body, _ = self.call('/api/account/age', {'age': 'u14'}, h)
        self.assertEqual((st, body['age'], body['guardian']), (200, 'u14', False))
        st, body, _ = self.call('/api/account/age', {'age': ''}, h)
        self.assertEqual((st, body['code']), (400, 'age'))


class GuardianGateTests(Privacy):
    def test_under_14_without_the_agreement_keeps_everything_but_ai_on_its_own_words(self):
        h, _ = self.signed('xiaohong', age='18+')
        self.call('/api/account/age', {'age': 'u14'}, h)
        for path in ('/api/next/rewrite', '/api/next/essay', '/api/next/translate', '/api/next/retell', '/api/next/shadow', '/api/next/dialog', '/api/next/ielts'):
            st, body, _ = self.call(path, {}, h)
            self.assertEqual((st, body.get('code')), (403, 'guardian'), path)
        st, body, _ = self.call('/api/next/explain', {}, h)  # a sentence of the material: not the learner's own words
        self.assertNotEqual(body.get('code'), 'guardian')
        st, body, _ = self.call('/api/next/cards', {'text': 'commute', 'context': 'I commute to work by train.'}, h)  # studying goes on
        self.assertEqual(st, 200, body)
        st, body, _ = self.call('/api/account/age', {'age': 'u14', 'guardian': True}, h)
        self.assertTrue(body['guardian'])
        st, body, _ = self.call('/api/next/rewrite', {}, h)
        self.assertNotEqual(body.get('code'), 'guardian')

    def test_the_gate_covers_every_ai_path_that_takes_the_learners_words(self):
        import next_service as nx, ai_stream
        shared = {'/api/next/variant', '/api/next/explain', '/api/next/vocab/examples', '/api/next/translate/source'}
        self.assertEqual(set(nx.AI_PATHS) - shared, set(nx.AI_PATHS) & pv.GUARDED)
        self.assertLessEqual({'/api/chat', '/api/ai/help', '/api/coach/chat', '/api/lab/feedback', '/api/lab/audio'}, pv.GUARDED & ai_stream.PATHS)


class ClassTests(Privacy):
    def test_joining_a_class_asks_the_band_first_and_under_14_the_agreement(self):
        self.signed('wanglaoshi', age='18+')
        with app.db() as c:
            import class_service as cs
            body, st, _ = cs.create(c, {'name': '初一（2）班', 'teacher': 'wanglaoshi'}, BOSS)
        code = body['code']
        h, _ = self.signed('xiaogang')
        st, body, _ = self.call('/api/next/class/join', {'code': code}, h)
        self.assertEqual((st, body['code']), (409, 'age'))
        st, body, _ = self.call('/api/next/class/join', {'code': code, 'age': 'u14'}, h)
        self.assertEqual((st, body['code']), (409, 'guardian'))
        st, body, _ = self.call('/api/next/class/join', {'code': code, 'age': 'u14', 'guardian': True}, h)
        self.assertEqual(st, 200, body)
        self.assertEqual(body['member']['name'], '初一（2）班')


class ConsoleAndExportTests(Privacy):
    def test_the_console_shows_the_band_and_export_carries_it(self):
        h, me = self.signed('xiaolan', age='u14', guardian=True)
        self.signed('adult', age='18+')
        self.signed('nobody')
        st, d = self.console(f"/learner?id={me['id']}")
        self.assertEqual((st, d['account']['age'], d['account']['age_label']), (200, 'u14', '不满 14 岁'))
        self.assertTrue(d['account']['guardian'])
        got = self.console('/learners?filter=minor')[1]
        self.assertEqual([r['username'] for r in got['items']], ['xiaolan'])
        counts = {f['key']: f['count'] for f in got['filters']}
        self.assertEqual((counts['minor'], counts['no_age']), (1, 1))
        csv = self.console('/export/learners.csv')[1].decode('utf-8-sig')
        self.assertIn('年龄段', csv.splitlines()[0])
        self.assertIn('不满 14 岁', csv)
        req = urllib.request.Request(f'http://127.0.0.1:{self.site.server_address[1]}/api/next/export/records.json', headers={'Cookie': h['Cookie']})
        with urllib.request.urlopen(req, timeout=10) as r:
            rec = json.loads(r.read())
        self.assertEqual(rec['account']['年龄段'], '不满 14 岁')
        self.assertIn('监护人同意', rec['account'])


class BackupTests(unittest.TestCase):
    def test_deploy_time_database_copies_go_after_14_days_and_the_code_stays(self):
        with tempfile.TemporaryDirectory() as d:
            ops_dir = Path(d)
            old, new = ops_dir / 'backup-pull-20261001-000000', ops_dir / 'backup-pull-beta-20261124-000000'
            for f in (old, new):
                (f / 'files').mkdir(parents=True)
                (f / 'flow-before.sqlite3').write_bytes(b'x')
                (f / 'new-files.txt').write_text('')
            past = time.time() - 15 * 86400
            os.utime(old / 'flow-before.sqlite3', (past, past))
            self.assertEqual(ops.prune_deploy_copies(ops_dir), 1)
            self.assertFalse((old / 'flow-before.sqlite3').exists())
            self.assertTrue((old / 'new-files.txt').exists() and (old / 'files').is_dir())  # a rollback still has its files
            self.assertTrue((new / 'flow-before.sqlite3').exists())
            self.assertEqual(ops.prune_deploy_copies(Path(d) / 'missing'), 0)

    def test_the_deploy_script_prunes_them_too(self):
        script = (HERE.parent / 'tools' / 'flow-pull.sh').read_text()
        self.assertIn('-path "$OPS/backup-pull*/flow-before.sqlite3" -mtime +13 -print -delete', script)


class PromiseTests(unittest.TestCase):
    def test_nothing_shared_carries_a_name(self):
        src = HERE / 'public' / 'src' / 'next'
        for part in ('86-share.js', '73-report.js', '82-class.js'):
            self.assertNotIn('username', (src / part).read_text(), part)

    def test_the_privacy_chapter_says_what_the_site_does(self):
        import user_guide as ug
        ch = next(c for c in ug.parse()['chapters'] if c['id'] == 'privacy')
        for words in ('香港的服务器', '保留 14 天', '最迟 14 天后删除', '阿里云百炼', 'Gemini', '不会被拿去训练', '不带你的用户名',
                      '录音不保存', '不满 14 岁', '导出我的数据', '注销账号', '只能看到全班的汇总数字'):
            self.assertIn(words, ch['text'], words)
        self.assertIn('/#/guide/privacy', (HERE / 'public' / 'about.html').read_text())


if __name__ == '__main__':
    unittest.main()
