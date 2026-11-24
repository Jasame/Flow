"""班级试用问卷 (survey_service.TRIAL): the 8 questions the owner approved, anonymous like the needs survey and kept apart
from it; offered on 今日 three weeks after joining a class (class_service.survey_due) and never linked to an account;
the console shows each survey on its own."""
import json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import app, flow_admin, class_service as cs, survey_service as sv  # noqa: E402

BOSS, INTERN = 'boss@example.com', 'intern@example.com'
DAY = 86400
TRIAL_ANSWERS = {'often': '每周 3–5 天', 'useful': ['背单词和复习', '用出来（AI 批改仿写、复述、翻译）'], 'useless': '都还好',
                 'change': '有一点进步', 'more': '多了一点', 'keep': '可能会', 'recommend': '愿意', 'say': '希望多一些考试题'}


class TrialSurvey(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'flow.sqlite3'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_ADMIN_EMAILS': BOSS, 'FLOW_DATA_DIR': self.tmp.name})]
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

    def call(self, path, data=None, headers=None, srv=None, raw=False):
        srv = srv or self.site
        req = urllib.request.Request(f'http://127.0.0.1:{srv.server_address[1]}{path}', data=json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type': 'application/json', **(headers or {})})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                body = r.read()
                return r.status, (body if raw else json.loads(body or b'{}'))
        except urllib.error.HTTPError as e:
            body = e.read()
            return e.code, (body if raw else json.loads(body or b'{}'))

    def console(self, path, email=BOSS):
        return self.call('/flow/api' + path, headers={'Cf-Access-Authenticated-User-Email': email}, srv=self.admin, raw=path.split('?')[0].endswith('.csv'))

    def send(self, answers, survey=sv.TRIAL_ID, ip='10.7.0.1'):
        return self.call('/api/survey', {'survey': survey, 'answers': answers, 'seconds': 90}, {'X-Real-IP': ip})


class DefinitionTests(TrialSurvey):
    def test_the_approved_eight_questions_and_the_needs_survey_unchanged(self):
        st, d = self.call('/api/survey?s=trial')
        qs = [q for s in d['sections'] for q in s['questions']]
        self.assertEqual((st, d['id'], len(qs)), (200, sv.TRIAL_ID, len(list(sv.questions('trial')))))  # what the server holds, sent whole
        self.assertEqual([q['id'] for q in qs], ['often', 'useful', 'useless', 'change', 'more', 'keep', 'recommend', 'say'])
        self.assertEqual([q['required'] for q in qs], [q['type'] != 'text' for q in qs])  # the open question alone is optional
        self.assertIn('匿名', d['intro'])
        self.assertEqual(self.call('/api/survey')[1]['id'], sv.SURVEY_ID)
        self.assertEqual(self.call('/api/survey?s=nothing')[1]['id'], sv.SURVEY_ID)


class SubmitTests(TrialSurvey):
    def test_answers_are_kept_apart_from_the_needs_survey_and_checked(self):
        self.assertEqual(self.send(TRIAL_ANSWERS)[0], 200)
        self.assertEqual(self.send({**TRIAL_ANSWERS, 'useful': ['听材料和跟读', '理解题', '口语练习']})[0], 400)  # at most 2
        self.assertEqual(self.send({**TRIAL_ANSWERS, 'keep': '也许'})[0], 400)
        self.assertEqual(self.send({k: v for k, v in TRIAL_ANSWERS.items() if k != 'more'})[0], 400)
        self.assertEqual(self.send(TRIAL_ANSWERS, survey='made-up')[0], 400)
        with app.db() as c:
            rows = c.execute('SELECT * FROM survey_responses').fetchall()
            self.assertEqual([r['survey'] for r in rows], [sv.TRIAL_ID])
            self.assertNotIn('user', ' '.join(rows[0].keys()))  # no account in a response
            self.assertEqual(sv.summary(c)['total'], 0)
            got = sv.summary(c, sid='trial')
        self.assertEqual(got['total'], 1)
        keep = next(q for q in got['questions'] if q['id'] == 'keep')
        self.assertEqual({o['label']: o['count'] for o in keep['options']}['可能会'], 1)

    def test_each_survey_has_its_own_daily_limit(self):
        needs = {q['id']: (q['options'][0] if q['type'] == 'single' else [q['options'][0]] if q['type'] == 'multi'
                           else {r: 3 for r in q['rows']} if q['type'] == 'matrix' else '') for q in sv.questions()}
        needs = {k: v for k, v in needs.items() if v != ''}
        for _ in range(sv.DAILY_PER_CLIENT):
            self.assertEqual(self.send(needs, survey=sv.SURVEY_ID)[0], 200)
        self.assertEqual(self.send(needs, survey=sv.SURVEY_ID)[0], 429)
        self.assertEqual(self.send(TRIAL_ANSWERS)[0], 200)


class DueTests(TrialSurvey):
    def test_offered_three_weeks_after_joining_and_only_while_in_an_active_class(self):
        with app.db() as c:
            for n in ('wang', 'a', 'b'):
                c.execute('INSERT INTO users(username,password,age_band) VALUES(?,?,?)', (n, 'x', '18+'))
            uid = lambda n: c.execute('SELECT id FROM users WHERE username=?', (n,)).fetchone()[0]
            body, st, _ = cs.create(c, {'name': '高一（3）班', 'teacher': 'wang'}, BOSS)
            now = time.time()
            c.execute('INSERT INTO class_members(user_id,class_id,joined_at) VALUES(?,?,?)', (uid('a'), body['id'], now - 22 * DAY))
            c.execute('INSERT INTO class_members(user_id,class_id,joined_at) VALUES(?,?,?)', (uid('b'), body['id'], now - 10 * DAY))
            c.commit()
            self.assertTrue(cs.survey_due(c, uid('a')))
            self.assertFalse(cs.survey_due(c, uid('b')))
            self.assertFalse(cs.survey_due(c, uid('wang')))  # the teacher is not a member
            self.assertTrue(cs.survey_due(c, uid('b'), now + 12 * DAY))
            c.execute('UPDATE classes SET active=0'); c.commit()
            self.assertFalse(cs.survey_due(c, uid('a')))
            c.execute('UPDATE classes SET active=1'); c.execute('UPDATE class_members SET left_at=? WHERE user_id=?', (now, uid('a'))); c.commit()
            self.assertFalse(cs.survey_due(c, uid('a')))

    def test_the_home_page_carries_the_flag(self):
        self.assertFalse(self.call('/api/next/home')[1]['trial_survey'])  # a guest


class ConsoleTests(TrialSurvey):
    def test_the_console_shows_each_survey_and_exports_it(self):
        self.send(TRIAL_ANSWERS)
        st, d = self.console('/survey/summary?s=trial', INTERN)  # numbers: 只看数据 too
        self.assertEqual((st, d['survey']['id'], d['total']), (200, sv.TRIAL_ID, 1))
        self.assertEqual([x['id'] for x in d['surveys']], [sv.SURVEY_ID, sv.TRIAL_ID])
        self.assertEqual(self.console('/survey/summary', INTERN)[1]['total'], 0)
        self.assertEqual(self.console('/survey/responses?s=trial', INTERN)[0], 403)
        st, csv = self.console('/survey/export.csv?s=trial')
        head = csv.decode('utf-8-sig').splitlines()[0]
        self.assertTrue(head.startswith('id,date_utc,seconds,often,useful,useless,change,more,keep,recommend,say'), head)
        self.assertEqual(self.console('/overview', INTERN)[1]['trial_responses'], 1)
        self.assertIn('trial-survey', flow_admin.TAP_LABEL)


if __name__ == '__main__':
    unittest.main()
