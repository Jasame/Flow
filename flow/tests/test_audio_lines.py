"""Every route that reads a recording has an AI line to hear it, with Gemini off (2026-11-26, r35: 能力测评·口语 had no
audio route on 正式版 and every attempt failed; A1 and B3 asked for this guard). No AI is called and nothing is spent: a
stand-in gateway answers. PROD_AUDIO_ROUTES is what the servers' FLOW_AUDIO_ROUTES should say (/etc/flow.env line 41,
/etc/flow-beta.env line 50 add next-say); A1 checks a server change against it."""
import base64, importlib.util, io, json, os, sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, ai_routes, chat_service as cs  # noqa: E402

OMNI = 'flow-audio-omni-flash'
PROD_AUDIO_ROUTES = f'next-dialog={OMNI},next-retell={OMNI},next-ielts={OMNI},next-shadow={OMNI},*={OMNI}'
PROD = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_URL': 'https://gw.test/v1/chat/completions', 'FLOW_AI_KEY': 'k',
        'FLOW_AI_MODEL': 'gemini-3.8-flash', 'FLOW_AI_AUDIO': '1', 'FLOW_TEXT_AI_MODEL': 'flow-text',
        'FLOW_AI_ROUTES': '*=flow-text-ds-flash', 'FLOW_MAIN_AI': 'off', 'FLOW_BACKUP_AI_MODEL': 'flow-text-qwen-plus',
        'FLOW_ASR_AI_MODEL': '', 'FLOW_AUDIO_ROUTES': PROD_AUDIO_ROUTES}
# The route each recording endpoint's handler runs its AI under (B3 checked it against the handlers on main, 2026-11-26).
KIND_OF = {'/api/lab/audio': 'audio', '/api/next/shadow': 'next-shadow', '/api/next/retell': 'next-retell',
           '/api/next/dialog': 'next-dialog', '/api/next/say': 'next-say', '/api/next/ielts': 'next-ielts',
           '/api/next/assess/speaking': 'next-assess-speaking'}
WORD_ONLY = {'next-say'}  # 发音: chat_service.hear_word writes the one word down on word_model(), not request_model
WEBM = {'mime_type': 'audio/webm', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * 64).decode()}
MSGS = [{'role': 'system', 'content': '只输出 JSON。'}, {'role': 'user', 'content': '学习者的回答是一段录音。'}]


class Answer:
    def __init__(self, model, stream):
        text = '{"ok": 1}'
        if stream:
            chunks = [{'model': model, 'choices': [{'index': 0, 'delta': {'content': text}}]},
                      {'model': model, 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]}]
            self.body = [x for c in chunks for x in (f'data: {json.dumps(c)}\n'.encode(), b'\n')] + [b'data: [DONE]\n', b'\n']
        else:
            self.body = io.BytesIO(json.dumps({'model': model, 'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]}).encode())
        self.headers = {'Content-Type': 'text/event-stream' if stream else 'application/json'}

    def __enter__(self):
        return iter(self.body) if isinstance(self.body, list) else self.body

    def __exit__(self, *a):
        return False


class AudioLineTests(unittest.TestCase):
    def setUp(self):
        self.asked = []

        def urlopen(req, timeout=None):
            body = json.loads(req.data)
            self.asked.append(body['model'])
            return Answer(body['model'], bool(body.get('stream')))
        for p in (patch.dict(os.environ, PROD), patch('urllib.request.urlopen', urlopen), patch('time.sleep')):
            p.start(); self.addCleanup(p.stop)

    def test_every_recording_endpoint_is_in_the_list(self):
        # B3: found from the code itself (test_request_size.recording_routes), a step before app.AUDIO_PATHS; the routes
        # that only share a recording handler (SHARES_A_HANDLER) take no recording of their own
        spec = importlib.util.spec_from_file_location('request_size', Path(__file__).with_name('test_request_size.py'))
        rs = importlib.util.module_from_spec(spec); spec.loader.exec_module(rs)
        found = set(rs.recording_routes()) - set(rs.SHARES_A_HANDLER)
        self.assertEqual(sorted(found - set(KIND_OF)), [], 'these read a recording: give each its AI kind in KIND_OF')
        self.assertEqual(sorted(set(KIND_OF) - found), [], 'these no longer read a recording: take them out of KIND_OF')
        self.assertEqual(sorted(KIND_OF), sorted(app.AUDIO_PATHS))

    def test_the_servers_line_is_understood(self):
        routes, problem = ai_routes.parse_routes(PROD_AUDIO_ROUTES)
        self.assertIsNone(problem); self.assertEqual(routes.get('*'), OMNI)

    def test_every_recording_is_heard_on_a_domestic_line_with_gemini_off(self):
        for path, kind in KIND_OF.items():
            with self.subTest(path=path, kind=kind), ai_routes.task(kind):
                self.asked.clear()
                if kind in WORD_ONLY:
                    self.assertEqual(cs.word_model(), OMNI)
                    continue
                self.assertEqual(ai_routes.audio_route(), OMNI)
                cs.request_model(MSGS, audio=WEBM)  # raises AIConfigurationError when nothing can hear it
                self.assertEqual(self.asked[:1], [OMNI]); self.assertNotIn('gemini-3.8-flash', self.asked)

    def test_without_the_star_a_task_left_out_is_caught_here(self):  # what r35 had on 正式版
        from vertex_auth import AIConfigurationError
        r35 = f'next-dialog={OMNI},next-retell={OMNI},next-ielts={OMNI},next-shadow={OMNI}'
        with patch.dict(os.environ, {'FLOW_AUDIO_ROUTES': r35}), ai_routes.task('next-assess-speaking'):
            self.assertEqual(ai_routes.audio_route(), '')
            try:
                cs.request_model(MSGS, audio=WEBM)
            except AIConfigurationError:
                pass  # before #352: nothing hears it
            else:
                self.assertEqual(self.asked[:1], [OMNI])  # after #352: it borrows 情景对话's line


if __name__ == '__main__':
    unittest.main()
