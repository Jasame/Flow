"""shadow_eval.py, offline: 跟读 and 发音 build the site's own prompts, Gemini (main model) and Qwen-Omni (the site's audio
route call) answer from a stand-in gateway, and the report reads both the way the site does: the 跟读 score, the
planted mistake caught or not, mistakes filed on a sentence read right, and 发音 verdicts against what was read."""
import base64, io, json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import shadow_eval as se  # noqa: E402
import voice_eval as ve  # noqa: E402

ENV = {'FLOW_AI_PROVIDER': 'openai', 'FLOW_AI_URL': 'https://gw.test/v1/chat/completions', 'FLOW_AI_KEY': 'k', 'FLOW_AI_MODEL': 'gemini-3.8-flash',
       'FLOW_TEXT_AI_MODEL': 'flow-text', 'FLOW_AI_AUDIO': '1', 'FLOW_AUDIO_ROUTES': 'next-shadow=flow-audio-omni-flash'}
MP3 = b'ID3' + b'\0' * 64
CASES = {'shadow': [{'id': 's01', 'sentence': 'I think this is the best way to learn.',
                     'mistake': {'kind': 'sound', 'read': 'I sink dis is the best way to learn.', 'words': ['think', 'this']}}],
         'say': [{'word': 'think', 'wrong': 'sink'}]}


class Audio:
    """A stand-in clip that carries what was read, so the stand-in models can answer to it."""
    def __init__(self, text):
        self.text = text

    def __enter__(self):
        return io.BytesIO(MP3 + self.text.encode())

    def __exit__(self, *a):
        return False


class Stream:
    def __init__(self, text):
        chunks = [{'model': 'qwen3.8-omni-flash', 'choices': [{'index': 0, 'delta': {'content': text[i:i + 9]}}]} for i in range(0, len(text), 9)]
        chunks.append({'model': 'qwen3.8-omni-flash', 'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}]})
        chunks.append({'model': 'qwen3.8-omni-flash', 'choices': [], 'usage': {'prompt_tokens': 900, 'completion_tokens': 80, 'total_tokens': 980}})
        self.lines = [x for c in chunks for x in (f'data: {json.dumps(c)}\n'.encode(), b'\n')] + [b'data: [DONE]\n', b'\n']

    def __enter__(self):
        return iter(self.lines)

    def __exit__(self, *a):
        return False


def shadow_reply(transcript, accuracy, sounds=()):
    return json.dumps({'transcript': transcript, 'accuracy': accuracy, 'fluency_score': 80, 'fluency': 'ok',
                       'sounds': [{'sound': '/θ/', 'word': w, 'note': '舌尖放在上下齿之间', 'set': 'th-s'} for w in sounds], 'issues': [], 'tip': '注意 th'})


class ShadowEvalTests(unittest.TestCase):
    def test_both_paths_scored_the_site_way(self):
        spoken, sent, main = [], [], []

        def post(path, body, timeout=90):  # flow-tts only
            spoken.append((body['input'], body['voice']))
            return Audio(body['input'])

        def request_model(messages, audio=None, grounding=False):
            main.append((messages, audio['mime_type'], os.environ.get('FLOW_AUDIO_ROUTES')))
            system = messages[0]['content']
            if '跟读' in system:  # Gemini: hears the right reading as right, misses the planted one, and over-flags once
                planted = b'sink' in base64.b64decode(audio['data'])
                return shadow_reply('I think this is the best way to learn.', 80 if planted else 92, () if planted else ('think',)), 'stop'
            return json.dumps({'heard': 'think', 'ok': True, 'note': '', 'tip': ''}), 'stop'

        def urlopen(req, timeout=None):  # Qwen-Omni through the gateway
            body = json.loads(req.data)
            sent.append(body)
            system = body['messages'][0]['content']
            planted = b'sink' in base64.b64decode(body['messages'][-1]['content'][0]['input_audio']['data'].split(',', 1)[1])
            if '跟读' in system:
                return Stream(shadow_reply('I sink dis is the best way to learn.' if planted else 'I think this is the best way to learn.', 70 if planted else 90,
                                           ('think',) if planted else ()))
            return Stream(json.dumps({'heard': 'sink' if planted else 'zink', 'ok': False, 'note': '听起来像 sink', 'tip': ''}))

        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ, ENV):
            cf = Path(tmp) / 'cases.json'
            cf.write_text(json.dumps(CASES))
            out = Path(tmp) / 'r.json'
            import chat_service as cs
            with patch.object(ve, 'post', post), patch.object(cs, 'request_model', request_model), patch('urllib.request.urlopen', urlopen):
                self.assertEqual(se.main(['--env-file', os.devnull, '--cases', str(cf), '--output', str(out)]), 0)
            report = json.loads(out.read_text())
        # recordings: right and planted, by an English and a Chinese voice
        self.assertEqual(spoken[:4], [('I think this is the best way to learn.', 'loongabby_v3'), ('I think this is the best way to learn.', 'longxiaochun_v3'),
                                      ('I sink dis is the best way to learn.', 'loongabby_v3'), ('I sink dis is the best way to learn.', 'longxiaochun_v3')])
        # the site's own prompts, Gemini asked with no audio route, Omni with the eval name and the recording
        self.assertTrue(all(r == '' for _, _, r in main))
        self.assertIn('跟读一句英文', main[0][0][0]['content'])
        self.assertIn('原句：I think this is the best way to learn.', main[0][0][1]['content'])
        self.assertTrue(all(b['model'] == 'flow-eval-omni-flash' and b['messages'][-1]['content'][0]['type'] == 'input_audio' for b in sent))
        self.assertTrue(any('目标词：think' in b['messages'][-1]['content'][1]['text'] for b in sent))
        s = report['summary']
        sh = s['shadow']
        self.assertEqual(sh['gemini']['ok'], [4, 4])
        self.assertEqual(sh['omni']['ok'], [4, 4])
        self.assertEqual(sh['omni']['caught'], [2, 2])
        self.assertEqual(sh['gemini']['caught'], [0, 2])
        self.assertEqual(sh['gemini']['false_cards'], [2, 2, 2])
        self.assertEqual(sh['omni']['false_cards'], [0, 0, 2])
        # totals the site's way: 0.5 accuracy + 0.25 fluency + 0.25 completeness (Omni's planted transcript misses 2 of 9 words)
        self.assertEqual(sh['omni']['total_right'], round(0.5 * 90 + 0.25 * 80 + 25))
        self.assertEqual(sh['omni']['total_planted'], round(0.5 * 70 + 0.25 * 80 + 0.25 * round(100 * 7 / 9)))
        self.assertEqual(sh['compare']['n'], 4)
        self.assertEqual(sh['compare']['caught_agree'], [0, 2])
        say = s['say']
        self.assertEqual(say['gemini']['right_on_right'], [2, 2])
        self.assertEqual(say['gemini']['right_on_planted'], [0, 2])
        self.assertEqual(say['omni']['right_on_right'], [0, 2])  # "think" heard as "zink"
        self.assertEqual(say['omni']['right_on_planted'], [2, 2])
        self.assertGreater(sh['omni']['cost'], 0)
        self.assertIn('跟读（整句）', se.describe(s))


if __name__ == '__main__':
    unittest.main()
