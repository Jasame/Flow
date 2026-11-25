import unittest, tempfile, sys, os, sqlite3, time, json, base64, datetime
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, fsrs, next_service as nx, vocab_service as vs


class FsrsTests(unittest.TestCase):
    def test_new_item_goes_through_steps_then_grows(self):
        now = 1_800_000_000
        a = fsrs.review({}, 'good', now, rnd=None)
        self.assertEqual((a['state'], a['step'], a['due'] - now), ('learning', 1, 600))
        b = fsrs.review(a, 'good', now + 600, rnd=None)
        self.assertEqual(b['state'], 'review'); self.assertGreaterEqual(b['interval'], 1)
        c = fsrs.review(b, 'good', b['due'], rnd=None)
        self.assertGreater(c['interval'], b['interval']); self.assertGreater(c['stability'], b['stability'])
        d = fsrs.review(c, 'again', c['due'], rnd=None)
        self.assertEqual((d['state'], d['lapses'], d['due'] - c['due']), ('relearning', 1, 600))
        self.assertLess(d['stability'], c['stability'])

    def test_retention_target_changes_interval(self):
        self.assertGreater(fsrs.interval_days(10, 0.8), fsrs.interval_days(10, 0.9))
        self.assertGreater(fsrs.interval_days(10, 0.9), fsrs.interval_days(10, 0.95))
        self.assertEqual(fsrs.interval_days(10, 0.9), 10)  # stability is defined at 90% recall
        self.assertAlmostEqual(fsrs.retrievability(10, 10), 0.9, places=6)

    def test_fuzz_stays_near_interval(self):
        for days in (3, 10, 50, 300):
            for r in (0.0, 0.5, 0.999):
                f = fsrs.fuzz(days, lambda: r)
                self.assertLessEqual(abs(f - days), max(2, days * 0.1)); self.assertGreaterEqual(f, 2)


class VocabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'v.db'); self.p.start()
        app.init(); self.c = app.db()
        for n in ('learner', 'other'): self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def age(self, cid, days):
        self.c.execute('UPDATE next_cards SET due=?, last=? WHERE id=?', (time.time() - 1, time.time() - days * 86400, cid)); self.c.commit()

    def test_saved_expression_review_cycle(self):
        cid = nx.save_card(self.c, 1, {'text': 'make the bus'})[0]['card']['id']
        q = vs.queue(self.c, 1); self.assertEqual((q['due'], q['new'], q['items'][0]['mode']), (0, 1, 'recall'))
        r = vs.rate(self.c, 1, {'id': cid, 'rating': 'good', 'mode': 'recall', 'ms': 2300})[0]
        self.assertEqual(r['card']['state'], 'learning'); self.assertEqual(vs.queue(self.c, 1)['items'], [])
        self.c.execute('UPDATE next_cards SET due=0 WHERE id=?', (cid,)); self.c.commit()
        r = vs.rate(self.c, 1, {'id': cid, 'rating': 'good'})[0]['card']; self.assertEqual(r['state'], 'review')
        s1 = r['stability']; self.age(cid, 3)
        r = vs.rate(self.c, 1, {'id': cid, 'rating': 'good'})[0]['card']; self.assertGreater(r['stability'], s1)
        self.age(cid, 10)
        r = vs.rate(self.c, 1, {'id': cid, 'rating': 'again'})[0]['card']
        self.assertEqual((r['state'], r['lapses']), ('relearning', 1))
        self.assertEqual(vs.rate(self.c, 2, {'id': cid, 'rating': 'good'})[1], 404)
        self.assertEqual(vs.rate(self.c, 1, {'id': cid, 'rating': 'meh'})[1], 400)
        self.assertEqual(nx.stats(self.c, 1)['reviews_week'], 4)
        logged = self.c.execute('SELECT mode, ms FROM next_reviews ORDER BY id LIMIT 1').fetchone()
        self.assertEqual((logged['mode'], logged['ms']), ('recall', 2300))

    def test_word_book_plan_daily_new_and_known(self):
        self.assertEqual(vs.save_plan(self.c, 1, {'book': 'nope'})[1], 400)
        self.assertEqual(vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 7})[1], 200)  # any number from 1 to 200
        self.assertEqual(vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 500})[1], 400)
        o = vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 5, 'retention': 0.9})[0]
        self.assertEqual(o['plan']['book'], 'core'); self.assertGreater(o['books'][0]['size'], 1500)
        q = vs.queue(self.c, 1)
        words = [i for i in q['items'] if i['source'] == 'book']
        self.assertEqual(len(words), 5); self.assertEqual(q['new'], 5)
        self.assertTrue(all(i['mode'] == 'recognize' and i['kind'] == 'word' and i['meaning'] for i in words))
        self.assertEqual(len([i for i in vs.queue(self.c, 1)['items'] if i['source'] == 'book']), 5)  # no top-up twice a day
        self.c.execute("UPDATE next_cards SET created=created-86400 WHERE source='book'"); self.c.commit()
        self.assertEqual(vs.introduce(self.c, 1), 0)  # yesterday's five are still unstudied: don't pile up more
        first = words[0]['id']
        self.assertEqual(vs.set_known(self.c, 1, {'id': first})[1], 200)
        self.assertNotIn(first, [i['id'] for i in vs.queue(self.c, 1)['items']])
        o = vs.overview(self.c, 1)
        self.assertEqual(o['mastered'], 1); self.assertEqual(o['book']['started'], 1)  # 已学: studied or known, not merely queued
        self.assertIsNotNone(o['book']['finish']); self.assertGreater(o['book']['skipped'], 100)  # the everyday words of 基础词汇
        self.assertEqual(len(o['forecast']), 7); self.assertEqual(len(o['calendar']), 35)
        self.assertEqual(vs.overview(self.c, 2)['total'], 0)

    def test_examples_audio_and_reading_links(self):
        ex = vs.examples('decision', 'B1')
        self.assertTrue(ex); self.assertTrue(all('decision' in e['text'].lower() for e in ex))
        self.assertEqual(len({e['pack'] for e in ex}), len(ex))
        cid = nx.save_card(self.c, 1, {'text': 'decision', 'context': 'It was a hard decision.'})[0]['card']['id']
        item = vs.queue(self.c, 1)['items'][0]
        self.assertEqual(item['id'], cid); self.assertEqual(item['mode'], 'recognize')
        self.assertTrue(all(e['text'] != 'It was a hard decision.' for e in item['examples']))
        mine = vs.mine_in_text(self.c, 1, 'Two decisions were made. Nothing else.')
        self.assertEqual(mine, [{'form': 'decisions', 'id': cid}])
        self.assertIsNone(vs.met_in_reading(self.c, 1, 'decisions'))  # still new: nothing to bring forward
        self.c.execute("UPDATE next_cards SET state='review', stability=10, difficulty=5, last=?, due=? WHERE id=?",
                       (time.time() - 2 * 86400, time.time() + 8 * 86400, cid)); self.c.commit()
        self.assertTrue(vs.met_in_reading(self.c, 1, 'decisions')['moved'])
        self.assertLessEqual(self.c.execute('SELECT due FROM next_cards WHERE id=?', (cid,)).fetchone()[0], time.time())
        self.assertEqual(vs.queue(self.c, 1)['due'], 1)

    def test_modes_follow_stability(self):
        row = lambda **k: {'kind': 'word', 'context': '', 'text': 'x', 'state': 'review', 'stability': 1, **k}
        self.assertEqual(vs.mode(row(state='new', stability=None)), 'recognize')
        self.assertEqual(vs.mode(row(stability=1)), 'recognize')
        self.assertEqual(vs.mode(row(stability=8)), 'recall')
        self.assertEqual(vs.mode(row(stability=40)), 'spell')
        self.assertEqual(vs.mode(row(kind='phrase', text='make it', context='We can make it.')), 'cloze')

    def test_vocab_test_estimate_corrects_for_guessing(self):
        items = vs.test_items(seed=1)['items']
        self.assertGreaterEqual(len(items), 40)
        fakes = [w for w in items if w in vs.PSEUDO]; self.assertEqual(len(fakes), 6)
        band = {w: k for k in vs.BOOKS for _, w in vs.book_words()[k]}
        honest = {w: band.get(w) in ('core', 'mid') for w in items}
        r = vs.score_test(self.c, None, {'answers': honest})[0]
        sizes = {k: len(vs.book_words()[k]) for k in vs.BOOKS}
        self.assertEqual(r['suggest'], 'high'); self.assertAlmostEqual(r['estimate'], sizes['core'] + sizes['mid'], delta=200)
        self.assertFalse(r['guessing']); self.assertEqual(r['titles']['high'], '高阶词汇')
        r = vs.score_test(self.c, None, {'answers': {w: True for w in items}})[0]
        self.assertTrue(r['guessing']); self.assertEqual(r['estimate'], 0)
        self.assertEqual(vs.score_test(self.c, None, {'answers': {}})[1], 400)

    def test_import_words_and_phrases(self):
        r = vs.import_words(self.c, 1, {'text': 'serendipity\nmake ends meet, 中文\nDecisions'})[0]
        self.assertEqual((r['added'], r['skipped']), (3, 0))
        rows = {x['norm']: x for x in self.c.execute('SELECT * FROM next_cards WHERE user_id=1')}
        self.assertEqual(rows['make ends meet']['kind'], 'phrase'); self.assertEqual(rows['serendipity']['source'], 'import')
        self.assertEqual(vs.import_words(self.c, 1, {'text': 'serendipity'})[0]['skipped'], 1)
        self.assertEqual(vs.import_words(self.c, 1, {'text': '只有中文'})[1], 400)

    def test_sm2_cards_migrate_without_losing_progress(self):
        c = sqlite3.connect(':memory:'); c.row_factory = sqlite3.Row
        c.executescript('''CREATE TABLE users(id INTEGER PRIMARY KEY);
CREATE TABLE next_cards(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, text TEXT NOT NULL, norm TEXT NOT NULL, meaning TEXT NOT NULL DEFAULT '',
 context TEXT NOT NULL DEFAULT '', pack TEXT, kind TEXT NOT NULL DEFAULT 'phrase', created REAL NOT NULL, due REAL NOT NULL,
 interval REAL NOT NULL DEFAULT 0, ease REAL NOT NULL DEFAULT 2.5, reps INTEGER NOT NULL DEFAULT 0, lapses INTEGER NOT NULL DEFAULT 0, last REAL);
CREATE TABLE next_reviews(id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, card INTEGER NOT NULL, rating TEXT NOT NULL, created REAL NOT NULL);
INSERT INTO next_cards(user_id,text,norm,created,due,interval,ease,reps) VALUES(1,'a','a',0,0,6,2.2,3),(1,'b','b',0,0,0,2.5,0);''')
        vs.schema(c)
        a, b = c.execute('SELECT state, stability, difficulty FROM next_cards ORDER BY id').fetchall()
        self.assertEqual((a['state'], a['stability']), ('review', 6.0)); self.assertGreater(a['difficulty'], 5)
        self.assertEqual((b['state'], b['stability']), ('new', None))
        vs.schema(c)  # running again changes nothing
        self.assertEqual(c.execute('SELECT stability FROM next_cards WHERE id=1').fetchone()[0], 6.0)


if __name__ == '__main__':
    unittest.main()


AI_ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
          'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0', 'FLOW_AI_AUDIO': '1'}



class BacklogTests(unittest.TestCase):
    """A day of words that can be done: reviews due by the day, new words held back when reviews pile up, estimates
    from the learner's own pace (ux-longterm-audit 1.1, 1.3, 10, 11, 17)."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'v.db'); self.p.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password,email) VALUES(?,?,?)', ('learner', 'h', 'learner@example.test'))
        self.c.commit()
        self.now = datetime.datetime.now(nx.TZ).replace(hour=8, minute=0, second=0, microsecond=0).timestamp()
        self.day = vs._day_start(self.now)

    def tearDown(self):
        self.c.close(); self.p.stop(); self.tmp.cleanup()

    def card(self, word, state, due):
        self.c.execute("INSERT INTO next_cards(user_id,text,norm,meaning,context,kind,created,due,state,source,stability,difficulty,last) "
                       "VALUES(1,?,?,'',' ','word',?,?,?,'saved',3,5,?)", (word, word, self.now - 9 * 86400, due, state, self.now - 3 * 86400))
        self.c.commit()

    def test_a_review_card_is_due_all_of_its_day_a_learning_step_only_from_its_minute(self):
        self.card('tonight', 'review', self.day + 20 * 3600)      # due this evening: due all day today
        self.card('tomorrow', 'review', self.day + 86400 + 60)     # tomorrow just after midnight: not yet
        self.card('in-ten', 'learning', self.now + 600)            # a learning step ten minutes away: not yet
        self.card('stepped', 'relearning', self.now - 60)          # a step that has come round: due
        self.assertEqual(vs.counts(self.c, 1, self.now)['due'], 2)
        with patch.object(vs.time, 'time', lambda: self.now):
            self.assertEqual(sorted(i['text'] for i in vs.queue(self.c, 1)['items']), ['stepped', 'tonight'])

    def test_new_words_wait_a_day_while_reviews_pile_up(self):
        vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 5, 'retention': 0.9})
        self.c.execute("DELETE FROM next_cards"); self.c.commit()
        for k in range(16):  # more than 5 x 3 reviews due
            self.card(f'w{k}', 'review', self.now - 3600)
        self.assertEqual(vs.introduce(self.c, 1, self.now), 0)
        n = vs.counts(self.c, 1, self.now)
        self.assertEqual((n['due'], n['new'], n['new_paused']), (16, 0, True))
        self.c.execute("UPDATE next_cards SET known=1"); self.c.commit()  # the reviews done: still none today
        self.assertEqual(vs.introduce(self.c, 1, self.now + 3600), 0)
        self.assertTrue(vs.counts(self.c, 1, self.now + 3600)['new_paused'])
        tomorrow = self.now + 86400
        self.assertEqual(vs.introduce(self.c, 1, tomorrow), 5)
        self.assertFalse(vs.counts(self.c, 1, tomorrow)['new_paused'])
        self.assertEqual(vs.PAUSE_OVER, 3)  # the word page says 「超过每天新词的 3 倍」 (50-words.js)

    def test_a_few_reviews_do_not_hold_back_new_words(self):
        vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 5, 'retention': 0.9})
        self.c.execute("DELETE FROM next_cards"); self.c.commit()
        for k in range(15):  # exactly 5 x 3: not over
            self.card(f'w{k}', 'review', self.now - 3600)
        self.assertEqual(vs.introduce(self.c, 1, self.now), 5)

    def test_the_estimate_follows_the_learners_own_pace(self):
        self.assertEqual(vs.answer_seconds(self.c, 1, self.now), vs.ANSWER_SECONDS)
        self.assertEqual(vs.minutes_for(100, 20, 9.5), round((100 * 1.2 + 20 * 3) * 9.5 / 60))
        for k in range(30):
            self.c.execute('INSERT INTO next_reviews(user_id,card,rating,created,ms) VALUES(1,1,?,?,5000)', ('good', self.now - k * 60))
        self.c.execute('INSERT INTO next_reviews(user_id,card,rating,created,ms) VALUES(1,1,?,?,600000)', ('good', self.now))  # looked away
        self.c.commit()
        self.assertEqual(vs.answer_seconds(self.c, 1, self.now), 5.0)
        for k in range(40):
            self.card(f'w{k}', 'review', self.now - 3600)
        self.assertEqual(vs.counts(self.c, 1, self.now)['minutes'], vs.minutes_for(40, 0, 5.0))  # 40 x 1.2 x 5 s = 4 min

    def test_the_plan_page_gets_the_same_numbers(self):
        vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 20, 'retention': 0.9})
        load = vs.overview(self.c, 1)['load']
        self.assertEqual((load['per_review'], load['per_new'], load['answer_seconds']), (1.2, 3, 9.5))
        self.assertEqual(set(load['month_reviews_per_new']), {str(r) for r in vs.RETENTION})
        self.assertEqual(load['month_reviews_per_new']['0.9'], 6)
        # a month in at 20 a day and 90 %: about 120 reviews, half an hour with the new words (the audit simulated 33 minutes)
        self.assertEqual(vs.minutes_for(20 * 6, 20, 9.5), 32)

    def test_a_reminder_for_a_pile_asks_for_the_first_forty(self):
        self.assertTrue(vs.set_reminder(self.c, 1, {'enabled': True, 'hour': 20})[0]['enabled'])
        at = self.day + 20 * 3600 + 300
        for k in range(120):
            self.card(f'w{k}', 'review', self.now - 3600)
        sent = []
        self.assertEqual(vs.send_reminders(self.c, at, lambda to, sub, text, html=None: sent.append((sub, text, html))), 1)
        sub, text, html = sent[0]
        self.assertIn('先复习最要紧的 40 个', sub); self.assertIn('先复习最要紧的 40 个', text); self.assertIn('先复习最要紧的 40 个', html)
        self.assertNotIn('120', sub + text)
        self.assertIn(f"约 {vs.minutes_for(40, 0, vs.ANSWER_SECONDS)} 分钟", sub)
        # the card layout (mail_layout): the same words as text and HTML, a button to the review, the way to turn it off
        self.assertIn('去复习：', text); self.assertIn('/#/review', text); self.assertIn('调整计划', text.split('——')[-1])
        self.assertIn('class="fl-btn"', html); self.assertIn('/#/review', html); self.assertIn('/#/vocab/plan', html)


    def test_a_reminder_goes_as_text_and_the_card_layout(self):
        """Through the real mail function (the outbox in tests): the .txt and the .html beside it, same words."""
        self.assertTrue(vs.set_reminder(self.c, 1, {'enabled': True, 'hour': 20})[0]['enabled'])
        for k in range(3):
            self.card(f'w{k}', 'review', self.now - 3600)
        box = Path(self.tmp.name) / 'outbox'
        with patch.dict(os.environ, {'FLOW_MAIL_OUTBOX': str(box)}):
            self.assertEqual(vs.send_reminders(self.c, self.day + 20 * 3600 + 300), 1)
        txt = next(box.glob('*.txt')).read_text(encoding='utf-8'); html = next(box.glob('*.html')).read_text(encoding='utf-8')
        self.assertIn('今天有 3 个单词该复习了', txt); self.assertIn('今天有 3 个单词该复习了', html)
        self.assertIn('去复习：', txt); self.assertIn('class="fl-card"', html)
        self.assertIn('learner，你好：', txt)


class OnceReminderTests(unittest.TestCase):
    """这次什么时候复习 (a trial student, 2026-11-25): a time today or tomorrow for the next reminder only; the mail goes
    then if there are words and none went that day, and the reminder is back to every day at its hour."""
    setUp, tearDown, card = BacklogTests.setUp, BacklogTests.tearDown, BacklogTests.card

    def mails(self, at):
        sent = []
        n = vs.send_reminders(self.c, at, lambda to, sub, text, html=None: sent.append((to, sub)))
        self.assertEqual(n, len(sent))
        return n

    def test_a_time_tonight_takes_the_place_of_the_hour_and_then_the_hour_is_back(self):
        vs.set_reminder(self.c, 1, {'enabled': True, 'hour': 20})
        self.card('w1', 'review', self.now - 3600)
        r, st = vs.set_once(self.c, 1, {'at': self.day + 21 * 3600 + 17}, now=self.now)
        self.assertEqual((st, r['once']), (200, self.day + 21 * 3600))  # to the minute
        self.assertEqual(self.mails(self.day + 20 * 3600 + 300), 0)  # 20:05: not the daily one while a time is chosen
        self.assertEqual(self.mails(self.day + 21 * 3600 + 60), 1)  # 21:01: the chosen time
        self.assertIsNone(vs.reminder(self.c, 1, self.day + 21 * 3600 + 60)['once'])
        self.assertEqual(self.mails(self.day + 21 * 3600 + 600), 0)  # once a day
        self.assertEqual(self.mails(self.day + 86400 + 20 * 3600 + 300), 1)  # tomorrow: every day at 20:00 again

    def test_tomorrow_morning_comes_instead_of_tonight_and_that_day_has_no_second_mail(self):
        vs.set_reminder(self.c, 1, {'enabled': True, 'hour': 20})
        self.card('w1', 'review', self.now - 3600)
        vs.set_once(self.c, 1, {'at': self.day + 86400 + 8 * 3600}, now=self.now)
        self.assertEqual(self.mails(self.day + 20 * 3600 + 300), 0)
        self.assertEqual(self.mails(self.day + 86400 + 8 * 3600 + 60), 1)
        self.assertEqual(self.mails(self.day + 86400 + 20 * 3600 + 300), 0)

    def test_nothing_to_review_at_the_chosen_time_sends_nothing_and_the_hour_still_may(self):
        vs.set_reminder(self.c, 1, {'enabled': True, 'hour': 20})
        vs.set_once(self.c, 1, {'at': self.day + 12 * 3600}, now=self.now)
        self.assertEqual(self.mails(self.day + 12 * 3600 + 60), 0)
        self.assertIsNone(vs.reminder(self.c, 1, self.day + 12 * 3600 + 60)['once'])  # used up all the same
        self.card('w1', 'review', self.day + 13 * 3600)
        self.assertEqual(self.mails(self.day + 20 * 3600 + 300), 1)

    def test_a_chosen_time_mails_even_without_the_daily_mail_and_a_long_past_one_is_only_cleared(self):
        self.card('w1', 'review', self.now - 3600)
        vs.set_once(self.c, 1, {'at': self.day + 9 * 3600}, now=self.now)
        self.assertFalse(vs.reminder(self.c, 1, self.now)['enabled'])
        self.assertEqual(self.mails(self.day + 9 * 3600 + 60), 1)  # asked for just now: it goes
        vs.set_once(self.c, 1, {'at': self.day + 86400 + 9 * 3600}, now=self.now)
        self.assertEqual(self.mails(self.day + 86400 + 15 * 3600), 0)  # six hours late (the server was down): not now
        self.assertIsNone(vs.reminder(self.c, 1, self.day + 86400 + 15 * 3600)['once'])

    def test_only_today_or_tomorrow_and_none_clears_it(self):
        for at in (self.now + 60, self.now + 3 * 86400, True, 'tonight', [1]):
            self.assertEqual(vs.set_once(self.c, 1, {'at': at}, now=self.now)[1], 400, at)
        vs.set_once(self.c, 1, {'at': self.now + 3600}, now=self.now)
        r, st = vs.set_once(self.c, 1, {'at': None}, now=self.now)
        self.assertEqual((st, r['once'], r['hour']), (200, None, 20))
        r, st = vs.post(self.c, 1, '/api/next/vocab/reminder/once', {'at': time.time() + 7200})  # the route the sheet posts to
        self.assertEqual((st, r['once']), (200, float(int((time.time() + 7200) // 60 * 60))))

    def test_the_calendar_gets_one_event_at_that_time(self):
        at = int(self.day + 86400 + 8 * 3600)
        cal = vs.ics(20, at=at)
        self.assertNotIn('RRULE', cal); self.assertIn(f'UID:flow-vocab-once-{at}@flow', cal)
        start = datetime.datetime.fromtimestamp(at, datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        self.assertIn(f'DTSTART:{start}', cal)
        self.assertIn('RRULE:FREQ=DAILY', vs.ics(20))  # the daily one unchanged

class WordCapTests(unittest.TestCase):
    """r28 section 3 (the owner chose the recommended plan, 2026-11-25): a day of words capped in minutes, reviews most
    at risk first and new words in the time left; after a break the most urgent 40, the rest over 5 days; a finished
    book names the next one."""
    setUp, tearDown = BacklogTests.setUp, BacklogTests.tearDown  # the same learner, without running BacklogTests twice

    def review(self, word, recall_days, due=None):
        """A review card due now; recall_days: days since its last review at stability 3 (more days: more at risk)."""
        self.c.execute("INSERT INTO next_cards(user_id,text,norm,meaning,context,kind,created,due,state,source,stability,difficulty,last) "
                       "VALUES(1,?,?,'',' ','word',?,?,'review','saved',3,5,?)", (word, word, self.now - 30 * 86400, due or self.now - 60, self.now - recall_days * 86400))

    def answered(self, n, at=None):
        for _ in range(n):
            self.c.execute("INSERT INTO next_reviews(user_id,card,rating,created) VALUES(1,0,'good',?)", (at or self.now - 60,))
        self.c.commit()

    def plan(self, minutes=5, book='core', daily=10):
        vs.save_plan(self.c, 1, {'book': book, 'daily_new': daily, 'retention': 0.9, 'word_minutes': minutes})
        self.c.execute('DELETE FROM next_cards'); self.c.commit()

    def test_a_cap_gives_todays_share_most_at_risk_first(self):
        self.plan(5)
        for k in range(28):
            self.review(f'w{k:02d}', 3 + k)  # w27 the most at risk
        self.c.commit()
        holds = int(5 * 60 / vs.ANSWER_SECONDS // vs.ANSWERS_PER_REVIEW)  # 26 reviews in 5 minutes at 9.5 s an answer
        n = vs.counts(self.c, 1, self.now, cap=5)
        self.assertEqual((n['due'], n['later'], n['cap'], n['catch_up']), (holds, 28 - holds, 5, None))
        self.assertLessEqual(n['minutes'], 5)
        with patch.object(vs.time, 'time', lambda: self.now):
            q = vs.queue(self.c, 1)
            self.assertEqual(len(q['items']), holds)
            self.assertNotIn('w00', [i['text'] for i in q['items']]); self.assertNotIn('w01', [i['text'] for i in q['items']])  # the safest wait
            self.assertEqual(len(vs.queue(self.c, 1, more=True)['items']), 28)  # 继续复习: everything due
        self.assertEqual(vs.counts(self.c, 1, self.now)['due'], 28)  # without a cap, as before (今日 before r28, the badge)

    def test_answers_today_use_up_the_share(self):
        self.plan(5)
        for k in range(20):
            self.review(f'w{k}', 5)
        self.c.commit()
        self.assertEqual(vs.counts(self.c, 1, self.now, cap=5)['due'], 20)
        self.answered(12)  # about ten cards done: the share is what is left of the time
        n = vs.counts(self.c, 1, self.now, cap=5)
        self.assertEqual(n['due'], int((5 * 60 / vs.ANSWER_SECONDS - 12) // vs.ANSWERS_PER_REVIEW))
        self.answered(30)  # past the cap: today's words are done, the rest is for later
        n = vs.counts(self.c, 1, self.now, cap=5)
        self.assertEqual((n['due'], n['new'], n['minutes'], n['later']), (0, 0, 0, 20))

    def test_new_words_come_in_the_time_the_reviews_leave(self):
        self.plan(5, daily=10)
        self.assertEqual(vs.introduce(self.c, 1, self.now), 10)  # nothing due: 5 minutes hold 10 new words (3 answers each)
        self.c.execute('DELETE FROM next_cards'); self.c.execute("UPDATE next_vocab_plans SET paused_on=NULL"); self.c.commit()
        for k in range(15):
            self.review(f'w{k}', 5)
        self.c.commit()
        left = 5 * 60 / vs.ANSWER_SECONDS - 15 * vs.ANSWERS_PER_REVIEW
        self.assertEqual(vs.introduce(self.c, 1, self.now), int(left // vs.ANSWERS_PER_NEW))
        self.assertEqual(vs.introduce(self.c, 1, self.now), 0)  # asked again: no more than fits
        self.assertEqual(vs.fit_new(5, 0.9, vs.ANSWER_SECONDS), 3)  # what 5 minutes keep up with a month in

    def test_the_cap_is_the_learners_own_else_the_days_plan_and_an_exam_date_raises_it(self):
        import types
        self.plan(0)
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'daily', 'themes': [], 'minutes': 15})
        self.assertEqual(vs.word_cap(self.c, 1, self.now), __import__('time_budget').budget(15)['words'])  # the day's plan (time_budget, r28 第 1 段)
        tb = types.ModuleType('time_budget'); tb.budget = lambda minutes, exam=False: {'words': {15: 5}.get(minutes, 9)}
        with patch.dict(sys.modules, {'time_budget': tb}):
            self.assertEqual(vs.word_cap(self.c, 1, self.now), 5)
            self.assertEqual(vs.word_cap(self.c, 1, self.now, default=4), 4)  # the caller's budget
            self.c.execute('UPDATE next_vocab_plans SET word_minutes=8'); self.c.commit()
            self.assertEqual(vs.word_cap(self.c, 1, self.now, default=4), 8)  # 单词每天 set on the plan page wins
            with patch('exam_sprint.countdown', return_value={'need': 20, 'book': 'core', 'plan_book': 'core'}):
                per = vs.ANSWERS_PER_NEW + vs.MONTH_REVIEWS_PER_NEW[0.9] * vs.ANSWERS_PER_REVIEW
                self.assertEqual(vs.word_cap(self.c, 1, self.now), -(-20 * per * vs.ANSWER_SECONDS // 60))  # 20 new a day to make the exam

    def test_after_a_break_the_most_urgent_40_then_the_rest_over_5_days_without_new_words(self):
        self.plan(5, daily=10)
        self.answered(1, at=self.now - 4 * 86400)  # last review four days ago
        for k in range(140):
            self.review(f'w{k:03d}', 3 + k % 20)
        self.c.commit()
        n = vs.counts(self.c, 1, self.now, cap=5)
        self.assertEqual((n['due'], n['new'], n['later']), (vs.BATCH, 0, 100))
        holds = int(5 * 60 / vs.ANSWER_SECONDS // vs.ANSWERS_PER_REVIEW)
        # today 40; the other 100 over 5 days, or faster when a day's cap holds more than 100 / 5
        self.assertEqual(n['catch_up'], {'left': 140, 'days': 1 + -(-100 // max(holds, 20))})
        self.assertEqual(vs.introduce(self.c, 1, self.now), 0)  # no new words until caught up
        self.assertEqual((vs.BACK_DAYS, vs.SPREAD_DAYS), (3, 5))  # r28 section 2 (回来模式) says 3 days and 5 days
        # the next day, 100 left: a day's share is the larger of the cap and 100 / 5
        self.c.execute("DELETE FROM next_cards WHERE norm IN (SELECT norm FROM next_cards ORDER BY norm LIMIT 40)"); self.c.commit()
        self.answered(48, at=self.now)
        tomorrow = self.now + 86400
        n = vs.counts(self.c, 1, tomorrow, cap=5)
        self.assertEqual(n['due'], max(26, 20)); self.assertIsNotNone(n['catch_up'])
        # once a day's cap holds what is due, catching up is over and new words come back
        self.c.execute("DELETE FROM next_cards WHERE norm IN (SELECT norm FROM next_cards ORDER BY norm LIMIT 80)"); self.c.commit()
        n = vs.counts(self.c, 1, tomorrow + 86400, cap=5)
        self.assertIsNone(n['catch_up']); self.assertIsNone(vs.plan(self.c, 1)['catch_up'])

    def test_a_short_break_or_a_small_heap_is_not_catching_up(self):
        self.plan(5)
        self.answered(1, at=self.now - 86400)  # yesterday
        for k in range(60):
            self.review(f'w{k}', 5)
        self.c.commit()
        self.assertIsNone(vs.counts(self.c, 1, self.now, cap=5)['catch_up'])
        self.c.execute('DELETE FROM next_reviews'); self.answered(1, at=self.now - 3 * 86400)
        self.assertIsNone(vs.counts(self.c, 1, self.now, cap=5)['catch_up'])  # two days without a review in between: not yet
        self.c.execute('DELETE FROM next_reviews'); self.answered(1, at=self.now - 5 * 86400)
        self.c.execute('DELETE FROM next_cards WHERE rowid > 10'); self.c.commit()  # 10 due: a day's cap holds them
        self.assertIsNone(vs.counts(self.c, 1, self.now, cap=5)['catch_up'])

    def test_a_finished_book_names_the_next_one_and_a_book_nearly_done_says_so(self):
        books = {**vs.book_words(), 'zk': [(1, 'apple'), (2, 'banana'), (3, 'cherry')], 'gk': [(1, 'apple'), (2, 'cherry'), (3, 'date'), (4, 'elder')]}
        with patch.object(vs, 'book_words', lambda: books):
            self.plan(0, book='zk', daily=10)
            for w in ('apple', 'banana'):
                self.review(w, 5, due=self.now + 9 * 86400)
            self.c.commit()
            b = vs.overview(self.c, 1)['book']
            self.assertEqual((b['left'], b['soon'], b['done']), (1, True, False))
            self.assertEqual(b['next'], {'id': 'gk', 'title': vs.book_title('gk'), 'new': 3})  # apple is known already
            self.review('cherry', 5, due=self.now + 9 * 86400); self.c.commit()
            b = vs.overview(self.c, 1)['book']
            self.assertTrue(b['done']); self.assertIsNone(b['finish']); self.assertEqual(b['next']['new'], 2)
            self.assertEqual(vs.next_book(self.c, 1, 'cet6'), 'ky')
            nx.save_profile(self.c, 1, {'level': 'B2', 'goal': 'abroad', 'themes': [], 'minutes': 30})
            self.assertEqual(vs.next_book(self.c, 1, 'cet6'), 'ielts')  # going abroad: 雅思 after 六级
            self.assertIsNone(vs.next_book(self.c, 1, 'gre'))

    def test_the_plan_keeps_its_word_minutes(self):
        self.plan(8)
        self.assertEqual(vs.plan(self.c, 1)['word_minutes'], 8)
        vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 5, 'retention': 0.9})  # left out: kept
        self.assertEqual(vs.plan(self.c, 1)['word_minutes'], 8)
        self.assertEqual(vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 5, 'retention': 0.9, 'word_minutes': 7})[1], 400)
        o = vs.overview(self.c, 1)
        self.assertEqual(o['word_minutes_options'], list(vs.WORD_MINUTES)); self.assertEqual(o['cap'], 8)
        self.assertEqual(vs.get(self.c, 1, '/api/next/review', {'more': ['1']})[0]['more'], True)


class ReadingLinkedTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'r.db'); self.p.start()
        self.env = patch.dict(os.environ, AI_ENV); self.env.start()
        app.init(); self.c = app.db()
        for n in ('learner', 'other'): self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'A2', 'goal': 'daily', 'themes': [], 'minutes': 10})

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def test_preread_words_then_add_them_in_one_go(self):
        m, _ = nx.material(self.c, 1, 'v5-science-b2-noise-cancelling')
        pre = m['preread']
        self.assertTrue(1 <= len(pre) <= 5); self.assertTrue(all(w['meaning'] for w in pre))
        r = vs.add_many(self.c, 1, {'pack': m['id'], 'items': [{'word': w['form'], 'sentence': m['sentences'][0]} for w in pre]})[0]
        self.assertEqual(r['added'], len(pre))
        again = nx.material(self.c, 1, 'v5-science-b2-noise-cancelling')[0]
        self.assertFalse({w['word'] for w in again['preread']} & {w['word'] for w in pre})  # already being learned
        self.assertTrue(again['mine'])
        self.assertEqual(vs.add_many(self.c, 1, {'items': [{'word': pre[0]['word']}]})[0]['skipped'], 1)
        r = vs.add_many(self.c, 1, {'min_rank': 1500, 'items': [{'word': 'the'}, {'word': 'scrutiny'}, {'word': 'not a word!'}]})[0]
        self.assertEqual((r['added'], r['skipped']), (1, 2))
        self.assertEqual(vs.add_many(self.c, 1, {'items': []})[1], 400)

    def test_examples_roots_and_ai_examples(self):
        self.assertTrue(any(r['part'].startswith('ben') for r in vs.roots('beneficial')))
        self.assertEqual(vs.extra_examples(None, 'even')[0]['title'], '词典例句')
        word = next(w for _, w in vs.book_words()['gre'] if not vs.examples(w) and not vs.extra_examples(self.c, w))
        reply = json.dumps({'examples': [{'word': word, 'sentence': f'She used the word {word} in her essay.', 'translation': '她在文章里用了这个词。'},
                                         {'word': 'nonsense', 'sentence': 'x', 'translation': ''}]})
        with patch('chat_service.request_model', return_value=(reply, 'stop')):
            out, s = vs.ai_examples(self.c, 1, {'words': [word, 'decision'], 'request_id': 'next-ex-0001'})
        self.assertEqual(s, 200); self.assertEqual(list(out['examples']), [word])
        self.assertEqual(vs.extra_examples(self.c, word)[0]['title'], 'AI 例句')
        self.assertEqual(vs.ai_examples(self.c, 1, {'words': [word]})[0], {'examples': {}})  # cached: no second call

    def test_test_skips_known_bands_in_exam_books(self):
        band = {w: k for k in vs.BOOKS for _, w in vs.book_words()[k]}
        items = vs.test_items(seed=3)['items']
        vs.save_plan(self.c, 1, {'book': 'cet6', 'daily_new': 10, 'retention': 0.9})
        r = vs.score_test(self.c, 1, {'answers': {w: band.get(w) in ('core', 'mid') for w in items}})[0]
        self.assertEqual(r['skip_rank'], 5000)
        q = vs.queue(self.c, 1)
        self.assertTrue(q['items']); self.assertTrue(all((i.get('stability') is None) for i in q['items']))
        ranks = [self.c.execute('SELECT rank FROM next_cards WHERE id=?', (i['id'],)).fetchone()[0] for i in q['items']]
        self.assertTrue(all(r > 5000 for r in ranks), ranks)
        vs.save_plan(self.c, 1, {'book': 'cet6', 'daily_new': 10, 'retention': 0.9, 'skip_known': False})
        self.assertEqual(vs.plan(self.c, 1)['skip_rank'], 0)

    def test_offline_reviews_keep_their_time(self):
        cid = nx.save_card(self.c, 1, {'text': 'serendipity'})[0]['card']['id']
        at = int(time.time()) - 3600
        vs.rate(self.c, 1, {'id': cid, 'rating': 'good', 'at': at})
        self.assertEqual(int(self.c.execute('SELECT last FROM next_cards WHERE id=?', (cid,)).fetchone()[0]), at)
        vs.rate(self.c, 1, {'id': cid, 'rating': 'good', 'at': 1})  # too old: ignored, now is used
        self.assertGreater(self.c.execute('SELECT last FROM next_cards WHERE id=?', (cid,)).fetchone()[0], time.time() - 60)

    def test_reminder_email_and_calendar(self):
        self.assertEqual(vs.set_reminder(self.c, 1, {'enabled': True, 'hour': 20})[1], 400)  # no email yet
        self.c.execute("UPDATE users SET email='learner@example.test' WHERE id=1"); self.c.commit()
        self.assertEqual(vs.set_reminder(self.c, 1, {'enabled': True, 'hour': 25})[1], 400)
        self.assertTrue(vs.set_reminder(self.c, 1, {'enabled': True, 'hour': 20})[0]['enabled'])
        nx.save_card(self.c, 1, {'text': 'make ends meet'})
        sent = []
        at8 = datetime.datetime.now(nx.TZ).replace(hour=20, minute=5, second=0)
        if at8.timestamp() < time.time():  # the next 20:05, so the card saved just now is already due then
            at8 += datetime.timedelta(days=1)
        at8 = at8.timestamp()
        self.assertEqual(vs.send_reminders(self.c, at8, lambda to, sub, text, html=None: sent.append((to, sub))), 1)
        self.assertEqual(sent[0][0], 'learner@example.test'); self.assertIn('单词', sent[0][1])
        self.assertEqual(vs.send_reminders(self.c, at8 + 60, lambda *a, **kw: sent.append(a)), 0)  # once a day
        self.assertEqual(vs.send_reminders(self.c, at8 - 3600, lambda *a, **kw: sent.append(a)), 0)  # other hours
        cal = vs.ics(21)
        self.assertIn('RRULE:FREQ=DAILY', cal); self.assertIn('DTSTART:', cal); self.assertTrue(cal.endswith('\r\n'))
        self.assertTrue(vs.overview(self.c, 1)['reminder']['has_email'])

    def test_writing_with_a_studied_word_counts_as_a_review(self):
        cid = nx.save_card(self.c, 1, {'text': 'devise'})[0]['card']['id']
        self.c.execute("UPDATE next_cards SET state='review', stability=5, difficulty=5, last=?, due=? WHERE id=?",
                       (time.time() - 4 * 86400, time.time() + 86400, cid)); self.c.commit()
        pid = nx.home(self.c, 1)['today'][0]['id']
        reply = {'verdict': 'natural', 'summary': '很好。', 'corrected': 'We devised a plan.', 'changes': [],
                 'versions': [{'label': '更自然', 'text': 'We came up with a plan.', 'why': '口语'}], 'used_well': [],
                 'word_use': [{'word': 'devise', 'ok': True, 'note': '“想出（计划）”用得对'}, {'word': 'plan', 'ok': True, 'note': 'x'}]}
        with patch('chat_service.request_model', return_value=(json.dumps(reply, ensure_ascii=False), 'stop')) as model:
            out, s = nx.rewrite(self.c, 1, {'pack': pid, 'text': 'We devised a clever plan.', 'request_id': 'next-rw-word-0001'})
        self.assertEqual(s, 200); self.assertIn('devise', model.call_args[0][0][1]['content'])
        self.assertEqual(out['result']['word_use'], [{'word': 'devise', 'ok': True, 'note': '“想出（计划）”用得对'}])
        row = self.c.execute('SELECT stability, reps FROM next_cards WHERE id=?', (cid,)).fetchone()
        self.assertGreater(row['stability'], 5); self.assertEqual(row['reps'], 1)
        self.assertEqual(self.c.execute("SELECT rating FROM next_reviews WHERE card=? ORDER BY id DESC", (cid,)).fetchone()[0], 'used')

    def test_shadowing_feedback(self):
        self.assertEqual([w['ok'] for w in nx.compare_words('A pair of noisy headphones.', 'a pair of headphones')], [True, True, True, False, True])
        audio = {'mime_type': 'audio/webm', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * 64).decode()}
        reply = json.dumps({'transcript': 'The first time you switch a pair of headphones', 'issues': [{'word': 'on', 'note': '漏读了 on'}],
                            'tip': '把 switch on 连起来读', 'fluency': 'ok'}, ensure_ascii=False)
        with patch('chat_service.request_model', return_value=(reply, 'stop')) as model:
            out, s = nx.shadow(self.c, 1, {'pack': 'v5-science-b2-noise-cancelling', 'i': 0, 'audio': audio, 'request_id': 'next-sh-0001'})
        self.assertEqual(s, 200); self.assertEqual(model.call_args.kwargs['audio'], audio)
        self.assertIn('连字符', ' '.join(m['content'] for m in model.call_args[0][0]))  # spelling and hyphens are not what was heard (Omni, 2026-11-25)
        r = out['result']
        self.assertEqual(r['issues'][0]['word'], 'on'); self.assertLess(r['matched'], len(r['words']))
        self.assertEqual(nx.shadow(self.c, 1, {'pack': 'v5-science-b2-noise-cancelling', 'i': 999, 'audio': audio})[1], 400)
        with patch.dict(os.environ, {'FLOW_AI_AUDIO': '0'}):
            self.assertEqual(nx.shadow(self.c, 1, {'pack': 'v5-science-b2-noise-cancelling', 'i': 0, 'audio': audio})[1], 503)
        self.assertIsNone(r['score'])  # an older-style reply (no estimate) shows no score

    def test_a_right_reading_files_nothing_and_a_misread_word_files_that_word(self):
        pid = 'v5-science-b2-noise-cancelling'
        sentence = nx.sentences(next(x for x in __import__('content_v50').v5_materials() if x['id'] == pid)['body'])[0]
        audio = {'mime_type': 'audio/webm', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * 80).decode()}
        listed = {'sounds': [{'sound': '/θ/', 'word': 'the', 'note': '舌尖再往前', 'set': 'th-s'}],
                  'issues': [{'word': 'pair of noise-cancelling headphones on a train', 'note': '连读'}], 'tip': '', 'fluency': 'ok', 'accuracy': 90, 'fluency_score': 85}
        cards = lambda: [r[0] for r in self.c.execute("SELECT text FROM next_cards WHERE user_id=1 AND kind='sound' ORDER BY id")]
        with patch('chat_service.request_model', return_value=(json.dumps({**listed, 'transcript': sentence}, ensure_ascii=False), 'stop')):
            nx.shadow(self.c, 1, {'pack': pid, 'i': 0, 'audio': audio, 'request_id': 'next-sh-right-01'})
        self.assertEqual(cards(), [])  # read right: what the model listed is shown, nothing filed
        with patch('chat_service.request_model', return_value=(json.dumps({**listed, 'transcript': sentence.replace('train', 'rain')}, ensure_ascii=False), 'stop')):
            nx.shadow(self.c, 1, {'pack': pid, 'i': 0, 'audio': audio, 'request_id': 'next-sh-wrong-01'})
        self.assertEqual(cards(), ['train'])  # the phrase files its misread word, not the whole phrase

    def test_shadowing_pronunciation_score(self):
        pid = 'v5-science-b2-noise-cancelling'
        audio = {'mime_type': 'audio/webm', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * 80).decode()}
        reply = {'transcript': 'The first time you switch a pair of headphones', 'accuracy': 81.4, 'fluency_score': 70, 'fluency': 'ok',
                 'sounds': [{'sound': '/θ/', 'word': 'think', 'note': '不在原句里，不该出现', 'set': 'th-s'},
                            {'sound': '/ɪ/', 'word': 'switch', 'note': '读成了 /iː/：短一点、放松', 'set': 'i-long-short'},
                            {'sound': '/f/', 'word': 'first', 'note': 'f 要上齿碰下唇', 'set': 'no-such-set'}],
                 'issues': [{'word': 'on', 'note': '漏读了 on'}], 'tip': '把 switch on 连起来读'}
        with patch('chat_service.request_model', return_value=(json.dumps(reply, ensure_ascii=False), 'stop')) as model:
            out, s = nx.shadow(self.c, 1, {'pack': pid, 'i': 0, 'audio': audio, 'request_id': 'next-sh-score-1'})
        self.assertEqual(s, 200)
        prompt = model.call_args[0][0][1]['content']
        self.assertIn('th-s（/θ/ 和 /s/）', prompt)  # the AI picks from 发音入门's own sets
        r = out['result']
        self.assertEqual([x['word'] for x in r['sounds']], ['switch', 'first'])  # a word not in the sentence is dropped
        self.assertEqual((r['sounds'][0]['set'], r['sounds'][0]['set_title']), ('i-long-short', '/iː/ 和 /ɪ/'))
        self.assertEqual(r['sounds'][1]['set'], '')  # unknown set ids are not linked
        sc = r['score']
        self.assertEqual((sc['accuracy'], sc['fluency']), (81, 70))
        self.assertEqual(sc['complete'], round(100 * r['matched'] / len(r['words'])))
        self.assertEqual(sc['total'], round(0.5 * 81 + 0.25 * 70 + 0.25 * sc['complete']))
        ev = self.c.execute("SELECT skill, score FROM next_skill_events WHERE user_id=1 AND kind='shadow-pron'").fetchall()
        self.assertEqual([(e['skill'], e['score']) for e in ev], [('pronunciation', sc['total'] / 100)])
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_skill_events WHERE user_id=1 AND kind='shadow'").fetchone()[0], 1)
        mk = self.c.execute("SELECT text, meaning FROM next_cards WHERE user_id=1 AND kind='sound' ORDER BY id").fetchall()
        # only what the transcript shows went wrong is filed: "on" was not heard; "switch" and "first" were, so they are
        # shown under 要练的音 but not filed (语流 12, 2026-11-25: models list sounds on right readings too)
        self.assertEqual([m['text'] for m in mk], ['on']); self.assertEqual(mk[0]['meaning'], '漏读了 on')
        # the same request again is a replay: same score, nothing logged twice
        with patch('chat_service.request_model', return_value=(json.dumps(reply, ensure_ascii=False), 'stop')):
            again, _ = nx.shadow(self.c, 1, {'pack': pid, 'i': 0, 'audio': audio, 'request_id': 'next-sh-score-1'})
        self.assertEqual(again['result']['score'], sc)
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_skill_events WHERE user_id=1 AND kind='shadow-pron'").fetchone()[0], 1)
        # nothing of the sentence heard: no score (the page asks to read it again)
        with patch('chat_service.request_model', return_value=(json.dumps({**reply, 'transcript': '[听不清]'}, ensure_ascii=False), 'stop')):
            quiet, _ = nx.shadow(self.c, 1, {'pack': pid, 'i': 0, 'audio': audio, 'request_id': 'next-sh-score-2'})
        self.assertIsNone(quiet['result']['score'])
        self.assertEqual(nx.pron_score({'accuracy': 90, 'fluency_score': None, 'words': [{'ok': True}], 'matched': 1}),
                         {'accuracy': 90, 'fluency': 72, 'complete': 100, 'total': round(45 + 18 + 25)})

    def test_admin_learning_dashboard(self):
        import flow_admin
        nx.mark(self.c, 1, 'v5-science-b2-noise-cancelling', 'read')
        cid = nx.save_card(self.c, 1, {'text': 'serendipity'})[0]['card']['id']
        vs.rate(self.c, 1, {'id': cid, 'rating': 'good'})
        d = flow_admin.learning(self.c)
        self.assertEqual(d['active_today'], 1); self.assertEqual(d['funnel_7d']['read'], 1)
        self.assertEqual(d['ratings_7d'], {'good': 1}); self.assertEqual(len(d['active_days']), 14)
        self.assertGreaterEqual(d['materials'], 192)


class SaveCardTwiceTests(unittest.TestCase):
    """A word saved twice at once (a double tap, the page open twice): both saves answer 200 and there is one card; a
    save of a card already there still takes the meaning and the sentence it brings (语流 02, 2026-11-25: a 500 on
    UNIQUE(user_id, norm) when the check and the insert were two steps)."""
    setUp, tearDown = BacklogTests.setUp, BacklogTests.tearDown

    def test_two_saves_at_once_both_answer_and_leave_one_card(self):
        import threading
        words = [f'serendipity{k}' for k in range(30)]
        gate, out = threading.Barrier(2), []

        def saver():
            c = app.db()
            try:
                for w in words:
                    gate.wait(timeout=10)
                    out.append(nx.save_card(c, 1, {'text': w, 'context': f'It was pure {w}.'})[1])
            finally:
                c.close()
        ts = [threading.Thread(target=saver) for _ in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        self.assertEqual(out, [200] * 60)
        rows = dict(self.c.execute("SELECT norm, COUNT(*) FROM next_cards WHERE user_id=1 AND norm LIKE 'serendipity%' GROUP BY norm").fetchall())
        self.assertEqual(rows, {w: 1 for w in words})

    def test_saving_again_takes_the_new_meaning_and_keeps_the_card(self):
        first, st = nx.save_card(self.c, 1, {'text': 'decisions', 'context': 'We need to explain our decisions.'})
        self.assertEqual((st, first['existing']), (200, False))
        again, st = nx.save_card(self.c, 1, {'text': 'Decisions!', 'meaning': '决策'})
        self.assertEqual((st, again['existing'], again['card']['id']), (200, True, first['card']['id']))
        self.assertEqual(again['card']['meaning'], '决策'); self.assertEqual(again['card']['context'], 'We need to explain our decisions.')  # an empty one keeps it

