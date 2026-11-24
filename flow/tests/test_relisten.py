"""复听 (relisten_service): a text learned a few days ago comes back in 今日, is heard without the words, rated by how
much was understood, and comes back after 3 days while it is hard to follow; once mostly understood it is known.
The one due most recently comes first, and a long queue keeps only the last two weeks' texts (r27)."""
import json, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, skills_service as sk, relisten_service as rl  # noqa: E402

JS = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8')
PID = 'v5-science-b2-noise-cancelling'
DAY = 86400


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
            nx.save_profile(c, self.uid, {'level': 'B2', 'goal': next(iter(nx.GOALS)), 'themes': [], 'minutes': 15})
            self.now = time.time()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def studied(self, c, pack, days_ago, step='check'):
        c.execute('INSERT INTO next_progress(user_id,pack,step,created) VALUES(?,?,?,?)', (self.uid, pack, step, self.now - days_ago * DAY)); c.commit()

    def heard(self, c, pack, understood, days_ago):
        c.execute('INSERT INTO next_relisten(user_id,pack,understood,created) VALUES(?,?,?,?)', (self.uid, pack, understood, self.now - days_ago * DAY)); c.commit()


class ScheduleTests(unittest.TestCase):
    def test_three_days_then_known_once_mostly_understood(self):
        t0 = 1_000_000.0
        self.assertEqual(rl.next_time(t0, []), (t0 + 3 * DAY, 0))
        self.assertEqual(rl.next_time(t0, [(2, t0 + 3 * DAY)]), (None, 1))  # 大部分: known, no 7 and 21 days any more
        self.assertEqual(rl.next_time(t0, [(3, t0 + 3 * DAY)]), (None, 1))

    def test_a_hard_listen_comes_back_in_three_days_until_understood(self):
        t0 = 1_000_000.0
        self.assertEqual(rl.next_time(t0, [(1, t0 + 3 * DAY)]), (t0 + 6 * DAY, 0))
        self.assertEqual(rl.next_time(t0, [(1, t0 + 3 * DAY), (0, t0 + 6 * DAY)]), (t0 + 9 * DAY, 0))
        self.assertEqual(rl.next_time(t0, [(1, t0 + 3 * DAY), (0, t0 + 6 * DAY), (2, t0 + 9 * DAY)]), (None, 1))


class PlanTests(Db):
    def plan(self, c):
        home = nx.home(c, self.uid)
        return {s['key']: s for s in sk.daily_path(c, self.uid, home, self.now)['steps']}

    def test_a_text_from_four_days_ago_comes_back_right_after_the_words(self):
        with app.db() as c:
            self.assertNotIn('relisten', self.plan(c))  # nothing studied yet
            self.studied(c, PID, 4)
            steps = sk.daily_path(c, self.uid, nx.home(c, self.uid), self.now)['steps']
            self.assertEqual([s['key'] for s in steps][:2], ['review', 'relisten'])
            s = steps[1]
            self.assertEqual((s['href'], s['done']), (f'#/m/{PID}/listen/again', False))
            self.assertIn('4 天前学过', s['sub'])
            self.assertTrue(s['title'].startswith('复听：'))

    def test_not_too_soon_not_too_old_not_on_five_minute_days(self):
        with app.db() as c:
            self.studied(c, PID, 2)
            self.assertNotIn('relisten', self.plan(c))  # 3 days have not passed
            c.execute('UPDATE next_progress SET created=?', (self.now - 70 * DAY,)); c.commit()
            self.assertNotIn('relisten', self.plan(c))  # too long ago
            c.execute('UPDATE next_progress SET created=?', (self.now - 4 * DAY,))
            c.execute('UPDATE next_profiles SET minutes=5'); c.commit()
            self.assertNotIn('relisten', self.plan(c))
            self.studied(c, 'only-listened', 5, 'listen')  # only the listen step: not studied enough to come back
            c.execute('UPDATE next_profiles SET minutes=15'); c.commit()
            self.assertEqual(self.plan(c)['relisten']['href'], f'#/m/{PID}/listen/again')

    def test_after_the_listen_it_is_ticked_and_the_week_counts_the_day(self):
        with app.db() as c:
            self.studied(c, PID, 4)
            body, st = nx.post(c, self.uid, '/api/next/relisten', {'pack': PID, 'understood': 2})
            self.assertEqual((st, body['label'], body['next_days'], body['known']), (200, '大部分', None, True))
            s = self.plan(c)['relisten']
            self.assertTrue(s['done'])
            self.assertIn('听懂了大部分', s['sub'])
            self.assertTrue(nx.habit(c, self.uid, 4, self.now)['days'][[d['today'] for d in nx.habit(c, self.uid, 4, self.now)['days']].index(True)]['active'])
            self.assertEqual(sk.report(c, self.uid, self.now)['relisten'], {'count': 1, 'avg': 2.0, 'label': '大部分'})


class RecordTests(Db):
    def test_answers_are_checked_and_a_second_rating_on_the_same_visit_replaces_the_first(self):
        with app.db() as c:
            self.studied(c, PID, 4)
            for bad in (-1, 4, '2', None, 1.5):
                self.assertEqual(rl.record(c, self.uid, {'pack': PID, 'understood': bad})[1], 400, bad)
            self.assertEqual(rl.record(c, self.uid, {'pack': 'nothing-here', 'understood': 2})[1], 404)
            self.assertEqual(rl.record(c, self.uid, {'pack': PID, 'understood': 0})[0]['next_days'], 3)
            body, _ = rl.record(c, self.uid, {'pack': PID, 'understood': 3})  # changed their mind: almost all, known
            self.assertEqual((body['next_days'], body['known']), (None, True))
            self.assertEqual(c.execute('SELECT COUNT(*) FROM next_relisten').fetchone()[0], 1)

    def test_the_one_due_most_recently_comes_first_and_a_known_text_never_again(self):
        with app.db() as c:
            other = next(r[0] for r in c.execute("SELECT id FROM lab_packs WHERE owner IS NULL AND id LIKE 'v5-%' AND id!=? LIMIT 1", (PID,)))
            self.studied(c, PID, 5); self.studied(c, other, 9)
            self.assertEqual([d['pack'] for d in rl.due(c, self.uid, self.now)], [PID, other])  # due 2 days ago before 6 days ago
            self.heard(c, PID, 1, 1)  # half or less: back in 3 days
            self.assertEqual([d['pack'] for d in rl.due(c, self.uid, self.now)], [other])
            self.assertEqual([d['pack'] for d in rl.due(c, self.uid, self.now + 2 * DAY)], [PID, other])
            self.heard(c, other, 2, 0.5)
            self.assertEqual([d['pack'] for d in rl.due(c, self.uid, self.now + 2 * DAY)], [PID])  # other: known
            self.heard(c, PID, 3, 0.2)
            self.assertEqual(rl.due(c, self.uid, self.now + 30 * DAY), [])

    def test_a_long_queue_keeps_the_last_two_weeks(self):
        with app.db() as c:
            packs = [r[0] for r in c.execute("SELECT id FROM lab_packs WHERE owner IS NULL AND id LIKE 'v5-%' ORDER BY id LIMIT 10")]
            for k, pk in enumerate(packs[:7]):
                self.studied(c, pk, 20 + k)  # seven old ones, 20–26 days ago
            self.assertEqual(len(rl.due(c, self.uid, self.now)), 7)  # seven waiting: all offered, oldest last
            self.studied(c, packs[7], 5); self.studied(c, packs[8], 12)
            self.heard(c, packs[6], 1, 1)  # an old text heard yesterday (half or less) is recent again, but not due yet
            d = rl.due(c, self.uid, self.now)
            self.assertEqual([x['pack'] for x in d], [packs[7], packs[8]])  # eight waiting: only the last two weeks'
            self.assertEqual(rl.due(c, self.uid, self.now + 2.5 * DAY)[0]['pack'], packs[6])  # its 3 days are up: it comes first

    def test_the_account_data_carries_and_drops_the_listens(self):
        import account_data
        with app.db() as c:
            self.studied(c, PID, 4); rl.record(c, self.uid, {'pack': PID, 'understood': 2})
            u = {'id': self.uid, 'admin': 0}
            self.assertIn('next_relisten', json.loads(account_data.records(c, u))['tables'])


class PageTests(unittest.TestCase):
    def test_the_listen_page_hides_the_text_and_asks(self):
        for s in ("parts()[3] === 'again'", 'st.blind = true', "api('/api/next/relisten'", 'data-und="${k}"', "OUTBOX.push({ path: '/api/next/relisten'",
                  '平均听懂'):
            self.assertIn(s, JS)


if __name__ == '__main__':
    unittest.main()
