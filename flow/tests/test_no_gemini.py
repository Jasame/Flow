"""No Gemini for learners (2026-11-25, the owner: 「换成国内已备案模型」): with FLOW_MAIN_AI=off the main model is never
asked. A text route that fails goes to FLOW_BACKUP_AI_MODEL (another 百炼 model); a dialogue / retell / IELTS recording
whose audio route fails is written down by FLOW_ASR_AI_MODEL and answered by that backup model; 跟读 has no text
backup; run_job's last try asks the backup model. 发音 (FLOW_SAY_JUDGE=asr) is judged by speech recognition told the
word and its pair word. With the switch on (the default) nothing changes (test_ai_routing, test_audio_route)."""
import base64, io, json, os, sys, tempfile, unittest, urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, ai_routes, chat_service as cs, next_service as nx, output_service as out  # noqa: E402

GW = 'https://gw.test/v1/chat/completions'
ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_URL': GW, 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'gemini-3.8-flash', 'FLOW_AI_AUDIO': '1',
       'FLOW_TEXT_AI_MODEL': 'flow-text', 'FLOW_AI_ROUTES': '*=flow-text-ds-flash', 'FLOW_MAIN_AI': 'off',
       'FLOW_BACKUP_AI_MODEL': 'flow-text-qwen-plus', 'FLOW_ASR_AI_MODEL': 'flow-audio-asr-flash',
       'FLOW_AUDIO_ROUTES': 'next-dialog=flow-audio-omni-flash,next-shadow=flow-audio-omni-flash',
       'FLOW_AI_DAILY_LIMIT': '0', 'FLOW_AI_USER_DAILY_LIMIT': '0'}
WEBM = {'mime_type': 'audio/webm', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * 64).decode()}
MSGS = [{'role': 'system', 'content': '只输出 JSON。'}, {'role': 'user', 'content': '学习者刚才说了一句话（录音，先忠实转写）。'}]


class Reply:
    def __init__(self, text, model):
        self.body = json.dumps({'model': model, 'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]}).encode()
        self.headers = {'Content-Type': 'application/json'}

    def __enter__(self):
        return io.BytesIO(self.body)

    def __exit__(self, *a):
        return False


class Stream:
    def __init__(self, text, model):
        chunks = [{'model': model, 'choices': [{'index': 0, 'delta': {'content': text}}]},
                  {'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}]
        self.lines = [x for c in chunks for x in (f'data: {json.dumps(c)}\n'.encode(), b'\n')] + [b'data: [DONE]\n', b'\n']
        self.headers = {'Content-Type': 'text/event-stream'}

    def __enter__(self):
        return iter(self.lines)

    def __exit__(self, *a):
        return False


def gateway(answers):
    """urlopen stand-in for the gateway: answers maps a model name to a reply text or an exception (or a list of them)."""
    sent = []

    def urlopen(req, timeout=None):
        body = json.loads(req.data)
        sent.append(body)
        name = body['model']
        a = answers.get(name, AssertionError('asked ' + name))
        if isinstance(a, list):
            a = a.pop(0)
        if isinstance(a, Exception):
            raise a
        return Stream(a, name) if body.get('stream') else Reply(a, name)
    return urlopen, sent


def down(code=503):
    return urllib.error.HTTPError(GW, code, 'down', None, None)


class RoutingTests(unittest.TestCase):
    def ask(self, answers, kind='next-rewrite', audio=None, env=None, main_only=False):
        urlopen, sent = gateway(answers)
        with patch.dict(os.environ, {**ENV, **(env or {})}), patch('urllib.request.urlopen', urlopen), ai_routes.task(kind), \
                patch('time.sleep'):
            if main_only:
                with cs.main_only():
                    outp = cs.request_model(MSGS, audio=audio)
            else:
                outp = cs.request_model(MSGS, audio=audio)
        return outp, [b['model'] for b in sent], sent

    def test_text_that_fails_goes_to_the_other_bailian_model_never_gemini(self):
        outp, models, _ = self.ask({'flow-text-ds-flash': down(), 'flow-text-qwen-plus': '{"ok": 1}'})
        self.assertEqual(outp[0], '{"ok": 1}')
        self.assertEqual(models, ['flow-text-ds-flash', 'flow-text-qwen-plus'])

    def test_with_gemini_on_the_main_model_still_takes_over_as_before(self):
        outp, models, _ = self.ask({'flow-text-ds-flash': down(), 'gemini-3.8-flash': 'from gemini'}, env={'FLOW_MAIN_AI': 'on'})
        self.assertEqual(models, ['flow-text-ds-flash', 'gemini-3.8-flash'])

    def test_a_dialogue_recording_whose_omni_fails_is_written_down_then_answered_by_text(self):
        outp, models, sent = self.ask({'flow-audio-omni-flash': down(502), 'flow-audio-asr-flash': 'I would like a coffee.',
                                       'flow-text-qwen-plus': '{"heard": "I would like a coffee.", "reply": "Sure."}'}, kind='next-dialog', audio=WEBM)
        self.assertEqual(models, ['flow-audio-omni-flash', 'flow-audio-asr-flash', 'flow-text-qwen-plus'])
        self.assertIn('学习者说：I would like a coffee.', sent[-1]['messages'][-1]['content'])
        self.assertNotIn('input_audio', json.dumps(sent[-1]))  # the text model gets words, not the recording
        self.assertEqual(sent[1]['asr_options']['language'], 'en')

    def test_shadowing_has_no_text_backup_it_needs_the_sound(self):
        with self.assertRaises(urllib.error.HTTPError):
            self.ask({'flow-audio-omni-flash': [down(502), down(502)]}, kind='next-shadow', audio=WEBM)

    def test_a_recording_without_an_audio_route_is_refused_not_sent_to_gemini(self):
        from vertex_auth import AIConfigurationError
        with self.assertRaises(AIConfigurationError):
            self.ask({}, kind='next-say', audio=WEBM)

    def test_the_last_try_of_run_job_asks_the_backup_model(self):
        outp, models, _ = self.ask({'flow-text-qwen-plus': '{"ok": 2}'}, main_only=True)
        self.assertEqual(models, ['flow-text-qwen-plus'])

    def test_after_omni_twice_with_nothing_heard_the_last_try_is_recognition_then_text(self):  # r30 e2e
        outp, models, sent = self.ask({'flow-audio-asr-flash': 'I want headphones for the train.',
                                       'flow-text-qwen-plus': '{"heard": "I want headphones for the train.", "reply": "Sure."}'},
                                      kind='next-dialog', audio=WEBM, main_only=True)
        self.assertEqual(models, ['flow-audio-asr-flash', 'flow-text-qwen-plus'])

    def test_a_search_without_bailian_search_is_refused(self):
        from vertex_auth import AIConfigurationError
        urlopen, sent = gateway({})
        with patch.dict(os.environ, ENV), patch('urllib.request.urlopen', urlopen), self.assertRaises(AIConfigurationError):
            cs.request_model(MSGS, grounding=True)
        self.assertEqual(sent, [])

    def test_transcribe_tells_the_recogniser_the_two_words(self):
        urlopen, sent = gateway({'flow-audio-asr-flash': 'Sink.'})
        with patch.dict(os.environ, ENV), patch('urllib.request.urlopen', urlopen):
            self.assertEqual(cs.transcribe(WEBM, ['think', 'sink']), 'Sink.')
        body = sent[0]
        self.assertEqual(body['model'], 'flow-audio-asr-flash')
        self.assertIn('"think" or "sink"', body['messages'][0]['content'][0]['text'])
        self.assertEqual(body['messages'][1]['content'][0]['type'], 'input_audio')
        self.assertEqual(body['asr_options'], {'language': 'en', 'enable_itn': False})


class DialogTests(unittest.TestCase):
    """A dialogue turn by voice end to end: Omni answers twice with nothing heard (Shape heard_empty), the last try is
    speech recognition then the backup model; a refused service reads as a plain sentence, never an admin's."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 's.db'); self.p.start()
        self.env = patch.dict(os.environ, ENV); self.env.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'h')); self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'daily', 'themes': [], 'minutes': 15})

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def turn(self, answers, rid):
        urlopen, sent = gateway(answers)
        hist = [{'role': 'ai', 'text': 'Hi! What can I get you?'}]
        with patch('urllib.request.urlopen', urlopen), patch('time.sleep'), patch('tts_service.start', create=True):
            result, status = out.dialog(self.c, 1, {'scenario': 'cafe-order', 'history': hist, 'audio': WEBM, 'request_id': rid})
        return result, status, [b['model'] for b in sent]

    def test_nothing_heard_twice_then_recognition_and_text_answer(self):
        empty = json.dumps({'heard': '', 'reply': 'Sure.', 'correction': None, 'hint': '', 'say': ''})
        good = json.dumps({'heard': 'A latte, please.', 'reply': 'Sure, one latte.', 'correction': None, 'hint': '', 'say': ''})
        result, status, models = self.turn({'flow-audio-omni-flash': [empty, empty], 'flow-audio-asr-flash': 'A latte, please.',
                                            'flow-text-qwen-plus': good}, 'dlg-empty-0001')
        self.assertEqual(status, 200, result)
        self.assertEqual(result['result']['heard'], 'A latte, please.')
        self.assertEqual(models, ['flow-audio-omni-flash', 'flow-audio-omni-flash', 'flow-audio-asr-flash', 'flow-text-qwen-plus'])

    def test_a_refused_service_reads_as_a_plain_sentence(self):
        result, status, models = self.turn({'flow-audio-omni-flash': [down(403), down(403)], 'flow-audio-asr-flash': down(403)}, 'dlg-403-0001')
        self.assertNotEqual(status, 200)
        self.assertNotIn('管理员', result['error']); self.assertNotIn('Google', result['error'])
        self.assertIn('稍后再试', result['error'])


class VerdictTests(unittest.TestCase):
    def test_wrong_only_when_the_pair_word_was_heard_and_the_target_not(self):
        self.assertFalse(out.say_verdict('think', 'sink', 'Sink.')['ok'])
        self.assertTrue(out.say_verdict('think', 'sink', 'Think.')['ok'])
        self.assertTrue(out.say_verdict('think', 'sink', 'think sink')['ok'])  # both: not sure, not wrong
        self.assertTrue(out.say_verdict('think', 'sink', 'Thing.')['ok'])  # neither: lenient, as the prompt was
        v = out.say_verdict('think', 'sink', 'sink')
        self.assertEqual((v['heard'], v['note']), ('sink', '听起来像 sink，不像 think'))
        self.assertIn('/θ/', v['tip'])

    def test_the_target_counts_only_as_a_whole_word(self):  # 语流 09's review of #175
        for target, heard in (('hat', 'That.'), ('it', 'Sit.'), ('ear', 'Year.')):
            v = out.say_verdict(target, '', heard)
            self.assertFalse(v['ok'], (target, heard))
        v = out.say_verdict('ship', 'sheep', 'Worship.')
        self.assertTrue(v['ok'])  # not the pair's mistake: let through, but said as heard
        self.assertEqual(v['note'], '听起来像 worship，没有读成 sheep')
        v = out.say_verdict('think', 'sink', 'Pink.')
        self.assertEqual(v['note'], '听起来像 pink，没有读成 sink')
        self.assertNotIn('听起来是 think', v['note'])

    def test_nothing_heard_is_a_reference_not_a_verdict(self):
        v = out.say_verdict('think', 'sink', '')
        self.assertTrue(v['unclear'])

    def test_a_word_without_a_pair_is_judged_on_what_was_heard(self):
        self.assertTrue(out.say_verdict('library', '', 'Libary.')['ok'])
        self.assertFalse(out.say_verdict('library', '', 'Banana.')['ok'])


class SayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 's.db'); self.p.start()
        self.env = patch.dict(os.environ, {**ENV, 'FLOW_SAY_JUDGE': 'asr'}); self.env.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'h')); self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'daily', 'themes': [], 'minutes': 15})

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def say(self, heard, rid):
        def transcribe(audio, words=None):
            self.assertEqual(words, ['think', 'sink'])
            ai_routes.CTX.last_service = 'asr'
            return heard
        with patch.object(cs, 'transcribe', transcribe), patch.object(cs, '_request_main', side_effect=AssertionError('Gemini asked')):
            result, status = out.say(self.c, 1, {'text': 'think', 'audio': WEBM, 'request_id': rid})
        self.assertEqual(status, 200, result)
        return result['result']

    def test_a_miss_then_a_second_miss_makes_the_card_a_right_reading_does_not(self):
        r = self.say('Think.', 'say-asr-0001')
        self.assertTrue(r['ok']); self.assertFalse(r['tentative'])
        r = self.say('Sink.', 'say-asr-0002')
        self.assertFalse(r['ok']); self.assertFalse(r['confirmed']); self.assertEqual(r['heard'], 'sink')
        r = self.say('Sink.', 'say-asr-0003')
        self.assertTrue(r['confirmed'])  # trusted (the recogniser, not a model's guess): two misses in a row file it
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE user_id=1 AND norm='sound:think'").fetchone()[0], 1)

    def test_nothing_heard_counts_as_practice_only(self):
        r = self.say('', 'say-asr-0004')
        self.assertTrue(r['tentative']); self.assertFalse(r['confirmed'])

    def test_without_the_switch_the_model_prompt_is_used(self):
        with patch.dict(os.environ, {'FLOW_SAY_JUDGE': ''}):
            self.assertFalse(out.say_by_asr())
        self.assertTrue(out.say_by_asr())


if __name__ == '__main__':
    unittest.main()
