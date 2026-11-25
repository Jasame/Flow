"""例句预生成 (fill_examples.py): words without an example get one AI example each, written into the site's own
database with the learner request's checks; a word that has one is never asked for again, so a run can stop and go
on; a sentence that does not use its word is not kept; failed calls stop the run. The model here is a stand-in."""
import json, os, re, sqlite3, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, fill_examples, vocab_service as vs  # noqa: E402

AI_ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'test', 'FLOW_AI_MODEL': 'stand-in', 'FLOW_AI_URL': 'https://ai.invalid/v1/chat/completions'}


def writer(bad=()):
    """A stand-in model: one sentence per asked word (a sentence without the word for those in bad)."""
    asked = []

    def request_model(messages, audio=None, grounding=False):
        words = re.findall(r'^([a-z-]+)：', messages[-1]['content'], re.M)
        asked.append(words)
        return json.dumps({'examples': [{'word': w, 'sentence': ('This sentence forgets it.' if w in bad else f'People often say {w} at work.'),
                                         'translation': '一个例句。'} for w in words]}), 'stop'
    return request_model, asked


class FillExamplesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {**AI_ENV, 'FLOW_DATA_DIR': self.tmp.name}); self.env.start()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 'flow.sqlite3'); self.p.start()
        app.init()
        self.c = sqlite3.connect(Path(self.tmp.name) / 'flow.sqlite3'); self.c.row_factory = sqlite3.Row
        self.args = ['--env-file', '/nonexistent', '--books', 'gre', '--pause', '0']

    def tearDown(self):
        self.c.close(); self.p.stop(); self.env.stop(); self.tmp.cleanup()

    def cached(self):
        return {r['norm']: r['sentence'] for r in self.c.execute('SELECT norm, sentence FROM next_word_examples')}

    def test_a_run_writes_examples_and_the_next_one_goes_on_where_it_stopped(self):
        todo = [w for _, _, w in fill_examples.pending(self.c, vs, ['gre'])]
        self.assertTrue(len(todo) > 20)
        model, asked = writer(bad={todo[1]})
        with patch('chat_service.request_model', model):
            self.assertEqual(fill_examples.main(self.args + ['--per-call', '4', '--max-calls', '2']), 1)  # words are left
        self.assertEqual([len(a) for a in asked], [4, 4])
        got = self.cached()
        self.assertEqual(set(got), set(todo[:8]) - {todo[1]})  # the sentence without its word is not kept
        self.assertTrue(all(w in s for w, s in got.items()))
        self.assertEqual(vs.extra_examples(self.c, todo[0])[0]['title'], 'AI 例句')  # what a word card then shows
        model2, asked2 = writer()
        with patch('chat_service.request_model', model2):
            fill_examples.main(self.args + ['--per-call', '4', '--max-calls', '1'])
        self.assertEqual(asked2, [[todo[1]] + todo[8:11]])  # done words are not asked for again; the refused one is

    def test_a_dry_run_only_counts_and_failures_stop_the_run(self):
        with patch('chat_service.request_model', side_effect=AssertionError('no call in a dry run')):
            self.assertEqual(fill_examples.main(self.args + ['--dry-run']), 1)
        with patch('chat_service.request_model', side_effect=TimeoutError('slow')) as m, patch('time.sleep'):
            self.assertEqual(fill_examples.main(self.args + ['--per-call', '4']), 1)
        self.assertEqual(m.call_count, 5)
        self.assertEqual(self.cached(), {})

    def test_no_model_no_calls(self):
        with patch.dict(os.environ, {'FLOW_AI_MODEL': '', 'FLOW_AI_KEY': ''}), patch('chat_service.request_model') as m:
            self.assertEqual(fill_examples.main(self.args), 2)
        m.assert_not_called()



class LevelAndSenseTests(FillExamplesTests):
    """An example is written for the word: other words easier than it (school and basic books A2, 四级 B1, the rest
    B2), in the first sense unless that one is a rare use, and the sense used is kept (b5 trial, 2026-11-24)."""
    def test_the_level_is_the_words_own(self):
        books = vs.book_words()
        only = lambda b, others: next(w for _, w in books[b] if all(w not in {x for _, x in books[o]} for o in others))
        self.assertEqual(vs.example_level('mouse'), 'A2')  # 中考 and the basic book
        self.assertEqual(vs.example_level(only('cet4', ('core', 'zk', 'mid', 'gk'))), 'B1')
        self.assertEqual(vs.example_level(only('gre', ('core', 'zk', 'mid', 'gk', 'cet4'))), 'B2')
        msgs = vs.example_messages(['mouse', only('gre', ('core', 'zk', 'mid', 'gk', 'cet4'))])
        self.assertIn('A2 学习者', msgs[0]['content'])  # the easiest of the words asked together
        self.assertIn('比这个单词简单', msgs[0]['content'])

    def test_the_first_sense_is_named_and_preferred(self):
        self.assertEqual(vs.first_sense('n. 老鼠, 胆小羞怯的人, 鼠标；vi. 捕鼠, 窥探'), '老鼠')
        self.assertEqual(vs.first_sense('n. 玫瑰；（rise 的过去式）'), '玫瑰')
        self.assertEqual(vs.first_sense('n. 伦敦'), '伦敦')
        self.assertEqual(vs.first_sense('vt. 认出, 承认；vi. 认可'), '认出')
        msgs = vs.example_messages(['mouse'])
        self.assertIn('mouse：', msgs[1]['content']); self.assertIn('（第一个义项：老鼠）', msgs[1]['content'])
        self.assertIn('优先用词书给的第一个义项', msgs[0]['content']); self.assertIn('"sense"', msgs[1]['content'])

    def test_the_sense_used_is_kept_and_counted(self):
        def model(messages, audio=None, grounding=False):
            words = re.findall(r'^([a-z-]+)：', messages[-1]['content'], re.M)
            return json.dumps({'examples': [{'word': w, 'sense': '别的意思' if k == 0 else vs.first_sense(vs.nx.dictionary()[w]['meaning']),
                                             'sentence': f'People often say {w} at work.', 'translation': '一个例句。'} for k, w in enumerate(words)]}), 'stop'
        status = Path(self.tmp.name) / 'status.json'
        with patch('chat_service.request_model', model):
            fill_examples.main(self.args + ['--per-call', '4', '--max-calls', '1', '--status', str(status)])
        rows = {r['norm']: r['sense'] for r in self.c.execute('SELECT norm, sense FROM next_word_examples')}
        self.assertEqual(len(rows), 4); self.assertEqual(sorted(rows.values()).count('别的意思'), 1)
        self.assertEqual(json.loads(status.read_text())['other_sense'], 1)

    def test_a_learners_request_is_written_at_the_words_level_not_the_learners(self):
        self.c.execute("INSERT INTO users(username,password) VALUES('c1','x')"); self.c.commit()
        uid = self.c.execute("SELECT id FROM users WHERE username='c1'").fetchone()[0]
        __import__('next_service').save_profile(self.c, uid, {'level': 'C1', 'goal': 'exam', 'themes': [], 'minutes': 15})
        seen = []

        def model(messages, audio=None, grounding=False):
            seen.append(messages[0]['content'])
            return json.dumps({'examples': [{'word': 'mouse', 'sense': '老鼠', 'sentence': 'A small mouse ran across the kitchen floor.', 'translation': '一只小老鼠跑过厨房地板。'}]}), 'stop'
        with patch('chat_service.request_model', model):
            r, st = vs.ai_examples(self.c, uid, {'words': ['mouse'], 'request_id': 'ex-request-0001'})
        self.assertEqual(st, 200); self.assertIn('A2 学习者', seen[0])
        self.assertEqual(self.c.execute("SELECT sense FROM next_word_examples WHERE norm='mouse'").fetchone()[0], '老鼠')

    def test_an_old_table_gets_the_sense_column(self):
        c = self.c
        c.execute('ALTER TABLE next_word_examples DROP COLUMN sense')  # as before this change
        c.execute("INSERT INTO next_word_examples VALUES('mouse','A mouse ran.','',1)"); c.commit()
        vs.schema(c); vs.schema(c)  # twice: the second run finds the column there
        self.assertIn('sense', {r[1] for r in c.execute('PRAGMA table_info(next_word_examples)')})
        self.assertEqual(c.execute("SELECT sense FROM next_word_examples WHERE norm='mouse'").fetchone()[0], '')

    def test_the_docstring_says_to_run_as_www(self):
        doc = fill_examples.__doc__
        self.assertIn('systemd-run', doc); self.assertIn('--uid=www', doc); self.assertIn('never as root', doc)
        self.assertNotIn('nohup python3 fill_examples.py', doc)


class WorkersTests(FillExamplesTests):
    """--workers (2026-11-25): calls at once in threads, the database written by the main thread only; a rate limit
    halves the calls at once and asks the batch again; a batch line of its own never falls back to the main model."""

    def test_calls_run_at_once_and_only_the_main_thread_writes(self):
        import threading
        todo = [w for _, _, w in fill_examples.pending(self.c, vs, ['gre'])]
        write, lock, now, most, writers = writer()[0], threading.Lock(), [0], [0], set()

        def model(messages, audio=None, grounding=False):
            with lock:
                now[0] += 1; most[0] = max(most[0], now[0])
            threading.Event().wait(0.05)
            with lock:
                now[0] -= 1
            return write(messages)
        save = vs.save_examples
        with patch('chat_service.request_model', model), patch.object(vs, 'save_examples', lambda c, made, now=None: (writers.add(threading.current_thread().name), save(c, made, now))):
            fill_examples.main(self.args + ['--per-call', '2', '--max-calls', '12', '--workers', '4'])
        self.assertEqual(writers, {'MainThread'})
        self.assertGreater(most[0], 1); self.assertLessEqual(most[0], 4)
        self.assertEqual(set(self.cached()), set(todo[:24]))

    def test_the_pace_halves_on_a_rate_limit_and_grows_back(self):
        p = fill_examples.Pace(8)
        p.slow(); self.assertEqual((p.now, p.hold), (4, 5))
        p.slow(); self.assertEqual((p.now, p.hold), (2, 10))
        for _ in range(10):
            p.ok()
        self.assertEqual(p.now, 3)
        q = fill_examples.Pace(1)
        q.slow(); self.assertEqual(q.now, 1)

    def test_a_rate_limited_batch_is_asked_again(self):
        import itertools, urllib.error
        todo = [w for _, _, w in fill_examples.pending(self.c, vs, ['gre'])]
        write, order = writer()[0], itertools.count()  # next() on a count is atomic: exactly the first two calls fail

        def model(messages, audio=None, grounding=False):
            if next(order) < 2:
                raise urllib.error.HTTPError('https://ai.invalid', 429, 'busy', None, None)
            return write(messages)
        status = Path(self.tmp.name) / 'status.json'
        with patch('chat_service.request_model', model), patch('time.sleep') as sleep:
            fill_examples.main(self.args + ['--per-call', '4', '--max-calls', '6', '--workers', '2', '--status', str(status)])
        self.assertEqual(set(self.cached()), set(todo[:16]))  # 6 calls: 2 refused, their words asked again
        st = json.loads(status.read_text())
        self.assertEqual((st['calls'], st['failed'], st['made']), (6, 2, 16))
        self.assertTrue(any(x.args[0] >= 5 for x in sleep.call_args_list))  # waited before the next call

    def test_a_batch_line_of_its_own_never_falls_back_to_the_main_model(self):
        import chat_service, itertools, urllib.error
        write, seen, order = writer()[0], [], itertools.count()  # next() on a count is atomic: exactly one call fails

        def line(messages, model=None, extra=None):
            seen.append(model)
            if next(order) == 0:
                raise urllib.error.HTTPError('https://ai.invalid', 503, 'down', None, None)
            chat_service.INFO.served = 'deepseek-v4.1-flash'
            return write(messages)
        with patch.dict(os.environ, {'FLOW_AI_ROUTES': 'next-examples=flow-batch-x'}), patch.object(chat_service, '_request_text_service', line), \
                patch.object(chat_service, '_request_main', side_effect=AssertionError('no fallback')), patch('time.sleep'):
            fill_examples.main(self.args + ['--per-call', '4', '--max-calls', '3', '--workers', '2'])
        self.assertEqual(seen, ['flow-batch-x'] * 3)
        # two calls at once: their ai_calls rows land in either order
        rows = sorted(tuple(r) for r in self.c.execute("SELECT model, ok, status, served FROM ai_calls WHERE kind='fill-examples'"))
        self.assertEqual(rows, [('flow-batch-x', 0, 503, ''), ('flow-batch-x', 1, 200, 'deepseek-v4.1-flash'), ('flow-batch-x', 1, 200, 'deepseek-v4.1-flash')])
        self.assertEqual(len(self.cached()), 8)

    def test_max_yuan_stops_new_calls(self):
        import ai_routes
        write, db = writer()[0], Path(self.tmp.name) / 'flow.sqlite3'

        def model(messages, audio=None, grounding=False):  # each call leaves its ai_calls row, as request_model does
            with sqlite3.connect(db) as c:
                c.execute("INSERT INTO ai_calls(ts,kind,service,ok) VALUES(?,?,?,1)", (__import__('time').time(), 'fill-examples', 'text'))
            return write(messages)
        status = Path(self.tmp.name) / 'status.json'
        with patch('chat_service.request_model', model), patch.object(ai_routes, 'cost', return_value=1.0):
            self.assertEqual(fill_examples.main(self.args + ['--per-call', '4', '--max-yuan', '2', '--status', str(status)]), 1)
        st = json.loads(status.read_text())
        self.assertEqual((st['calls'], st['yuan'], st['state']), (2, 2.0, 'left'))



class ReviewTests(unittest.TestCase):
    """2026-11-25, the owner: AI examples must not mock or stereotype (illness, disability, race, nationality, gender,
    places). The prompt says so (vocab_service.FAIR); --review finds the old ones, takes them out and writes them again."""
    setUp, tearDown, cached = FillExamplesTests.setUp, FillExamplesTests.tearDown, FillExamplesTests.cached

    def test_the_prompt_asks_for_fair_examples(self):
        system = vs.example_messages(['mouse'], 'A2')[0]['content']
        for part in ('刻板印象', '疾病', '残障', '种族', '性别', '地域', '疯子'):
            self.assertIn(part, system)

    def test_review_takes_out_what_the_editor_names_and_the_fill_writes_it_again(self):
        todo = [w for _, _, w in fill_examples.pending(self.c, vs, ['gre'])]
        w0, w1 = todo[0], todo[1]
        vs.save_examples(self.c, {w0: {'sentence': f'The mad man shouts {w0} all day.', 'translation': '那个疯子整天喊。'},
                                  w1: {'sentence': f'An old woman sells {w1} at the market.', 'translation': '一位老太太在市场上卖东西。'},
                                  'apple': {'sentence': 'I eat an apple every morning.', 'translation': '我每天早上吃一个苹果。'}})
        self.assertEqual([r['norm'] for r in fill_examples.candidates(self.c)], sorted([w0, w1]))  # apple: no review word
        write, asked = writer()

        def model(messages, audio=None, grounding=False):
            if '审读编辑' in messages[0]['content']:  # the editor: only the mad man
                asked.append('review')
                lines = messages[-1]['content'].split('\n')
                return json.dumps({'flag': [{'id': k, 'why': '嘲笑精神状况'} for k, line in enumerate(lines, 1) if 'mad man' in line]
                                   + [{'id': 99}, {'id': 'x'}]}), 'stop'  # ids outside the batch are ignored
            return write(messages)
        log = Path(self.tmp.name) / 'review.jsonl'
        with patch('chat_service.request_model', model):
            fill_examples.main(self.args + ['--review', '--review-log', str(log), '--per-call', '4', '--max-calls', '1'])
        got = self.cached()
        self.assertEqual(got[w0], f'People often say {w0} at work.')  # written again, with today's prompt
        self.assertEqual(got[w1], f'An old woman sells {w1} at the market.')  # neutral: kept
        self.assertIn('apple', got)
        lines = [json.loads(x) for x in log.read_text(encoding='utf-8').splitlines()]
        self.assertEqual([(x['norm'], x['why']) for x in lines], [(w0, '嘲笑精神状况')])
        self.assertEqual(asked[0], 'review')

    def test_a_dry_run_review_only_counts(self):
        vs.save_examples(self.c, {'mouse': {'sentence': 'The crazy mouse runs.', 'translation': '疯狂的老鼠在跑。'}})
        with patch('chat_service.request_model', side_effect=AssertionError('no call in a dry run')):
            self.assertEqual(fill_examples.main(self.args + ['--review', '--dry-run']), 1)
        self.assertIn('mouse', self.cached())

if __name__ == '__main__':
    unittest.main()
