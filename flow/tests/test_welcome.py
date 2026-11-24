"""选方向和目标 (r27): a new learner's goal, exam and the level to reach, written in one call; the level guessed one
band below the target until a test says more; settings left out of a call keep what was saved."""
import datetime, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, exam_sprint as sp


class WelcomeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'welcome.db'); self.p.start()
        app.init(); self.c = app.db()
        for n in ('new', 'old'):
            self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def day(self, n):
        return (sp._today() + datetime.timedelta(days=n)).isoformat()

    def test_goal_exam_and_target_in_one_call_with_the_level_guessed(self):
        out, code = nx.save_profile(self.c, 1, {'goal': 'exam', 'target': 'B2', 'exam': 'cet6', 'exam_date': self.day(40)})
        self.assertEqual(code, 200)
        p = out['profile']
        self.assertEqual((p['goal'], p['target'], p['level'], p['level_source']), ('exam', 'B2', 'B1', 'guess'))
        self.assertEqual((p['exam'], p['exam_date']), ('cet6', self.day(40)))
        self.assertEqual((p['themes'], p['minutes']), ([], 10))
        self.assertEqual(sp.goal(self.c, 1)['exam'], 'cet6')  # the same field 考试冲刺 reads
        self.assertEqual(nx.save_profile(self.c, 2, {'goal': 'daily', 'target': 'A2'})[0]['profile']['level'], 'A2')  # nothing below A2
        self.assertEqual(nx.save_profile(self.c, 2, {'goal': 'daily'})[1], 400)  # neither a level nor a target
        self.assertEqual(nx.save_profile(self.c, 2, {'goal': 'exam', 'target': 'B1', 'exam': 'toefl'})[1], 400)

    def test_fields_left_out_keep_what_was_saved(self):
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'work', 'themes': ['science'], 'minutes': 20})
        p = nx.save_profile(self.c, 1, {'goal': 'media', 'target': 'C1'})[0]['profile']
        self.assertEqual((p['goal'], p['themes'], p['minutes'], p['level'], p['level_source']), ('media', ['science'], 20, 'B2', 'guess'))
        p = nx.save_profile(self.c, 1, {'level': 'B2', 'level_source': 'placed'})[0]['profile']
        self.assertEqual((p['level'], p['level_source'], p['target'], p['goal']), ('B2', 'placed', 'C1', 'media'))
        p = nx.save_profile(self.c, 1, {'level': 'B1'})[0]['profile']
        self.assertEqual(p['level_source'], 'self')
        # an exam whose date has passed does not block saving other settings; changing it to a past date is refused
        nx.save_profile(self.c, 1, {'goal': 'exam', 'target': 'B2', 'exam': 'ielts', 'exam_date': self.day(10)})
        self.c.execute('UPDATE next_profiles SET exam_date=? WHERE user_id=1', (self.day(-5),)); self.c.commit()
        prof = nx.profile(self.c, 1)
        self.assertEqual(nx.save_profile(self.c, 1, {**prof, 'minutes': 30})[1], 200)
        self.assertEqual(nx.save_profile(self.c, 1, {**prof, 'exam_date': self.day(-1)})[1], 400)
        # older rows (before r27) read as chosen by the learner
        self.c.execute('UPDATE next_profiles SET level_source=NULL WHERE user_id=1'); self.c.commit()
        self.assertEqual(nx.profile(self.c, 1)['level_source'], 'self')

    def test_today_suggests_a_test_until_one_is_taken(self):
        nx.save_profile(self.c, 1, {'goal': 'daily', 'target': 'B2'})
        h = nx.home(self.c, 1)
        self.assertTrue(h['level_guess'])
        self.assertEqual(h['level'], 'B1')  # materials one band below the target
        __import__('ability_radar').record(self.c, 1, 'reading', 55)
        self.assertFalse(nx.home(self.c, 1)['level_guess'])
        nx.save_profile(self.c, 2, {'level': 'B1', 'goal': 'work', 'themes': [], 'minutes': 10})
        self.assertFalse(nx.home(self.c, 2)['level_guess'])

    def test_an_exam_chosen_at_the_start_makes_a_word_plan_once(self):
        import vocab_service as vs
        out, _ = nx.save_profile(self.c, 1, {'goal': 'exam', 'target': 'B2', 'exam': 'cet6', 'exam_date': self.day(40)})
        self.assertEqual(out['plan_made'], {'book': 'cet6', 'title': '六级词汇', 'daily_new': 10})
        self.assertEqual((vs.plan(self.c, 1)['book'], vs.plan(self.c, 1)['daily_new']), ('cet6', 10))
        vs.save_plan(self.c, 1, {'book': 'cet6', 'daily_new': 25, 'retention': 0.9})
        out, _ = nx.save_profile(self.c, 1, {'goal': 'exam', 'target': 'B2', 'exam': 'ielts'})
        self.assertIsNone(out['plan_made'])  # a plan the learner has is never replaced
        self.assertEqual(vs.plan(self.c, 1)['daily_new'], 25)
        self.assertIsNone(nx.save_profile(self.c, 2, {'goal': 'daily', 'target': 'B1'})[0]['plan_made'])
        self.assertIsNone(vs.plan(self.c, 2))

    def test_without_a_word_plan_the_first_step_asks_for_a_book(self):
        import vocab_service as vs
        nx.save_profile(self.c, 2, {'goal': 'daily', 'target': 'B2'})
        first = nx.home(self.c, 2)['path']['steps'][0]
        self.assertEqual((first['title'], first['href'], first['done']), ('选一本词书', '#/vocab/plan', False))
        self.assertEqual((first['minutes'], first['group']), (1, 'must'))
        self.assertIn('进阶词汇', first['sub'])  # the level's book (B1, one band below B2)
        sp.set_goal(self.c, 2, {'exam': 'cet4', 'date': ''})  # an exam set elsewhere, still no plan: its book comes first
        self.assertIn('《四级词汇》', nx.home(self.c, 2)['path']['steps'][0]['sub'])
        self.assertEqual(vs.overview(self.c, 2)['suggested_book'], 'cet4')
        vs.save_plan(self.c, 2, {'book': 'cet4', 'daily_new': 10, 'retention': 0.9})
        self.assertTrue(nx.home(self.c, 2)['path']['steps'][0]['title'].startswith('单词'))

    def test_the_page_gets_what_it_shows_from_meta(self):
        m = nx.meta()
        self.assertEqual([t['id'] for t in m['targets']], ['A2', 'B1', 'B2', 'C1'])
        self.assertTrue(all(m['goal_hints'].get(g['id']) for g in m['goals']))
        self.assertTrue(all(m['target_for'].get(e['id']) in nx.BANDS for e in m['exams']))
        self.assertTrue(all(m['target_for'].get(g['id']) in nx.BANDS for g in m['goals']))
        self.assertTrue(all(e['book_title'].endswith('词汇') for e in m['exams']))


if __name__ == '__main__':
    unittest.main()
