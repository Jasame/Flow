"""今日 by 学习目的 (r28 第 5 段, audit 7.1/7.2): the first text suits the learner's goal when this tier has one, on a
short day one that fits the time first; the other two are ranked as before; no level is skipped for a goal; 今日热点
is the newest at the learner's level, or one below. Counts come from the corpus, never hard-coded."""
import copy, json, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx


class GoalRecommendTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'g.db'); self.p.start()
        app.init(); self.c = app.db()
        self.c.execute("INSERT INTO users(id,username,password) VALUES(1,'learner','x')"); self.c.commit()

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def learner(self, level, goal, minutes=30):
        nx.save_profile(self.c, 1, {'level': level, 'goal': goal, 'themes': [], 'minutes': minutes})

    def featured(self, level):
        return [p for _, p in nx._public_packs(self.c, level) if nx.featured(p) and not p.get('series')]

    def learn(self, ids):
        for i, pid in enumerate(ids):
            self.c.execute('INSERT OR IGNORE INTO next_progress VALUES(?,?,?,?)', (1, pid, 'check', time.time() - i))
        self.c.commit()

    def test_first_text_suits_the_goal_at_every_level(self):
        for goal in nx.GOAL_PURPOSES:
            for level in ('A2', 'B1', 'B2', 'C1'):
                self.learner(level, goal)
                suit = [p['id'] for p in self.featured(level) if nx.suits_goal(p, goal)]
                h = nx.home(self.c, 1)
                first = h['today'][0]
                self.assertEqual(first['level'], level, (goal, level))
                if suit:
                    self.assertIn(first['id'], suit, (goal, level))
                    self.assertEqual(first['reasons'][0], nx.GOAL_REASON[goal])
                self.assertEqual(len(h['today']), 3)
                self.assertFalse(any(nx.GOAL_REASON[goal] in m['reasons'] for m in h['today'][1:]))  # only the first says so

    def test_no_level_is_skipped_for_a_goal(self):
        self.learner('A2', 'media')
        suit = [p['id'] for p in self.featured('A2') if nx.suits_goal(p, 'media')]
        self.assertTrue(suit)
        self.learn(suit)  # every A2 text for 影视新闻 learned: the next A2 text, not a B1 one that suits the goal
        first = nx.home(self.c, 1)['today'][0]
        self.assertEqual(first['level'], 'A2')
        self.assertNotIn(first['id'], suit)
        self.assertNotIn(nx.GOAL_REASON['media'], first['reasons'])

    def test_short_day_puts_a_text_that_fits_first(self):
        for minutes in (5, 10, 15):
            self.learner('B2', 'abroad', minutes)
            suit = [p for p in self.featured('B2') if nx.suits_goal(p, 'abroad')]
            fit = [p['id'] for p in suit if nx.read_fits(len(p['body'].split()), minutes)]
            first = nx.home(self.c, 1)['today'][0]
            if fit:
                self.assertIn(first['id'], fit, minutes)
            self.assertIn(first['id'], [p['id'] for p in suit])  # the goal still comes before the time

    def test_read_fits_follows_the_time_budget(self):
        # 今天这篇: 5 min → a glance (2), 10 → 6, 15 → 8 (core = words / 30 + 2); one minute over still fits
        self.assertTrue(nx.read_fits(380, 5))
        self.assertTrue(nx.read_fits(100, 10)); self.assertFalse(nx.read_fits(200, 10))
        self.assertTrue(nx.read_fits(200, 15)); self.assertFalse(nx.read_fits(300, 15))
        self.assertTrue(nx.read_fits(10_000, 20))  # longer days: the length does not decide

    def test_guest_has_no_goal_line(self):
        h = nx.home(self.c, None, level='B1')
        self.assertEqual(len(h['today']), 3)
        self.assertFalse(any(r in nx.GOAL_REASON.values() for m in h['today'] for r in m['reasons']))

    def daily(self, day, level, purpose, age_days):
        p = copy.deepcopy(self.featured('B1')[0])
        p.update(id='daily-' + day, daily_day=day, purposes=[purpose], level='B2' if level == 'C1' else level, title='热点 ' + day)
        p.pop('cefr', None)
        if level == 'C1':
            p['cefr'] = 'C1'
        self.c.execute('INSERT INTO lab_packs VALUES(?,NULL,?,?,?)', (p['id'], 'daily', json.dumps(p), time.time() - age_days * 86400))
        self.c.commit()

    def test_hotspot_is_at_the_learners_level(self):
        self.daily('2026-11-25', 'C1', 'news-commentary', 0)
        self.daily('2026-11-24', 'B2', 'expository', 1)
        self.daily('2026-11-23', 'B1', 'film-culture', 2)
        self.daily('2026-11-20', 'B1', 'workplace', 5)  # too old
        self.learner('B1', 'media')
        news = nx.home(self.c, 1)['news']
        self.assertEqual(news['id'], 'daily-2026-11-23')
        self.assertEqual(news['reasons'], ['和你的目标相关'])
        self.learner('C1', 'work')
        news = nx.home(self.c, 1)['news']
        self.assertEqual(news['id'], 'daily-2026-11-25'); self.assertNotIn('和你的目标相关', news.get('reasons') or [])
        self.learner('A2', 'daily')  # nothing at A2 and nothing below it: no card
        self.assertIsNone(nx.home(self.c, 1)['news'])
        self.c.execute("DELETE FROM lab_packs WHERE id='daily-2026-11-24'"); self.c.commit()
        self.learner('B2', 'exam')  # this level's day failed: one level below
        self.assertEqual(nx.home(self.c, 1)['news']['id'], 'daily-2026-11-23')


if __name__ == '__main__':
    unittest.main()
