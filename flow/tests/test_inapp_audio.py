"""r20: sound in WeChat's built-in browser. A looked-up word comes with its recorded pronunciation (the browser voice is
missing there), and the front end starts every sound inside the tap or on a player an earlier tap unlocked; the UI
suite checks the page under WeChat's rules (tools/ui_test.py, wechat_run)."""
import json, os, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import next_service as nx, vocab_service as vs  # noqa: E402

SRC = ROOT / 'public' / 'src' / 'next'


class LookupAudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        words = Path(self.tmp.name) / 'words'; words.mkdir()
        (words / 'index.json').write_text(json.dumps({'us': {'drain': ['w031', 19.248, 19.872]}, 'uk': {'drain': ['w030', 1.0, 1.6]}}))
        self.p = patch.object(vs, 'WORD_AUDIO_DIR', words); self.p.start(); vs._WA.update(mtime=None)

    def tearDown(self):
        self.p.stop(); vs._WA.update(mtime=None); self.tmp.cleanup()

    def test_a_looked_up_word_carries_its_recorded_pronunciation(self):
        body, status = nx.get(None, None, '/api/next/lookup', {'w': ['drains']})
        self.assertEqual(status, 200)
        self.assertEqual(body['entry']['lemma'], 'drain')
        self.assertEqual(body['entry']['audio'], {'us': ['w031', 19.248, 19.872], 'uk': ['w030', 1.0, 1.6]})
        body, _ = nx.get(None, None, '/api/next/lookup', {'w': ['unrecordedwordzz']})
        self.assertIsNone(body['entry'])

    def test_words_added_later_play_from_their_own_files(self):
        """r27: words of the newer word books (中考/高考/专四/商务/学术…) were made later, in b### files after the old ones."""
        words = vs.WORD_AUDIO_DIR
        (words / 'index.json').write_text(json.dumps({'us': {'receivable': ['b000', 79.993, 80.818]}, 'uk': {'receivable': ['b000', 83.9, 84.8]}}))
        (words / 'us').mkdir(); (words / 'us' / 'b000.m4a').write_bytes(b'sprite')
        vs._WA.update(mtime=None)
        body, _ = nx.get(None, None, '/api/next/lookup', {'w': ['receivable']})
        self.assertEqual(body['entry']['audio']['us'], ['b000', 79.993, 80.818])
        self.assertEqual(vs.word_audio_file('us', 'b000'), words / 'us' / 'b000.m4a')
        self.assertIsNone(vs.word_audio_file('us', 'z000')); self.assertIsNone(vs.word_audio_file('us', 'b00'))


class FrontEndTests(unittest.TestCase):
    def setUp(self):
        self.js = (ROOT / 'public' / 'next.js').read_text(encoding='utf-8')

    def test_the_page_knows_wechat_and_offers_the_way_out(self):
        self.assertIn("const WECHAT = /MicroMessenger/i.test(navigator.userAgent);", self.js)
        self.assertIn('在浏览器打开', self.js); self.assertIn('在默认浏览器中打开', self.js)
        self.assertIn("function wechatBar()", self.js); self.assertIn('wechatBar();', self.js)

    def test_the_first_tap_unlocks_both_players_and_the_lookup_uses_the_recording(self):
        self.assertIn("['touchend', 'click', 'keydown'].forEach(t => window.addEventListener(t, unlockAudio, true));", self.js)
        lookup = (SRC / '30-lookup.js').read_text(encoding='utf-8')
        self.assertIn('CLIP.word({ text: e.word, audio: e.audio })', lookup)
        self.assertNotIn('TTS.say(e ? e.word : word);\n  }', lookup)  # no longer the browser voice first

    def test_recordings_are_preloaded_and_not_on_a_frugal_connection(self):
        self.assertIn('const PRELOAD = {', self.js)
        self.assertIn("c.saveData || /(^|-)2g$/.test(c.effectiveType || '')", self.js)
        self.assertIn('setTimeout(() => preloadMaterial(nextRead), 600)', self.js)


if __name__ == '__main__':
    unittest.main()
