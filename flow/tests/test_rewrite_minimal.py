"""仿写 marking keeps the learner's own sentence: corrected is that sentence with the smallest change, never another
sentence in the lesson's pattern on the lesson's topic (what the 批改考题集 found on the real model: "She sings very
good." came back as "She is not singing so much as shouting."). Such an answer is asked for once more, and if it is
still another sentence it is not shown; a sentence left as it was is marked natural."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, chat_service, next_service as nx  # noqa: E402

CASES = json.loads((Path(app.ROOT) / 'corpus_data' / 'ai-eval.json').read_text(encoding='utf-8'))
PID = CASES['pack']
AI_ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'test', 'FLOW_AI_MODEL': 'stand-in', 'FLOW_AI_URL': 'https://ai.invalid/v1/chat/completions',
          'FLOW_AI_USER_DAILY_LIMIT': '1000', 'FLOW_AI_DAILY_LIMIT': '1000', 'FLOW_COOKIE_SECURE': '0'}
# What the real model wrote instead of correcting (ai-eval report, 2026-11-24)
REPLACED = [("She sings very good.", "She is not singing so much as shouting."),
            ("There are three child in the room.", "The headphones are not blocking the noise so much as fighting it with more sound."),
            ("Can you make a photo of us?", "Noise-cancelling headphones are not silencing the train so much as cancelling its roar."),
            ("I usually take the subway to work because it is faster than driving.", "My headphones are not blocking the noise so much as fighting it."),
            ("Could you tell me where the nearest bank is?", "The chip is not ignoring voices so much as failing to keep up with them.")]


def answer(corrected, verdict='minor', changes=None):
    return json.dumps({'verdict': verdict, 'summary': '意思清楚。', 'corrected': corrected, 'changes': changes or [],
                       'versions': [{'label': '更自然', 'text': corrected, 'why': '—'}], 'used_well': [], 'keep': None})


class KeptTests(unittest.TestCase):
    def test_the_real_replacements_are_told_apart(self):
        for text, other in REPLACED:
            self.assertFalse(nx.kept_own_sentence(text, other), other)

    def test_every_reference_fix_and_every_correct_sentence_is_kept(self):
        for c in CASES['rewrite']:
            self.assertTrue(nx.kept_own_sentence(c['text'], c.get('fix') or c['text']), c['id'])

    def test_short_and_heavily_mended_sentences_still_count(self):
        for a, b in (("Me happy.", "I am happy."), ("I goed home.", "I went home."),
                     ("Yesterday me and my friend go to park play basketball very happy.",
                      "Yesterday my friend and I went to the park to play basketball, and we had a great time.")):
            self.assertTrue(nx.kept_own_sentence(a, b), b)
        self.assertFalse(nx.kept_own_sentence("I like it.", "I like it. " + "And then I went home and read a long book about noise. " * 2))
        self.assertFalse(nx.kept_own_sentence("I like it.", ""))


class MarkingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)), patch.dict(os.environ, AI_ENV)]
        for p in self.patches:
            p.start()
        app.init()
        with app.db() as c:
            c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('lin', 'x')); c.commit()
            self.uid = c.execute("SELECT id FROM users WHERE username='lin'").fetchone()[0]
            nx.save_profile(c, self.uid, {'level': 'B1', 'goal': next(iter(nx.GOALS)), 'themes': [], 'minutes': 15})
        self.calls, self.n = [], 0

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def mark(self, text, *replies):
        def model(messages, audio=None, grounding=False):
            self.calls.append(messages)
            chat_service.LAST['provider'] = 'text'
            return replies[min(len(self.calls), len(replies)) - 1], 'stop'
        self.n += 1
        with patch.object(chat_service, 'request_model', model), app.db() as c:
            return nx.rewrite(c, self.uid, {'pack': PID, 'text': text, 'request_id': f'test-rewrite-{self.n:06d}'})

    def test_the_prompt_asks_for_the_smallest_change_of_the_learners_own_sentence(self):
        self.mark('She sings very good.', answer('She sings very well.', changes=[{'from': 'very good', 'to': 'very well', 'why': '修饰动词用副词'}]))
        system, user = self.calls[0][0]['content'], self.calls[0][1]['content']
        for s in ('最小改动', '绝不能换成另一句话', '不要为了套用本课的句型或话题去改写', '用学习者自己的意思和话题来写', '不要替他改写原句'):
            self.assertIn(s, system)
        self.assertIn('不要据此改写学习者的句子', user)
        self.assertIn('学习者写的英文：\nShe sings very good.', user)  # the format the marking reads is the same

    def test_another_sentence_is_asked_for_once_more_and_the_learners_one_is_kept(self):
        result, status = self.mark('She sings very good.', answer('She is not singing so much as shouting.'),
                                   answer('She sings very well.', changes=[{'from': 'very good', 'to': 'very well', 'why': '修饰动词用副词'}]))
        self.assertEqual(status, 200)
        self.assertEqual(result['result']['corrected'], 'She sings very well.')
        self.assertEqual(len(self.calls), 2)
        again = self.calls[1]
        self.assertEqual(again[2]['role'], 'assistant')
        self.assertIn('不是学习者原句的最小改动', again[3]['content'])
        self.assertIn('She is not singing so much as shouting.', again[3]['content'])

    def test_still_another_sentence_is_not_shown(self):
        result, status = self.mark('There are three child in the room.', answer('The headphones are not blocking sound so much as fighting it.'))
        self.assertEqual(status, 502)
        self.assertNotIn('result', result)
        self.assertEqual(len(self.calls), 2)
        with app.db() as c:  # nothing recorded from it: no mistakes, no score
            self.assertEqual(c.execute("SELECT COUNT(*) FROM next_cards WHERE source='mistake'").fetchone()[0], 0)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM next_skill_events').fetchone()[0], 0)

    def test_a_right_sentence_left_as_it_is_is_marked_natural_in_one_call(self):
        text = 'We decided to stay at home because of the heavy rain.'
        result, status = self.mark(text, answer(text, verdict='rewrite'))  # the model left it, but called it "rewrite"
        self.assertEqual((status, result['result']['verdict'], result['result']['corrected']), (200, 'natural', text))
        self.assertEqual(len(self.calls), 1)

    def test_the_answer_keeps_its_shape(self):
        result, status = self.mark('I very like this song.', answer('I really like this song.', changes=[{'from': 'very like', 'to': 'really like', 'why': '副词位置'}]))
        self.assertEqual(status, 200)
        self.assertTrue({'verdict', 'summary', 'corrected', 'changes', 'versions', 'keep', 'used_well', 'word_use'} <= set(result['result']))


if __name__ == '__main__':
    unittest.main()
