"""按时间打包今日计划 (r28 第 1 段): the day's minutes split into a budget, 必做 only what fits, the rest under
「还有时间的话」 (not counted), the week's exam set as 本周任务, today's minutes from the learner's own records, and the
line once they pass the minutes chosen by a fifth."""
import datetime, inspect, os, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, progress_service as ps, skills_service as sk, time_budget as tb, vocab_service as vs  # noqa: E402
import exam_service as ex  # noqa: E402

CN = datetime.timezone(datetime.timedelta(hours=8))
at = lambda *a: datetime.datetime(*a, tzinfo=CN).timestamp()
JS = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8')
CSS = (Path(app.ROOT) / 'public' / 'next.css').read_text(encoding='utf-8')
GUIDE = (Path(app.ROOT) / 'public' / 'guide' / 'guide.md').read_text(encoding='utf-8')


class BudgetTests(unittest.TestCase):
    def test_every_tier_adds_up_to_its_minutes_with_or_without_the_exam_drill(self):
        for t in tb.TIERS:
            for exam in (False, True):
                b = tb.budget(t, exam=exam)
                self.assertEqual(sum(b[p] for p in tb.PARTS), t, (t, exam))
                self.assertEqual(b['tier'], t)
        self.assertEqual(tb.budget(5, exam=True)['exam'], 0)  # five minutes: words and today's text, nothing else
        for t in (10, 15, 20):
            self.assertTrue(3 <= tb.budget(t, exam=True)['exam'] <= 5)
        for t in (30, 45, 60):
            self.assertTrue(6 <= tb.budget(t, exam=True)['exam'] <= 10)

    def test_the_tier_is_the_largest_not_above_the_minutes(self):
        self.assertEqual([tb.tier(m) for m in (None, 3, 5, 12, 30, 59, 90)], [10, 5, 5, 10, 30, 45, 60])

    def test_the_text_mode_follows_the_minutes(self):
        self.assertEqual(tb.budget(5)['read_mode'], 'glance')
        self.assertEqual(tb.budget(10)['read_mode'], 'core')
        self.assertEqual(tb.budget(10, exam=True)['read_mode'], 'listen-read')  # its minutes went to 考试小练
        self.assertEqual((tb.budget(45)['texts'], tb.budget(60)['texts']), (1, 2))
        self.assertLess(tb.read_minutes(190, 'glance'), tb.read_minutes(190, 'listen-read'))
        self.assertLess(tb.read_minutes(190, 'listen-read'), tb.read_minutes(190, 'core'))
        self.assertEqual(tb.over_at(15), 18)


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
            vs.save_plan(c, self.uid, {'book': 'mid', 'daily_new': 10, 'retention': 0.9})

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def path(self, c, minutes, goal='work', **kw):
        nx.save_profile(c, self.uid, {'level': 'B1', 'goal': goal, 'themes': [], 'minutes': minutes, **kw})
        return nx.home(c, self.uid)['path']


class PlanTests(Db):
    def test_every_step_says_its_minutes_part_and_group_and_only_must_counts(self):
        with app.db() as c:
            for m in nx.MINUTES:
                p = self.path(c, m)
                must = [s for s in p['steps'] if s['group'] == 'must']
                extra = [s for s in p['steps'] if s['group'] == 'extra']
                self.assertEqual(p['total'], len(must))
                self.assertEqual(p['done'], sum(1 for s in must if s['done']))
                self.assertEqual(p['must_minutes'], sum(s['minutes'] for s in must))
                self.assertLessEqual(len(extra), sk.EXTRA)
                self.assertEqual(p['budget'], tb.budget(m))
                for s in p['steps']:
                    self.assertIsInstance(s['minutes'], int)
                    self.assertIn(s['group'], ('must', 'extra', 'week'))
                    self.assertTrue(s['part'] in tb.PARTS or s['part'] == 'week')
                    self.assertNotRegex(s['sub'], r'\d+\s*分钟')  # the page writes the minutes, once (a title may say 十分钟)
                self.assertEqual([s['key'] for s in must[:1]], ['review'])  # words first, always 必做
                self.assertIn('read', [s['key'] for s in must])  # today's text, always 必做
                # 必做 first, then 还有时间的话, then 本周任务
                groups = [s['group'] for s in p['steps']]
                self.assertEqual(groups, sorted(groups, key=('must', 'extra', 'week').index))

    def test_besides_words_and_the_text_must_steps_fit_their_part(self):
        with app.db() as c:
            for m in nx.MINUTES:
                p, b = self.path(c, m), tb.budget(m)
                used = {}
                for s in p['steps']:
                    if s['group'] == 'must' and s['part'] not in ('words', 'read'):
                        used[s['part']] = used.get(s['part'], 0) + s['minutes']
                for part, mins in used.items():
                    self.assertLessEqual(mins, b[part] + 1, (m, part))

    def test_five_minutes_is_the_words_and_one_listen_of_todays_text(self):
        with app.db() as c:
            p = self.path(c, 5)
            must = [s for s in p['steps'] if s['group'] == 'must']
            self.assertEqual([s['key'] for s in must], ['review', 'read'])
            read = must[1]
            self.assertEqual((read['mode'], read['mode_label']), ('glance', '只听一遍，或只读一段'))
            # one step of the text is enough on a five-minute day
            c.execute("INSERT INTO next_progress(user_id,pack,step,created) VALUES(?,?,'listen',?)",
                      (self.uid, read['href'].split('/')[2], time.time()))
            c.commit()
            self.assertTrue(next(s for s in nx.home(c, self.uid)['path']['steps'] if s['key'] == 'read')['done'])

    def test_with_two_minutes_for_output_one_modelled_sentence_is_must_and_the_task_waits(self):
        with app.db() as c:
            p = self.path(c, 15)
            must = {s['key']: s for s in p['steps'] if s['group'] == 'must'}
            self.assertIn('model', must)
            self.assertEqual((must['model']['title'], must['model']['minutes']), ('仿写一句', 2))
            self.assertTrue(must['model']['href'].endswith('/output'))
            self.assertTrue(any(s['group'] == 'extra' and s['part'] in ('output', 'other') for s in p['steps']))
            # at 45 minutes the weak skill's own task is 必做
            p = self.path(c, 45)
            self.assertNotIn('model', [s['key'] for s in p['steps']])
            self.assertTrue(any(s['group'] == 'must' and s['part'] == 'output' for s in p['steps']))

    def test_ten_minutes_keeps_output_out_of_must(self):
        with app.db() as c:
            p = self.path(c, 10)
            self.assertFalse(any(s['group'] == 'must' and s['part'] == 'output' for s in p['steps']))
            self.assertTrue(any(s['group'] == 'extra' and s['part'] == 'output' for s in p['steps']))

    def test_the_weekly_exam_set_is_this_weeks_task_and_a_newcomer_may_skip_it(self):
        with app.db() as c:
            p = self.path(c, 15, goal='exam')
            wk = [s for s in p['steps'] if s['group'] == 'week']
            self.assertEqual([s['key'] for s in wk], ['exam'])
            self.assertIn('摸底，可以跳过', wk[0]['sub'])
            self.assertNotIn('exam', [s['key'] for s in p['steps'] if s['group'] != 'week'])
            self.assertEqual(p['total'], len([s for s in p['steps'] if s['group'] == 'must']))  # not counted
            c.execute('UPDATE next_profiles SET created=? WHERE user_id=?', (time.time() - 10 * 86400, self.uid)); c.commit()
            self.assertNotIn('摸底', next(s for s in nx.home(c, self.uid)['path']['steps'] if s['key'] == 'exam')['sub'])

    def test_the_exam_drill_takes_its_minutes_from_output_and_relisten_once_it_exists(self):
        calls = []

        def drill(c, uid, minutes, now=None):
            calls.append(minutes)
            return {'key': 'exam-drill', 'title': '考试小练：阅读一篇', 'sub': '四级阅读，4 题', 'href': '#/exam/cet4/drill', 'done': False, 'minutes': minutes}
        with app.db() as c, patch.object(ex, 'drill_step', drill, create=True):
            p = self.path(c, 30, goal='exam')
            self.assertEqual(p['budget'], tb.budget(30, exam=True))
            st = next(s for s in p['steps'] if s['key'] == 'exam-drill')
            self.assertEqual((st['group'], st['part'], st['minutes']), ('must', 'exam', 6))
            self.assertEqual(calls[-1], 6)
            self.assertFalse(any(s['group'] == 'must' and s['part'] == 'relisten' for s in p['steps']))
            p = self.path(c, 30, goal='work')  # not preparing for an exam: the usual day
            self.assertNotIn('exam-drill', [s['key'] for s in p['steps']])
            self.assertEqual(p['budget'], tb.budget(30))

    def test_the_words_cap_goes_to_vocab_service_once_it_takes_one(self):
        seen = []
        real = vs.counts

        def capped(c, uid, now=None, cap=None):
            seen.append(cap)
            return real(c, uid, now)
        with app.db() as c:
            with patch.object(vs, 'counts', capped):
                self.path(c, 20)
            self.assertEqual(seen[-1], tb.budget(20)['words'])


    def test_four_grammar_questions_once_the_plan_is_done(self):
        import grammar_bank as GB
        with app.db() as c:
            self.path(c, 30)
            m, code = GB.mix(c, self.uid, most=4)
            self.assertEqual(code, 200)
            self.assertLessEqual(len(m['items']), 4)
            self.assertGreater(len(m['items']), 0)


class StudiedTests(Db):
    def test_todays_minutes_come_from_the_records_and_long_gaps_do_not_count(self):
        day = at(2026, 11, 25, 0, 0)
        with app.db() as c:
            card = c.execute("INSERT INTO next_cards(user_id,text,norm,kind,created,due) VALUES(?,'a','a','word',?,?)", (self.uid, day, day)).lastrowid
            for k in range(11):  # 08:00 to 08:10, an answer a minute: ten minutes and the minute before the first
                c.execute('INSERT INTO next_reviews(user_id,card,rating,created) VALUES(?,?,3,?)', (self.uid, card, at(2026, 11, 25, 8, k)))
            c.execute("INSERT INTO next_progress(user_id,pack,step,created) VALUES(?,'p','read',?)", (self.uid, at(2026, 11, 25, 12, 0)))  # a sitting at noon
            c.commit()
            self.assertEqual(ps.active_minutes(c, self.uid, day, day + 86400), 12)
            c.execute("INSERT INTO next_exam_results(user_id,exam,paper,score,total,parts,seconds,created) VALUES(?,'cet4','x',1,2,'{}',900,?)",
                      (self.uid, at(2026, 11, 25, 20, 0)))  # an exam set counts its own fifteen minutes
            c.commit()
            self.assertEqual(ps.active_minutes(c, self.uid, day, day + 86400), 27)
            self.assertEqual(ps.active_minutes(c, self.uid, day + 86400, day + 2 * 86400), 0)

    def test_past_the_minutes_by_a_fifth_the_plan_says_so_until_must_is_done(self):
        now = at(2026, 11, 25, 10, 0)
        with app.db() as c:
            self.path(c, 5)
            card = c.execute("INSERT INTO next_cards(user_id,text,norm,kind,created,due) VALUES(?,'b','b','word',?,?)", (self.uid, 0, 0)).lastrowid
            for k in range(5):  # 09:56 to 10:00, an answer a minute: five minutes, not yet six
                c.execute('INSERT INTO next_reviews(user_id,card,rating,created) VALUES(?,?,3,?)', (self.uid, card, at(2026, 11, 25, 9, 56 + k) if k < 4 else now))
            c.commit()
            p = sk.daily_path(c, self.uid, nx.home(c, self.uid), now)
            self.assertEqual((p['studied'], p['over']), (5, False))
            c.execute('INSERT INTO next_reviews(user_id,card,rating,created) VALUES(?,?,3,?)', (self.uid, card, at(2026, 11, 25, 9, 55)))
            c.commit()
            p = sk.daily_path(c, self.uid, nx.home(c, self.uid), now)
            self.assertEqual(p['studied'], 6)
            self.assertEqual(p['over'], p['done'] < p['total'])


class BackTests(Db):
    """回归模式 (r28 第 2 段): three days or more away, the day back is short."""
    PID = 'v5-science-b2-noise-cancelling'

    def setUp(self):
        super().setUp()
        self.now = time.time()
        with app.db() as c:
            nx.save_profile(c, self.uid, {'level': 'B1', 'goal': 'work', 'themes': [], 'minutes': 30})
            c.execute('DELETE FROM next_cards WHERE user_id=?', (self.uid,))
            for k in range(100):  # 100 words due, from before the break
                c.execute("INSERT INTO next_cards(user_id,text,norm,kind,created,due,state,stability) VALUES(?,?,?,'word',?,?,'review',5)",
                          (self.uid, f'w{k}', f'w{k}', self.now - 30 * 86400, self.now - 5 * 86400))
            c.commit()

    def step(self, c, pid, step, days_ago):
        c.execute('INSERT OR IGNORE INTO next_progress(user_id,pack,step,created) VALUES(?,?,?,?)', (self.uid, pid, step, self.now - days_ago * 86400))
        c.commit()

    def plan(self, c, counts=None):
        """The plan with vocab_service.counts as it was before it sized the day's share (no cap: one round of 40 here),
        or as given."""
        real = vs.counts.__wrapped__ if hasattr(vs.counts, '__wrapped__') else vs.counts

        def old(c, uid, now=None):
            r = real(c, uid, now)
            return {k: v for k, v in r.items() if k not in ('catch_up', 'later', 'cap')}
        with patch.object(vs, 'counts', counts or old):
            return sk.daily_path(c, self.uid, nx.home(c, self.uid), self.now)

    def test_with_the_days_share_from_vocab_service_the_backlog_says_how_many_days(self):
        real = vs.counts

        def share(c, uid, now=None, cap=None):  # vocab_service once it sizes the day's share (r28 第 3 段, 语流 11)
            r = real(c, uid, now)
            return {**r, 'due': 40, 'new': 0, 'minutes': 6, 'later': 60, 'catch_up': {'left': 60, 'days': 5}, 'cap': cap}
        with app.db() as c:
            self.step(c, self.PID, 'listen', 10)
            p = self.plan(c, share)
            w = p['steps'][0]
            self.assertEqual((w['title'], w['sub'], w['minutes'], w['done']), ('单词：先复习最容易忘的 40 个', '补积压：还剩 60 个，大约 5 天补完', 6, False))
            self.assertEqual(p['back'], {'days': 9, 'left': 60, 'catch_days': 5})

            def ordinary(c, uid, now=None, cap=None):
                return {**real(c, uid, now), 'due': 12, 'new': 3, 'minutes': 5, 'later': 30, 'catch_up': None, 'cap': cap, 'new_paused': False}
            self.step(c, 'other-pack', 'listen', 1)  # yesterday: an ordinary day, the rest of the reviews later
            p = self.plan(c, ordinary)
            self.assertIsNone(p['back'])
            self.assertEqual(p['steps'][0]['sub'], '还有 30 个复习留到之后几天')
            p = self.plan(c, lambda c, uid, now=None, cap=None: {**ordinary(c, uid, now, cap), 'new_paused': True})
            self.assertEqual(p['steps'][0]['sub'], '还有 30 个复习留到之后几天 · 新词明天继续')

    def test_after_nine_days_away_one_round_of_words_and_a_text_nothing_else(self):
        with app.db() as c:
            self.step(c, self.PID, 'listen', 10)
            p = self.plan(c)
            self.assertEqual(p['back']['days'], 9)
            self.assertTrue(set(s['key'] for s in p['steps'] if s['group'] != 'week') <= set(sk.BACK_KEEP))
            self.assertFalse([s for s in p['steps'] if s['group'] == 'extra'])
            w = p['steps'][0]
            self.assertEqual((w['key'], w['title'], w['done']), ('review', '单词：先复习最该复习的 40 个', False))
            self.assertEqual(w['minutes'], vs.minutes_for(40, 0, vs.answer_seconds(c, self.uid, self.now)))
            self.assertEqual(p['back']['left'], vs.counts(c, self.uid, self.now)['due'] - 40)
            # the text read half way before the break comes back
            self.assertEqual(next(s for s in p['steps'] if s['key'] == 'read')['href'], f'#/m/{self.PID}')

    def test_the_round_is_done_after_forty_words_answered_today(self):
        with app.db() as c:
            self.step(c, self.PID, 'listen', 10)
            ids = [r[0] for r in c.execute('SELECT id FROM next_cards WHERE user_id=? ORDER BY id LIMIT 40', (self.uid,))]
            for i in ids:
                c.execute("INSERT INTO next_reviews(user_id,card,rating,created) VALUES(?,?,'good',?)", (self.uid, i, self.now - 60))
                c.execute('UPDATE next_cards SET due=? WHERE id=?', (self.now + 5 * 86400, i))
            c.commit()
            p = self.plan(c)
            w = p['steps'][0]
            self.assertTrue(w['done'])
            self.assertEqual(p['back']['left'], 60)
            self.assertIsNotNone(p['back'])  # still the day back after studying today

    def test_with_nothing_half_read_a_text_a_level_easier(self):
        with app.db() as c:
            for st in ('listen', 'read', 'check', 'output'):
                self.step(c, self.PID, st, 10)
            read = next(s for s in self.plan(c)['steps'] if s['key'] == 'read')
            self.assertIn('低一级（A2）', read['sub'])

    def test_yesterday_or_never_is_not_a_day_back(self):
        with app.db() as c:
            self.assertIsNone(self.plan(c)['back'])  # a new learner
            self.step(c, self.PID, 'listen', 3)  # two days missed
            self.assertIsNone(self.plan(c)['back'])
            self.step(c, 'other-pack', 'listen', 1)
            self.assertIsNone(self.plan(c)['back'])


class PageTests(unittest.TestCase):
    def test_the_page_shows_must_extra_this_weeks_task_and_the_over_line(self):
        for s in ('还有时间的话', '本周任务', 'tp-extra', 'tp-week', 'tp-over', '剩下的可以留到明天', 'must_minutes', 'left_minutes', 'tp-back', '欢迎回来', '之后几天慢慢补上',
                  "data-tap=\"home-more-grammar\"", '做 4 道语法题'):
            self.assertTrue(s in JS, s)
        for s in ('.tp-extra', '.tp-week', '.tp-over', '.tp-back'):
            self.assertTrue(s in CSS, s)

    def test_the_guide_explains_the_budget(self):
        for s in ('还有时间的话', '本周任务', '超过你定的', '仿写一句', '摸底，可以跳过', '几天没来，回来那天', '先复习最容易忘的 40 个', '大约 5 天补完'):
            self.assertTrue(s in GUIDE, s)


if __name__ == '__main__':
    unittest.main()
