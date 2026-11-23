"""tools/push_media.py: AWS Signature Version 4 (checked against AWS's published example), what gets uploaded, the
manifest it writes, and the public-domain check. Uploads go to a stand-in S3 endpoint on 127.0.0.1."""
import contextlib, hashlib, importlib.util, io, json, os, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('push_media', ROOT / 'tools' / 'push_media.py')
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)
CREDS = {'R2_ACCOUNT_ID': 'acct', 'R2_BUCKET': 'flow-media', 'R2_ACCESS_KEY_ID': 'AKIDEXAMPLE', 'R2_SECRET_ACCESS_KEY': 'secret-not-printed'}


def fake_s3(status=200):
    got = []

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_PUT(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            got.append({'path': self.path, 'headers': dict(self.headers), 'body': body})
            self.send_response(status); self.send_header('Content-Length', '0'); self.end_headers()
    srv = ThreadingHTTPServer(('127.0.0.1', 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, got


def audio_dir(tmp):
    src = Path(tmp) / 'audio'
    for v in ('us-f', 'uk-m'):
        (src / v).mkdir(parents=True)
        (src / v / 'v5-a.m4a').write_bytes(b'\x00\x00\x00\x18ftypM4A ' + v.encode())
        (src / v / 'v5-a.json').write_text(json.dumps({'v': 1, 'voice': v}))
    (src / 'us-f' / 'v5-b.m4a').write_bytes(b'audio without timings')  # incomplete: not listed as narration
    (src / 'words' / 'us').mkdir(parents=True)
    (src / 'words' / 'us' / 'w000.m4a').write_bytes(b'word sprite')
    (src / 'words' / 'us' / 'w000.json').write_text('{}')  # generator side file: not uploaded
    (src / 'words' / 'index.json').write_text(json.dumps({'us': {'apple': ['w000', 0, 0.5]}, 'uk': {}}))
    (src / 'index.json').write_text(json.dumps({'v5-a': ['us-f', 'uk-m'], 'v5-b': ['us-f']}))
    return src


class SignatureTests(unittest.TestCase):
    def test_signature_matches_the_aws_documentation_example(self):
        auth = pm.authorization('GET', 'examplebucket.s3.amazonaws.com', '/test.txt', {'range': 'bytes=0-9'},
                                'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855', '20130524T000000Z',
                                'AKIAIOSFODNN7EXAMPLE', 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY', region='us-east-1')
        self.assertEqual(auth, 'AWS4-HMAC-SHA256 Credential=AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request, '
                               'SignedHeaders=host;range;x-amz-content-sha256;x-amz-date, '
                               'Signature=f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41')


class PushTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = audio_dir(self.tmp.name)
        self.manifest = Path(self.tmp.name) / 'media-manifest.json'

    def tearDown(self):
        self.tmp.cleanup()

    def run_tool(self, *args, env=None):
        out = io.StringIO()
        with patch.dict(os.environ, env or {}, clear=False), contextlib.redirect_stdout(out):
            for k in (*pm.KEYS, 'R2_ENDPOINT'):
                if not (env or {}).get(k):
                    os.environ.pop(k, None)
            code = pm.main([str(self.src), '--manifest', str(self.manifest), '--env-file', str(Path(self.tmp.name) / 'none.env'), *args])
        return code, out.getvalue()

    def test_uploads_what_the_site_serves_and_writes_the_manifest(self):
        srv, got = fake_s3()
        try:
            code, out = self.run_tool(env={**CREDS, 'R2_ENDPOINT': f'http://127.0.0.1:{srv.server_address[1]}'})
        finally:
            srv.shutdown(); srv.server_close()
        self.assertEqual(code, 0)
        paths = sorted(r['path'] for r in got)
        self.assertEqual(paths, ['/flow-media/audio/uk-m/v5-a.json', '/flow-media/audio/uk-m/v5-a.m4a', '/flow-media/audio/us-f/v5-a.json',
                                 '/flow-media/audio/us-f/v5-a.m4a', '/flow-media/audio/us-f/v5-b.m4a', '/flow-media/audio/words/index.json',
                                 '/flow-media/audio/words/us/w000.m4a'])
        for r in got:
            h = {k.lower(): v for k, v in r['headers'].items()}
            self.assertEqual(h['x-amz-content-sha256'], hashlib.sha256(r['body']).hexdigest())
            self.assertTrue(h['authorization'].startswith('AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/'))
            self.assertIn('/auto/s3/aws4_request', h['authorization'])
            self.assertEqual(h['cache-control'], 'public, max-age=31536000')
            self.assertEqual(h['content-type'], 'audio/mp4' if r['path'].endswith('.m4a') else 'application/json')
        self.assertNotIn('secret-not-printed', out)
        m = json.loads(self.manifest.read_text())
        self.assertEqual(m['narration'], {'v5-a': ['us-f', 'uk-m']})  # v5-b has no timings: not offered as narration
        self.assertEqual(m['files']['us-f/v5-a.m4a'], [hashlib.sha256((self.src / 'us-f' / 'v5-a.m4a').read_bytes()).hexdigest(), (self.src / 'us-f' / 'v5-a.m4a').stat().st_size])
        self.assertRegex(m['version'], r'^[0-9a-f]{12}$')

    def test_a_second_run_uploads_only_what_changed(self):
        srv, got = fake_s3()
        env = {**CREDS, 'R2_ENDPOINT': f'http://127.0.0.1:{srv.server_address[1]}'}
        try:
            self.run_tool(env=env); first = json.loads(self.manifest.read_text())['version']; got.clear()
            code, out = self.run_tool(env=env)
            self.assertEqual(got, []); self.assertIn('0 to upload', out)
            (self.src / 'uk-m' / 'v5-a.m4a').write_bytes(b'new take')
            self.run_tool(env=env)
            self.assertEqual([r['path'] for r in got], ['/flow-media/audio/uk-m/v5-a.m4a'])
            self.assertNotEqual(json.loads(self.manifest.read_text())['version'], first)
        finally:
            srv.shutdown(); srv.server_close()

    def test_dry_run_uploads_and_writes_nothing_and_needs_no_key(self):
        code, out = self.run_tool('--dry-run')
        self.assertEqual(code, 0); self.assertIn('7 to upload', out); self.assertFalse(self.manifest.exists())

    def test_missing_credentials_and_a_refused_token_stop_with_a_plain_message(self):
        with self.assertRaises(SystemExit) as e:
            self.run_tool()
        self.assertIn('R2_ACCESS_KEY_ID', str(e.exception))
        srv, _ = fake_s3(status=403)
        try:
            with self.assertRaises(SystemExit) as e:
                self.run_tool(env={**CREDS, 'R2_ENDPOINT': f'http://127.0.0.1:{srv.server_address[1]}'})
        finally:
            srv.shutdown(); srv.server_close()
        self.assertIn('HTTP 403', str(e.exception)); self.assertNotIn('secret-not-printed', str(e.exception))
        self.assertFalse(self.manifest.exists())

    def test_verify_checks_bytes_and_cors_through_the_public_domain(self):
        files = pm.collect(self.src); manifest = pm.build_manifest(self.src, pm.describe(files))
        for cors in (True, False):
            class Public(BaseHTTPRequestHandler):
                def log_message(self, *a):
                    pass

                def do_GET(self):
                    rel = self.path.split('?')[0][len('/audio/'):]
                    body = files[rel].read_bytes()
                    self.send_response(200); self.send_header('Content-Length', str(len(body)))
                    if cors:
                        self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers(); self.wfile.write(body)
            srv = ThreadingHTTPServer(('127.0.0.1', 0), Public); threading.Thread(target=srv.serve_forever, daemon=True).start()
            try:
                problems = pm.verify(f'http://127.0.0.1:{srv.server_address[1]}', manifest, sample=7)
            finally:
                srv.shutdown(); srv.server_close()
            if cors:
                self.assertEqual(problems, [])
            else:
                self.assertTrue(problems) and self.assertTrue(all('CORS' in p for p in problems))


if __name__ == '__main__':
    unittest.main()
