"""The learner round (r22): 每周目标 (weeks Monday to Sunday in China time, a streak of weeks, never of days), a
material kept on the phone with its answers (graded there without a connection), and the parts of the page for
存到手机 and 分享卡片 (their behaviour in a browser: tools/ui_test.py, learner_run)."""
import datetime, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, flow_admin  # noqa: E402

JS = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8')
PID = 'v5-science-b2-noise-cancelling'
CN = datetime.timezone(datetime.timedelta(hours=8))
at = lambda *a: datetime.datetime(*a, tzinfo=CN).timestamp()
NOW = at(2026, 11, 25, 10, 0)  # a Wednesday; the week began on Monday 2026-11-23


class Db(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0'})]
        for p in self.patches:
            p.start()
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('lin', 'x'))
            self.uid = c.execute("SELECT id FROM users WHERE username='lin'").fetchone()[0]

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def studied(self, c, *times):  # a step of a material at each time (one row per material and step)
        for t in times:
            c.execute("INSERT INTO next_progress(user_id,pack,step,created) VALUES(?,?,'read',?)", (self.uid, f'pack-{t}', t))
        c.commit()


class HabitTests(Db):
    def test_a_week_runs_monday_to_sunday_in_china_time(self):
        with app.db() as c:
            # Sunday 23:30 in China is last week; Monday 00:10 in China (still Sunday in UTC) is this week; a review counts too
            self.studied(c, at(2026, 11, 22, 23, 30), at(2026, 11, 23, 0, 10))
            c.execute('INSERT INTO next_reviews(user_id,card,rating,created) VALUES(?,?,?,?)', (self.uid, 1, 'good', at(2026, 11, 24, 21, 0)))
            h = nx.habit(c, self.uid, 4, NOW)
        self.assertEqual((h['monday'], h['done'], h['met'], h['goal']), ('2026-11-23', 2, False, 4))
        self.assertEqual([d['day'][5:] for d in h['days']], ['11-23', '11-24', '11-25', '11-26', '11-27', '11-28', '11-29'])
        self.assertEqual([d['active'] for d in h['days']], [True, True, False, False, False, False, False])
        self.assertEqual([d['today'] for d in h['days']].index(True), 2)
        self.assertEqual(h['last_week'], {'done': 1, 'met': False})

    def test_the_streak_is_of_weeks_that_reached_the_goal(self):
        with app.db() as c:
            self.studied(c, at(2026, 11, 2, 9), at(2026, 11, 4, 9),                            # 3 weeks ago: 2 days, met
                         at(2026, 11, 10, 9), at(2026, 11, 12, 9), at(2026, 11, 13, 9),         # 2 weeks ago: 3 days
                         at(2026, 11, 16, 9), at(2026, 11, 16, 18), at(2026, 11, 21, 9))        # last week: 2 days (twice on Monday is one day)
            self.assertEqual(nx.habit(c, self.uid, 2, NOW)['streak'], 3)  # this week not yet: the streak still stands
            self.assertEqual(nx.habit(c, self.uid, 3, NOW)['streak'], 0)  # with 3 a week, last week missed it
            self.studied(c, at(2026, 11, 23, 9), at(2026, 11, 25, 8))
            h = nx.habit(c, self.uid, 2, NOW)
            self.assertEqual((h['met'], h['streak']), (True, 4))  # this week counts once it is reached
            self.studied(c, at(2026, 10, 26, 9))  # a week with one day before them: it does not join the streak
            self.assertEqual(nx.habit(c, self.uid, 2, NOW)['streak'], 4)

    def test_the_goal_is_one_to_seven_days_and_comes_with_the_stats(self):
        with app.db() as c:
            self.assertEqual(nx.post(c, self.uid, '/api/next/habit', {'goal': 3})[1], 400)  # no profile yet
            nx.save_profile(c, self.uid, {'level': 'B1', 'goal': next(iter(nx.GOALS)), 'themes': [], 'minutes': 10})
            for bad in (0, 8, 'x', None):
                self.assertEqual(nx.post(c, self.uid, '/api/next/habit', {'goal': bad})[1], 400, bad)
            body, st = nx.post(c, self.uid, '/api/next/habit', {'goal': '5'})
            self.assertEqual((st, body['habit']['goal']), (200, 5))
            self.assertEqual(nx.stats(c, self.uid)['habit']['goal'], 5)
            self.assertEqual(nx.profile(c, self.uid)['weekly_goal'], 5)


class OfflineTests(Db):
    def test_answers_come_only_with_a_copy_kept_on_the_phone_and_grade_like_the_server(self):
        with app.db() as c:
            plain, st = nx.material(c, self.uid, PID)
            self.assertEqual(st, 200)
            self.assertNotIn('answers', plain)
            self.assertNotIn('answer', str([q.keys() for q in plain['questions']]))
            kept, _ = nx.material(c, self.uid, PID, offline=True)
            self.assertEqual(len(kept['answers']), len(kept['questions']))
            for i, a in enumerate(kept['answers']):
                self.assertTrue(a['evidence'])
                body, _ = nx.check(c, None, {'pack': PID, 'index': i, 'choice': a['answer']})  # what the server says
                self.assertTrue(body['correct'], i)
            guest, _ = nx.material(c, None, PID, 'B2', offline=True)  # a guest can keep one too
            self.assertEqual(guest['answers'], kept['answers'])

    def test_the_route_asks_for_them_with_offline_1(self):
        with app.db() as c:
            self.assertIn('answers', nx.get(c, self.uid, '/api/next/material', {'id': [PID], 'offline': ['1']})[0])
            self.assertNotIn('answers', nx.get(c, self.uid, '/api/next/material', {'id': [PID]})[0])


class PageTests(unittest.TestCase):
    def test_keep_share_and_the_week_are_on_the_page(self):
        for s in ("const OFF = {", "materialPath(id) + '&offline=1'", 'function keepTodayOffline', "data-tap=\"study-keep\"", 'm.answers && m.answers[k]',
                  "const SHARE_URL = 'https://flowlang.cn/?f=card'", 'function shareFromMaterial', 'id="shareX"', 'id="shareDone"', 'QR.draw(g, SHARE_URL',
                  'function mountWeekCards', 'function habitSheet', "api('/api/next/habit'", 'id="lastWeek"'):
            self.assertIn(s, JS)
        for k in ('share-material', 'share-week', 'study-keep', 'notice-week', 'me-habit'):
            self.assertIn(k, flow_admin.TAP_LABEL)


if __name__ == '__main__':
    unittest.main()
