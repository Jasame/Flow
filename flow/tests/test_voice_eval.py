"""voice_eval.py, offline: the scene's own prompt is built for audio and for text, the three paths run against a
stand-in gateway, and the report scores what was heard (word error rate) and whether the planted mistake was caught."""
import io, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import voice_eval as ve  # noqa: E402

ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_URL': 'https://gw.test/v1/chat/completions', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'gemini-3.8-flash',
       'FLOW_TEXT_AI_MODEL': 'flow-text', 'FLOW_AI_AUDIO': '1'}
MP3 = b'ID3' + b'\0' * 64


def reply_json(heard, corr=None):
    return json.dumps({'heard': heard, 'reply': 'Sure, one tea coming up.', 'correction': corr, 'hint': '可以说你要什么杯型', 'say': ''})


class Stream:
    def __init__(self, text, usage=None):
        chunks = [{'choices': [{'delta': {'content': text[i:i + 7]}}]} for i in range(0, len(text), 7)]
        chunks.append({'choices': [], 'usage': usage or {'prompt_tokens': 300, 'completion_tokens': 60}})
        self.lines = [f'data: {json.dumps(c)}\n'.encode() for c in chunks] + [b'data: [DONE]\n']

    def __enter__(self):
        return iter(self.lines)

    def __exit__(self, *a):
        return False


class Audio:
    def __enter__(self):
        return io.BytesIO(MP3)

    def __exit__(self, *a):
        return False


def fake_post(sent):
    def post(path, body, timeout=90):
        sent.append((path, body))
        if path == '/audio/speech':
            return Audio()
        if body['model'] == 'flow-eval-asr-flash':
            return Stream("She don't like coffee, so she want a cup of tea.")
        return Stream(reply_json("She don't like coffee so she want a cup of tea", {'original': "she don't", 'better': "she doesn't", 'why': '第三人称'}))
    return post


class VoiceEvalTests(unittest.TestCase):
    def test_three_paths_on_a_stand_in_gateway(self):
        sent = []
        gemini = reply_json('She don like coffee, so she want tea', None)
        text = json.dumps({'reply': 'OK, a cup of tea.', 'correction': {'original': "don't", 'better': "doesn't", 'why': '主谓一致'}, 'hint': '…', 'say': ''})
        cases = {'cases': [{'id': 'c04-agree-zh', 'scene': 'cafe', 'opener': 'Hi there! What can I get for you today?',
                            'text': "She don't like coffee, so she want a cup of tea.", 'error': {'original': "don't", 'better': "doesn't"}},
                           {'id': 'c01-ok-us', 'scene': 'cafe', 'opener': 'Hi there!', 'text': 'Hi, can I get a large latte, please?', 'error': None}]}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, ENV):
            cf = Path(tmp) / 'cases.json'
            cf.write_text(json.dumps(cases))
            (Path(tmp) / 'c04-agree-zh.m4a').write_bytes(b'\0\0\0\x18ftypM4A ' + b'\0' * 64)
            out = Path(tmp) / 'r.json'
            calls = []

            def request_model(messages, audio=None, grounding=False):
                calls.append(('main', messages[-1]['content'], audio['mime_type'] if audio else None))
                return gemini, 'stop'

            def text_service(messages, model=None, extra=None):
                calls.append(('text', messages[-1]['content'], model))
                return text, 'stop'
            import chat_service as cs
            with patch.object(ve, 'post', fake_post(sent)), patch.object(cs, 'request_model', request_model), patch.object(cs, '_request_text_service', text_service):
                self.assertEqual(ve.main(['--env-file', os.devnull, '--cases', str(cf), '--clips', tmp, '--output', str(out)]), 0)
            report = json.loads(out.read_text())
        s = report['summary']
        self.assertEqual(set(s), {'gemini', 'asr', 'omni'})
        self.assertEqual(s['omni']['ok'], [3, 3])  # two CosyVoice readings + the m4a clip
        self.assertEqual(s['omni']['caught'], [2, 2])
        self.assertEqual(s['gemini']['caught'], [0, 2])
        self.assertEqual(s['asr']['caught'], [2, 2])
        # the scene's real prompt: audio turns ask for a transcript, the text turn reads the recogniser's words
        audio_prompt = next(c for c in calls if c[0] == 'main')[1]
        self.assertIn('录音，先忠实转写', audio_prompt)
        text_prompt = next(c for c in calls if c[0] == 'text')[1]
        self.assertIn("学习者刚说：She don't like coffee, so she want a cup of tea.", text_prompt)
        self.assertEqual(next(c for c in calls if c[0] == 'text')[2], 'flow-eval-ds-flash')
        omni = next(b for p, b in sent if p == '/chat/completions' and b['model'] == 'flow-eval-omni-flash')
        self.assertEqual(omni['messages'][1]['content'][0]['type'], 'input_audio')
        self.assertFalse(omni['enable_thinking'])
        self.assertTrue(all(p == '/audio/speech' and b['model'] == 'flow-tts' for p, b in sent if p == '/audio/speech'))
        item = next(i for i in report['items'] if i['path'] == 'asr' and i['case'] == 'c04-agree-zh')
        self.assertEqual(item['wer'], 0.0)
        self.assertIsNotNone(item['heard_s'])
        self.assertIsNotNone(s['asr']['heard_s_p50'])
        self.assertIn('clip:c04-agree-zh.m4a', {i['recording'] for i in report['items']})

    def test_word_error_rate_and_catching(self):
        self.assertEqual(ve.wer('I want to go home', 'I want go home'), 0.2)
        self.assertEqual(ve.wer('a b', ''), 1.0)
        case = {'error': {'original': 'where nearest', 'better': 'where is the nearest'}}
        self.assertTrue(ve.caught(case, {'original': 'Where nearest subway', 'better': 'Where is the nearest subway'}))
        self.assertFalse(ve.caught(case, None))
        self.assertIsNone(ve.caught({'error': None}, {'original': 'x', 'better': 'y'}))


if __name__ == '__main__':
    unittest.main()
