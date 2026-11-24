"""考试冲刺 (r27): the exam goal and its date, the countdown word plan, the score trend, question-type practice
(original items whose answers rest on their texts) and what 今日's plan adds in the last four weeks."""
import datetime, json, re, sys, tempfile, time, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, exam_service as ex, exam_sprint as sp, exam_types as T, vocab_service as vs

DAY = 86400


def words(line):
    """How the page splits a 改错 line into words to tap (42-sprint.js does the same)."""
    return [''.join(ch for ch in w.lower() if ch.isalpha() or ch in "'-").strip("'-") for w in line.split()]


class ContentTests(unittest.TestCase):
    """Every answer rests on its text, and every set is whole."""

    def test_two_types_per_exam_about_twenty_items_each(self):
        self.assertEqual(set(T.TYPES), set(ex.EXAMS))
        for exam, types in T.TYPES.items():
            self.assertEqual(len(types), 2, exam)
            for t in types:
                n = sum(len(s['items']) for s in t['sets'])
                self.assertTrue(18 <= n <= 22, (exam, t['id'], n))
                self.assertTrue(t['how'])

    def test_answers_rest_on_the_text(self):
        for exam, types in T.TYPES.items():
            for t in types:
                for s in t['sets']:
                    k, items, at = t['kind'], s['items'], f"{exam}/{s['id']}"
                    self.assertTrue(all(i['why'] for i in items), at)
                    if k in ('cloze', 'bank'):  # one gap per item, numbered in order
                        self.assertEqual([int(x) for x in re.findall(r'\{(\d+)\}', s['text'])], list(range(1, len(items) + 1)), at)
                    if k == 'bank':  # each option at most once, and more options than gaps
                        answers = [i['answer'] for i in items]
                        self.assertEqual(len(set(answers)), len(answers), at)
                        self.assertGreater(len(s['bank']), len(items), at)
                    if k in ('cloze', 'choice'):
                        for i in items:
                            self.assertEqual(len(set(i['options'])), 4, at)
                            self.assertIn(i['answer'], range(4))
                            if k == 'choice':
                                self.assertIn('____', i['prompt'], at)
                    if k == 'match':  # the quoted sentence is in the answer's paragraph and in no other
                        for i in items:
                            self.assertEqual([j for j, p in enumerate(s['paras']) if i['evidence'] in p], [i['answer']], (at, i['prompt']))
                    if k == 'headings':
                        self.assertEqual(len(items), len(s['paras']))
                        self.assertEqual(len({i['answer'] for i in items}), len(items), at)
                        for j, i in enumerate(items):
                            self.assertIn(i['evidence'], s['paras'][j], at)
                    if k == 'tfng':  # TRUE and FALSE quote the text; NOT GIVEN explains what the text does not say
                        for i in items:
                            self.assertEqual(i['answer'] == 2, i['evidence'] == '', (at, i['prompt']))
                            if i['evidence']:
                                self.assertIn(i['evidence'], s['text'], at)
                        self.assertEqual({i['answer'] for i in items}, {0, 1, 2}, at)
                    if k == 'proof':  # the wrong word is in its line exactly once, so a tap finds it
                        for i in items:
                            self.assertEqual(words(s['lines'][i['line']]).count(i['wrong'].lower()), 1, (at, i['wrong']))
                            self.assertNotEqual(i['wrong'], i['fix'])

    def test_answer_positions_are_spread(self):
        pos = [i['answer'] for types in T.TYPES.values() for t in types if t['kind'] in ('cloze', 'choice') for s in t['sets'] for i in s['items']]
        self.assertTrue(all(pos.count(k) > len(pos) / 8 for k in range(4)), [pos.count(k) for k in range(4)])

    def test_labelled_original(self):
        self.assertIn('不是真题', sp.TYPES_NOTE)
        self.assertIn('原创', sp.TYPES_NOTE)
        self.assertIn('None is taken or adapted from a past paper', T.__doc__)


class SprintTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'sprint.db'); self.p.start()
        app.init(); self.c = app.db()
        for n in ('learner', 'other', 'new'):
            self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()
        for uid in (1, 2):
            nx.save_profile(self.c, uid, {'level': 'B1', 'goal': 'daily', 'themes': [], 'minutes': 15})
        self.now = time.time()
        self.today = sp._today(self.now)

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def day(self, n):
        return (self.today + datetime.timedelta(days=n)).isoformat()

    def goal(self, exam, n=None, uid=1):
        return sp.set_goal(self.c, uid, {'exam': exam, 'date': self.day(n) if n is not None else ''}, self.now)

    # ---------------- the goal ----------------

    def test_goal_is_stored_in_the_profile_and_checked(self):
        cols = {r[1] for r in self.c.execute('PRAGMA table_info(next_profiles)')}
        self.assertTrue({'exam', 'exam_date'} <= cols)
        out, code = self.goal('cet4', 30)
        self.assertEqual(code, 200)
        self.assertEqual(out['goal'], {'exam': 'cet4', 'date': self.day(30), 'title': '大学英语四级', 'short': '四级'})
        self.assertEqual((nx.profile(self.c, 1)['exam'], nx.profile(self.c, 1)['exam_date']), ('cet4', self.day(30)))
        # saving the learning goal again keeps the exam
        nx.save_profile(self.c, 1, {'level': 'B2', 'goal': 'exam', 'themes': [], 'minutes': 20})
        self.assertEqual(sp.goal(self.c, 1)['exam'], 'cet4')
        self.assertEqual(self.goal('toefl', 30)[1], 400)  # a word book, not one of the eight exams
        self.assertEqual(self.goal('cet4', -1)[1], 400)  # in the past
        self.assertEqual(sp.set_goal(self.c, 1, {'exam': 'cet4', 'date': '13/12/2026'}, self.now)[1], 400)
        self.assertEqual(sp.set_goal(self.c, 3, {'exam': 'cet4'}, self.now)[1], 400)  # no profile yet: answer the questions first
        self.assertEqual(self.goal('', 30)[0]['goal'], None)  # 不考试 clears it, date too
        self.assertIsNone(nx.profile(self.c, 1)['exam_date'])

    # ---------------- the countdown ----------------

    def test_countdown_says_plainly_whether_the_plan_keeps_up(self):
        size = len(vs.book_words()['cet4'])
        self.goal('cet4')
        cd = sp.countdown(self.c, 1, self.now)
        self.assertEqual((cd['status'], cd['left'], cd['size'], cd['days']), ('no_date', size, size, None))
        self.goal('cet4', 60)
        self.assertEqual(sp.countdown(self.c, 1, self.now)['status'], 'no_plan')
        vs.save_plan(self.c, 1, {'book': 'mid', 'daily_new': 10, 'retention': 0.9})
        cd = sp.countdown(self.c, 1, self.now)
        self.assertEqual((cd['status'], cd['plan_book']), ('other_book', 'mid'))
        # 60 days: new words end a week before, so 53 days of new words
        vs.save_plan(self.c, 1, {'book': 'cet4', 'daily_new': 10, 'retention': 0.9})
        cd = sp.countdown(self.c, 1, self.now)
        self.assertEqual((cd['study_days'], cd['review_days'], cd['need']), (53, 7, -(-size // 53)))
        self.assertEqual(cd['status'], 'behind')
        self.assertTrue(cd['too_many'])  # 70-odd a day is more than can be remembered
        self.assertEqual(cd['suggest'], sp.EASY_MAX)
        self.assertEqual(cd['suggest_reach'], sp.EASY_MAX * 53)
        self.assertEqual(cd['reach'], 10 * 53)
        # a year ahead: about 11 a day, so 10 a day is behind but a reachable number is suggested
        self.goal('cet4', 365)
        cd = sp.countdown(self.c, 1, self.now)
        self.assertEqual((cd['status'], cd['too_many'], cd['suggest']), ('behind', False, 15))
        vs.save_plan(self.c, 1, {'book': 'cet4', 'daily_new': 15, 'retention': 0.9})
        cd = sp.countdown(self.c, 1, self.now)
        self.assertEqual((cd['status'], cd['suggest']), ('on_time', None))
        self.goal('cet4', 0)
        self.assertEqual(sp.countdown(self.c, 1, self.now)['status'], 'today')
        self.c.execute('UPDATE next_profiles SET exam_date=? WHERE user_id=1', (self.day(-3),)); self.c.commit()
        self.assertEqual(sp.countdown(self.c, 1, self.now)['status'], 'past')

    def test_words_studied_and_skipped_are_not_left(self):
        self.goal('cet4', 40)
        vs.save_plan(self.c, 1, {'book': 'cet4', 'daily_new': 20, 'retention': 0.9})
        before = sp.countdown(self.c, 1, self.now)['left']
        for _, w in vs.book_words()['cet4'][:30]:
            self.c.execute("INSERT INTO next_cards(user_id,text,norm,kind,created,due,state,source) VALUES(1,?,?,'word',?,?,'review','book')", (w, w, self.now, self.now))
        self.c.commit()
        cd = sp.countdown(self.c, 1, self.now)
        self.assertEqual(cd['left'], before - 30)
        self.assertEqual(cd['week_avg'], round(30 / 7, 1))  # really learned in the last seven days

    def test_home_and_plan_add_the_weekly_set_and_grammar_in_the_last_four_weeks(self):
        self.goal('cet6', 40)
        h = nx.home(self.c, 1)
        self.assertEqual(h['sprint'], {'exam': 'cet6', 'short': '六级', 'days': 40, 'status': 'no_plan', 'sprint': False})
        keys = [s['key'] for s in h['path']['steps']]
        self.assertNotIn('exam', keys); self.assertNotIn('exam-grammar', keys)  # goal 'daily', six weeks out
        self.goal('cet6', 20)
        steps = {s['key']: s for s in nx.home(self.c, 1)['path']['steps']}
        self.assertEqual((steps['exam']['href'], steps['exam']['title']), ('#/exam/cet6', '考试练习：六级'))
        self.assertIn('考前 20 天', steps['exam']['sub'])
        g = steps['exam-grammar']
        self.assertEqual((g['href'], g['done']), ('#/mix/exam/cet6', False))
        # the round: that exam's points (B1, B2), answered from 'exam', ticks the step
        m, code = nx.GB.mix(self.c, 1, exam='cet6')
        self.assertEqual((code, m['kind']), (200, 'exam'))
        self.assertTrue(all(nx.node_level(n['id']) in ('B1', 'B2') for n in m['nodes']))
        for q in m['items'][:4]:
            nx.node_answer(self.c, 1, {'question': q['id'], 'choice': 0, 'from': 'exam'})
        self.assertEqual(sp.grammar_today(self.c, 1), 4)
        self.assertTrue(next(s for s in nx.home(self.c, 1)['path']['steps'] if s['key'] == 'exam-grammar')['done'])
        self.assertIsNone(nx.home(self.c, 2).get('sprint'))  # no goal, nothing added
        self.assertNotIn('exam-grammar', [s['key'] for s in nx.home(self.c, 2)['path']['steps']])

    # ---------------- 成绩走势 ----------------

    def test_trend_has_every_part_oldest_first(self):
        for k in range(3):
            p, _ = ex.paper(self.c, 1, 'cet4')
            r, _ = ex.submit(self.c, 1, {'paper': p['paper'], 'answers': {'vocab': [0] * 10, 'grammar': [0] * 8, 'reading': [0] * 4}, 'seconds': 600})
            self.c.execute('UPDATE next_exam_results SET created=? WHERE paper=?', (self.now - (3 - k) * DAY, p['paper'])); self.c.commit()
        tr = sp.trend(self.c, 1, 'cet4')
        self.assertEqual(len(tr), 3)
        self.assertEqual(set(tr[0]['parts']), {'vocab', 'grammar', 'reading'})
        self.assertEqual([t['day'] for t in tr], sorted(t['day'] for t in tr))
        self.assertEqual(sp.trend(self.c, 2, 'cet4'), [])
        o, _ = ex.overview(self.c, 1)
        cet4 = next(e for e in o['exams'] if e['id'] == 'cet4')
        self.assertEqual(len(cet4['trend']), 3)
        self.assertEqual([t['id'] for t in cet4['types']], ['banked', 'match'])

    # ---------------- 题型专练 ----------------

    def test_a_set_hides_its_answers_and_is_graded_on_submit(self):
        for exam, types in T.TYPES.items():
            for t in types:
                s, code = sp.type_set(self.c, 1, exam, t['id'])
                self.assertEqual(code, 200)
                blob = json.dumps(s['set'], ensure_ascii=False)
                for key in ('"answer"', '"why"', '"evidence"', '"wrong"', '"fix"'):
                    self.assertNotIn(key, blob, (exam, t['id']))
                self.assertIn('不是真题', s['note'])
        s, _ = sp.type_set(self.c, 1, 'cet4', 'banked')
        full = T.TYPES['cet4'][0]['sets'][0]
        right = [i['answer'] for i in full['items']]
        out, code = sp.type_submit(self.c, 1, {'exam': 'cet4', 'type': 'banked', 'set': s['set']['id'], 'answers': right[:9] + [None]})
        self.assertEqual((code, out['right'], out['of'], out['saved']), (200, 9, 10, True))
        self.assertFalse(out['items'][9]['correct']); self.assertTrue(out['items'][9]['why'])
        # the next call serves the set not done yet, and the list remembers the last result
        self.assertEqual(sp.type_set(self.c, 1, 'cet4', 'banked')[0]['set']['id'], 'banked-2')
        self.assertEqual(sp.type_list(self.c, 1, 'cet4')[0]['last'], {'right': 9, 'of': 10})
        # 改错: the tapped word, compared without case or punctuation
        proof = T.TYPES['tem8'][0]['sets'][0]
        taps = [i['wrong'].upper() + ',' for i in proof['items']]
        out, _ = sp.type_submit(self.c, 1, {'exam': 'tem8', 'type': 'proof', 'set': proof['id'], 'answers': taps})
        self.assertEqual(out['right'], 10)
        self.assertEqual(out['items'][5]['fix'], 'few')
        # a guest can practise; nothing is kept
        out, _ = sp.type_submit(self.c, None, {'exam': 'ielts', 'type': 'tfng', 'set': 'tfng-1', 'answers': [0] * 7})
        self.assertFalse(out['saved'])
        self.assertEqual(sp.type_submit(self.c, 1, {'exam': 'ielts', 'type': 'tfng', 'set': 'nope', 'answers': []})[1], 404)
        self.assertEqual(sp.type_set(self.c, 1, 'cet4', 'nope')[1], 404)

    def test_routes(self):
        self.assertEqual(nx.get(self.c, None, '/api/next/exam/type', {'exam': ['ky'], 'type': ['newtype']})[1], 200)
        self.assertEqual(nx.get(self.c, None, '/api/next/exam/goal', {})[1], 401)
        self.assertEqual(nx.post(self.c, 1, '/api/next/exam/goal', {'exam': 'ielts', 'date': self.day(10)})[1], 200)
        g, code = nx.get(self.c, 1, '/api/next/exam/goal', {})
        self.assertEqual((code, g['goal']['exam'], len(g['exams'])), (200, 'ielts', 8))
        self.assertEqual(nx.post_public(self.c, None, '/api/next/exam/type', {'exam': 'zk', 'type': 'dialog', 'set': 'dialog-1', 'answers': []})[1], 200)


if __name__ == '__main__':
    unittest.main()
