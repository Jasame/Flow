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


if __name__ == '__main__':
    unittest.main()
