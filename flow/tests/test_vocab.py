import unittest, tempfile, sys, os, sqlite3, time, json
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
        self.assertEqual(vs.save_plan(self.c, 1, {'book': 'core', 'daily_new': 7})[1], 400)
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
        self.assertEqual(o['mastered'], 1); self.assertGreaterEqual(o['book']['started'], 5); self.assertIsNotNone(o['book']['finish'])
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
        band = {w: k for k, ws in vs.book_words().items() for _, w in ws}
        honest = {w: band.get(w) in ('core', 'mid') for w in items}
        r = vs.score_test(self.c, None, {'answers': honest})[0]
        sizes = {k: len(v) for k, v in vs.book_words().items()}
        self.assertEqual(r['suggest'], 'high'); self.assertAlmostEqual(r['estimate'], sizes['core'] + sizes['mid'], delta=200)
        self.assertFalse(r['guessing'])
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
