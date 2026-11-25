"""No Gemini for learners (2026-11-25, the owner: 「换成国内已备案模型」): with FLOW_MAIN_AI=off the main model is never
asked. A text route that fails goes to FLOW_BACKUP_AI_MODEL (another 百炼 model); a dialogue / retell / IELTS recording
whose audio route fails is written down by FLOW_ASR_AI_MODEL and answered by that backup model; 跟读 has no text
backup; run_job's last try asks the backup model. 发音 (FLOW_SAY_JUDGE=asr) is judged by speech recognition told the
word and its pair word. With the switch on (the default) nothing changes (test_ai_routing, test_audio_route)."""
import base64, io, json, os, sys, tempfile, time, unittest, urllib.error
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
        self.assertTrue(out.say_verdict('think', 'sink', 'Thing.')['ok'])  # neither, but nearer the target: right
        v = out.say_verdict('think', 'sink', 'sink')
        self.assertEqual((v['heard'], v['note']), ('sink', '听起来像 sink，不像 think'))
        self.assertIn('/θ/', v['tip'])

    def test_the_target_counts_only_as_a_whole_word(self):  # 语流 09's review of #175
        for target, heard in (('hat', 'That.'), ('it', 'Sit.'), ('ear', 'Year.')):
            v = out.say_verdict(target, '', heard)
            self.assertFalse(v['ok'], (target, heard))
        v = out.say_verdict('ship', 'sheep', 'Worship.')
        self.assertTrue(v['ok'])  # not the pair's mistake, and nearer the target: let through, said as heard
        self.assertEqual(v['note'], '听起来像 worship，接近 ship')
        v = out.say_verdict('think', 'sink', 'Pink.')
        self.assertNotIn('听起来是 think', v['note'])

    def test_a_third_word_is_right_only_when_it_leans_to_the_target(self):  # 语流 B3, 2026-11-25 (zinc in the r32 e2e)
        cases = [('think', 'sink', 'Zinc.', False, 'third_near_pair', '听起来像 zinc，不像 think'),  # one sound from both: spelling
                 ('think', 'sink', 'Thing.', True, 'third_ok', '听起来像 thing，接近 think'),
                 ('think', 'sink', 'Pink.', False, 'third_near_pair', '听起来像 pink，不像 think'),
                 ('think', 'sink', 'Sing.', False, 'third_near_pair', '听起来像 sing，更接近 sink，不像 think'),  # by sound
                 ('ship', 'sheep', 'Shape.', False, 'third_unclear', '没听出 ship，听着像 shape，可以再读一遍'),  # a tie is never right
                 ('ship', 'sheep', 'Worship.', True, 'third_ok', '听起来像 worship，接近 ship'),
                 ('think', 'sink', 'Banana.', False, 'third_unclear', '没听出 think，听着像 banana，可以再读一遍')]
        for target, partner, heard, ok, reason, note in cases:
            v = out.say_verdict(target, partner, heard)
            self.assertEqual((v['ok'], v['reason'], v['note']), (ok, reason, note), heard)
            self.assertEqual(v.get('reference') is True, not ok, heard)  # wrong this way: a reference only, never a card
        self.assertIn('/θ/', out.say_verdict('think', 'sink', 'Zinc.')['tip'])  # leans to the pair: the tip as for the pair
        self.assertEqual(out.say_verdict('think', 'sink', 'Banana.')['tip'], '')

    def test_nothing_heard_is_a_reference_not_a_verdict(self):
        v = out.say_verdict('think', 'sink', '')
        self.assertTrue(v['unclear'])

    def test_a_word_without_a_pair_is_judged_on_what_was_heard(self):
        self.assertTrue(out.say_verdict('library', '', 'Libary.')['ok'])
        self.assertFalse(out.say_verdict('library', '', 'Banana.')['ok'])

    def test_a_word_written_as_one_that_sounds_the_same_is_right(self):  # 语流 09: their written as there
        for target, heard in (('their', 'There.'), ('right', 'Write.'), ('too', 'two'), ('whole', 'Hole.'),
                              ('weather', 'Whether.'), ('flour', 'Flower.'), ('know', 'No.'), ('to', 'Too.')):
            v = out.say_verdict(target, '', heard)
            self.assertTrue(v['ok'], (target, heard))
            self.assertEqual(v['note'], f'听起来是 {target}（和 {heard.strip(".").lower()} 同音）')

    def test_sounding_alike_needs_the_same_vowel_length_and_a_full_form(self):
        for target, partner, heard in (('ship', '', 'Sheep.'), ('ship', 'sheep', 'Sheep.'), ('bean', '', 'Bin.'),
                                       ('there', '', 'The.'), ('ear', '', 'Year.')):
            self.assertFalse(out.say_verdict(target, partner, heard)['ok'], (target, heard))
        self.assertFalse(out.same_sound('bean', 'bin'))  # [biːn] / [bin]: the length mark tells them apart
        self.assertFalse(out.same_sound('there', 'the'))  # [ðə] is only there's weak form

    def test_the_pair_word_written_as_one_that_sounds_like_it_is_still_the_pair_word(self):
        v = out.say_verdict('light', 'right', 'Write.')
        self.assertFalse(v['ok'])
        self.assertEqual(v['note'], '听起来像 right（和 write 同音），不像 light')

    def test_no_practice_pair_sounds_alike_in_the_dictionary(self):
        import sounds
        self.assertGreater(len(sounds.SETS), 5)
        for s in sounds.SETS:
            for a, b in s['pairs']:
                self.assertFalse(out.same_sound(a, b), (a, b))


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



class OmniWordTests(unittest.TestCase):
    """发音 without qwen3-asr (Aliyun ticket 2026-11-25 13:58: no filing; the owner: 「不用 qwen3-asr，先用 Omni」): Qwen-Omni
    writes down the word it hears, told nothing of the word expected, and say_verdict decides. A reference only until
    FLOW_SAY_COUNTS=on (the owner: 「先只作参考」); every verdict is logged without the account for the spot-check."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = patch.object(app, 'DB', Path(self.tmp.name) / 's.db'); self.p.start()
        self.env = patch.dict(os.environ, {**ENV, 'FLOW_SAY_JUDGE': ''}); self.env.start()
        app.init(); self.c = app.db()
        self.c.execute('INSERT INTO users(username,password) VALUES(?,?)', ('learner', 'h')); self.c.commit()
        nx.save_profile(self.c, 1, {'level': 'B1', 'goal': 'daily', 'themes': [], 'minutes': 15})

    def tearDown(self):
        self.c.close(); self.env.stop(); self.p.stop(); self.tmp.cleanup()

    def say(self, answer, rid, text='think', counts=''):
        urlopen, sent = gateway({'flow-audio-omni-flash': [answer]})
        with patch('urllib.request.urlopen', urlopen), patch('time.sleep'), patch.dict(os.environ, {'FLOW_SAY_COUNTS': counts}), \
                patch.object(cs, '_request_main', side_effect=AssertionError('Gemini asked')), \
                patch.object(cs, 'transcribe', side_effect=AssertionError('qwen3-asr asked')):
            result, status = out.say(self.c, 1, {'text': text, 'audio': WEBM, 'request_id': rid})
        self.assertEqual(status, 200, result)
        return result['result'], sent

    def test_omni_writes_the_word_down_told_nothing_and_with_the_switch_two_misses_make_the_card(self):
        r, sent = self.say('Think.', 'say-omni-0001', counts='on')
        self.assertTrue(r['ok']); self.assertFalse(r['tentative'])
        self.assertEqual([b['model'] for b in sent], ['flow-audio-omni-flash'])
        asked = json.dumps([m if isinstance(m['content'], str) else [x for x in m['content'] if x.get('type') == 'text'] for m in sent[0]['messages']])
        self.assertNotIn('think', asked); self.assertNotIn('sink', asked)  # told nothing: hints made it worse (5 / 10 in 48)
        r, _ = self.say('Sink.', 'say-omni-0002', counts='on')
        self.assertFalse(r['ok']); self.assertFalse(r['confirmed']); self.assertEqual(r['heard'], 'sink')
        r, _ = self.say('Sink.', 'say-omni-0003', counts='on')
        self.assertTrue(r['confirmed'])
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE user_id=1 AND norm='sound:think'").fetchone()[0], 1)
        self.assertEqual([x[0] for x in self.c.execute("SELECT DISTINCT service FROM ai_calls")], ['word'])

    def test_by_default_a_reference_only_never_a_mistake_and_logged_without_the_account(self):
        for i in range(3):
            r, _ = self.say('Sink.', f'say-omni-01{i}0')
            self.assertFalse(r['ok']); self.assertTrue(r['tentative']); self.assertFalse(r['confirmed'])
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE user_id=1").fetchone()[0], 0)
        rows = [tuple(x) for x in self.c.execute('SELECT word, partner, judge, reason, ok, counted FROM say_judgements')]
        self.assertEqual(rows, [('think', 'sink', 'omni', 'pair', 0, 0)] * 3)
        cols = [x[1] for x in self.c.execute('PRAGMA table_info(say_judgements)')]
        self.assertEqual(cols, ['id', 'day', 'word', 'partner', 'judge', 'reason', 'ok', 'counted'])  # nothing of the learner's
        self.assertRegex(self.c.execute('SELECT day FROM say_judgements').fetchone()[0], r'^\d{4}-\d\d-\d\d$')  # the day, not the moment
        self.assertEqual(out.say_summary(self.c)['wrong_words'], [{'word': 'think', 'partner': 'sink', 'n': 3}])
        self.c.execute("UPDATE say_judgements SET day='2000-01-01'"); self.c.commit()
        self.say('Think.', 'say-omni-0200')
        self.assertEqual([tuple(x) for x in self.c.execute('SELECT word, reason FROM say_judgements')], [('think', 'target')])  # 14 days
        self.c.execute("UPDATE say_judgements SET day='2000-01-01'"); self.c.commit()
        ai_routes.tick(self.c, now=time.time() // 86400 * 86400)  # the daily round (a day's first 5 minutes), nobody practising
        self.assertEqual(self.c.execute('SELECT COUNT(*) FROM say_judgements').fetchone()[0], 0)

    def test_a_word_written_as_one_that_sounds_the_same_is_right(self):
        r, _ = self.say('There.', 'say-omni-0004', text='their')
        self.assertTrue(r['ok']); self.assertEqual(r['note'], '听起来是 their（和 there 同音）')

    def test_nothing_written_down_is_practice_only(self):
        r, _ = self.say('', 'say-omni-0005')
        self.assertTrue(r['tentative']); self.assertFalse(r['confirmed'])

    def test_a_third_word_never_makes_a_card_even_with_the_switch_on(self):  # zinc for think, r32 e2e
        for i in range(3):
            r, _ = self.say('Zinc.', f'say-omni-03{i}0', counts='on')
            self.assertFalse(r['ok']); self.assertTrue(r['tentative']); self.assertFalse(r['confirmed'])
            self.assertEqual(r['reason'], 'third_near_pair')
        self.assertEqual(self.c.execute("SELECT COUNT(*) FROM next_cards WHERE user_id=1").fetchone()[0], 0)
        self.assertEqual([x[0] for x in self.c.execute('SELECT DISTINCT reason FROM say_judgements')], ['third_near_pair'])

    def test_which_judge(self):
        cases = [({}, 'omni'), ({'FLOW_SAY_JUDGE': 'model'}, ''), ({'FLOW_MAIN_AI': 'on'}, ''), ({'FLOW_AUDIO_ROUTES': ''}, ''),
                 ({'FLOW_SAY_JUDGE': 'omni', 'FLOW_MAIN_AI': 'on'}, 'omni'), ({'FLOW_SAY_JUDGE': 'asr'}, 'asr'),
                 ({'FLOW_SAY_JUDGE': 'asr', 'FLOW_ASR_AI_MODEL': ''}, '')]
        for env, judge in cases:
            with patch.dict(os.environ, env):
                self.assertEqual(out.say_judge(), judge, env)
        with patch.dict(os.environ, {'FLOW_AUDIO_ROUTES': 'next-say=flow-audio-omni-x,next-dialog=flow-audio-omni-flash'}):
            self.assertEqual(cs.word_model(), 'flow-audio-omni-x')  # 发音's own route first, else 情景对话's


if __name__ == '__main__':
    unittest.main()
