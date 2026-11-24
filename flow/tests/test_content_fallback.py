"""今日 once a level's featured texts run out (r27 content line, audit 3.2): this level's unlearned featured texts, then
the next level's, then 精读重学 (the longest ago first), and the older texts (简版) only when nothing else is left.
Counts come from the corpus, never hard-coded: the corpus grows every week."""
import sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx


class ContentFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'f.db'); self.p.start()
        app.init(); self.c = app.db()
        self.c.execute("INSERT INTO users(id,username,password) VALUES(1,'learner','x')"); self.c.commit()

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def learner(self, level):
        nx.save_profile(self.c, 1, {'level': level, 'goal': 'daily', 'themes': [], 'minutes': 15})

    def featured(self, level, series=True):
        return [p['id'] for _, p in nx._public_packs(self.c, level) if nx.featured(p) and (series or not p.get('series'))]

    def learn(self, ids, ago=0):
        for i, pid in enumerate(ids):
            self.c.execute('INSERT OR IGNORE INTO next_progress VALUES(?,?,?,?)', (1, pid, 'check', time.time() - ago - i))
        self.c.commit()

    def test_counts_down_then_moves_up_a_level(self):
        self.learner('B2')
        b2 = self.featured('B2')
        h = nx.home(self.c, 1)
        self.assertEqual(h['featured_left'], len(b2)); self.assertEqual(h['level_up'], 'C1')
        self.assertTrue(all(m['level'] == 'B2' and m['featured'] and not m['brief'] for m in h['today']))
        self.learn(b2[:-1])  # one left
        h = nx.home(self.c, 1)
        self.assertEqual(h['featured_left'], 1)
        self.assertEqual(h['today'][0]['id'], b2[-1])
        self.assertTrue(all(m['level'] == 'C1' and m['featured'] for m in h['today'][1:]))
        self.assertTrue(all(m['reasons'][0].startswith('这一级的精选学完了') for m in h['today'][1:]))
        self.assertFalse(any(m['brief'] for m in h['today']))  # older texts wait while featured ones remain

    def test_c1_goes_to_close_reading_the_longest_ago_first(self):
        self.learner('C1')
        c1 = self.featured('C1')
        self.learn(c1, ago=86400)
        oldest = sorted(c1, key=lambda pid: self.c.execute("SELECT created FROM next_progress WHERE user_id=1 AND pack=? AND step='check'", (pid,)).fetchone()[0])
        h = nx.home(self.c, 1)
        self.assertEqual(h['featured_left'], 0); self.assertIsNone(h['level_up'])
        self.assertEqual([m['id'] for m in h['today']], oldest[:3])
        self.assertTrue(all(m['redo'] and m['reasons'][0].startswith('精读重学') for m in h['today']))
        # Learning the first one again moves it to the back the next day (the redo is in next_step_log, #51)
        first = oldest[0]
        nx.mark(self.c, 1, first, 'check')
        h = nx.home(self.c, 1)
        self.assertNotIn(first, [m['id'] for m in h['today']])
        self.assertEqual([m['id'] for m in h['today']], oldest[1:4])
        self.assertTrue(h['today'][0]['reasons'][0].endswith('1 天前学过'))
        cards = {m['id']: m for m in nx.home(self.c, 1)['today']}
        self.assertEqual(len(cards), 3)

    def test_older_texts_only_when_nothing_else_is_left(self):
        self.learner('A2')
        a2_old = [p['id'] for _, p in nx._public_packs(self.c, 'A2') if not nx.featured(p) and p.get('daily_day') is None]
        self.assertTrue(a2_old)
        self.learn(self.featured('A2') + self.featured('B1'))  # everything featured learned: still 精读重学, not 简版
        self.assertTrue(all(m.get('redo') for m in nx.home(self.c, 1)['today']))
        with patch.object(nx, 'featured', return_value=False):  # a level with no featured texts at all: then 简版
            h = nx.home(self.c, 1)
        self.assertEqual(len(h['today']), 3)
        self.assertTrue(all(m['level'] == 'A2' and m['brief'] and not m.get('redo') for m in h['today']))
        cards = [nx._card(p) for _, p in nx._public_packs(self.c, 'A2')]
        self.assertEqual(sum(c['brief'] for c in cards), len(a2_old))  # 简版 on every older text, and only there
        self.assertFalse(any(c['brief'] and c['featured'] for c in cards))


if __name__ == '__main__':
    unittest.main()
