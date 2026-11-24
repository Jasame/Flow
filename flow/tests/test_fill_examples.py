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

if __name__ == '__main__':
    unittest.main()
