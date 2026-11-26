"""「听两句、答一句」(two_lines, 2026-11-26): the two lines must be neighbours in the text or a level version of it; the
question is shared for the day (one model call for everyone); the answer comes back as met / not_yet, a Chinese line, a
better sentence with one [[expression]] and that expression; assisted goes back as it came; a spoken answer is written
down once and never kept. No AI is called: a stand-in answers."""
import base64, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, ai_routes, next_service as nx, two_lines as tl  # noqa: E402
from lab_service import Shape  # noqa: E402

AI_ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'm', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
          'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0', 'FLOW_AI_AUDIO': '1'}
PID = 'v5-science-b2-noise-cancelling'
AUDIO = {'mime_type': 'audio/webm', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * 64).decode()}
QUESTION = {'question': 'When do you need some quiet in your day', 'zh': '你一天里什么时候需要安静？', 'hint': 'I usually need some quiet when'}
GOOD = {'met': 'met', 'note': '说清楚了在图书馆需要安静。', 'better': 'I need some quiet when I [[focus on]] my homework.', 'save': 'focus on'}


def model(obj):
    return patch('chat_service.request_model', return_value=(json.dumps(obj, ensure_ascii=False), 'stop'))


class TwoLinesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 't.db'); self.p.start()
        self.env = patch.dict(os.environ, AI_ENV); self.env.start()
        app.init(); self.c = app.db()
        for n in ('learner', 'other'):
            self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', (n, 'h'))
        self.c.commit()
        for uid in (1, 2):
            nx.save_profile(self.c, uid, {'level': 'B2', 'goal': 'exam', 'themes': ['science'], 'minutes': 15})
        body = json.loads(self.c.execute('SELECT content FROM lab_packs WHERE id=?', (PID,)).fetchone()[0])['body']
        self.sents = nx.sentences(body)
        self.lines = self.sents[1:3]
        self.n = 0

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def rid(self):
        self.n += 1
        return f'two-test-{self.n:06d}'

    def ask(self, uid=1, **kw):
        return tl.ask(self.c, uid, {'pack': PID, 'i': 1, 'lines': self.lines, 'request_id': self.rid(), **kw})

    def check(self, uid=1, **kw):
        return tl.check(self.c, uid, {'pack': PID, 'i': 1, 'lines': self.lines, 'question': QUESTION['question'] + '?',
                                      'request_id': self.rid(), **kw})

    # ---- the two lines ----
    def test_the_two_lines_must_be_neighbours_in_the_text(self):
        with model(QUESTION):
            self.assertEqual(self.ask()[1], 200)
            self.assertEqual(self.ask(lines=[self.sents[1], self.sents[3]])[1], 400)  # not next to each other
            self.assertEqual(self.ask(lines=['I like tea.', 'It is nice.'])[1], 400)  # not in the text at all
            self.assertEqual(self.ask(lines=[self.sents[1]])[1], 400)
            self.assertEqual(self.ask(pack='no-such-pack')[1], 404)

    def test_a_level_version_counts_too(self):
        self.c.execute('INSERT INTO next_variants(pack, level, body, notes, created) VALUES(?,?,?,?,?)',
                       (PID, 'A2', 'Headphones can stop noise. They make a new sound wave. The two waves cancel out.', '[]', 1.0))
        self.c.commit()
        with model(QUESTION):
            r, s = self.ask(lines=['They make a new sound wave.', 'The two waves cancel out.'])
        self.assertEqual(s, 200, r)

    # ---- the question ----
    def test_a_question_with_an_opener_and_the_day_shares_it(self):
        with model(QUESTION) as m:
            r, s = self.ask()
            self.assertEqual(s, 200)
            self.assertEqual(r['result'], {'question': QUESTION['question'] + '?', 'zh': QUESTION['zh'], 'hint': QUESTION['hint'] + '…'})
            r2, s2 = self.ask(uid=2)  # another learner, the same two lines, the same day: no model call, nothing counted
            self.assertEqual((s2, r2['result'], r2.get('cached')), (200, r['result'], True))
            self.assertEqual(m.call_count, 1)
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM lab_jobs WHERE user_id=2').fetchone()[0], 0)

    def test_what_a_question_must_look_like(self):
        with self.assertRaises(Shape):
            tl.convert_ask({'question': '你平时喝咖啡吗？', 'zh': '你平时喝咖啡吗？'}, guard=lambda p: [])
        with self.assertRaises(Shape):
            tl.convert_ask({'question': 'Why?', 'zh': '为什么？'}, guard=lambda p: [])  # too short to answer
        with self.assertRaises(Shape):
            tl.convert_ask({**QUESTION}, guard=lambda p: ['碰到'])  # a sensitive topic: asked again
        r = tl.convert_ask({**QUESTION, 'hint': '我通常…'}, guard=lambda p: [])
        self.assertEqual(r['hint'], '')  # an opener in Chinese is no opener

    def test_the_prompts_carry_the_lines_the_level_and_the_rules(self):
        q = tl.ask_messages(['A.', 'B.'], 'A2')[1]['content']
        for part in ('1. A.', '2. B.', '入门水平', '不能只用 yes 或 no', '不问真实姓名', '以 … 结尾'):
            self.assertIn(part, q)
        k = tl.check_messages(['A.', 'B.'], 'Why?', 'Because.', 'B1', True)[1]['content']
        for part in ('语音转写', '语法小错不影响', '[[ ]]', '整句只标一处', '不评价学习者本人'):
            self.assertIn(part, k)

    # ---- the answer ----
    def test_a_typed_answer_is_judged_and_assisted_goes_back_as_it_came(self):
        with model(GOOD):
            r, s = self.check(text='I need quiet when I do homework.', assisted=True)
        self.assertEqual(s, 200, r)
        self.assertEqual(r['result'], {**GOOD, 'assisted': True})
        with model({**GOOD, 'met': 'not yet'}):
            r, _ = self.check(text='Noise is bad for me.')
        self.assertEqual((r['result']['met'], r['result']['assisted']), ('not_yet', None))  # not sent: not known
        self.assertEqual(self.check(text='hi')[1], 400)  # one word is no answer
        self.assertEqual(self.check(text='I like it.', question='你喜欢吗？')[1], 400)

    def test_one_expression_is_marked_and_saved(self):
        r = tl.convert_check({**GOOD, 'better': 'I need some quiet when I focus on my homework.'})  # the mark left out
        self.assertEqual((r['better'], r['save']), ('I need some quiet when I [[focus on]] my homework.', 'focus on'))
        r = tl.convert_check({**GOOD, 'better': 'I [[need]] quiet to [[focus on]] work.', 'save': 'need'})
        self.assertEqual((r['better'], r['save']), ('I [[need]] quiet to focus on work.', 'need'))
        for bad in ({**GOOD, 'met': 'maybe'}, {**GOOD, 'note': 'Good job.'}, {**GOOD, 'better': '我需要安静。'},
                    {**GOOD, 'better': 'I need quiet.', 'save': 'focus on'}):
            with self.assertRaises(Shape):
                tl.convert_check(bad)

    def test_a_spoken_answer_is_written_down_once_and_never_kept(self):
        heard = 'I need some quiet when I read before bed.'
        replies = iter([('{"met": "met"}', 'stop'), (json.dumps(GOOD, ensure_ascii=False), 'stop')])  # the first one in a bad shape
        with patch('chat_service.write_down', return_value=heard) as wd, patch('chat_service.request_model', side_effect=lambda m: next(replies)) as rm:
            r, s = self.check(audio=AUDIO)
        self.assertEqual(s, 200, r)
        self.assertEqual((wd.call_count, rm.call_count), (1, 2))  # asked again, not written down again
        self.assertIn(heard, rm.call_args_list[0][0][0][1]['content'])  # the text model judged what was said
        stored = self.c.execute("SELECT result FROM lab_jobs WHERE kind=?", (tl.CHECK,)).fetchone()[0]
        self.assertNotIn('read before bed', stored)  # what was heard is not kept

    def test_nothing_heard_asks_again_without_a_text_model(self):
        with patch('chat_service.write_down', return_value=''), patch('chat_service.request_model') as rm:
            r, s = self.check(audio=AUDIO)
        self.assertEqual(s, 200)
        self.assertEqual((r['result']['met'], r['result']['note'], r['result'].get('heard_nothing')), ('not_yet', tl.NOTHING_HEARD, True))
        rm.assert_not_called()

    def test_both_are_the_learners_own_tasks_on_a_route(self):
        self.assertEqual((ai_routes.GROUP[tl.CHECK], ai_routes.GROUP[tl.ASK]), ('grading', 'content'))
        self.assertIn(tl.CHECK, ai_routes.LABEL); self.assertNotIn(tl.CHECK, ai_routes.NOT_LEARNER)
        with patch.dict(os.environ, {'FLOW_TEXT_AI_MODEL': 'flow-text', 'FLOW_AI_ROUTES': '*=flow-text-ds-flash'}):
            self.assertEqual(ai_routes.route(tl.CHECK), 'flow-text-ds-flash')


if __name__ == '__main__':
    unittest.main()
