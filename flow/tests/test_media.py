"""Audio kept in R2 and served from this server (media.py): a file the manifest lists is fetched once from the media
origin, checked, kept and then served from here; the page is told the origin as its second line; nothing changes
without FLOW_MEDIA_BASE."""
import hashlib, json, os, sys, tempfile, threading, time, unittest, urllib.error, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, media, next_service as nx, vocab_service as vs  # noqa: E402

PID = 'v5-life-a2-test-piece'


def sha(b):
    return hashlib.sha256(b).hexdigest()


class Origin:
    """A stand-in for the R2 public domain: serves /audio/<rel> from a dict and counts requests."""
    def __init__(self, files):
        self.files, self.hits = files, []
        outer = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                rel = self.path.split('?')[0][len('/audio/'):]
                outer.hits.append(self.path)
                body = outer.files.get(rel)
                if body is None:
                    self.send_response(404); self.send_header('Content-Length', '0'); self.end_headers(); return
                time.sleep(0.05)
                self.send_response(200); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f'http://127.0.0.1:{self.srv.server_address[1]}'

    def close(self):
        self.srv.shutdown(); self.srv.server_close()


class MediaCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.audio = root / 'audio'; self.audio.mkdir()
        self.mf = root / 'media-manifest.json'
        self.files = {f'us-f/{PID}.m4a': b'\x00\x00\x00\x18ftypM4A narration', f'us-f/{PID}.json': json.dumps({'v': 1, 'sentences': []}).encode(),
                      'words/index.json': json.dumps({'us': {'apple': ['w001', 0.1, 0.6]}, 'uk': {}}).encode(), 'words/us/w001.m4a': b'word sprite'}
        self.origin = Origin(dict(self.files))
        self.write_manifest(self.files)
        self.patches = [patch.object(media, 'MANIFEST', self.mf), patch.object(media, 'DIR', self.audio),
                        patch.object(nx, 'AUDIO_DIR', self.audio), patch.object(vs, 'WORD_AUDIO_DIR', self.audio / 'words'),
                        patch.dict(os.environ, {'FLOW_MEDIA_BASE': self.origin.base})]
        for p in self.patches:
            p.start()
        media._M.update(mtime=None, data=None); media._STATE.clear(); media._FAILED.clear(); vs._WA.update(mtime=None)

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.origin.close(); self.tmp.cleanup()
        media._M.update(mtime=None, data=None); media._STATE.clear(); media._FAILED.clear(); vs._WA.update(mtime=None)

    def write_manifest(self, files, version='abc123def456'):
        self.mf.write_text(json.dumps({'v': 1, 'version': version, 'narration': {PID: ['us-f', 'uk-x']},
                                       'files': {rel: [sha(b), len(b)] for rel, b in files.items()}}))
        media._M.update(mtime=None, data=None)


class MediaTests(MediaCase):
    def test_a_listed_file_is_fetched_once_checked_kept_and_then_served_from_here(self):
        f = nx.audio_file('us-f', PID, 'mp4')
        self.assertEqual(f.read_bytes(), self.files[f'us-f/{PID}.m4a'])
        self.assertEqual(len(self.origin.hits), 1); self.assertIn(f'?v={sha(self.files[f"us-f/{PID}.m4a"])[:12]}', self.origin.hits[0])
        self.assertEqual(nx.audio_file('us-f', PID, 'm4a'), f); self.assertEqual(len(self.origin.hits), 1)  # kept
        self.assertEqual(oct(f.stat().st_mode & 0o777), '0o644')

    def test_a_file_that_does_not_match_the_manifest_is_refused(self):
        self.origin.files[f'us-f/{PID}.json'] = b'{"tampered": true}'
        self.assertIsNone(nx.audio_file('us-f', PID, 'json'))
        self.assertFalse((self.audio / 'us-f' / f'{PID}.json').exists())
        self.assertEqual(list((self.audio / 'us-f').glob('.*')), [])  # no half-written file left behind

    def test_a_changed_file_replaces_the_old_copy_here(self):
        nx.audio_file('us-f', PID, 'json')
        new = dict(self.files, **{f'us-f/{PID}.json': b'{"v":1,"sentences":[{"s":0}]}'})
        self.origin.files.update(new); self.write_manifest(new, version='fedcba987654')
        self.assertEqual(nx.audio_file('us-f', PID, 'json').read_bytes(), new[f'us-f/{PID}.json'])

    def test_while_the_origin_is_down_the_old_copy_is_served_and_retries_wait_a_minute(self):
        nx.audio_file('us-f', PID, 'm4a')
        self.write_manifest(dict(self.files, **{f'us-f/{PID}.m4a': b'a new take not uploaded yet'}))
        self.origin.close()
        f = nx.audio_file('us-f', PID, 'm4a')
        self.assertEqual(f.read_bytes(), self.files[f'us-f/{PID}.m4a'])  # better the old take than silence
        self.assertIn(f'us-f/{PID}.m4a', media._FAILED)
        t = media._FAILED[f'us-f/{PID}.m4a']
        nx.audio_file('us-f', PID, 'm4a'); self.assertEqual(media._FAILED[f'us-f/{PID}.m4a'], t)  # not tried again yet
        self.origin = Origin({})  # (so tearDown has something to close)

    def test_many_requests_at_once_fetch_the_file_once(self):
        out = []
        threads = [threading.Thread(target=lambda: out.append(nx.audio_file('us-f', PID, 'm4a'))) for _ in range(8)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(len(self.origin.hits), 1); self.assertTrue(all(o and o.is_file() for o in out))

    def test_names_are_checked_and_unlisted_files_are_never_fetched(self):
        self.assertIsNone(media.path('../app.py')); self.assertIsNone(media.path('us-f/../../x.json'))
        self.assertIsNone(nx.audio_file('us-f', '../x', 'json')); self.assertIsNone(nx.audio_file('xx', PID, 'json'))
        self.assertIsNone(media.path('us-f/v5-not-listed.m4a')); self.assertEqual(self.origin.hits, [])

    def test_the_narration_index_and_the_word_index_come_from_the_manifest(self):
        index, version = nx.audio_index()
        self.assertEqual(index, {PID: ['us-f']}); self.assertEqual(version, 'abc123def456')  # unknown voices dropped
        self.assertEqual(vs.word_audio('apple'), {'us': ['w001', 0.1, 0.6]})
        self.assertEqual(vs.word_audio_file('us', 'w001').read_bytes(), b'word sprite')

    def test_without_the_media_base_nothing_is_fetched_and_local_files_are_used(self):
        with patch.dict(os.environ, {'FLOW_MEDIA_BASE': ''}):
            self.assertIsNone(media.info()); self.assertIsNone(media.narration())
            self.assertIsNone(nx.audio_file('us-f', PID, 'm4a'))
            (self.audio / 'index.json').write_text(json.dumps({PID: ['us-m']}))
            self.assertEqual(nx.audio_index()[0], {PID: ['us-m']})
        self.assertEqual(self.origin.hits, [])
        for bad in ('http://example.com', 'ftp://x', 'javascript:alert(1)'):
            with patch.dict(os.environ, {'FLOW_MEDIA_BASE': bad}):
                self.assertEqual(media.base(), '')


class MediaHttpTests(MediaCase):
    """Through the real handler: Range requests, the CSP and the session the page reads."""
    def setUp(self):
        super().setUp()
        self.p2 = patch.object(app, 'DB', Path(self.tmp.name) / 'm.db'); self.p2.start()
        app.SECURE = False
        app.init()
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler); threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close(); self.p2.stop()
        super().tearDown()

    def get(self, path, headers=None):
        req = urllib.request.Request(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            return e.code, e.read(), dict(e.headers)

    def test_audio_is_served_with_ranges_after_the_first_fetch(self):
        st, body, h = self.get(f'/audio/us-f/{PID}.mp4?v=abc', {'Range': 'bytes=0-3'})
        self.assertEqual(st, 206); self.assertEqual(body, self.files[f'us-f/{PID}.m4a'][:4])
        self.assertEqual(h['Content-Type'], 'audio/mp4')
        self.assertEqual(self.get(f'/audio/us-f/{PID}.json')[0], 200)
        self.assertEqual(self.get('/audio/words/us/w001.m4a')[1], b'word sprite')

    def test_the_csp_and_the_session_name_the_media_origin_only_when_it_is_set(self):
        _, _, h = self.get('/')
        self.assertIn(f"media-src 'self' blob: {self.origin.base}", h['Content-Security-Policy'])
        self.assertIn(f"connect-src 'self' {self.origin.base}", h['Content-Security-Policy'])
        s = json.loads(self.get('/api/session')[1])
        self.assertEqual(s['media'], {'base': self.origin.base + '/audio', 'version': 'abc123def456'})
        with patch.dict(os.environ, {'FLOW_MEDIA_BASE': ''}):
            _, _, h = self.get('/')
            self.assertIn("media-src 'self' blob:;", h['Content-Security-Policy'])
            self.assertIsNone(json.loads(self.get('/api/session')[1])['media'])


if __name__ == '__main__':
    unittest.main()
