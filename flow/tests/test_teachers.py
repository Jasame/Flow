"""老师模式 (teacher_service.py): a 老师账号 is made only through a 老师注册链接 a 管理员 makes in the console (or on the
server); a link makes one account, once, before it expires, and only its hash is kept; an ordinary sign-up is always
a 学生账号. A teacher account makes and renames its own classes, never joins one, and sees the whole class's numbers
only. Wrong tokens from one address are paused."""
import contextlib, io, json, os, re, sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, teacher_service as ts  # noqa: E402
from test_classes import Classes, BOSS, INTERN, PW  # noqa: E402


class Teachers(Classes):
    def link(self, days=7, note='实验中学 王老师'):
        st, body = self.console('/teacher-link/create', {'days': days, 'note': note})
        self.assertEqual(st, 200, body)
        token = body['link'].rsplit('/#/teacher/', 1)[1]
        return body, token

    def check(self, token, ip='10.20.0.1'):
        return self.call(self.site, '/api/teacher/check', {'token': token}, {'X-Real-IP': ip})

    def sign_up(self, name, token, ip='10.21.0.1', **more):
        st, body = self.call(self.site, '/api/register', {'username': name, 'password': PW, 'teacher': token, **more}, {'X-Real-IP': ip})
        return st, body

    def teacher(self, name='wanglaoshi'):
        """A teacher account made with a fresh link; returns (cookie, csrf, id) like person()."""
        _, token = self.link()
        import urllib.request
        req = urllib.request.Request(f'http://127.0.0.1:{self.site.server_address[1]}/api/register',
                                     data=json.dumps({'username': name, 'password': PW, 'teacher': token}).encode(),
                                     headers={'Content-Type': 'application/json', 'X-Real-IP': '10.22.0.%d' % (len(self.people) + 1)})
        with urllib.request.urlopen(req, timeout=10) as r:
            cookie = r.headers['Set-Cookie'].split(';')[0]
        s = self.call(self.site, '/api/session', headers={'Cookie': cookie})[1]['user']
        self.people[name] = (cookie, s['csrf'], s['id'])
        return self.people[name]

    def session(self, name):
        return self.call(self.site, '/api/session', headers={'Cookie': self.people[name][0]})[1]['user']


class LinkTests(Teachers):
    def test_a_link_makes_one_teacher_account_once_and_keeps_only_its_hash(self):
        body, token = self.link()
        self.assertGreaterEqual(len(token), 40)
        self.assertTrue(body['link'].startswith(ts.origin() + '/#/teacher/'))
        self.assertEqual(body['days'], ts.LINK_DAYS)
        with app.db() as c:
            row = dict(c.execute('SELECT * FROM teacher_links').fetchone())
        self.assertNotIn(token, json.dumps(row, ensure_ascii=False))  # only the hash is kept
        self.assertEqual(self.log()[-1]['action'], 'teacher-link')
        st, ok = self.check(token)
        self.assertEqual(st, 200, ok)
        st, got = self.sign_up('wanglaoshi', token)
        self.assertEqual(st, 200, got)
        with app.db() as c:
            u = c.execute("SELECT role, age_band FROM users WHERE username='wanglaoshi'").fetchone()
        self.assertEqual((u['role'], u['age_band']), ('teacher', '18+'))  # a teacher is not asked the 年龄段
        # used: neither the check nor a second sign-up gets through, and no second account is made
        self.assertEqual(self.check(token)[0], 410)
        st, again = self.sign_up('lilaoshi', token, ip='10.21.0.2')
        self.assertEqual(st, 410, again)
        with app.db() as c:
            self.assertIsNone(c.execute("SELECT 1 FROM users WHERE username='lilaoshi'").fetchone())
        items = self.console('/teacher-links')[1]
        self.assertEqual(items['items'][0]['status'], 'used')
        self.assertEqual(items['items'][0]['teacher']['username'], 'wanglaoshi')
        self.assertEqual(items['teachers'], 1)

    def test_an_ordinary_sign_up_is_always_a_learner(self):
        self.person('xiaolin')
        self.assertFalse(self.session('xiaolin')['teacher'])
        with app.db() as c:
            self.assertIsNone(c.execute("SELECT role FROM users WHERE username='xiaolin'").fetchone()['role'])
        st, body = self.sign_up('fake', 'x' * 43)  # a made-up token signs nobody up
        self.assertEqual(st, 404, body)

    def test_the_sign_up_by_link_works_with_mail_on(self):
        """Both sites have mail on: the teacher verifies an email with a code like anyone, and needs no 年龄段."""
        outbox = Path(self.tmp.name) / 'outbox'
        with patch.dict(os.environ, {'FLOW_MAIL_OUTBOX': str(outbox)}):
            _, token = self.link()
            st, body = self.call(self.site, '/api/auth/code', {'email': 'wang@example.com', 'purpose': 'register'}, {'X-Real-IP': '10.23.0.1'})
            self.assertEqual(st, 200, body)
            mail = sorted(outbox.glob('*.txt'))[-1].read_text(encoding='utf-8')
            code = re.search(r'验证码：(\d{6})', mail).group(1)
            st, got = self.sign_up('wanglaoshi', token, email='wang@example.com', code=code)
            self.assertEqual(st, 200, got)
        with app.db() as c:
            u = c.execute("SELECT role, email FROM users WHERE username='wanglaoshi'").fetchone()
        self.assertEqual((u['role'], u['email']), ('teacher', 'wang@example.com'))

    def test_revoked_and_expired_links_say_so_and_a_used_one_cannot_be_revoked(self):
        body, token = self.link()
        st, r = self.console('/teacher-link/revoke', {'id': body['id']})
        self.assertEqual(st, 200, r)
        st, why = self.check(token)
        self.assertEqual(st, 410)
        self.assertIn('作废', why['error'])
        self.assertEqual(self.log()[-1]['action'], 'teacher-link-revoke')
        body2, token2 = self.link()
        with app.db() as c:
            c.execute('UPDATE teacher_links SET expires=created-1 WHERE id=?', (body2['id'],)); c.commit()
        st, why = self.check(token2)
        self.assertEqual(st, 410)
        self.assertIn('过期', why['error'])
        self.assertEqual(self.sign_up('wanglaoshi', token2)[0], 410)
        body3, token3 = self.link()
        self.assertEqual(self.sign_up('wanglaoshi', token3)[0], 200)
        self.assertEqual(self.console('/teacher-link/revoke', {'id': body3['id']})[0], 409)
        labels = {x['id']: x['status'] for x in self.console('/teacher-links')[1]['items']}
        self.assertEqual(labels, {body['id']: 'revoked', body2['id']: 'expired', body3['id']: 'used'})

    def test_the_validity_is_one_to_max_days(self):
        for bad in (0, ts.MAX_DAYS + 1, 'x'):
            self.assertEqual(self.console('/teacher-link/create', {'days': bad})[0], 400, bad)
        body, _ = self.link(days=ts.MAX_DAYS)
        self.assertEqual(body['days'], ts.MAX_DAYS)

    def test_only_an_administrator_makes_and_sees_links(self):
        self.assertEqual(self.console('/teacher-links', email=INTERN)[0], 403)
        self.assertEqual(self.console('/teacher-link/create', {'days': 7}, email=INTERN)[0], 403)
        self.assertEqual(self.console('/teacher-link/create', {'days': 7}, marked=False)[0], 403)

    def test_wrong_tokens_from_one_address_are_paused(self):
        _, token = self.link()
        for i in range(ts.TRIES):
            self.assertEqual(self.check('y' * 40 + str(i), ip='10.30.0.1')[0], 404)
        st, body = self.check(token, ip='10.30.0.1')  # paused: even a good one waits
        self.assertEqual(st, 429, body)
        self.assertEqual(self.check(token, ip='10.30.0.2')[0], 200)  # another address is not

    def test_a_link_can_be_made_on_the_server(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(ts.main(['link', '--days', '3', '--note', '内测']), 0)
        token = re.search(r'/#/teacher/(\S+)', out.getvalue()).group(1)
        self.assertEqual(self.check(token)[0], 200)
        self.assertEqual(self.console('/teacher-links')[1]['items'][0]['note'], '内测')

    def test_deleting_the_teacher_account_keeps_the_link_used(self):
        self.teacher()
        st, body = self.me('wanglaoshi', '/api/account/delete', {'password': PW})
        self.assertEqual(st, 200, body)
        x = self.console('/teacher-links')[1]['items'][0]
        self.assertEqual((x['status'], x['teacher']), ('used', None))


class TeacherClassTests(Teachers):
    def test_a_teacher_makes_and_renames_classes_and_sees_numbers_only(self):
        self.teacher()
        self.assertTrue(self.session('wanglaoshi')['teacher'])
        st, got = self.me('wanglaoshi', '/api/next/class/create', {'name': '高二（1）班'})
        self.assertEqual(st, 200, got)
        cid = got['created']
        k = next(t for t in got['teaching'] if t['id'] == cid)
        self.assertRegex(k['code'], r'^[A-Z2-9]{6}$')
        self.assertFalse(k['ready'])
        self.assertNotIn('members', k)  # never how many fewer than 5
        with app.db() as c:
            self.assertEqual(c.execute('SELECT by FROM classes WHERE id=?', (cid,)).fetchone()[0], '老师 wanglaoshi')
        st, got = self.me('wanglaoshi', '/api/next/class/rename', {'id': cid, 'name': '高二（2）班'})
        self.assertEqual(st, 200, got)
        self.assertEqual(next(t for t in got['teaching'] if t['id'] == cid)['name'], '高二（2）班')
        self.assertEqual(self.me('wanglaoshi', '/api/next/class/create', {'name': 'x'})[0], 400)
        self.joined_class(5, k['code'])
        k = next(t for t in self.me('wanglaoshi', '/api/next/class')[1]['teaching'] if t['id'] == cid)
        self.assertTrue(k['ready'])
        st, summary = self.me('wanglaoshi', f'/api/next/class/teach?id={cid}')
        self.assertEqual((st, summary['ready'], summary['members']), (200, True, 5))
        text = json.dumps(summary, ensure_ascii=False)
        for n in ('stu00', 'stu04'):
            self.assertNotIn(n, text)

    def test_only_teacher_accounts_make_classes_and_only_their_own_are_renamed(self):
        self.teacher()
        self.person('xiaolin')
        self.assertEqual(self.me('xiaolin', '/api/next/class/create', {'name': '高一（3）班'})[0], 403)
        cid, _ = self.make(teacher='xiaolin')  # an operator may still make a class for any account
        self.assertEqual(self.me('wanglaoshi', '/api/next/class/rename', {'id': cid, 'name': '别人的班'})[0], 404)

    def test_a_teacher_account_never_joins_a_class(self):
        self.teacher()
        self.person('lilaoshi')
        _, code = self.make(teacher='lilaoshi')
        st, body = self.me('wanglaoshi', '/api/next/class/join', {'code': code})
        self.assertEqual(st, 409, body)
        self.assertIn('老师账号不能加入班级', body['error'])

    def test_a_teacher_has_at_most_so_many_classes_in_use(self):
        self.teacher()
        for i in range(ts.CLASSES_MAX):
            self.assertEqual(self.me('wanglaoshi', '/api/next/class/create', {'name': f'第 {i + 1} 班'})[0], 200)
        st, body = self.me('wanglaoshi', '/api/next/class/create', {'name': '再一个班'})
        self.assertEqual(st, 409, body)

    def test_the_console_marks_teacher_accounts(self):
        _, _, uid = self.teacher()
        self.person('xiaolin')
        rows = {r['username']: r for r in self.console('/learners')[1]['items']}
        self.assertTrue(rows['wanglaoshi']['teacher'])
        self.assertFalse(rows['xiaolin']['teacher'])
        self.assertTrue(self.console(f'/learner?id={uid}')[1]['account']['teacher'])



class OperatorTests(Teachers):
    """The user's rules (2026-11-26): a 管理员 may make an existing account a teacher and back (not one in a class), in the
    operator log; teacher accounts are out of the learner numbers, like 员工账号."""
    def test_an_operator_makes_an_account_a_teacher_and_back(self):
        _, _, uid = self.person('xiaolin')
        st, body = self.console('/learner/teacher', {'id': uid, 'teacher': True})
        self.assertEqual(st, 200, body)
        self.assertTrue(self.session('xiaolin')['teacher'])
        self.assertEqual(self.me('xiaolin', '/api/next/class/create', {'name': '高一（3）班'})[0], 200)
        self.assertEqual(self.console('/learner/teacher', {'id': uid, 'teacher': False})[0], 200)
        self.assertFalse(self.session('xiaolin')['teacher'])
        self.assertEqual([r['action'] for r in self.log()][-2:], ['account-teacher-on', 'account-teacher-off'])
        self.assertEqual(self.console('/learner/teacher', {'id': uid, 'teacher': True}, email=INTERN)[0], 403)

    def test_an_account_in_a_class_is_not_made_a_teacher(self):
        self.person('wanglaoshi')
        _, code = self.make()
        _, _, uid = self.person('xiaolin')
        self.assertEqual(self.me('xiaolin', '/api/next/class/join', {'code': code})[0], 200)
        st, body = self.console('/learner/teacher', {'id': uid, 'teacher': True})
        self.assertEqual(st, 409, body)
        self.assertIn('高一（3）班', body['error'])
        self.me('xiaolin', '/api/next/class/leave', {})
        self.assertEqual(self.console('/learner/teacher', {'id': uid, 'teacher': True})[0], 200)

    def test_teacher_accounts_are_out_of_the_learner_numbers(self):
        for n in ('xiaolin', 'xiaowang'):
            self.person(n)
        before = self.console('/funnel')[1]['steps'][0]['count'], self.console('/overview')[1]['never_started']
        self.teacher()
        after = self.console('/funnel')[1]['steps'][0]['count'], self.console('/overview')[1]['never_started']
        self.assertEqual(after, before)
        rows = self.console('/learners?filter=teacher')[1]['items']
        self.assertEqual([r['username'] for r in rows], ['wanglaoshi'])


if __name__ == '__main__':
    unittest.main()
