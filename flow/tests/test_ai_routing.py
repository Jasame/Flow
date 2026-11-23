"""AI calls: text to an optional second service (e.g. DeepSeek), audio only to the main one, and one more try on a
transient failure, so a single hiccup does not cost the learner their answer."""
import unittest, sys, os, json, io, urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import chat_service as cs

MAIN = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_URL': 'https://main.test/v1/chat/completions', 'FLOW_AI_KEY': 'k1', 'FLOW_AI_MODEL': 'main-model'}
TEXT = {'FLOW_TEXT_AI_URL': 'https://text.test/chat/completions', 'FLOW_TEXT_AI_KEY': 'k2', 'FLOW_TEXT_AI_MODEL': 'text-model'}
MSGS = [{'role': 'user', 'content': 'hi'}]


class Reply:
    def __init__(self, text):
        self.body = json.dumps({'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]}).encode()
        self.headers = {'Content-Type': 'application/json'}

    def read(self, *a):
        return self.body

    def __enter__(self):
        return io.BytesIO(self.body)

    def __exit__(self, *a):
        return False


def server(script):
    """urlopen stand-in: script maps a host to a list of outcomes (a reply text or an exception), used in order."""
    calls = []

    def urlopen(req, timeout=None):
        host = req.full_url.split('/')[2]
        calls.append((host, json.loads(req.data)['model'], 'flow_audio' in json.loads(req.data)))
        out = script[host].pop(0)
        if isinstance(out, Exception):
            raise out
        return Reply(out)
    return urlopen, calls


def http(code):
    return urllib.error.HTTPError('https://x', code, 'err', None, None)


class RoutingTests(unittest.TestCase):
    def call(self, env, script, **kw):
        fake, calls = server(script)
        with patch.dict(os.environ, env, clear=False), patch('urllib.request.urlopen', fake), patch('time.sleep'), patch('ai_stream.active', return_value=False):
            for k in ('FLOW_TEXT_AI_URL', 'FLOW_TEXT_AI_KEY', 'FLOW_TEXT_AI_MODEL'):
                if k not in env:
                    os.environ.pop(k, None)
            try:
                return cs.request_model(MSGS, **kw), calls
            except Exception as e:
                return e, calls

    def test_text_goes_to_the_text_service_when_configured(self):
        out, calls = self.call({**MAIN, **TEXT}, {'text.test': ['from text']})
        self.assertEqual(out[0], 'from text'); self.assertEqual(calls, [('text.test', 'text-model', False)])
        self.assertEqual(cs.LAST['provider'], 'text')

    def test_without_a_text_service_everything_goes_to_the_main_one(self):
        out, calls = self.call(MAIN, {'main.test': ['from main']})
        self.assertEqual(out[0], 'from main'); self.assertEqual([c[0] for c in calls], ['main.test'])

    def test_a_text_service_outage_falls_back_to_the_main_service(self):
        out, calls = self.call({**MAIN, **TEXT}, {'text.test': [http(503)], 'main.test': ['from main']})
        self.assertEqual(out[0], 'from main'); self.assertEqual([c[0] for c in calls], ['text.test', 'main.test'])
        out, calls = self.call({**MAIN, **TEXT}, {'text.test': [urllib.error.URLError('down')], 'main.test': ['from main']})
        self.assertEqual(out[0], 'from main')

    def test_one_service_is_tried_twice_on_a_transient_failure_but_not_on_a_refusal(self):
        out, calls = self.call(MAIN, {'main.test': [http(502), 'second try']})
        self.assertEqual(out[0], 'second try'); self.assertEqual(len(calls), 2)
        out, calls = self.call(MAIN, {'main.test': [http(400), 'never']})
        self.assertIsInstance(out, urllib.error.HTTPError); self.assertEqual(out.code, 400); self.assertEqual(len(calls), 1)
        out, calls = self.call(MAIN, {'main.test': [http(503), http(503)]})
        self.assertIsInstance(out, urllib.error.HTTPError); self.assertEqual(len(calls), 2)

    def test_a_rate_limit_is_not_retried_on_the_same_service_but_falls_back_to_the_other(self):
        out, calls = self.call(MAIN, {'main.test': [http(429), 'never']})
        self.assertIsInstance(out, urllib.error.HTTPError); self.assertEqual(out.code, 429); self.assertEqual(len(calls), 1)
        out, calls = self.call({**MAIN, **TEXT}, {'text.test': [http(429)], 'main.test': ['from main']})
        self.assertEqual(out[0], 'from main'); self.assertEqual([c[0] for c in calls], ['text.test', 'main.test'])

    def test_audio_only_goes_to_the_main_service(self):
        audio = {'mime_type': 'audio/webm', 'data': __import__('base64').b64encode(b'\x1aE\xdf\xa3' + b'0' * 4000).decode()}
        out, calls = self.call({**MAIN, **TEXT}, {'main.test': ['heard it']}, audio=audio)
        self.assertEqual(out[0], 'heard it'); self.assertEqual(calls, [('main.test', 'main-model', True)])

    def test_an_incomplete_text_set_up_is_ignored(self):
        out, calls = self.call({**MAIN, 'FLOW_TEXT_AI_URL': 'https://text.test/x', 'FLOW_TEXT_AI_MODEL': 'm'}, {'main.test': ['from main']})
        self.assertEqual(out[0], 'from main'); self.assertEqual([c[0] for c in calls], ['main.test'])


if __name__ == '__main__':
    unittest.main()
