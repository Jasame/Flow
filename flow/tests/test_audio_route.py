"""Recordings on an audio route (FLOW_AUDIO_ROUTES, Qwen-Omni on 百炼): the task's recording goes to the gateway as an
OpenAI input_audio part with the same prompt, streamed and without thinking; any failure hands it to Gemini as before;
every attempt is in ai_calls with Omni's price; without the setting, or for a task it does not name, nothing changes."""
import base64, io, json, os, sys, tempfile, unittest, urllib.error
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, ai_routes, chat_service as cs  # noqa: E402

GATEWAY = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_URL': 'https://gw.test/v1/chat/completions', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'gemini-3.8-flash',
           'FLOW_TEXT_AI_MODEL': 'flow-text', 'FLOW_AI_AUDIO': '1'}
WEBM = {'mime_type': 'audio/webm', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * 64).decode()}
MP4 = {'mime_type': 'audio/mp4', 'data': base64.b64encode(b'\0\0\0\x18ftypisom' + b'\0' * 64).decode()}
REPLY = json.dumps({'heard': "She don't like coffee", 'reply': 'Oh, what would she like?', 'correction': {'original': "don't", 'better': "doesn't", 'why': '主谓一致'}, 'hint': '', 'say': ''})
MSGS = [{'role': 'system', 'content': '你在和学习者做情景对话。只输出 JSON。'}, {'role': 'user', 'content': '情景：咖啡店\n学习者刚才说了一句话（录音，先忠实转写）。输出 JSON：{…}'}]


class Stream:
    """An SSE answer from the gateway."""
    def __init__(self, text, model='qwen3.8-omni-flash', finish='stop'):
        chunks = [{'model': model, 'choices': [{'index': 0, 'delta': {'content': text[i:i + 9]}}]} for i in range(0, len(text), 9)]
        chunks.append({'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': finish}]})
        chunks.append({'model': model, 'choices': [], 'usage': {'prompt_tokens': 812, 'completion_tokens': 64, 'total_tokens': 876}})
        self.lines = [x for c in chunks for x in (f'data: {json.dumps(c)}\n'.encode(), b'\n')] + [b'data: [DONE]\n', b'\n']
        self.headers = {'Content-Type': 'text/event-stream'}

    def __enter__(self):
        return iter(self.lines)

    def __exit__(self, *a):
        return False


class Plain:
    def __init__(self, body):
        self.body = json.dumps(body).encode()
        self.headers = {'Content-Type': 'application/json'}

    def __enter__(self):
        return io.BytesIO(self.body)

    def __exit__(self, *a):
        return False


def gemini(text=REPLY):
    return Plain({'model': 'gemini-3.8-flash', 'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]})


class AudioRouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.p = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.dict(os.environ, GATEWAY), patch('ai_stream.active', return_value=False), patch('time.sleep')]
        for x in self.p:
            x.start()
        os.environ.pop('FLOW_AUDIO_ROUTES', None)
        os.environ.pop('FLOW_AI_LANE', None)
        ai_routes._CHOICES.update(at=9e18, names=['flow-audio-omni-flash', 'flow-eval-omni-flash'])
        app.init()

    def tearDown(self):
        for x in reversed(self.p):
            x.stop()
        self.tmp.cleanup()

    def ask(self, script, kind='next-dialog', audio=WEBM, env=None):
        sent = []

        def urlopen(req, timeout=None):
            sent.append((req.full_url, json.loads(req.data), timeout))
            outcome = script.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome
        with patch.dict(os.environ, env or {}), patch('urllib.request.urlopen', urlopen), ai_routes.task(kind):
            out = cs.request_model([dict(m) for m in MSGS], audio=audio)
        return out, sent

    def rows(self):
        c = app.db()
        try:
            return [dict(r) for r in c.execute('SELECT kind,route,service,model,served,ok,fallback,prompt,completion FROM ai_calls ORDER BY id')]
        finally:
            c.close()

    def test_without_the_setting_gemini_hears_it_as_before(self):
        (reply, reason), sent = self.ask([gemini()])
        self.assertEqual(sent[0][1]['model'], 'gemini-3.8-flash')
        self.assertEqual(sent[0][1]['flow_audio'], WEBM)
        self.assertEqual(reply, REPLY)

    def test_a_task_on_the_omni_route_sends_the_recording_with_the_same_prompt(self):
        env = {'FLOW_AUDIO_ROUTES': 'next-dialog=flow-audio-omni-flash,next-retell=flow-audio-omni-flash'}
        for audio, fmt in ((WEBM, 'webm'), (MP4, 'mp4')):
            (reply, reason), sent = self.ask([Stream(REPLY)], audio=audio, env=env)
            url, body, timeout = sent[0]
            self.assertEqual(url, 'https://gw.test/v1/chat/completions')
            self.assertEqual(body['model'], 'flow-audio-omni-flash')
            self.assertTrue(body['stream'])
            self.assertFalse(body['enable_thinking'])
            self.assertEqual(body['modalities'], ['text'])
            self.assertNotIn('flow_audio', body)
            self.assertEqual(body['messages'][0], MSGS[0])
            part, text = body['messages'][1]['content']
            self.assertEqual(part['type'], 'input_audio')
            self.assertEqual(part['input_audio'], {'data': f"data:{audio['mime_type']};base64,{audio['data']}", 'format': fmt})
            self.assertEqual(text, {'type': 'text', 'text': MSGS[1]['content']})
            self.assertEqual((reply, reason), (REPLY, 'stop'))
            self.assertLessEqual(timeout, 25)
        row = self.rows()[-1]
        self.assertEqual((row['kind'], row['route'], row['service'], row['model'], row['served'], row['ok'], row['prompt'], row['completion']),
                         ('next-dialog', 'flow-audio-omni-flash', 'audio', 'flow-audio-omni-flash', 'qwen3.8-omni-flash', 1, 812, 64))

    def test_any_failure_hands_the_recording_to_gemini(self):
        env = {'FLOW_AUDIO_ROUTES': '*=flow-audio-omni-flash'}
        for failure in (urllib.error.HTTPError('https://gw.test', 400, 'bad', None, None), urllib.error.HTTPError('https://gw.test', 502, 'down', None, None),
                        TimeoutError('slow'), Stream('   '), Stream(REPLY[:20], finish='length')):
            (reply, reason), sent = self.ask([failure, gemini()], env=env)
            self.assertEqual([b['model'] for _, b, _ in sent], ['flow-audio-omni-flash', 'gemini-3.8-flash'])
            self.assertEqual(sent[1][1]['flow_audio'], WEBM)
            self.assertEqual(reply, REPLY)
            self.assertEqual([(r['service'], r['ok'], r['fallback']) for r in self.rows()[-2:]], [('audio', 0, 0), ('main', 1, 1)])

    def test_only_the_named_tasks_and_never_text_or_search(self):
        env = {'FLOW_AUDIO_ROUTES': 'next-dialog=flow-audio-omni-flash'}
        _, sent = self.ask([gemini()], kind='next-shadow', env=env)  # 跟读 is not named: Gemini
        self.assertEqual(sent[0][1]['model'], 'gemini-3.8-flash')
        sent = []

        def urlopen(req, timeout=None):
            sent.append(json.loads(req.data)['model'])
            return gemini('plain')
        with patch.dict(os.environ, env), patch('urllib.request.urlopen', urlopen), ai_routes.task('next-dialog'):
            cs.request_model([{'role': 'user', 'content': 'typed, not spoken'}])
        self.assertEqual(sent, ['flow-text'])  # a typed turn of the same task takes the text route

    def test_evals_ask_the_eval_name_and_omni_has_a_price(self):
        with patch.dict(os.environ, {'FLOW_AUDIO_ROUTES': 'flow-audio-omni-flash', 'FLOW_AI_LANE': 'eval'}):
            self.assertEqual(ai_routes.audio_route('next-ielts'), 'flow-eval-omni-flash')
        with patch.dict(os.environ, {'FLOW_AUDIO_ROUTES': 'next-dialog=bad name!'}):
            self.assertEqual(ai_routes.audio_route('next-dialog'), '')
        self.assertAlmostEqual(ai_routes.cost('qwen3.8-omni-flash', 1795000000, 1_000_000, 0, 1_000_000), (0.8 + 2.7) * 0.65)
        self.assertEqual(ai_routes.price_of('qwen3.8-omni-flash')['label'], '通义千问 3.8 Omni Flash（听录音）')


if __name__ == '__main__':
    unittest.main()
