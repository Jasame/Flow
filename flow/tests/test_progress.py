"""看得见的进步 (r27): 这周进步 on 今日 from the learner's own records only, the summary after a text, weeks at the
weekly goal counted up (never back to zero), and the Sunday progress mail with its unsubscribe link (mail goes to
FLOW_MAIL_OUTBOX files, never to a real address)."""
import datetime, json, os, re, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, progress_service as ps, vocab_service as vs, skills_service as sk  # noqa: E402

CN = datetime.timezone(datetime.timedelta(hours=8))
at = lambda *a: datetime.datetime(*a, tzinfo=CN).timestamp()
NOW = at(2026, 11, 25, 10, 0)        # a Wednesday; this week began on Monday 2026-11-23, last week on 2026-11-16
SUNDAY = at(2026, 11, 29, 20, 5)     # the Sunday mail of this week
PID = 'v5-science-b2-noise-cancelling'
JS = (Path(app.ROOT) / 'public' / 'next.js').read_text(encoding='utf-8')
CSS = (Path(app.ROOT) / 'public' / 'next.css').read_text(encoding='utf-8')


class Db(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outbox = Path(self.tmp.name) / 'outbox'
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_MAIL_OUTBOX': str(self.outbox), 'FLOW_PUBLIC_URL': 'https://flow.test'})]
        for p in self.patches:
            p.start()
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password,email) VALUES(?,?,?)', ('lin', 'x', 'lin@example.test'))
            self.uid = c.execute("SELECT id FROM users WHERE username='lin'").fetchone()[0]
            nx.save_profile(c, self.uid, {'level': 'B1', 'goal': next(iter(nx.GOALS)), 'themes': [], 'minutes': 10})

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def studied(self, c, *times):  # a step of a material at each time
        for t in times:
            c.execute("INSERT INTO next_progress(user_id,pack,step,created) VALUES(?,?,'read',?)", (self.uid, f'pack-{t}', t))
        c.commit()

    def word(self, c, text, added, known=0):
        return c.execute("INSERT INTO next_cards(user_id,text,norm,kind,created,due,known) VALUES(?,?,?,'word',?,?,?)",
                         (self.uid, text, text, added, added, known)).lastrowid

    def review(self, c, card, rating, t):
        c.execute('INSERT INTO next_reviews(user_id,card,rating,created) VALUES(?,?,?,?)', (self.uid, card, rating, t))

    def answer(self, c, correct, t, assisted=0, context='q', source='next:x'):
        c.execute("INSERT INTO learning_events(user_id,node,source,kind,item,context,correct,assisted,evaluator,details,created) "
                  "VALUES(?,?,?,?,?,?,?,?,'rule','{}',?)", (self.uid, 'skill:reading', f'{source}:{t}:{correct}', 'choice', 'i', context, correct, assisted, t))


class WeekTests(Db):
    def test_a_word_counts_once_when_it_is_first_recalled_on_a_later_day(self):
        with app.db() as c:
            same_day = self.word(c, 'commute', at(2026, 11, 23, 9))
            self.review(c, same_day, 'good', at(2026, 11, 23, 9, 5))          # the day it was added: not yet remembered
            self.review(c, same_day, 'good', at(2026, 11, 24, 8))             # the next day: remembered this week
            self.review(c, same_day, 'easy', at(2026, 11, 25, 8))             # again: still one word
            last = self.word(c, 'deadline', at(2026, 11, 16, 9))
            self.review(c, last, 'hard', at(2026, 11, 17, 9))                 # remembered last week
            self.review(c, last, 'good', at(2026, 11, 24, 9))                 # this week again: it stays last week's
            missed = self.word(c, 'drain', at(2026, 11, 22, 9))
            self.review(c, missed, 'again', at(2026, 11, 24, 9))              # forgotten: not remembered
            known = self.word(c, 'the', at(2026, 11, 20, 9), known=1)
            self.review(c, known, 'good', at(2026, 11, 24, 9))                # marked as already known: not new
            used = self.word(c, 'ledger', at(2026, 11, 22, 21))
            self.review(c, used, 'used', at(2026, 11, 23, 0, 30))             # written correctly in 用出来 after midnight (China time)
            c.commit()
            w = ps.week(c, self.uid, NOW, detail=True)
        self.assertEqual((w['remembered']['now'], w['remembered']['before']), (2, 1))
        self.assertEqual(sorted(w['remembered']['words']), ['commute', 'ledger'])

    def test_texts_finished_and_accuracy_against_last_week(self):
        with app.db() as c:
            c.execute("INSERT INTO next_progress VALUES(?,?,?,?)", (self.uid, PID, 'check', at(2026, 11, 24, 20)))
            c.execute("INSERT INTO next_progress VALUES(?,?,?,?)", (self.uid, 'other', 'check', at(2026, 11, 18, 20)))
            for k in range(4):
                self.answer(c, 1, at(2026, 11, 24, 9, k))
            self.answer(c, 0, at(2026, 11, 24, 9, 9))
            self.answer(c, 0, at(2026, 11, 24, 10), assisted=1)               # with a hint: left out
            self.answer(c, 0, at(2026, 11, 24, 11), context='placement')      # the placement test: left out
            for k in range(3):
                self.answer(c, k % 2, at(2026, 11, 18, 9, k))                 # last week: 3 questions, too few for a percentage
            c.commit()
            w = ps.week(c, self.uid, NOW, detail=True)
        self.assertEqual((w['finished']['now'], w['finished']['before']), (1, 1))
        self.assertEqual(w['finished']['titles'][0]['id'], PID)
        self.assertEqual(w['accuracy']['now'], {'right': 4, 'total': 5, 'rate': 80})
        self.assertEqual(w['accuracy']['before'], {'right': 1, 'total': 3, 'rate': None})

    def test_a_new_learner_has_zeros_not_made_up_numbers(self):
        with app.db() as c:
            st = nx.stats(c, self.uid)
        p = st['progress']
        self.assertEqual((p['remembered'], p['finished']), ({'now': 0, 'before': 0}, {'now': 0, 'before': 0}))
        self.assertEqual(p['accuracy']['now'], {'right': 0, 'total': 0, 'rate': None})
        self.assertEqual(p['mail'], {'on': True, 'email': True, 'hour': 20})
        self.assertEqual((st['habit']['done'], st['habit']['weeks']), (0, 0))


class WeeksTests(Db):
    def test_weeks_reached_only_count_up(self):
        with app.db() as c:
            self.studied(c, at(2026, 11, 2, 9), at(2026, 11, 4, 9),                     # 3 weeks ago: 2 days
                         at(2026, 11, 16, 9), at(2026, 11, 21, 9))                      # last week: 2 days (2 weeks ago: none)
            h = nx.habit(c, self.uid, 2, NOW)
            self.assertEqual((h['weeks'], h['streak']), (2, 1))  # a missed week breaks the run, not the total
            self.studied(c, at(2026, 11, 23, 9), at(2026, 11, 25, 8))
            self.assertEqual(nx.habit(c, self.uid, 2, NOW)['weeks'], 3)  # this week counts once it is reached

    def test_any_learning_makes_a_study_day(self):
        with app.db() as c:
            c.execute("INSERT INTO next_easy_reads(user_id,pack,words,seconds,wpm,rating,created) VALUES(?,?,?,?,?,'ok',?)", (self.uid, 'p', 300, 120, 150, at(2026, 11, 23, 9)))
            sk.log(c, self.uid, 'listening', 'dictation', 0.8)
            c.execute('UPDATE next_skill_events SET created=?', (at(2026, 11, 24, 9),))
            self.answer(c, 1, at(2026, 11, 25, 8))
            c.commit()
            h = nx.habit(c, self.uid, 3, NOW)
        self.assertEqual((h['done'], h['met']), (3, True))  # easy reading, a dictation and a question: three days

    def test_a_new_goal_counts_from_its_own_week_and_keeps_the_weeks_before(self):
        with patch('time.time', return_value=NOW), app.db() as c:
            self.studied(c, at(2026, 11, 9, 9), at(2026, 11, 10, 9), at(2026, 11, 11, 9),                    # 3 days
                         at(2026, 11, 16, 9), at(2026, 11, 17, 9), at(2026, 11, 18, 9), at(2026, 11, 19, 9))  # 4 days
            self.assertEqual(nx.stats(c, self.uid)['habit']['weeks'], 1)  # the default goal, 4 days
            nx.post(c, self.uid, '/api/next/habit', {'goal': 3})  # lowered: the 3-day week before still had 4 as its goal
            self.assertEqual(nx.stats(c, self.uid)['habit']['weeks'], 1)
            nx.post(c, self.uid, '/api/next/habit', {'goal': 6})  # raised: the week reached at 4 stays
            self.assertEqual(nx.habit(c, self.uid, 6, NOW)['weeks'], 1)
            nx.post(c, self.uid, '/api/next/habit', {'goal': 2})
            self.studied(c, at(2026, 11, 23, 9), at(2026, 11, 24, 9))
            self.assertEqual(nx.habit(c, self.uid, 2, NOW)['weeks'], 2)  # this week, at the goal set this week
            rows = [tuple(r) for r in c.execute('SELECT monday, goal FROM next_goal_weeks ORDER BY monday')]
            self.assertEqual(rows, [('0000-00-00', 4), ('2026-11-23', 2)])  # every week before this one: 4; from this one: 2

    def test_my_progress_counts_days_the_same_way(self):
        import growth_report as gr
        with app.db() as c:
            self.studied(c, at(2026, 11, 3, 9))
            c.execute("INSERT INTO next_relisten(user_id,pack,understood,created) VALUES(?,?,?,?)", (self.uid, 'p', 0.8, at(2026, 11, 5, 9)))
            c.commit()
            self.assertEqual(gr._days(c, self.uid, at(2026, 11, 1), at(2026, 12, 1)), 2)


class SummaryTests(Db):
    def test_the_three_lines_after_a_text(self):
        with app.db() as c:
            nx.save_card(c, self.uid, {'text': 'make ends meet', 'pack': PID})
            nx.save_card(c, self.uid, {'text': 'commute', 'pack': PID})
            nx.save_card(c, self.uid, {'text': 'elsewhere', 'pack': 'another-text'})
            body, st = ps.text_summary(c, self.uid, PID)
            self.assertEqual(st, 200)
            self.assertEqual([x['text'] for x in body['expressions']['saved']], ['make ends meet'])
            self.assertEqual([x['text'] for x in body['words']['saved']], ['commute'])
            self.assertTrue(body['expressions']['key'])  # the text's own expressions, to save when none were
            g = body['grammar']
            self.assertEqual(g['why'], 'check')  # nothing corrected yet: one of its points not yet checked with questions
            self.assertIn(g['id'], nx.pack_grammar(json.loads(c.execute('SELECT content FROM lab_packs WHERE id=?', (PID,)).fetchone()[0])))
            c.execute("INSERT INTO next_node_notes(user_id,node,pack,kind,detail,created) VALUES(?,?,?,?,?,?)",
                      (self.uid, 'tense-perfect', PID, 'flag', 'rid|I have went → I have gone', NOW))
            c.commit()
            g = ps.text_summary(c, self.uid, PID)[0]['grammar']
            self.assertEqual((g['id'], g['why'], g['times'], g['change']), ('tense-perfect', 'flag', 1, 'I have went → I have gone'))
            self.assertEqual(ps.text_summary(c, self.uid, 'no-such-text')[1], 404)

    def test_routes(self):
        with app.db() as c:
            self.assertEqual(nx.get(c, None, '/api/next/week', {})[1], 401)
            body, st = nx.get(c, self.uid, '/api/next/week', {})
            self.assertEqual((st, body['habit']['goal']), (200, 4))
            self.assertEqual(nx.get(c, self.uid, '/api/next/text-summary', {'pack': [PID]})[1], 200)
            self.assertEqual(nx.post(c, self.uid, '/api/next/weekly-mail', {'on': 'no'})[1], 400)
            self.assertEqual(nx.post(c, self.uid, '/api/next/weekly-mail', {'on': False})[0]['on'], False)
            self.assertEqual(nx.get(c, self.uid, '/api/next/weekly-mail', {})[0]['on'], False)


class MailTests(Db):
    def mails(self):
        return [f.read_text(encoding='utf-8') for f in sorted(self.outbox.glob('*.txt'))] if self.outbox.exists() else []

    def test_sunday_evening_with_the_week_and_a_link_to_stop_it(self):
        with app.db() as c:
            self.studied(c, at(2026, 11, 23, 9), at(2026, 11, 24, 9))
            c.execute("INSERT INTO next_progress VALUES(?,?,?,?)", (self.uid, PID, 'check', at(2026, 11, 24, 20)))
            card = self.word(c, 'commute', at(2026, 11, 23, 9)); self.review(c, card, 'good', at(2026, 11, 24, 8)); c.commit()
            self.assertEqual(ps.send_weekly(c, at(2026, 11, 29, 19, 55)), 0)  # before 20:00
            self.assertEqual(ps.send_weekly(c, at(2026, 11, 28, 20, 5)), 0)   # Saturday
            self.assertEqual(ps.send_weekly(c, SUNDAY), 1)
            self.assertEqual(ps.send_weekly(c, SUNDAY + 600), 0)              # once a Sunday
        m = self.mails()[0]
        self.assertIn('Subject: 语流 · 这周进步：记住 1 个新词，学完 1 篇', m)
        self.assertIn('· 每周目标：学了 2 天，目标 4 天，这周差 2 天。', m)
        self.assertIn('· 记住了 1 个新词（隔天复习还记得的）：commute', m)
        self.assertIn('· 学完 1 篇：《', m)
        token = re.search(r'https://flow\.test/#/weekly-off/([\w-]+)', m).group(1)
        self.assertIn(f'List-Unsubscribe: <https://flow.test/api/next/weekly-mail/off?t={token}>', m)
        self.assertIn('List-Unsubscribe-Post: List-Unsubscribe=One-Click', m)
        with app.db() as c:
            self.assertEqual(ps.unsubscribe(c, 'x' * 30)[1], 404)
            self.assertEqual(nx.post_public(c, None, '/api/next/weekly-mail/off', {'token': token}), ({'ok': True, 'on': False}, 200))
            self.assertFalse(ps.mail_state(c, self.uid)['on'])
            self.assertEqual(ps.send_weekly(c, SUNDAY + 7 * 86400), 0)  # turned off: no mail next Sunday
            nx.post_public(c, None, '/api/next/weekly-mail/off', {'token': token, 'on': True})  # 「撤销」 on the page
            self.studied(c, SUNDAY + 6 * 86400)
            self.assertEqual(ps.send_weekly(c, SUNDAY + 7 * 86400 + 60), 1)
        self.assertIn(token, self.mails()[-1])  # the same link every week

    def test_a_week_without_study_gets_a_nudge_for_three_weeks_then_none(self):
        with app.db() as c:
            self.studied(c, at(2026, 11, 12, 9))  # last study: Thursday two weeks before
            self.assertEqual(ps.send_weekly(c, SUNDAY), 1)
            m = self.mails()[0]
            self.assertIn('Subject: 语流 · 这周还没学，下周一起开个头', m)
            self.assertIn('上次学习是 11 月 12 日（周四）', m)
            self.assertIn('没学的周不会把以前的记录清零', m)
            self.assertEqual(ps.send_weekly(c, SUNDAY + 14 * 86400), 0)  # five weeks after: no more mail until they come back

    def test_the_goal_reached_is_in_the_subject(self):
        with app.db() as c:
            self.studied(c, *(at(2026, 11, d, 9) for d in (23, 24, 25, 26)))
            self.assertEqual(ps.send_weekly(c, SUNDAY), 1)
        self.assertIn('Subject: 语流 · 这周目标达成了', self.mails()[0])
        with app.db() as c:  # the next week reached too: two in all
            self.studied(c, at(2026, 11, 30, 9), *(at(2026, 12, d, 9) for d in (1, 2, 3)))
            self.assertEqual(ps.send_weekly(c, SUNDAY + 7 * 86400), 1)
        self.assertIn('Subject: 语流 · 这周目标达成，一共 2 周了', self.mails()[-1])

    def test_no_email_no_mail_and_the_daily_reminder_does_not_repeat_it(self):
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('noemail', 'x'))
            self.studied(c, at(2026, 11, 24, 9))
            vs.set_reminder(c, self.uid, {'enabled': True, 'hour': 20})
            card = self.word(c, 'commute', at(2026, 11, 20, 9)); c.execute('UPDATE next_cards SET due=?, state=? WHERE id=?', (at(2026, 11, 28), 'review', card)); c.commit()
            self.assertEqual(ps.send_weekly(c, SUNDAY), 1)  # the learner with an email only
            self.assertEqual(vs.send_reminders(c, SUNDAY + 60, lambda *a: self.fail('the weekly mail already said it')), 0)
            self.assertIn('个单词到了复习时间', self.mails()[0])
            self.assertEqual(vs.send_reminders(c, at(2026, 11, 30, 20, 5), lambda *a: None), 1)  # Monday: as before

    def test_one_click_unsubscribe_from_a_mail_app(self):
        with app.db() as c:
            self.studied(c, at(2026, 11, 24, 9))
            ps.send_weekly(c, SUNDAY)
        token = re.search(r'weekly-mail/off\?t=([\w-]+)', self.mails()[0]).group(1)
        srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            def post(body, ctype):
                req = urllib.request.Request(f'http://127.0.0.1:{srv.server_address[1]}/api/next/weekly-mail/off?t={token}', data=body, headers={'Content-Type': ctype})
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:
                        return r.status
                except urllib.error.HTTPError as e:
                    return e.code
            self.assertEqual(post(b'something=else', 'application/x-www-form-urlencoded'), 400)
            self.assertEqual(post(b'List-Unsubscribe=One-Click', 'application/x-www-form-urlencoded'), 200)
        finally:
            srv.shutdown(); srv.server_close()
        with app.db() as c:
            self.assertFalse(ps.mail_state(c, self.uid)['on'])



class FinishTests(Db):
    """r27 收尾: a text studied again ticks the plan; 新学的词 counts first answers; a pile of due words comes first."""
    def test_a_text_studied_again_ticks_todays_plan_and_counts_as_finished(self):
        import time as _t, skills_service as sk
        now = _t.time()
        with app.db() as c:
            for step in ('listen', 'read', 'check'):  # first studied ten days ago
                c.execute('INSERT INTO next_progress VALUES(?,?,?,?)', (self.uid, PID, step, now - 10 * 86400))
            c.commit()
            for step in ('listen', 'read', 'check'):  # studied again today
                nx.mark(c, self.uid, PID, step)
            first = c.execute("SELECT created FROM next_progress WHERE user_id=? AND pack=? AND step='check'", (self.uid, PID)).fetchone()[0]
            self.assertLess(first, now - 9 * 86400)  # the first time is kept (复听 and 这周进步 read it as first studied)
            home = nx.home(c, self.uid)
            read = next(x for x in home['path']['steps'] if x['key'] == 'read')
            self.assertEqual((read['sub'], read['done']), (json.loads(c.execute('SELECT content FROM lab_packs WHERE id=?', (PID,)).fetchone()[0])['title'], True))
            self.assertIn(PID, ps._finished(c, self.uid, now - 3600, now + 1))
            self.assertEqual(sk.report(c, self.uid)['materials'], 1)
            nx.mark(c, self.uid, PID, 'check')  # twice the same day: one row
            self.assertEqual(c.execute('SELECT COUNT(*) FROM next_step_log WHERE user_id=? AND step=?', (self.uid, 'check')).fetchone()[0], 1)

    def test_new_words_are_words_answered_for_the_first_time(self):
        import time as _t, skills_service as sk, growth_report as gr
        now = _t.time()
        with app.db() as c:
            queued = self.word(c, 'queued', now - 3600)                    # brought in by 今日, never answered
            fresh = self.word(c, 'fresh', now - 3600); self.review(c, fresh, 'again', now - 1800)
            old = self.word(c, 'older', now - 40 * 86400); self.review(c, old, 'good', now - 40 * 86400); self.review(c, old, 'good', now - 600)
            known = self.word(c, 'known', now - 3600, known=1); self.review(c, known, 'known', now - 1200)
            c.commit()
            self.assertEqual(sk.report(c, self.uid)['learned'], 1)          # fresh only
            self.assertEqual(ps.new_words(c, self.uid, now - 86400, now + 1), 1)
            lo, hi = gr._month(None, now)[:2]
            self.assertEqual(gr._figures(c, self.uid, lo, hi)['new_words'], 1)

    def test_a_pile_of_due_words_is_next_weeks_focus(self):
        import time as _t, skills_service as sk
        now = _t.time()
        with app.db() as c:
            for k in range(101):
                c.execute("INSERT INTO next_cards(user_id,text,norm,kind,created,due,state) VALUES(?,?,?,'word',?,?,'review')",
                          (self.uid, f'w{k}', f'w{k}', now - 30 * 86400, now - 86400))
            c.commit()
            self.assertTrue(sk.report(c, self.uid)['focus'].startswith('先把单词积压清掉：现在有 101 个单词到了复习时间'))

    def test_study_again_offers_the_next_recommendation(self):
        self.assertIn("const more1 = h.today.find(m => m && m.id !== readId", JS)
        self.assertIn("href=\"${more1 ? '#/m/' + encodeURIComponent(more1.id) : '#/library'}\"", JS)


class PageTests(unittest.TestCase):
    def test_the_page_has_the_card_the_summary_and_the_unsubscribe_page(self):
        for s in ('function weekCardHTML', 'id="weekCard"', 'data-tap="home-week"', 'function weekSheet', "api('/api/next/week')",
                  'function finishCard', "api('/api/next/text-summary?pack='", "'finish-grammar')", 'function weeklyOffView',
                  "api('/api/next/weekly-mail/off'", "name === 'weekly-off'", 'function weeklyMailSheet', "'me-weekly-mail')",
                  '已达成 ${', '一共达成 ${'):
            self.assertIn(s, JS, s)
        self.assertNotIn('连续 ${hb.streak} 周', JS)  # weeks are counted up, never as a run that breaks
        for s in ('.week-card', '.wk-tiles', '.fin-sum'):
            self.assertIn(s, CSS, s)


if __name__ == '__main__':
    unittest.main()
