"""班级试用 (class_service.py): an operator makes a class with a teacher and an invite code; a learner joins of their own
accord and leaves whenever they like; the teacher sees numbers for the whole class only — never a learner's name, id,
work or record — and nothing at all while the class has fewer than 5 members. 试用人次 counts the different learners
who studied at least one step while members. Every console change is 管理员 only and in the operator log; 注销账号
takes the class records with it and 导出 carries them."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, flow_admin, class_service as cs  # noqa: E402

DAY = 86400
BOSS, INTERN = 'boss@example.com', 'intern@example.com'
PW = 'correct horse 1'


class Classes(unittest.TestCase):
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
        self.people = {}
        with app.db() as c:
            self.nodes = [(r[0], r[1]) for r in c.execute('SELECT id, title FROM subskills ORDER BY rowid LIMIT 8')]

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
                return r.status, (body if raw else json.loads(body or b'{}'))
        except urllib.error.HTTPError as e:
            body = e.read()
            return e.code, (body if raw else json.loads(body or b'{}'))

    def console(self, path, data=None, email=BOSS, marked=True):
        h = {'Cf-Access-Authenticated-User-Email': email}
        if data is not None and marked:
            h['X-Requested-With'] = 'xmc'
        return self.call(self.admin, '/flow/api' + path, data, h, raw=path.endswith('.csv'))

    def person(self, name):
        """Sign up; returns (cookie, csrf, id)."""
        req = urllib.request.Request(f'http://127.0.0.1:{self.site.server_address[1]}/api/register', data=json.dumps({'username': name, 'password': PW}).encode(),
                                     headers={'Content-Type': 'application/json', 'X-Real-IP': f'10.9.{len(self.people) // 200}.{len(self.people) % 200 + 1}'})
        with urllib.request.urlopen(req, timeout=10) as r:  # each its own address: sign-ups share a ceiling per address
            cookie = r.headers['Set-Cookie'].split(';')[0]
        s = self.call(self.site, '/api/session', headers={'Cookie': cookie})[1]['user']
        self.people[name] = (cookie, s['csrf'], s['id'])
        return self.people[name]

    def me(self, name, path, data=None):
        cookie, csrf, _ = self.people[name]
        return self.call(self.site, path, data, {'Cookie': cookie, 'X-CSRF-Token': csrf})

    def make(self, name='高一（3）班', teacher='wanglaoshi'):
        st, body = self.console('/class/create', {'name': name, 'teacher': teacher})
        self.assertEqual(st, 200, body)
        return body['id'], body['code']

    def step(self, uid, when, pack='p1', step='listen'):
        with app.db() as c:
            c.execute('INSERT OR REPLACE INTO next_progress VALUES(?,?,?,?)', (uid, pack, step, when))
            c.commit()

    def wrong(self, uid, node, when, n=0):
        with app.db() as c:
            c.execute("INSERT INTO learning_events(user_id,node,source,kind,item,correct,evaluator,created) VALUES(?,?,?,?,?,0,'rule',?)",
                      (uid, node, f'test:{uid}:{node}:{n}:{when}', 'choice', 'q', when))
            c.commit()

    def log(self):
        with app.db() as c:
            return [dict(r) for r in c.execute('SELECT email, role, action, target, detail FROM flow_admin_log ORDER BY id')]

    def joined_class(self, size, code, back=25 * DAY):
        """size learners join; as if they joined `back` seconds ago, so what they study after that counts."""
        names = [f'stu{i:02d}' for i in range(size)]
        for n in names:
            self.person(n)
            st, body = self.me(n, '/api/next/class/join', {'code': code})
            self.assertEqual(st, 200, body)
        with app.db() as c:
            c.execute('UPDATE class_members SET joined_at=joined_at-?', (back,))
            c.commit()
        return names


class ConsoleTests(Classes):
    def test_only_a_manager_makes_or_changes_a_class_and_every_change_is_logged(self):
        self.person('wanglaoshi'); self.person('lilaoshi')
        writes = [('/class/create', {'name': '英语社', 'teacher': 'wanglaoshi'}), ('/class/rename', {'id': 1, 'name': '新名字'}),
                  ('/class/teacher', {'id': 1, 'teacher': 'lilaoshi'}), ('/class/code', {'id': 1}), ('/class/active', {'id': 1, 'active': False})]
        for path, data in writes:
            self.assertEqual(self.console(path, data, email=INTERN)[0], 403, path)
            self.assertEqual(self.console(path, data, marked=False)[0], 403, path)
        for path in ('/classes', '/class?id=1', '/export/classes.csv'):
            self.assertEqual(self.console(path, email=INTERN)[0], 403, path)
        self.assertEqual(self.log(), [])

        st, body = self.console('/class/create', {'name': '英语社', 'teacher': 'nobody'})
        self.assertEqual((st, body['field']), (404, 'teacher'))
        self.assertEqual(self.console('/class/create', {'name': 'x', 'teacher': 'wanglaoshi'})[0], 400)
        cid, code = self.make('英语社')
        self.assertRegex(code, '^[%s]{6}$' % cs.CODE_CHARS)
        self.assertEqual(self.console('/class/rename', {'id': cid, 'name': '英语社（周三）'})[0], 200)
        self.assertEqual(self.console('/class/teacher', {'id': cid, 'teacher': 'lilaoshi'})[0], 200)
        st, body = self.console('/class/code', {'id': cid})
        self.assertNotEqual(body['code'], code)
        self.assertEqual(self.console('/class/active', {'id': cid, 'active': False})[0], 200)
        self.assertEqual(self.console('/class/active', {'id': cid, 'active': True})[0], 200)
        self.assertEqual(self.console('/export/classes.csv')[0], 200)
        acts = [(r['action'], r['email']) for r in self.log()]
        self.assertEqual(acts, [(a, BOSS) for a in ('class-create', 'class-rename', 'class-teacher', 'class-code', 'class-stop', 'class-start', 'export')])
        lili = self.people['lilaoshi'][2]
        self.assertTrue(self.log()[2]['target'].endswith(f' #{lili}'))  # shows in the new teacher's own drawer too
        detail = self.console(f'/class?id={cid}')[1]
        self.assertEqual(detail['teacher']['username'], 'lilaoshi')
        self.assertEqual(len(detail['log']), 6)
        self.assertEqual(len(detail['weeks']), 8)
        self.assertIn('试用人数', detail['rule_people'])
        self.assertIn('试用人次', detail['rule_days'])

    def test_viewers_see_only_how_many(self):
        self.person('wanglaoshi')
        cid, code = self.make()
        self.joined_class(2, code)
        st, ov = self.console('/overview', email=INTERN)
        self.assertEqual(st, 200)
        self.assertEqual(ov['classes'], {'count': 1, 'members': 2, 'trial_people': 0, 'trial_days': 0})
        self.assertNotIn(code, json.dumps(ov))
        self.assertNotIn('wanglaoshi', json.dumps(ov))

    def test_the_old_code_stops_working_and_a_stopped_class_takes_no_one(self):
        self.person('wanglaoshi'); self.person('xiaolin'); self.person('xiaoyu')
        cid, code = self.make()
        new = self.console('/class/code', {'id': cid})[1]['code']
        self.assertEqual(self.me('xiaolin', '/api/next/class/join', {'code': code})[0], 404)
        self.assertEqual(self.me('xiaolin', '/api/next/class/join', {'code': new.lower()})[0], 200)  # any case, as typed
        self.console('/class/active', {'id': cid, 'active': False})
        self.assertEqual(self.me('xiaoyu', '/api/next/class/join', {'code': new})[0], 409)
        mine = self.me('xiaolin', '/api/next/class')[1]
        self.assertFalse(mine['member']['active'])  # still in it, and can leave
        self.assertEqual(self.me('xiaolin', '/api/next/class/leave', {})[0], 200)


class LearnerTests(Classes):
    def test_find_join_leave_one_class_at_a_time(self):
        self.person('wanglaoshi'); self.person('lilaoshi'); self.person('xiaolin')
        _, code = self.make()
        _, other = self.make('英语社', 'lilaoshi')
        self.assertEqual(self.call(self.site, '/api/next/class')[0], 401)
        st, found = self.me('xiaolin', '/api/next/class/find', {'code': f' {code[:3]}-{code[3:]} '})
        self.assertEqual((st, found['name'], found['teacher']), (200, '高一（3）班', 'wanglaoshi'))
        self.assertIsNone(self.me('xiaolin', '/api/next/class')[1]['member'])  # finding is not joining
        st, mine = self.me('xiaolin', '/api/next/class/join', {'code': code})
        self.assertEqual((st, mine['member']['name']), (200, '高一（3）班'))
        st, body = self.me('xiaolin', '/api/next/class/join', {'code': other})
        self.assertEqual(st, 409)
        self.assertIn('高一（3）班', body['error'])
        st, mine = self.me('xiaolin', '/api/next/class/leave', {})
        self.assertIsNone(mine['member'])
        self.assertEqual(self.me('xiaolin', '/api/next/class/leave', {})[0], 409)
        self.assertEqual(self.me('xiaolin', '/api/next/class/join', {'code': other})[0], 200)
        with app.db() as c:
            rows = c.execute('SELECT class_id, left_at IS NULL FROM class_members ORDER BY id').fetchall()
        self.assertEqual([tuple(r) for r in rows], [(1, 0), (2, 1)])  # the first stay: when joined and left, nothing else

    def test_a_teacher_does_not_join_their_own_class(self):
        self.person('wanglaoshi')
        _, code = self.make()
        st, body = self.me('wanglaoshi', '/api/next/class/join', {'code': code})
        self.assertEqual(st, 409)
        self.assertEqual(self.me('wanglaoshi', '/api/next/class')[1]['teaching'][0]['name'], '高一（3）班')

    def test_guessing_codes_is_paused(self):
        self.person('xiaolin')
        for i in range(cs.TRIES):
            self.assertEqual(self.me('xiaolin', '/api/next/class/find', {'code': f'ZZZZZ{i}'})[0], 404)
        self.assertEqual(self.me('xiaolin', '/api/next/class/find', {'code': 'ZZZZZZ'})[0], 429)

    def test_without_the_csrf_token_nothing_changes(self):
        self.person('wanglaoshi'); self.person('xiaolin')
        _, code = self.make()
        cookie = self.people['xiaolin'][0]
        self.assertEqual(self.call(self.site, '/api/next/class/join', {'code': code}, {'Cookie': cookie})[0], 403)
        self.assertIsNone(self.me('xiaolin', '/api/next/class')[1]['member'])


class TeacherTests(Classes):
    def test_under_five_members_the_teacher_gets_no_numbers(self):
        self.person('wanglaoshi')
        cid, code = self.make()
        names = self.joined_class(4, code)
        now = time.time()
        for n in names:
            self.step(self.people[n][2], now - 3600)
            self.wrong(self.people[n][2], self.nodes[0][0], now - 3600)
        st, body = self.me('wanglaoshi', f'/api/next/class/teach?id={cid}')
        self.assertEqual(st, 200)
        self.assertFalse(body['ready'])
        self.assertEqual(set(body), {'id', 'name', 'code', 'active', 'min', 'rule', 'ready'})  # no count of any kind
        self.person('stu99')
        self.me('stu99', '/api/next/class/join', {'code': code})
        self.assertTrue(self.me('wanglaoshi', f'/api/next/class/teach?id={cid}')[1]['ready'])
        self.me('stu99', '/api/next/class/leave', {})  # back to 4: nothing again
        self.assertFalse(self.me('wanglaoshi', f'/api/next/class/teach?id={cid}')[1]['ready'])

    def test_the_teacher_sees_numbers_for_the_class_never_a_learner(self):
        self.person('wanglaoshi'); self.person('outsider')
        cid, code = self.make()
        names = self.joined_class(6, code)
        ids = [self.people[n][2] for n in names]
        now = time.time()
        for u in ids[:4]:
            self.step(u, now - 2 * 3600)  # 4 studied in the last 7 days
        self.step(ids[4], now - 10 * DAY)  # one only 10 days ago: in the week before
        a, b, d = self.nodes[0][0], self.nodes[1][0], self.nodes[2][0]
        for u in ids[:3]:
            self.wrong(u, a, now - 3600)
        for u in ids[:2]:
            self.wrong(u, b, now - 3600)
            self.wrong(u, b, now - 3500, 1)
        self.wrong(ids[0], d, now - 9 * DAY)  # older than 7 days: not in the list
        self.wrong(self.people['outsider'][2], d, now - 3600)  # not a member
        self.wrong(self.people['outsider'][2], d, now - 3601, 1)
        st, body = self.me('wanglaoshi', f'/api/next/class/teach?id={cid}')
        self.assertEqual(st, 200)
        self.assertTrue(body['ready'])
        self.assertEqual((body['members'], body['active_7d']), (6, 4))
        self.assertEqual([w['studied'] for w in body['weeks']], [0, 0, 2, 4])  # stu04's step and stu00's wrong answer 9 days ago
        self.assertEqual([(p['node'], p['learners']) for p in body['points']], [(a, 3), (b, 2)])
        self.assertEqual(set(body), {'id', 'name', 'code', 'active', 'min', 'rule', 'ready', 'members', 'active_7d', 'weeks', 'points'})
        for p in body['points']:
            self.assertEqual(set(p), {'node', 'title', 'learners'})
        text = json.dumps(body, ensure_ascii=False)
        for n in names:
            self.assertNotIn(n, text)
        self.assertNotIn('user_id', text)
        # someone else's account (even a member) gets nothing; nor does a teacher for another class
        self.assertEqual(self.me(names[0], f'/api/next/class/teach?id={cid}')[0], 404)
        self.assertEqual(self.me('outsider', f'/api/next/class/teach?id={cid}')[0], 404)

    def test_a_member_who_leaves_is_out_of_the_summary_at_once(self):
        self.person('wanglaoshi')
        cid, code = self.make()
        names = self.joined_class(6, code)
        now = time.time()
        for n in names:
            self.step(self.people[n][2], now - 3600)
        self.wrong(self.people[names[0]][2], self.nodes[0][0], now - 3600)
        self.me(names[0], '/api/next/class/leave', {})
        body = self.me('wanglaoshi', f'/api/next/class/teach?id={cid}')[1]
        self.assertEqual((body['members'], body['active_7d'], body['points']), (5, 5, []))

    def test_studying_before_joining_is_not_counted(self):
        self.person('wanglaoshi')
        cid, code = self.make()
        names = self.joined_class(5, code, back=0)
        u = self.people[names[0]][2]
        with app.db() as c:
            joined = c.execute('SELECT joined_at FROM class_members WHERE user_id=?', (u,)).fetchone()[0]
        self.step(u, joined - 60)
        self.wrong(u, self.nodes[0][0], joined - 60)
        body = self.me('wanglaoshi', f'/api/next/class/teach?id={cid}')[1]
        self.assertEqual((body['active_7d'], body['points']), (0, []))
        self.assertEqual((self.console('/classes')[1]['trial_people'], self.console('/classes')[1]['trial_days']), (0, 0))


class TrialTests(Classes):
    def test_trial_counts_different_learners_who_studied_as_members(self):
        self.person('wanglaoshi'); self.person('lilaoshi'); self.person('staffer')
        c1, code1 = self.make()
        c2, code2 = self.make('英语社', 'lilaoshi')
        names = self.joined_class(3, code1, back=60)
        ids = [self.people[n][2] for n in names]
        now = time.time() - 1
        self.step(ids[0], now)
        self.step(ids[1], now)  # ids[2] joined but never studied
        with app.db() as c:
            c.execute('UPDATE users SET admin=1 WHERE username=?', ('staffer',))
            c.commit()
        self.me('staffer', '/api/next/class/join', {'code': code1})
        self.step(self.people['staffer'][2], time.time() + 1)
        # ids[0] leaves and joins 英语社, studies there too: once in each class, once in the total
        self.me(names[0], '/api/next/class/leave', {})
        self.me(names[0], '/api/next/class/join', {'code': code2})
        self.step(ids[0], time.time() + 5, 'p2')
        got = self.console('/classes')[1]
        per = {x['name']: x for x in got['items']}
        self.assertEqual((per['高一（3）班']['trial_people'], per['英语社']['trial_people'], got['trial_people']), (2, 1, 2))
        # 人次: stu00 studied today in both classes — one day in each class, but once in the total
        self.assertEqual((per['高一（3）班']['trial_days'], per['英语社']['trial_days'], got['trial_days']), (2, 1, 2))
        self.assertEqual((per['高一（3）班']['members'], per['英语社']['members']), (2, 1))  # staff not counted
        csv = self.console('/export/classes.csv')[1].decode('utf-8-sig')
        self.assertIn('试用人数', csv.splitlines()[0])
        self.assertIn('试用人次', csv.splitlines()[1])
        self.assertIn('合计（同一人、同一人同一天只算一次）,,,3,,2,2,', csv)
        detail = self.console(f'/class?id={c1}')[1]
        self.assertEqual((detail['joined'], detail['left'], detail['trial_people'], detail['trial_days'], detail['weeks'][-1]['new_people']), (4, 1, 2, 2, 2))

    def test_trial_days_count_a_learners_study_day_once(self):
        """试用人次: days studied as a member (progress_service.study_days), a learner's day once however much they did."""
        import progress_service as ps
        self.person('wanglaoshi')
        cid, code = self.make()
        names = self.joined_class(2, code, back=20 * DAY)
        a, b = (self.people[n][2] for n in names)
        now = time.time()
        for when, pack in ((now - 3600, 'p1'), (now - 3500, 'p2'), (now - 2 * DAY, 'p3'), (now - 12 * DAY, 'p4')):
            self.step(a, when, pack)  # two steps today: one day
        self.wrong(a, self.nodes[0][0], now - 3400)  # a question the same day: still one day
        self.step(b, now - 25 * DAY)  # before joining: not a trial day
        self.step(b, now - 5 * DAY)
        with app.db() as c:
            joined = c.execute('SELECT joined_at FROM class_members WHERE user_id=?', (a,)).fetchone()[0]
            self.assertEqual(len(ps.study_days(c, a, joined)), 3)
        got = self.console('/classes')[1]
        self.assertEqual((got['trial_people'], got['trial_days']), (2, 4))
        detail = self.console(f'/class?id={cid}')[1]
        self.assertEqual(sum(w['days'] for w in detail['weeks']), 4)
        self.assertEqual([w['days'] for w in detail['weeks']][-2:], [1, 3])  # 12 days ago; then today, 2 and 5 days ago
        self.assertIn('同一学员同一天算 1 次', detail['rule_days'])


class AccountTests(Classes):
    def test_deleting_an_account_takes_its_class_records_and_export_carries_them(self):
        self.person('wanglaoshi'); self.person('xiaolin')
        cid, code = self.make()
        self.me('xiaolin', '/api/next/class/join', {'code': code})
        self.me('xiaolin', '/api/next/class/find', {'code': 'WRONG1'})  # a pause key to be removed too
        cookie = self.people['xiaolin'][0]
        req = urllib.request.Request(f'http://127.0.0.1:{self.site.server_address[1]}/api/next/export/records.json', headers={'Cookie': cookie})
        with urllib.request.urlopen(req, timeout=10) as r:
            rec = json.loads(r.read())
        self.assertEqual(rec['班级'][0]['班级'], '高一（3）班')
        self.assertEqual(rec['班级'][0]['退出'], '还在班里')
        self.assertIn('class_members', rec['tables'])
        teacher = json.loads(urllib.request.urlopen(urllib.request.Request(
            f'http://127.0.0.1:{self.site.server_address[1]}/api/next/export/records.json', headers={'Cookie': self.people['wanglaoshi'][0]}), timeout=10).read())
        self.assertEqual(teacher['我当老师的班级'], ['高一（3）班'])
        uid = self.people['xiaolin'][2]
        self.assertEqual(self.me('xiaolin', '/api/account/delete', {'password': PW})[0], 200)
        with app.db() as c:
            self.assertEqual(c.execute('SELECT COUNT(*) FROM class_members WHERE user_id=?', (uid,)).fetchone()[0], 0)
            self.assertIsNone(c.execute('SELECT 1 FROM login_failures WHERE key=?', ('class:%d' % uid,)).fetchone())
        # the teacher's account goes: the class stays, with no teacher, for the learners in it
        self.assertEqual(self.me('wanglaoshi', '/api/account/delete', {'password': PW})[0], 200)
        with app.db() as c:
            k = c.execute('SELECT * FROM classes WHERE id=?', (cid,)).fetchone()
        self.assertIsNotNone(k)
        self.assertIsNone(k['teacher'])


if __name__ == '__main__':
    unittest.main()
