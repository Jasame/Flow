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


    def test_the_gateway_on_this_machine_may_use_plain_http_but_nothing_else_may(self):
        gw = {'FLOW_TEXT_AI_URL': 'http://127.0.0.1:3000/v1/chat/completions', 'FLOW_TEXT_AI_KEY': 'k3', 'FLOW_TEXT_AI_MODEL': 'flow-text'}
        out, calls = self.call({**MAIN, **gw}, {'127.0.0.1:3000': ['from the gateway']})
        self.assertEqual(out[0], 'from the gateway'); self.assertEqual(calls, [('127.0.0.1:3000', 'flow-text', False)])
        for url in ('http://example.com/v1/chat/completions', 'http://127.0.0.1.evil.test/v1/chat/completions',
                    'http://localhost@evil.test/v1/chat/completions', 'ftp://127.0.0.1/x'):
            with self.subTest(url=url):
                self.assertFalse(cs.endpoint_ok(url))
                out, calls = self.call({**MAIN, **gw, 'FLOW_TEXT_AI_URL': url}, {'main.test': ['from main']})
                self.assertEqual(out[0], 'from main'); self.assertEqual([c[0] for c in calls], ['main.test'])
        for url in ('http://localhost:3000/v1/chat/completions', 'http://[::1]:3000/v1/chat/completions', 'https://api.xmc.hk/v1/chat/completions'):
            self.assertTrue(cs.endpoint_ok(url), url)

    # ---- the text model on the same gateway (api.xmc.hk): one setting, FLOW_TEXT_AI_MODEL
    def test_a_text_model_alone_uses_the_main_gateway_and_key_with_another_model_name(self):
        out, calls = self.call({**MAIN, 'FLOW_TEXT_AI_MODEL': 'flow-text'}, {'main.test': ['from flow-text']})
        self.assertEqual(out[0], 'from flow-text'); self.assertEqual(calls, [('main.test', 'flow-text', False)])
        self.assertEqual(cs.text_provider(), None)  # outside the call the environment is back to normal
        with patch.dict(os.environ, {**MAIN, 'FLOW_TEXT_AI_MODEL': 'flow-text'}):
            os.environ.pop('FLOW_TEXT_AI_URL', None); os.environ.pop('FLOW_TEXT_AI_KEY', None)
            self.assertEqual(cs.text_provider(), (MAIN['FLOW_AI_URL'], MAIN['FLOW_AI_KEY'], 'flow-text'))

    def test_the_main_key_is_never_sent_to_another_address(self):
        with patch.dict(os.environ, {**MAIN, 'FLOW_TEXT_AI_MODEL': 'flow-text', 'FLOW_TEXT_AI_URL': 'https://other.test/v1/chat/completions'}):
            os.environ.pop('FLOW_TEXT_AI_KEY', None)
            self.assertIsNone(cs.text_provider())
        with patch.dict(os.environ, {'FLOW_AI_PROVIDER': 'vertex', 'FLOW_TEXT_AI_MODEL': 'flow-text'}):
            for k in ('FLOW_TEXT_AI_URL', 'FLOW_TEXT_AI_KEY', 'FLOW_AI_URL', 'FLOW_AI_KEY'):
                os.environ.pop(k, None)
            self.assertIsNone(cs.text_provider())  # Vertex direct has no gateway to share

    def test_a_text_model_switched_off_in_the_console_hands_over_to_the_main_model(self):
        env = {**MAIN, 'FLOW_TEXT_AI_MODEL': 'flow-text'}
        for failure in (http(404), http(401), http(403), http(429), http(502)):
            out, calls = self.call(env, {'main.test': [failure, 'from main']})
            self.assertEqual(out[0], 'from main', failure.code)
            self.assertEqual([c[1] for c in calls], ['flow-text', 'main-model'])

    def test_a_refused_request_is_not_sent_again_to_the_main_model(self):
        env = {**MAIN, 'FLOW_TEXT_AI_MODEL': 'flow-text'}
        for code in (400, 413, 422):
            out, calls = self.call(env, {'main.test': [http(code), 'never']})
            self.assertIsInstance(out, urllib.error.HTTPError); self.assertEqual(out.code, code); self.assertEqual(len(calls), 1)

if __name__ == '__main__':
    unittest.main()
