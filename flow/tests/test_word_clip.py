"""A word cut from its sprite as a small ADTS file with silence in front (word_clip.py, 2026-11-24): an iPhone waking its
audio lost the start of a word played from the middle of its sprite. The fixture sprite is tools/ui-fixtures; the
placement on a real sprite was measured in Chrome (the word starts 0.3 s in, plus its own onset; see the PR)."""
import json, shutil, sys, tempfile, threading, unittest, urllib.error, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app, vocab_service as vs, word_clip as wc  # noqa: E402

FIXTURE = ROOT.parent / 'tools' / 'ui-fixtures' / 'audio' / 'words'


def frames(data):
    """The ADTS frames of a clip: (header fields, payload); fails on anything that is not a clean ADTS stream."""
    out, i = [], 0
    while i < len(data):
        h = data[i:i + 7]
        assert h[0] == 0xFF and h[1] & 0xF6 == 0xF0, f'no ADTS sync at {i}'
        n = (h[3] & 3) << 11 | h[4] << 3 | h[5] >> 5
        out.append(({'profile': h[2] >> 6, 'sfi': h[2] >> 2 & 15, 'ch': (h[2] & 1) << 2 | h[3] >> 6, 'crc': not h[1] & 1}, data[i + 7:i + n]))
        i += n
    assert i == len(data)
    return out


class ClipTests(unittest.TestCase):
    def setUp(self):
        self.sprite = FIXTURE / 'us' / 'w000.m4a'
        self.word = json.loads((FIXTURE / 'index.json').read_text())['us']['drain']

    def test_a_clip_is_the_sprites_own_frames_as_adts_with_silence_in_front(self):
        buf, scale, offsets, sizes, starts, durs, prime, aot, sfi, ch = wc._tables(str(self.sprite), self.sprite.stat().st_mtime_ns)
        data = wc.clip(self.sprite, self.word[1], self.word[2])
        fs = frames(data)
        self.assertTrue(all(f[0] == {'profile': aot - 1, 'sfi': sfi, 'ch': ch, 'crc': False} for f in fs))
        payloads = {buf[o:o + n] for o, n in zip(offsets, sizes)}
        self.assertTrue(all(p in payloads for _, p in fs))  # nothing re-encoded: every frame is one of the sprite's
        seconds = len(fs) * durs[0] / scale
        length = self.word[2] - self.word[1]
        self.assertGreaterEqual(seconds, wc.LEAD + length + wc.PAD - 0.05)
        self.assertLessEqual(seconds, wc.LEAD + length + wc.PAD + 3 * durs[0] / scale)
        lead = 0
        while lead + 1 < len(fs) and fs[lead + 1][1] == fs[0][1]:
            lead += 1
        self.assertGreater(lead, 0)  # copies of one quiet frame make the silence in front

    def test_the_priming_note_is_read(self):
        self.assertEqual(wc._tables(str(self.sprite), self.sprite.stat().st_mtime_ns)[6], 2112)  # iTunSMPB, no edit list

    def test_odd_requests_are_refused(self):
        for s, e in ((0.9, 0.2), (0.5, 0.5), (-1, 0.5), (0, 9)):
            with self.assertRaises(ValueError):
                wc.clip(self.sprite, s, e)


class RouteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        words = Path(self.tmp.name) / 'words'
        shutil.copytree(FIXTURE, words)
        self.patches = [patch.object(vs, 'WORD_AUDIO_DIR', words), patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'),
                        patch.object(app, 'DATA', Path(self.tmp.name))]
        for p in self.patches:
            p.start()
        vs._WA.update(mtime=None); app.SECURE = False; app.init()
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()
        for p in reversed(self.patches):
            p.stop()
        vs._WA.update(mtime=None); self.tmp.cleanup()

    def get(self, path, headers=None):
        req = urllib.request.Request(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def test_the_audio_route_serves_a_clip(self):
        st, h, body = self.get('/audio/words/us/w000.aac?s=0.2&e=0.9')
        self.assertEqual((st, h['Content-Type']), (200, 'audio/aac'))
        self.assertEqual(body, wc.clip(vs.WORD_AUDIO_DIR / 'us' / 'w000.m4a', 0.2, 0.9))
        self.assertIn('max-age', h['Cache-Control'])
        st, h, part = self.get('/audio/words/us/w000.aac?s=0.2&e=0.9', {'Range': 'bytes=0-1'})  # Safari asks for a range first
        self.assertEqual((st, part, h['Content-Range']), (206, body[:2], f'bytes 0-1/{len(body)}'))
        self.assertEqual(self.get('/audio/words/us/w000.mp4')[0], 200)  # the sprite itself, as before

    def test_a_sentence_of_a_narration_is_cut_the_same_way(self):
        import next_service as nx
        voices = Path(self.tmp.name) / 'audio'; (voices / 'us-f').mkdir(parents=True)
        shutil.copy(FIXTURE / 'us' / 'w000.m4a', voices / 'us-f' / 'v5-science-b2-noise-cancelling.m4a')  # AAC in MP4, as narrations are
        with patch.object(nx, 'AUDIO_DIR', voices):
            st, h, body = self.get('/audio/us-f/v5-science-b2-noise-cancelling.aac?v=1&s=0.2&e=0.9')
            self.assertEqual((st, h['Content-Type']), (200, 'audio/aac'))
            self.assertTrue(frames(body))
            self.assertEqual(self.get('/audio/us-f/v5-science-b2-noise-cancelling.aac?v=1&s=0.2&e=60')[0], 404)  # longer than a sentence
            self.assertEqual(self.get('/audio/zz/v5-science-b2-noise-cancelling.aac?v=1&s=0.2&e=0.9')[0], 404)

    def test_a_clip_that_cannot_be_cut_is_not_found(self):
        for path in ('/audio/words/us/w000.aac', '/audio/words/us/w000.aac?s=x&e=1', '/audio/words/us/w000.aac?s=0.9&e=0.2',
                     '/audio/words/us/w999.aac?s=0.2&e=0.9', '/audio/words/zz/w000.aac?s=0.2&e=0.9', '/audio/words/us/../w000.aac?s=0.2&e=0.9'):
            self.assertEqual(self.get(path)[0], 404, path)


class FrontEndTests(unittest.TestCase):
    def test_iphones_play_the_clip_and_keep_the_sprite_to_fall_back_on(self):
        js = (ROOT / 'public' / 'src' / 'next' / '01-audio-offline.js').read_text(encoding='utf-8')
        self.assertIn("const WORD_CLIPS = /iPhone|iPad|iPod/.test(navigator.userAgent)", js)
        self.assertIn("`/audio/words/${ac}/${w[0]}.aac?s=${w[1]}&e=${w[2]}`", js)
        self.assertIn('if (w.fallback) { const n = CLIP.want = { ...w, fallback: null }; CLIP.element(w.fallback[0], w.fallback[1], w.fallback[2], w.text, w.onend, null, n); return; }', js)
        self.assertIn('/\\.aac(\\?|$)/.test(url)) return', js)  # never looked for in R2
        # Web Audio on iPhones: a 'playback' session (the ringer switch), named on the lock screen, rested after 20 s;
        # the browser voice stays the last resort of a failed clip (not TTS.say: that may be the server voice again)
        self.assertIn("if (this.session('playback') !== 'playback') { this.off = true; return false; }", js)
        self.assertIn("MS.claim('short', title || '语流'", js); self.assertIn('}, 20000);', js)
        self.assertIn('CLIP.stop(); if (w.text) TTS.browser(w.text, w.onend);', js)
        self.assertIn("const CLIP_LEAD = 0.3;", js); self.assertEqual(wc.LEAD, 0.3)
        # the learner's recordings (对比回放 of 今日好句 and of 跟读) play through it, beside the original
        for part in ('12-daily-line.js', '21-study-listen.js'):
            src = (ROOT / 'public' / 'src' / 'next' / part).read_text(encoding='utf-8')
            self.assertIn('CLIP.mine(', src, part); self.assertNotIn('new Audio(url)', src.replace('CLIP.mine(url)', ''), part)
        review = (ROOT / 'public' / 'src' / 'next' / '60-review.js').read_text(encoding='utf-8')
        self.assertIn('CLIP.wordSrc(x)', review)  # the review prefetches the file a word will play


if __name__ == '__main__':
    unittest.main()
