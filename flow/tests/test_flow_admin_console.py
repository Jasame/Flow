"""r26 console (xmc.hk/flow 2.0): learners one by one, the funnel and weekly cohorts, materials, word books and exam
practice, AI use; and what a 管理员 can change — stop / restore an account, sign out everywhere, level, daily new words,
员工账号, a material off the lists, the AI limits, 例句预生成, 公告, today's news again. Every change is 管理员 only on
the server, needs the X-Requested-With header and lands in the operator log; 只看数据 sees numbers, never people;
no password, session or link is ever in an answer."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, flow_admin, chat_service, console_ops, console_data, fill_examples, next_service as nx  # noqa: E402

DAY = 86400
BOSS, INTERN = 'boss@example.com', 'intern@example.com'


class Console(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'flow.sqlite3'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_ADMIN_EMAILS': BOSS, 'FLOW_AI_USER_DAILY_LIMIT': '100',
                                                'FLOW_AI_DAILY_LIMIT': '2000'})]
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
        req = urllib.request.Request(f'http://127.0.0.1:{srv.server_address[1]}{path}', data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read()
                return r.status, (body if raw else json.loads(body or b'{}')), dict(r.headers)
        except urllib.error.HTTPError as e:
            body = e.read()
            return e.code, (body if raw else json.loads(body or b'{}')), dict(e.headers)

    def console(self, path, data=None, email=BOSS, marked=True):
        h = {'Cf-Access-Authenticated-User-Email': email}
        if data is not None and marked:
            h['X-Requested-With'] = 'xmc'
        st, body, _ = self.call(self.admin, '/flow/api' + path, data, h, raw=path.endswith('.csv'))
        return st, body

    def register(self, name, password='correct horse 1'):
        st, body, h = self.call(self.site, '/api/register', {'username': name, 'password': password})
        self.assertEqual(st, 200, body)
        return h['Set-Cookie'].split(';')[0]

    def login(self, name, password='correct horse 1'):
        return self.call(self.site, '/api/login', {'username': name, 'password': password})

    def session(self, cookie):
        return self.call(self.site, '/api/session', headers={'Cookie': cookie})[1]

    def uid(self, name):
        with app.db() as c:
            return c.execute('SELECT id FROM users WHERE username=?', (name,)).fetchone()[0]

    def log(self):
        with app.db() as c:
            return [dict(r) for r in c.execute('SELECT email, role, action, target, detail FROM flow_admin_log ORDER BY id')]

    def study(self, uid, pack, steps, when):
        with app.db() as c:
            for i, s in enumerate(steps):
                c.execute('INSERT OR REPLACE INTO next_progress VALUES(?,?,?,?)', (uid, pack, s, when + i))
            c.commit()

    def profile(self, uid, level='B1', created=None):
        with app.db() as c:
            nx.save_profile(c, uid, {'level': level, 'goal': 'exam', 'themes': ['campus'], 'minutes': 10})
            if created:
                c.execute('UPDATE next_profiles SET created=? WHERE user_id=?', (created, uid))
            c.commit()


class RoleTests(Console):
    WRITES = [('/learner/disable', {'id': 1}), ('/learner/signout', {'id': 1}), ('/learner/staff', {'id': 1, 'staff': True}),
              ('/learner/level', {'id': 1, 'level': 'B2'}), ('/learner/daily-new', {'id': 1, 'daily_new': 20}),
              ('/material/hide', {'pack': 'x', 'hidden': True}), ('/settings/ai-limits', {'user_limit': 5}),
              ('/tasks/examples/start', {}), ('/tasks/examples/stop', {}), ('/announcements/create', {'text': '今晚升级十分钟'}),
              ('/announcements/end', {'id': 1}), ('/daily/run', {'again': True})]

    def test_only_a_manager_changes_anything_and_only_with_the_header(self):
        self.register('xiaolin')
        for path, data in self.WRITES:
            self.assertEqual(self.console(path, data, email=INTERN)[0], 403, path)
            self.assertEqual(self.console(path, data, marked=False)[0], 403, path)
        self.assertEqual(self.log(), [])
        with app.db() as c:
            self.assertEqual(c.execute('SELECT disabled, admin FROM users').fetchone()[:], (0, 0))

    def test_viewers_see_numbers_never_people(self):
        self.register('xiaolin')
        for path in ('/funnel', '/cohorts', '/content', '/books', '/ai', '/tasks', '/announcements'):
            self.assertEqual(self.console(path, email=INTERN)[0], 200, path)
        for path in ('/learners', '/learner?id=1', '/export/learners.csv', '/export/materials.csv', '/export/ai.csv'):
            self.assertEqual(self.console(path, email=INTERN)[0], 403, path)
        ai = self.console('/ai', email=INTERN)[1]
        self.assertNotIn('top', ai)
        self.assertNotIn('failures', ai)
        self.assertIn('top', self.console('/ai')[1])

    def test_no_password_session_or_link_in_any_answer(self):
        cookie = self.register('xiaolin', 'a secret pass 9')
        uid = self.uid('xiaolin')
        token = cookie.split('=', 1)[1]
        with app.db() as c:
            pw = c.execute('SELECT password FROM users WHERE id=?', (uid,)).fetchone()[0]
        for path in ('/learners', f'/learner?id={uid}', '/overview', '/ai', '/funnel'):
            text = json.dumps(self.console(path)[1], ensure_ascii=False)
            for secret in (token, pw, 'a secret pass 9'):
                self.assertNotIn(secret, text, path)
        self.assertNotIn(token.encode(), self.console('/export/learners.csv')[1])


class LearnerTests(Console):
    def test_the_list_and_one_learner(self):
        self.register('xiaolin')
        self.register('newbie')
        uid = self.uid('xiaolin')
        self.profile(uid)
        now = time.time()
        packs = [p['id'] for _, p in nx._public_packs(app.db())][:3]
        self.study(uid, packs[0], nx.STEPS, now - 3 * DAY)
        self.study(uid, packs[1], ['listen', 'read'], now - 60)
        with app.db() as c:
            c.execute("INSERT INTO next_cards(user_id,text,norm,meaning,created,due,lapses,source) VALUES(?,?,?,?,?,?,3,'book')", (uid, 'ubiquitous', 'ubiquitous', '无处不在的', now, now))
            c.execute("INSERT INTO ai_usage VALUES(?,?,7)", (uid, time.strftime('%Y-%m-%d', time.gmtime())))
            c.execute("INSERT INTO next_exam_results(user_id,exam,paper,score,total,parts,seconds,created) VALUES(?,?,?,?,?,?,?,?)",
                      (uid, 'cet4', 'p1', 15, 20, json.dumps([{'key': 'vocab', 'title': '词汇', 'right': 8, 'of': 10}]), 600, now))
            c.commit()
        st, d = self.console('/learners')
        self.assertEqual(st, 200)
        row = {r['username']: r for r in d['items']}
        self.assertEqual((row['xiaolin']['days_total'], row['xiaolin']['materials'], row['xiaolin']['materials_done'], row['xiaolin']['ai_7d'], row['xiaolin']['level']),
                         (2, 2, 1, 7, 'B1'))
        self.assertTrue(row['newbie']['joined_known'])  # sign-up time is kept since r26
        counts = {f['key']: f['count'] for f in d['filters']}
        self.assertEqual((counts['all'], counts['active7'], counts['never']), (2, 1, 1))
        self.assertEqual([r['username'] for r in self.console('/learners?filter=never')[1]['items']], ['newbie'])
        st, one = self.console(f'/learner?id={uid}')
        self.assertEqual(st, 200)
        self.assertEqual(one['study']['days_total'], 2)
        self.assertEqual(len(one['study']['calendar']), 84)
        self.assertEqual(one['mistakes'][0]['text'], 'ubiquitous')
        self.assertEqual((one['exams'][0]['title'], one['exams'][0]['pct']), ('大学英语四级', 75))
        self.assertEqual([m['id'] for m in one['materials']], [packs[1], packs[0]])
        self.assertEqual(self.console('/learner?id=9999')[0], 404)
        self.assertEqual(self.console('/overview')[1]['active_7d'], 1)  # a material step counts as active
        self.assertEqual(self.console('/overview')[1]['never_started'], 1)

    def test_stopping_an_account_signs_it_out_and_keeps_it_out_until_restored(self):
        cookie = self.register('xiaolin')
        uid = self.uid('xiaolin')
        self.assertTrue(self.session(cookie)['user'])
        st, body = self.console('/learner/disable', {'id': uid, 'disabled': True})
        self.assertEqual((st, body['sessions_ended']), (200, 1))
        self.assertIsNone(self.session(cookie)['user'])
        st, body, _ = self.login('xiaolin')
        self.assertEqual((st, body['code']), (403, 'disabled'))
        self.assertEqual(self.console('/learner/disable', {'id': uid, 'disabled': False})[0], 200)
        self.assertEqual(self.login('xiaolin')[0], 200)
        self.assertEqual([(r['action'], r['target'], r['email']) for r in self.log()],
                         [('account-disable', f'xiaolin #{uid}', BOSS), ('account-enable', f'xiaolin #{uid}', BOSS)])
        self.assertEqual([r['action'] for r in self.console(f'/learner?id={uid}')[1]['log']], ['account-enable', 'account-disable'])

    def test_sign_out_everywhere_staff_level_and_daily_new_words(self):
        a, b = self.register('xiaolin'), self.login('xiaolin')[2]['Set-Cookie'].split(';')[0]
        uid = self.uid('xiaolin')
        self.assertEqual(self.console('/learner/signout', {'id': uid})[1]['sessions_ended'], 2)
        self.assertIsNone(self.session(a)['user']); self.assertIsNone(self.session(b)['user'])
        self.assertEqual(self.login('xiaolin')[0], 200)  # signed out, not stopped
        self.assertEqual(self.console('/learner/level', {'id': uid, 'level': 'B2'})[0], 409)  # no profile yet
        self.profile(uid)
        self.assertEqual(self.console('/learner/level', {'id': uid, 'level': 'Z9'})[0], 400)
        self.assertEqual(self.console('/learner/level', {'id': uid, 'level': 'B2'})[0], 200)
        self.assertEqual(self.console('/learner/daily-new', {'id': uid, 'daily_new': 20})[0], 409)  # no word plan yet
        with app.db() as c:
            __import__('vocab_service').save_plan(c, uid, {'book': 'cet4', 'daily_new': 10, 'retention': 0.9})
        self.assertEqual(self.console('/learner/daily-new', {'id': uid, 'daily_new': 500})[0], 400)
        self.assertEqual(self.console('/learner/daily-new', {'id': uid, 'daily_new': 25})[0], 200)
        self.assertEqual(self.console('/learner/staff', {'id': uid, 'staff': True})[0], 200)
        with app.db() as c:
            self.assertEqual(c.execute('SELECT level FROM next_profiles WHERE user_id=?', (uid,)).fetchone()[0], 'B2')
            self.assertEqual(c.execute('SELECT daily_new FROM next_vocab_plans WHERE user_id=?', (uid,)).fetchone()[0], 25)
            self.assertIsNone(chat_service.remaining(c, uid))  # 员工账号: no daily AI limit
        self.assertEqual([r['action'] for r in self.log()],
                         ['account-signout', 'account-level', 'account-level', 'account-level', 'account-daily-new', 'account-daily-new', 'account-daily-new', 'account-staff-on'])
        self.assertEqual(self.console('/learner/signout', {'id': 9999})[0], 404)


class FunnelTests(Console):
    def test_how_far_accounts_got_and_who_came_back(self):
        now = time.time()
        for name in ('aa', 'bb', 'cc', 'dd'):
            self.register(name)
        a, b, c = self.uid('aa'), self.uid('bb'), self.uid('cc')
        packs = [p['id'] for _, p in nx._public_packs(app.db())][:3]
        for uid in (a, b, c):
            self.profile(uid)
        self.study(a, packs[0], nx.STEPS, now - 20 * DAY)
        self.study(a, packs[1], ['listen'], now - 17 * DAY)   # back in the first week
        self.study(a, packs[2], ['listen'], now - 10 * DAY)   # and in the second
        self.study(b, packs[0], nx.STEPS, now - 20 * DAY)     # finished one, never back
        self.study(c, packs[0], ['listen'], now - 2 * DAY)    # started only
        f = self.console('/funnel')[1]
        self.assertEqual([s['count'] for s in f['steps']], [4, 3, 3, 2, 1, 1])
        co = self.console('/cohorts')[1]
        week = [w for w in co['weeks'] if w['n'] == 2][0]
        self.assertEqual(week['cells'][0], {'back': 1, 'of': 2, 'pct': 50})
        self.register('staff')
        with app.db() as conn:
            conn.execute("UPDATE users SET admin=1 WHERE username='staff'"); conn.commit()
        self.assertEqual(self.console('/funnel')[1]['steps'][0]['count'], 4)  # staff accounts are not counted


class MaterialTests(Console):
    def test_a_material_off_the_lists_still_opens_and_comes_back(self):
        with app.db() as c:
            pid = next(p['id'] for _, p in nx._public_packs(c) if not p.get('series'))
        st, body = self.console('/material/hide', {'pack': pid, 'hidden': True, 'reason': '答案有误'})
        self.assertEqual(st, 200)
        with app.db() as c:
            self.assertNotIn(pid, {p['id'] for _, p in nx._public_packs(c)})
            self.assertIn(pid, {p['id'] for _, p in nx._public_packs(c, with_hidden=True)})
            self.assertTrue(nx._pack_row(c, None, pid))  # history and links still open it
        content = self.console('/content')[1]
        self.assertEqual(content['hidden'], 1)
        self.assertTrue(next(m for m in content['items'] if m['id'] == pid)['hidden'])
        self.assertEqual(self.console('/material/hide', {'pack': pid, 'hidden': False})[0], 200)
        with app.db() as c:
            self.assertIn(pid, {p['id'] for _, p in nx._public_packs(c)})
        self.assertEqual(self.console('/material/hide', {'pack': 'no-such', 'hidden': True})[0], 404)
        self.assertEqual([(r['action'], r['detail']) for r in self.log()], [('material-hide', '答案有误'), ('material-show', '')])

    def test_books_and_exam_practice(self):
        self.register('xiaolin')
        uid = self.uid('xiaolin')
        with app.db() as c:
            __import__('vocab_service').save_plan(c, uid, {'book': 'cet4', 'daily_new': 10, 'retention': 0.9})
            c.execute("INSERT INTO next_exam_results(user_id,exam,paper,score,total,parts,seconds,created) VALUES(?,?,?,?,?,?,?,?)",
                      (uid, 'cet4', 'p1', 12, 20, json.dumps([{'key': 'vocab', 'title': '词汇', 'right': 6, 'of': 10}, {'key': 'reading', 'title': '阅读', 'right': 6, 'of': 10}]), 900, time.time()))
            c.commit()
        d = self.console('/books')[1]
        cet4 = next(b for b in d['books']['items'] if b['id'] == 'cet4')
        self.assertEqual((cet4['learners'], cet4['avg_words']), (1, 0))
        ex = d['exams']['items'][0]
        self.assertEqual((ex['exam'], ex['avg_pct'], ex['parts']), ('cet4', 60, [{'title': '词汇', 'pct': 60}, {'title': '阅读', 'pct': 60}]))


class AiLimitTests(Console):
    def test_limits_set_in_the_console_win_at_once_and_go_back(self):
        self.assertEqual(chat_service.daily_limit('FLOW_AI_USER_DAILY_LIMIT'), 100)
        st, body = self.console('/settings/ai-limits', {'user_limit': 2, 'site_limit': 0})
        self.assertEqual((st, body['user_limit'], body['user_limit_source'], body['site_limit']), (200, 2, 'console', 0))
        self.register('xiaolin')
        uid = self.uid('xiaolin')
        with app.db() as c:
            self.assertIsNone(chat_service.reserve(c, uid)); self.assertIsNone(chat_service.reserve(c, uid))
            self.assertIn('2 次', chat_service.reserve(c, uid))
        self.assertEqual(self.console('/settings/ai-limits', {'user_limit': -1})[0], 400)
        self.assertEqual(self.console('/settings/ai-limits', {'user_limit': 'many'})[0], 400)
        body = self.console('/settings/ai-limits', {'user_limit': None, 'site_limit': ''})[1]
        self.assertEqual((body['user_limit'], body['user_limit_source'], body['site_limit']), (100, 'server', 2000))
        self.assertEqual([r['detail'] for r in self.log()], ['每账号 2 次 · 全站 不限', '每账号 100 次 · 全站 2000 次'])
        ai = self.console('/ai')[1]
        self.assertEqual(ai['limits']['user_limit'], 100)


class AnnouncementTests(Console):
    def test_learners_see_one_line_on_today_until_it_ends(self):
        home = lambda: self.call(self.site, '/api/next/home')[1]
        self.assertIsNone(home()['announce'])
        self.assertEqual(self.console('/announcements/create', {'text': 'hi'})[0], 400)  # too short
        self.assertEqual(self.console('/announcements/create', {'text': '新功能：考试练习', 'link': 'https://evil.example'})[0], 400)
        st, a = self.console('/announcements/create', {'text': '新功能：考试练习上线了', 'link': '#/exam', 'days': 3})
        self.assertEqual(st, 200)
        self.assertEqual(home()['announce'], {'id': a['id'], 'text': '新功能：考试练习上线了', 'link': '#/exam'})
        st, b = self.console('/announcements/create', {'text': '今晚 23:00 升级十分钟'})
        self.assertEqual(home()['announce']['id'], b['id'])  # one at a time: the new one replaces it
        self.assertEqual(self.console('/announcements/end', {'id': b['id']})[0], 200)
        self.assertIsNone(home()['announce'])
        self.assertEqual(self.console('/announcements/end', {'id': b['id']})[0], 409)
        listing = self.console('/announcements', email=INTERN)[1]
        self.assertEqual((listing['current'], len(listing['items'])), (None, 2))
        self.assertNotIn(BOSS, json.dumps(listing))  # 只看数据 does not see who posted
        self.assertIn(BOSS, json.dumps(self.console('/announcements')[1]))
        self.assertEqual([r['action'] for r in self.log()], ['announce', 'announce', 'announce-end'])
        js = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8')
        self.assertIn('function announceHTML', js)
        self.assertIn("load('flow-announce-seen') === a.id", js)


class TaskTests(Console):
    def test_example_writing_starts_reports_and_stops_from_the_console(self):
        class Proc:
            pid = 424242
            alive = True
            def poll(self):
                return None if self.alive else 0
            def terminate(self):
                self.alive = False
        proc = Proc()
        with patch.object(console_ops.subprocess, 'Popen', return_value=proc) as popen:
            self.assertEqual(self.console('/tasks/examples/start', {'books': ['nope']})[0], 400)
            st, body = self.console('/tasks/examples/start', {'books': ['gre'], 'max_calls': 20})
            self.assertEqual((st, body['state']), (202, 'running'))
            cmd = popen.call_args[0][0]
            self.assertEqual(cmd[1:], [str(Path(console_ops.HERE) / 'fill_examples.py'), '--env-file', os.devnull, '--status',
                                       str(Path(self.tmp.name) / 'fill-examples-status.json'), '--books', 'gre', '--max-calls', '20', '--offpeak'])
            self.assertEqual(popen.call_args[1]['env']['FLOW_DATA_DIR'], self.tmp.name)
            self.assertEqual(self.console('/tasks/examples/start', {})[0], 409)  # one run at a time
            self.assertEqual(self.console('/tasks', email=INTERN)[1]['examples']['state'], 'running')
            self.assertEqual(self.console('/tasks/examples/stop', {})[0], 200)
            self.assertFalse(proc.alive)
            self.assertEqual(self.console('/tasks')[1]['examples']['state'], 'stopped')
        self.assertEqual([(r['action'], r['detail']) for r in self.log()], [('examples-start', '词书 gre，最多 20 次请求'), ('examples-stop', '')])

    def test_the_script_writes_its_progress_for_the_console(self):
        status = Path(self.tmp.name) / 'st.json'
        with patch.dict(os.environ, {'FLOW_DATA_DIR': self.tmp.name}):
            code = fill_examples.main(['--env-file', os.devnull, '--books', 'gre', '--dry-run', '--status', str(status)])
        st = json.loads(status.read_text())
        self.assertEqual((code, st['state'], st['books']), (1, 'left', ['gre']))
        self.assertGreater(st['total'], 20)

    def test_todays_news_gets_another_round_after_it_failed(self):
        with app.db() as c:
            day = __import__('daily_service').today()
            c.execute("INSERT INTO daily_runs(day,status,attempts,updated,error) VALUES(?,'failed',2,?,'x')", (day, time.time())); c.commit()
        with patch('daily_service.run') as run:
            self.assertEqual(self.console('/daily/run', {'again': True})[0], 202)
            time.sleep(0.2)
        self.assertTrue(run.called)
        with app.db() as c:
            self.assertEqual(c.execute('SELECT attempts FROM daily_runs WHERE day=?', (day,)).fetchone()[0], 0)
        self.assertEqual(self.log()[-1]['action'], 'daily-again')


class ExportTests(Console):
    def test_csv_files_open_in_excel_and_are_logged(self):
        self.register('xiaolin')
        for path, head in (('/export/learners.csv', '编号,用户名'), ('/export/materials.csv', '编号,标题'), ('/export/ai.csv', '日期（北京时间）')):
            st, body = self.console(path)
            self.assertEqual(st, 200)
            text = body.decode('utf-8')
            self.assertTrue(text.startswith('﻿' + head), path)
        self.assertEqual([(r['action'], r['detail']) for r in self.log()], [('export', '学员'), ('export', '材料'), ('export', 'AI 用量')])
        self.assertIn('xiaolin', self.console('/export/learners.csv')[1].decode('utf-8'))


class PageTests(unittest.TestCase):
    def test_the_console_has_groups_tabs_and_views(self):
        root = Path(app.ROOT).parent / 'xmc-admin'
        html = (root / 'index.html').read_text(encoding='utf-8')
        js = (root / 'admin.js').read_text(encoding='utf-8')
        for g in ('data', 'people', 'content', 'ops'):
            self.assertIn(f'data-group="{g}"', html)
        for tab, fn in (('learners', 'learnersView'), ('funnel', 'funnelView'), ('content', 'contentView'), ('books', 'booksView'),
                        ('announce', 'announceView'), ('ai', 'aiView'), ('tasks', 'tasksView')):
            self.assertIn(f'data-tab="{tab}"', html)
            self.assertIn(f'function {fn}', js)
        self.assertIn('data-tab="learners" data-admin', html)
        v = html.split('admin.js?v=')[1].split('"')[0]
        self.assertEqual(v, html.split('admin.css?v=')[1].split('"')[0])
        self.assertNotIn('data-tab="accounts"', html)  # 账号 is part of 学员 now; #accounts still opens it
        self.assertIn("if (tab === 'accounts') tab = 'learners'", js)


if __name__ == '__main__':
    unittest.main()
