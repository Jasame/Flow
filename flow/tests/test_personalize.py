"""按我的学习记录推荐 (我的 → 设置; 个保法第二十四条, 算法推荐规定第十七条): on by default; switched off, 今日 recommends
by the level the learner chose only — featured first, the newest first — and nothing is picked from their records."""
import os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, skills_service as sk  # noqa: E402


class PersonalizeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'p.db'); self.p.start()
        self.env = patch.dict(os.environ, {'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0'}); self.env.start()
        app.init(); self.c = app.db()
        for n in ('learner', 'nobody'):
            self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'work', 'themes': ['work'], 'minutes': 20})

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def plain_order(self, level):
        rows = [rp for rp in nx._public_packs(self.c, level) if rp[0]['origin'] != 'daily' and not rp[1].get('series')]
        rows.sort(key=lambda rp: (0 if nx.featured(rp[1]) else 1, -(rp[0]['created'] or 0), rp[1]['id']))
        return [p['id'] for _, p in rows[:3]]

    def test_on_by_default_and_switched_by_the_learner(self):
        self.assertIs(nx.profile(self.c, 1)['personalize'], True)
        self.assertEqual(nx.post(self.c, 1, '/api/next/personalize', {'on': False}), ({'personalize': False}, 200))
        self.assertIs(nx.profile(self.c, 1)['personalize'], False)
        self.assertEqual(nx.post(self.c, 1, '/api/next/personalize', {'on': 'no'})[1], 400)
        self.assertEqual(nx.post(self.c, 2, '/api/next/personalize', {'on': False})[1], 400)  # no profile yet
        self.assertEqual(nx.post(self.c, 1, '/api/next/personalize', {'on': True}), ({'personalize': True}, 200))

    def test_off_today_follows_the_chosen_level_and_the_newest_only(self):
        on = nx.home(self.c, 1)
        self.assertTrue(on['personalized'])
        learned = on['today'][0]['id']
        nx.mark(self.c, 1, learned, 'check')
        self.assertNotIn(learned, [x['id'] for x in nx.home(self.c, 1)['today']])  # on: the records leave it out
        nx.set_personalize(self.c, 1, {'on': False})
        off = nx.home(self.c, 1)
        self.assertFalse(off['personalized'])
        self.assertEqual([x['id'] for x in off['today']], self.plain_order('B1'))  # nothing from the records
        self.assertTrue(all(not x.get('reasons') for x in off['today']))  # no 「补一补」「你收藏的」「和你的目标相关」
        self.assertTrue(all(x['level'] == 'B1' for x in off['today']))
        self.assertIsNone(off['suggest'])
        # 今日好句 asked without the account (it would leave learned texts out)
        with patch('daily_line.today', wraps=__import__('daily_line').today) as line:
            nx.home(self.c, 1)
        self.assertIsNone(line.call_args.args[1])

    def test_off_the_plan_does_not_pick_from_the_records(self):
        nx.set_personalize(self.c, 1, {'on': False})
        with patch('ability_radar.weakest', side_effect=AssertionError('the records were read')), \
                patch.object(sk, 'ability', side_effect=AssertionError('the records were read')):
            path = nx.home(self.c, 1)['path']
        self.assertTrue(path)
        self.assertIsNone(sk.suggest_level(self.c, 1))

    def test_off_the_ranking_reads_no_records_at_all(self):
        # D2: not just the reasons hidden — the saved words, the serials read and the times texts were learned stay unread
        nx.set_personalize(self.c, 1, {'on': False})
        with patch.object(nx, '_card_norms', side_effect=AssertionError('saved words read')), \
                patch.object(nx, 'series_list', side_effect=AssertionError('serials read')):
            self.assertEqual([x['id'] for x in nx.home(self.c, 1)['today']], self.plain_order('B1'))

    def test_off_there_is_no_day_back_reshaped_from_the_record(self):
        # 回归模式 follows the study record (days away), so it is under the switch; the plan's length follows the minutes
        old = __import__('time').time() - 12 * 86400
        self.c.execute('INSERT INTO next_progress VALUES(?,?,?,?)', (1, self.plain_order('B1')[0], 'read', old)); self.c.commit()
        self.assertIsNotNone(nx.home(self.c, 1)['path']['back'])
        nx.set_personalize(self.c, 1, {'on': False})
        self.assertIsNone(nx.home(self.c, 1)['path']['back'])

    def test_a_guest_and_an_account_without_a_profile_are_not_marked_off(self):
        self.assertFalse(nx.home(self.c, None, 'B1')['personalized'])  # no account: nothing personal to say
        self.assertTrue(nx.follows_records(None)); self.assertTrue(nx.follows_records({'level': 'B1'}))
        self.assertTrue(nx.home(self.c, 2, 'B1')['personalized'])


if __name__ == '__main__':
    unittest.main()
