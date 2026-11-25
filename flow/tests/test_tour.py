"""新手引导 (tour_service.py, 08-tour.js): once per new account, kept on the server; old accounts and guests never see it;
a 老师账号 gets its own; 再看一遍 is neither marked nor counted; the counts carry no account."""
import re, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, tour_service as ts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'public' / 'src' / 'next' / '08-tour.js').read_text(encoding='utf-8')


class TourTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'tour.db'); self.p.start()
        app.init(); self.c = app.db()
        now = time.time()
        for name, created, role in (('new', now, None), ('old', ts.TOUR_FROM - 86400, None), ('teacher', now, 'teacher'), ('nodate', None, None)):
            self.c.execute('INSERT INTO users(username,password,created) VALUES(?,?,?)', (name, 'h', created))
            if role:
                self.c.execute('UPDATE users SET role=? WHERE username=?', (role, name))
        self.c.commit()
        self.id = {r['username']: r['id'] for r in self.c.execute('SELECT id, username FROM users')}

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def test_a_new_account_sees_its_tour_old_accounts_and_guests_do_not(self):
        self.assertEqual(ts.due(self.c, self.id['new']), {'learner': True, 'teacher': False})
        self.assertEqual(ts.due(self.c, self.id['teacher']), {'learner': False, 'teacher': True})
        self.assertEqual(ts.due(self.c, self.id['old']), {'learner': False, 'teacher': False})
        self.assertEqual(ts.due(self.c, self.id['nodate']), {'learner': False, 'teacher': False})
        self.assertEqual(ts.due(self.c, None), {'learner': False, 'teacher': False})

    def test_once_per_account_and_counted_once_without_the_account(self):
        uid = self.id['new']
        self.assertEqual(ts.record(self.c, uid, {'tour': 'learner', 'result': 'skip', 'step': 2})[0]['counted'], True)
        self.assertFalse(ts.due(self.c, uid)['learner'], 'skipped: not again, on any phone or computer')
        self.assertFalse(ts.record(self.c, uid, {'tour': 'learner', 'result': 'done', 'step': 5})[0]['counted'])
        self.assertFalse(ts.record(self.c, uid, {'tour': 'learner', 'result': 'done', 'step': 5, 'again': True})[0]['counted'])  # 再看一遍
        ts.record(self.c, self.id['teacher'], {'tour': 'teacher', 'result': 'done', 'step': 3})
        self.assertEqual(ts.stats(self.c), {'learner': {'done': 0, 'skipped': 1, 'skipped_at': {2: 1}}, 'teacher': {'done': 1, 'skipped': 0, 'skipped_at': {}}})
        cols = {r[1] for r in self.c.execute('PRAGMA table_info(next_tour_stats)')}
        self.assertFalse(cols & {'user_id', 'username'}, 'the counts carry no account')
        self.assertEqual(ts.record(self.c, uid, {'tour': 'other', 'result': 'done'})[1], 400)
        self.assertEqual(ts.record(self.c, uid, {'tour': 'learner', 'result': 'maybe'})[1], 400)

    def test_given_on_purpose_and_through_the_api(self):
        # 'pending' gives an account its tour whatever its date (the UI tests' learner)
        self.c.execute("INSERT INTO next_tours(user_id, tour, result, created) VALUES(?, 'learner', 'pending', 0)", (self.id['old'],)); self.c.commit()
        self.assertTrue(ts.due(self.c, self.id['old'])['learner'])
        import next_service as nx
        self.assertEqual(nx.get(self.c, self.id['old'], '/api/next/tour', {})[0]['learner'], True)
        self.assertEqual(nx.post_public(self.c, self.id['old'], '/api/next/tour', {'tour': 'learner', 'result': 'done', 'step': 5})[0]['counted'], True)
        self.assertFalse(ts.due(self.c, self.id['old'])['learner'])

    def test_the_steps_match_the_counts(self):
        # each tour's steps in 08-tour.js are as many as tour_service counts (the skip step is kept within them)
        for name, n in ts.TOURS.items():
            block = re.search(name + r': \[(.*?)\n    \],', JS, re.S).group(1)
            self.assertEqual(len(re.findall(r"\{ at: \[", block)), n, name)

    def test_tips_are_kept_per_account_and_come_back_together(self):
        """使用提示: put away once, gone on every device of that account; 重新显示使用提示 brings them all back; the
        tour is not touched; a guest keeps them in its browser; an unknown name is refused."""
        new, old = self.id['new'], self.id['old']
        self.assertEqual(ts.tips(self.c, new), {'seen': []})
        self.assertEqual(ts.tip(self.c, new, {'tip': 'read'}), ({'seen': ['read']}, 200))
        self.assertEqual(ts.tip(self.c, new, {'tip': 'read'})[0], {'seen': ['read']})  # twice: still one
        self.assertEqual(ts.tips(self.c, old), {'seen': []})  # another account
        self.assertEqual(ts.tip(self.c, new, {'tip': 'nope'})[1], 400)
        self.assertTrue(ts.due(self.c, new)['learner'], 'a tip is not the tour')
        ts.tip(self.c, new, {'tip': 'listen'})
        self.assertEqual(ts.tips(self.c, new), {'seen': ['listen', 'read']})
        self.assertEqual(ts.tip(self.c, new, {'reset': True}), ({'seen': []}, 200))
        self.assertEqual(ts.tips(self.c, new), {'seen': []})
        self.assertEqual(ts.tips(self.c, None), {'seen': []})
        self.assertEqual(ts.tip(self.c, None, {'tip': 'read'}), ({'seen': []}, 200))
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_tour_stats").fetchone()[0], 0, 'tips are not counted')


if __name__ == '__main__':
    unittest.main()
