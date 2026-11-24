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
        self.assertEqual(vs.send_reminders(self.c, at8, lambda to, sub, text: sent.append((to, sub))), 1)
        self.assertEqual(sent[0][0], 'learner@example.test'); self.assertIn('单词', sent[0][1])
        self.assertEqual(vs.send_reminders(self.c, at8 + 60, lambda *a: sent.append(a)), 0)  # once a day
        self.assertEqual(vs.send_reminders(self.c, at8 - 3600, lambda *a: sent.append(a)), 0)  # other hours
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
        r = out['result']
        self.assertEqual(r['issues'][0]['word'], 'on'); self.assertLess(r['matched'], len(r['words']))
        self.assertEqual(nx.shadow(self.c, 1, {'pack': 'v5-science-b2-noise-cancelling', 'i': 999, 'audio': audio})[1], 400)
        with patch.dict(os.environ, {'FLOW_AI_AUDIO': '0'}):
            self.assertEqual(nx.shadow(self.c, 1, {'pack': 'v5-science-b2-noise-cancelling', 'i': 0, 'audio': audio})[1], 503)
        self.assertIsNone(r['score'])  # an older-style reply (no estimate) shows no score

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
        self.assertEqual(mk[0]['text'], 'switch'); self.assertTrue(mk[0]['meaning'].startswith('/ɪ/：'))
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
