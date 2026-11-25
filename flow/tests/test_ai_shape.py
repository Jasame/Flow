"""Answers worded unlike the prompt asked (DeepSeek does it now and then: 内测版 b12, 2026-11-25, a dialogue's feedback came
back whole but was refused as 「不完整」): scores as strings, a missing summary, extra fields, text around the JSON, a long
field. The readers take them; an answer still unusable is asked for once more on the same model, then from the main
service (Gemini); each miss is marked in ai_calls with a fixed code, never the learner's text."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, next_service as nx, output_service as out, lab_service as lab, ielts_speaking as ie  # noqa: E402

AI_ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'gemini-test', 'FLOW_AI_URL': 'https://x.test/v1/chat/completions',
          'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0', 'FLOW_TEXT_AI_MODEL': ''}
HIST = [{'role': 'ai', 'text': 'Hi! What can I get you?'}, {'role': 'me', 'text': 'A latte, please.'}, {'role': 'ai', 'text': 'Sure. Anything else?'}]
END = {'summary': '敢开口，回答切题。', 'good': ['A latte, please.'], 'fixes': [], 'expressions': [], 'score': 0.7}


class ReaderTests(unittest.TestCase):
    def test_json_in_a_fence_or_a_sentence(self):
        self.assertEqual(lab.parse('```json\n{"a": 1}\n```'), {'a': 1})
        self.assertEqual(lab.parse('Here is the JSON you asked for:\n{"a": {"b": 2}}\nHope it helps.'), {'a': {'b': 2}})
        with self.assertRaises(lab.Shape) as e:
            lab.parse('Sorry, I cannot do that.')
        self.assertEqual(e.exception.code, 'json_parse')

    def test_numbers_as_a_model_writes_them(self):
        for v, want in ((0.7, 0.7), ('0.7', 0.7), ('0.7分', 0.7), ('70%', 0.7), ('7/10', 0.7), (70, 0.7), ('score: 0.65', 0.65)):
            self.assertAlmostEqual(lab.mnum(v), want, msg=v)
        self.assertAlmostEqual(lab.mnum('Band 6.5', 1, 9), 6.5); self.assertAlmostEqual(lab.mnum('6.5/9', 1, 9), 6.5)
        self.assertAlmostEqual(lab.mnum('85%', 0, 100), 85); self.assertEqual(lab.mnum('4分', 1, 5), 4)
        self.assertEqual(lab.mnum(None, 1, 5, default=1), 1); self.assertEqual(lab.mnum(1.7, 0, 1), 1.0)
        for bad in (None, 'n/a', '', True, float('nan'), [0.5]):
            with self.assertRaises(lab.Shape):
                lab.mnum(bad)

    def test_text_and_flags_as_a_model_writes_them(self):
        self.assertEqual(lab.mtext('x' * 900, 1, 500), 'x' * 500)  # long is cut, not refused
        self.assertEqual(lab.mtext(None, 1, 500, default='兜底'), '兜底')
        with self.assertRaises(lab.Shape) as e:
            lab.mtext('  ', 1, 500, 'summary_empty')
        self.assertEqual(e.exception.code, 'summary_empty')
        self.assertEqual(lab.mtext(42, 1, 10), '42')
        self.assertEqual([lab.mbool(v) for v in (True, 'true', 'Yes', '是', 1, False, 'false', '否', 0)], [True] * 5 + [False] * 4)
        with self.assertRaises(lab.Shape):
            lab.mbool('maybe')
        self.assertEqual((ie.band('Band 6.5'), ie.band('7分'), ie.band('—')), (6.5, 7.0, None))


class JobTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 's.db'); self.p.start()
        self.env = patch.dict(os.environ, AI_ENV); self.env.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'h')); self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'daily', 'themes': [], 'minutes': 15})

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def end(self, rid='shape-end-00001'):
        with patch('tts_service.start', create=True):
            return out.dialog(self.c, 1, {'scenario': 'cafe-order', 'history': HIST, 'end': True, 'request_id': rid})

    def calls(self):
        return [tuple(r) for r in self.c.execute('SELECT service, ok, error FROM ai_calls ORDER BY id')]

    def test_a_deepseek_style_end_of_round_is_taken(self):
        # the b12 case: a score as a string with a unit, no summary, a field nobody asked for, the JSON after a sentence
        reply = '好的，以下是反馈：\n' + json.dumps({**END, 'summary': '', 'score': '0.7分', 'level_guess': 'B1', 'extra': [1, 2]}, ensure_ascii=False)
        with patch('chat_service._request_main', return_value=(reply, 'stop')) as m:
            r, st = self.end()
        self.assertEqual(st, 200); self.assertEqual(m.call_count, 1)
        self.assertEqual((r['result']['score'], r['result']['summary']), (0.7, '这一轮练完了，下面是具体的反馈。'))
        self.assertNotIn('extra', r['result'])

    def test_an_unusable_answer_is_asked_for_once_more(self):
        good = json.dumps(END, ensure_ascii=False)
        with patch('chat_service._request_main', side_effect=[('not json at all', 'stop'), (good, 'stop')]):
            r, st = self.end()
        self.assertEqual((st, r['result']['score']), (200, 0.7))
        self.assertEqual(self.calls(), [('main', 0, 'shape: json_parse'), ('main', 1, '')])

    def test_after_two_misses_on_the_text_model_gemini_answers(self):
        good = json.dumps(END, ensure_ascii=False)
        with patch.dict(os.environ, {'FLOW_TEXT_AI_MODEL': 'flow-text'}), \
             patch('chat_service._request_text_service', return_value=(json.dumps({**END, 'score': 'n/a'}), 'stop')) as t, \
             patch('chat_service._request_main', return_value=(good, 'stop')) as m:
            r, st = self.end()
        self.assertEqual((st, t.call_count, m.call_count), (200, 2, 1))
        self.assertEqual(self.calls(), [('text', 0, 'shape: score_nan'), ('text', 0, 'shape: score_nan'), ('main', 1, '')])

    def test_three_misses_say_incomplete_and_keep_no_text(self):
        with patch('chat_service._request_main', return_value=('{"summary": "我想说的是 I want buy a coffee"}', 'stop')):
            r, st = self.end()
        self.assertEqual(st, 502); self.assertIn('不完整', r['error'])
        rows = self.calls()
        self.assertEqual(len(rows), 3); self.assertTrue(all(ok == 0 and err == 'shape: score_nan' for _, ok, err in rows))
        self.assertNotIn('coffee', json.dumps(rows))

    def test_a_row_that_was_not_written_never_marks_an_older_one(self):
        import ai_routes, time as _t
        ai_routes.record('main', 'gemini-test', _t.monotonic(), [], 'ok')  # an earlier call, written
        with patch('ai_routes._db', return_value=None):
            ai_routes.record('main', 'gemini-test', _t.monotonic(), [], 'x')  # this one could not be written
        ai_routes.mark_shape('json_parse')
        self.assertEqual(self.calls(), [('main', 1, '')])

    def omni_then_gemini(self, *heard):
        # each call answered by Qwen-Omni ('audio'), the last of run_job's three by Gemini ('main'), as ai_routes notes it
        import ai_routes, chat_service
        it, by = iter(heard), []
        self.addCleanup(setattr, ai_routes.CTX, 'last_service', None)

        def fake(msgs, audio=None, grounding=False):
            s = 'main' if getattr(chat_service.MAIN_ONLY, 'on', False) else 'audio'
            ai_routes.CTX.last_service = s; by.append(s)
            return json.dumps({'heard': next(it), 'reply': 'Sure. Anything else?', 'correction': None, 'hint': ''}), 'stop'
        return patch('chat_service.request_model', side_effect=fake), by

    def spoken_turn(self, rid):
        import base64
        audio = {'mime_type': 'audio/webm', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * 64).decode()}
        with patch.dict(os.environ, {'FLOW_AI_AUDIO': '1'}), patch('tts_service.start', create=True):
            return out.dialog(self.c, 1, {'scenario': 'cafe-order', 'history': HIST, 'audio': audio, 'request_id': rid})

    def test_omni_hearing_nothing_is_asked_again(self):
        # 正式版 2026-11-25 08:26: Qwen-Omni answered a spoken turn whole with nothing heard (0 times in 20 with that clip)
        p, by = self.omni_then_gemini('', 'A latte, please.')
        with p:
            r, st = self.spoken_turn('shape-heard-0001')
        self.assertEqual((st, r['result']['heard'], by), (200, 'A latte, please.', ['audio', 'audio']))

    def test_when_gemini_hears_nothing_too_the_recording_may_be_silent(self):
        p, by = self.omni_then_gemini('', '', '')
        with p:
            r, st = self.spoken_turn('shape-heard-0002')
        self.assertEqual((st, r['result']['heard'], by), (200, '', ['audio', 'audio', 'main']))

    def test_an_empty_transcript_from_gemini_is_not_a_miss(self):
        import ai_routes
        self.addCleanup(setattr, ai_routes.CTX, 'last_service', None)  # thread-local: not left for the next test
        ai_routes.CTX.last_service = 'main'
        self.assertEqual(lab.mheard('  '), '')
        ai_routes.CTX.last_service = 'audio'
        with self.assertRaises(lab.Shape) as e:
            lab.mheard(None)
        self.assertEqual(e.exception.code, 'heard_empty')
        self.assertEqual(lab.mheard('x' * 900, 600), 'x' * 600)

    def test_a_cut_off_answer_counts_as_a_miss(self):
        good = json.dumps(END, ensure_ascii=False)
        with patch('chat_service._request_main', side_effect=[('{"summary": "敢开口', 'length'), (good, 'stop')]):
            r, st = self.end()
        self.assertEqual(st, 200); self.assertEqual(self.calls()[0][1:], (0, 'shape: truncated'))

    def test_an_ielts_answer_with_bands_as_strings(self):
        reply = json.dumps({'bands': {'fc': '6.5分', 'lr': 'Band 6', 'gra': '6', 'p': None}, 'notes': {}, 'summary': 'x' * 900,
                            'fixes': [], 'model': 'I usually get up early.', 'model_q': '1'}, ensure_ascii=False)
        answers = [{'q': 0, 'text': 'I get up at seven because I like a quiet morning.', 'spoken': False}]
        with patch('chat_service._request_main', return_value=(reply, 'stop')):
            r, st = ie.part1_feedback(self.c, 1, {'topic': 'mornings', 'answers': answers, 'request_id': 'shape-ielts-0001'})
        self.assertEqual(st, 200)
        self.assertEqual([x['band'] for x in r['result']['criteria']][:3], [6.5, 6.0, 6.0]); self.assertEqual(len(r['result']['summary']), 400)


if __name__ == '__main__':
    unittest.main()
