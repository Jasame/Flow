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
        return self.call('/api/register', {'username': name, 'password': PW, 'storage': True, 'terms': True, **extra}, {'X-Real-IP': f'10.8.0.{self.n}'})

    def signed(self, name, **extra):
        st, body, h = self.register(name, **extra)
        self.assertEqual(st, 200, body)
        cookie = h['Set-Cookie'].split(';')[0]
        me = self.call('/api/session', headers={'Cookie': cookie})[1]['user']
        return {'Cookie': cookie, 'X-CSRF-Token': me['csrf']}, me

    def console(self, path):
        return self.call('/flow/api' + path, headers={'Cf-Access-Authenticated-User-Email': BOSS}, srv=self.admin, raw=path.endswith('.csv'))[:2]




class ChapterDateTests(unittest.TestCase):
    def test_the_privacy_chapter_has_its_dates_and_a_change_log_that_agree(self):
        """「更新日期 ｜ 生效日期」 under the title, and 「修改记录」 at the end: a change of substance adds a line there and
        moves the 更新日期 to that day (A0, 2026-11-25)."""
        import re
        text = (HERE / 'public/guide/guide.md').read_text(encoding='utf-8')
        chapter = text[text.index('# 隐私和数据 {#privacy}'):]
        chapter = chapter[:chapter.index('\n# ', 5)]
        m = re.search(r'更新日期：(\d{4}-\d{2}-\d{2}) ｜ 生效日期：(\d{4}-\d{2}-\d{2})', chapter)
        self.assertIsNotNone(m, 'the 隐私和数据 chapter needs 「更新日期：… ｜ 生效日期：…」 under its title')
        self.assertLessEqual(m.group(2), m.group(1))
        log = chapter[chapter.index('## 修改记录'):]
        days = re.findall(r'^- (\d{4}-\d{2}-\d{2})：', log, re.M)
        self.assertTrue(days, 'the 修改记录 lists each change on a line of its own')
        self.assertEqual(max(days), m.group(1), 'the 更新日期 is the day of the newest line in 修改记录')


class StorageTests(Privacy):
    """数据存放在香港 (the user, 2026-11-25): its own tick at sign-up; an older account is held until it answers; 不同意 or
    撤回 pauses the account (only agree again, export, delete, sign out, the password), no mail, out of class numbers,
    PAUSE_DAYS to come back; every answer is kept with the wording's version."""

    def events(self, uid):
        with app.db() as c:
            return [tuple(r) for r in c.execute("SELECT agree, version FROM consent_events WHERE user_id=? AND kind='storage' ORDER BY id", (uid,))]

    def test_sign_up_needs_its_own_tick(self):
        for bad in (False, None, 'yes'):
            st, body, _ = self.register('dawei', age='18+', storage=bad)
            self.assertEqual((st, body['field'], body['code']), (400, 'storage', 'storage'), bad)
        with app.db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM users WHERE username='dawei'").fetchone())  # no account was made
        _, me = self.signed('dawei', age='18+')
        self.assertEqual(me['storage'], 'ok')
        self.assertEqual(self.events(me['id']), [(1, pv.STORAGE_VERSION)])

    def test_an_older_account_is_held_until_it_answers(self):
        h, me = self.signed('laowang', age='18+')
        with app.db() as c:
            c.execute('UPDATE users SET storage_ok=NULL WHERE id=?', (me['id'],)); c.commit()  # as every account before 2026-11-25
        self.assertIsNone(self.call('/api/session', headers=h)[1]['user']['storage'])
        st, body, _ = self.call('/api/next/class', headers=h)
        self.assertEqual((st, body['code']), (403, 'storage'))
        self.assertEqual(self.call('/api/next/class/leave', {}, h)[0], 403)  # a write too
        st, home, _ = self.call('/api/next/home', headers=h)  # the page starts: a guest's home, with the session to ask
        self.assertEqual((st, home['session']['user']['username'], home['session']['user']['storage']), (200, 'laowang', None))
        st, r, _ = self.call('/api/account/storage', {'agree': True}, h)
        self.assertEqual((st, r['storage']), (200, 'ok'))
        self.assertEqual(self.call('/api/next/class', headers=h)[0], 200)

    def test_declining_pauses_the_account_and_leaves_export_password_delete(self):
        h, me = self.signed('xiaolin', age='18+')
        st, r, _ = self.call('/api/account/storage', {'agree': False}, h)
        self.assertEqual((st, r['storage']), (200, 'no'))
        self.assertRegex(r['storage_until'], r'^\d{4}-\d{2}-\d{2}$')  # the day it goes, PAUSE_DAYS on
        self.assertEqual(self.call('/api/next/class', headers=h)[1]['code'], 'storage')
        self.assertEqual(self.call('/api/next/export/records.json', headers=h, raw=True)[0], 200)
        st, r, _ = self.call('/api/account/storage', {'agree': True}, h)  # 重新同意: goes on
        self.assertEqual(r['storage'], 'ok')
        self.assertEqual(self.events(me['id']), [(1, pv.STORAGE_VERSION), (0, pv.STORAGE_VERSION), (1, pv.STORAGE_VERSION)])
        self.call('/api/account/storage', {'agree': False}, h)
        self.assertEqual(self.call('/api/password', {'old_password': PW, 'new_password': 'another long one'}, h)[0], 200)  # paused, still allowed

    def test_a_paused_account_gets_no_weekly_mail_and_is_out_of_class_numbers(self):
        import datetime, class_service as cs, progress_service as ps
        sunday = datetime.datetime(2026, 11, 29, 21, tzinfo=datetime.timezone(datetime.timedelta(hours=8))).timestamp()
        ids = {}
        for n in ('xiaolin', 'xiaowang'):
            h, me = self.signed(n, age='18+')
            ids[n] = me['id']
        with app.db() as c:
            for n, uid in ids.items():
                c.execute('UPDATE users SET email=? WHERE id=?', (f'{n}@example.com', uid))
                c.execute('INSERT OR REPLACE INTO next_progress VALUES(?,?,?,?)', (uid, 'p1', 'listen', sunday - 2 * 86400))
            cid = c.execute("INSERT INTO classes(name, code, teacher, by, created, updated) VALUES('高一（3）班', 'TESTC2', NULL, 't', ?, ?)", (sunday, sunday)).lastrowid
            for uid in ids.values():
                c.execute('INSERT INTO class_members(user_id, class_id, joined_at) VALUES(?,?,?)', (uid, cid, sunday - 9 * 86400))
            c.commit()
            pv.set_storage(c, ids['xiaowang'], {'agree': False})
            sent = []
            ps.send_weekly(c, sunday, send=lambda to, *a, **k: sent.append(to))
            self.assertIn('xiaolin@example.com', sent)
            self.assertNotIn('xiaowang@example.com', sent)
            members = cs._members(c, cs._class(c, cid))
        self.assertEqual([u for u, _ in members], [ids['xiaolin']])

    def test_the_guardian_tick_says_hong_kong_too(self):
        self.assertIn('香港', pv.NEED_GUARDIAN)
        self.assertIn('录音不保存', pv.NEED_GUARDIAN)
        js = (HERE / 'public/src/next/81-privacy.js').read_text(encoding='utf-8')
        self.assertIn('也同意我的账号和学习数据存放在香港的服务器上', js)
        self.assertIn(pv.STORAGE_TEXT, js)  # the page and the server say the same words



class TermsTests(Privacy):
    """用户协议 and 隐私和数据 (the user's choice 2026-11-25): one tick at sign-up for both, next to and never merged with
    the storage one; an account without the current version (never asked, or agreed to an earlier one) is held until
    it agrees; every answer is kept with its version."""

    def test_sign_up_needs_the_terms_tick_apart_from_the_storage_one(self):
        st, body, _ = self.register('dawei', age='18+', terms=False)
        self.assertEqual((st, body['field'], body['code']), (400, 'terms', 'terms'))
        st, body, _ = self.register('dawei', age='18+', storage=False)  # the storage tick is still its own
        self.assertEqual(body['code'], 'storage')
        _, me = self.signed('dawei', age='18+')
        self.assertEqual((me['terms'], me['storage']), ('ok', 'ok'))
        with app.db() as c:
            kinds = {(r['kind'], r['version']) for r in c.execute('SELECT kind, version FROM consent_events WHERE user_id=?', (me['id'],))}
        self.assertEqual(kinds, {('storage', pv.STORAGE_VERSION), ('terms', pv.CONSENT_VERSION)})

    def test_an_account_without_the_current_version_is_held_until_it_agrees(self):
        h, me = self.signed('laowang', age='18+')
        for earlier in (None, 'an-earlier/version'):
            with app.db() as c:
                c.execute('UPDATE users SET terms_version=? WHERE id=?', (earlier, me['id'])); c.commit()
            self.assertIsNone(self.call('/api/session', headers=h)[1]['user']['terms'])
            st, body, _ = self.call('/api/next/class', headers=h)
            self.assertEqual((st, body['code'], body['need']), (403, 'storage', 'terms'))  # code storage: what the Apps out there know
            st, home, _ = self.call('/api/next/home', headers=h)  # the page starts: a guest's home, with the session to ask
            self.assertEqual((st, home['session']['user']['terms']), (200, None))
            self.assertEqual(self.call('/api/next/export/records.json', headers=h, raw=True)[0], 200)
            self.assertEqual(self.call('/api/account/terms', {'agree': False}, h)[0], 400)  # nothing to decline: it stays held
            st, r, _ = self.call('/api/account/terms', {'agree': True}, h)
            self.assertEqual((st, r['terms']), (200, 'ok'))
            self.assertEqual(self.call('/api/next/class', headers=h)[0], 200)

    def test_a_new_version_asks_everyone_again(self):
        h, me = self.signed('xiaolin', age='18+')
        with patch.object(pv, 'CONSENT_VERSION', pv.CONSENT_VERSION + '-next'):
            self.assertIsNone(self.call('/api/session', headers=h)[1]['user']['terms'])
            self.assertEqual(self.call('/api/next/class', headers=h)[1]['need'], 'terms')

    def test_the_versions_are_the_chapters_dates(self):
        """PRIVACY_VERSION is the 隐私和数据 chapter's 生效日期 (when it has one); TERMS_VERSION the 用户协议 chapter's
        once the text is approved. A new 生效日期 is a new version: everyone agrees again."""
        import re
        text = (HERE / 'public/guide/guide.md').read_text(encoding='utf-8')
        def chapter(tag):
            ch = text[text.index(tag):]
            return ch[:ch.index('\n# ', 5)]
        m = re.search(r'生效日期：(\d{4}-\d{2}-\d{2})', chapter('# 隐私和数据 {#privacy}'))
        if m:
            self.assertEqual(pv.PRIVACY_VERSION, m.group(1))
        if pv.TERMS_VERSION != pv.TERMS_DRAFT:
            self.assertIn('生效日期：' + pv.TERMS_VERSION, chapter('# 语流用户协议 {#terms}'))

    def test_the_draft_agreement_never_ships(self):
        """Red on purpose until the owner approves the 用户协议 text: then the chapter gets the text and its dates, and
        TERMS_VERSION its 生效日期 (privacy_service). Auto-merge waits for green, so the draft cannot go out."""
        text = (HERE / 'public/guide/guide.md').read_text(encoding='utf-8')
        terms = text[text.index('# 语流用户协议 {#terms}'):]
        terms = terms[:terms.index('\n# ', 5)]
        self.assertNotEqual(pv.TERMS_VERSION, pv.TERMS_DRAFT, 'the 用户协议 text is still a draft: wait for the owner\'s OK')
        self.assertNotIn('占位', terms)


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
    """Deploy-time database copies: each site prunes only its own (backup-pull-<date> 语流, backup-pull-beta-<date> 内测版),
    logs each copy with its size first, and the 内测版 only lists them unless told otherwise."""
    OLD = time.time() - 15 * 86400

    def make(self, root, name, old=True, size=2048):
        d = root / name
        (d / 'files').mkdir(parents=True)
        (d / 'new-files.txt').write_text('')
        f = d / 'flow-before.sqlite3'
        f.write_bytes(b'x' * size)
        if old:
            os.utime(f, (self.OLD, self.OLD))
        return f

    def test_the_beta_never_touches_the_main_sites_copies(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            prod_old, beta_old = self.make(root, 'backup-pull-20261101-020304'), self.make(root, 'backup-pull-beta-20261101-020304')
            lines = []
            got = ops.prune_deploy_copies(root, channel='beta', dry_run=False, say=lines.append)
            self.assertEqual([g[0] for g in got], [beta_old])
            self.assertTrue(prod_old.exists())
            self.assertFalse(beta_old.exists())
            self.assertTrue((beta_old.parent / 'new-files.txt').exists() and (beta_old.parent / 'files').is_dir())  # a rollback keeps its files

    def test_the_main_site_never_touches_the_betas_or_unknown_folders(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            prod_old, prod_new = self.make(root, 'backup-pull-20261101-020304'), self.make(root, 'backup-pull-20261124-020304', old=False)
            keep = [self.make(root, n) for n in ('backup-pull-beta-20261101-020304', 'backup-pull-20261101', 'backup-pull-x-20261101-020304',
                                                 'beta-setup-20261101-020304', 'backup-pull-20261101-020304-old')]
            got = ops.prune_deploy_copies(root, channel='prod', dry_run=False, say=lambda *_: None)
            self.assertEqual([g[0] for g in got], [prod_old])
            self.assertFalse(prod_old.exists())
            self.assertTrue(prod_new.exists() and all(f.exists() for f in keep))
            self.assertEqual(ops.prune_deploy_copies(root, channel='test', say=lambda *_: None), [])  # an unknown site: nothing

    def test_the_beta_lists_only_by_default_and_every_copy_is_logged_with_its_size(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {}, clear=False):
            os.environ.pop('FLOW_PRUNE_DRY_RUN', None)
            root = Path(d)
            beta_old = self.make(root, 'backup-pull-beta-20261101-020304', size=3 * 1048576)
            lines = []
            got = ops.prune_deploy_copies(root, channel='beta', say=lines.append)
            self.assertEqual(len(got), 1)
            self.assertTrue(beta_old.exists())  # listed, not deleted
            self.assertIn('只列不删', lines[0])
            self.assertIn(str(beta_old), lines[0])
            self.assertIn('3.0 MB', lines[0])
            self.assertIn('1 个超过 14 天的旧数据库副本，共 3.0 MB', lines[-1])
            os.environ['FLOW_PRUNE_DRY_RUN'] = '0'
            ops.prune_deploy_copies(root, channel='beta', say=lines.append)
            self.assertFalse(beta_old.exists())
            os.environ['FLOW_PRUNE_DRY_RUN'] = '1'
            prod_old = self.make(root, 'backup-pull-20261101-020304')
            ops.prune_deploy_copies(root, channel='prod', say=lines.append)
            self.assertTrue(prod_old.exists())  # the switch holds 语流 back too
            os.environ.pop('FLOW_PRUNE_DRY_RUN')
            self.assertTrue(ops.dry_default('beta'))
            self.assertFalse(ops.dry_default('prod'))
            self.assertEqual(ops.prune_deploy_copies(Path(d) / 'missing', say=lambda *_: None), [])

    def test_the_deploy_script_prunes_only_its_own_site(self):
        script = (HERE.parent / 'tools' / 'flow-pull.sh').read_text()
        self.assertIn('case "$SVC" in flow) CH=prod;; flow-beta) CH=beta;; *) CH=;; esac', script)
        self.assertIn('"$F/ops.py" prune-deploy --channel "$CH"', script)
        self.assertNotIn('find "$OPS" -maxdepth 2', script)  # the old rule matched both sites


class PromiseTests(unittest.TestCase):
    def test_nothing_shared_carries_a_name(self):
        src = HERE / 'public' / 'src' / 'next'
        for part in ('86-share.js', '73-report.js', '82-class.js'):
            self.assertNotIn('username', (src / part).read_text(), part)

    def test_the_privacy_chapter_says_what_the_site_does(self):
        import user_guide as ug
        ch = next(c for c in ug.parse()['chapters'] if c['id'] == 'privacy')
        for words in ('香港的服务器', '保留 14 天', '最迟 14 天后删除', '阿里云百炼', '不交给境外的 AI', '不会被拿去训练', '不带你的用户名',
                      '录音不保存', '不满 14 岁', '导出我的数据', '注销账号', '只能看到全班的汇总数字'):
            self.assertIn(words, ch['text'], words)
        self.assertIn('/#/guide/privacy', (HERE / 'public' / 'about.html').read_text())


if __name__ == '__main__':
    unittest.main()
