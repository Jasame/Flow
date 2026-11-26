"""How big a POST may be, and recordings in particular (2026-11-25: 能力测评的口语题 answered every real recording with
「请求大小不正确」: /api/next/assess/speaking was missing from app.py's recording size, so it fell to the 20 KB default).

The routes whose handlers read a recording are found from the code itself, so a new one left out of app.AUDIO_PATHS
fails here; and every one of them takes the biggest recording the page sends."""
import ast, base64, json, math, os, re, socket, sys, tempfile, threading, unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

FLOW = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FLOW))
import app, audio_validation  # noqa: E402

SEED = {'validate_audio', '_audio_or_text'}  # what reads a recording sent by the page
# Routes that share a handler with a recording route but never pass it a recording (text only): the same function
# serves both, so the scan below finds them too.
SHARES_A_HANDLER = {'/api/lab/feedback': 'lab_service.feedback (audio only for /api/lab/audio)',
                    '/api/next/assess/writing': 'ability_radar.judged (audio only for speaking)',
                    '/api/next/zh': 'ai_lang.to_zh (text only: the text service looks at a recording only when given one)'}
NGINX = 3 * 1024 * 1024  # client_max_body_size 3m


def recording_routes():
    """{route: handlers} for every route whose handler, at any depth, calls SEED: if-branches on the path
    (`if path == '/api/…': return shadow(…)`, `__import__('ielts_speaking').post(…)`) and route tables ({'/api/…': fn})."""
    mods = {p.stem: ast.parse(p.read_text(encoding='utf-8')) for p in FLOW.glob('*.py')}

    def target(mod, f):
        if isinstance(f, ast.Name):
            return mod, f.id
        if isinstance(f, ast.Attribute):
            v = f.value
            if isinstance(v, ast.Name) and v.id in mods:
                return v.id, f.attr
            if isinstance(v, ast.Call) and isinstance(v.func, ast.Name) and v.func.id == '__import__' and v.args and isinstance(v.args[0], ast.Constant):
                return v.args[0].value, f.attr
        return None

    def calls(mod, node):
        out = set()
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and target(mod, n.func):
                out.add(target(mod, n.func))
            elif isinstance(n, ast.Dict):
                out |= {(mod, v.id) for v in n.values if isinstance(v, ast.Name)}
        return out

    body = {(m, n.name): calls(m, n) for m, t in mods.items() for n in t.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    audio = {k for k, cs in body.items() if any(c[1] in SEED for c in cs)}
    while True:
        more = {k for k, cs in body.items() if k not in audio and cs & audio}
        if not more:
            break
        audio |= more
    routes = {}
    for m, t in mods.items():
        for n in ast.walk(t):
            if isinstance(n, ast.If):
                lits = {c.value for c in ast.walk(n.test) if isinstance(c, ast.Constant) and isinstance(c.value, str) and c.value.startswith('/api/') and not c.value.endswith('/')}
                hit = set().union(*(calls(m, s) for s in n.body)) & audio if lits else set()
                for lit in lits if hit else ():
                    routes.setdefault(lit, set()).update(f'{a}.{b}' for a, b in hit)
            elif isinstance(n, ast.Dict):
                for k, v in zip(n.keys, n.values):
                    if isinstance(k, ast.Constant) and isinstance(k.value, str) and k.value.startswith('/api/') and isinstance(v, ast.Name) and (m, v.id) in audio:
                        routes.setdefault(k.value, set()).add(f'{m}.{v.id}')
    return routes


def page_max():
    """The biggest recording the page sends (MIC.MAX in 70-learner.js)."""
    src = (FLOW / 'public' / 'src' / 'next' / '70-learner.js').read_text(encoding='utf-8')
    return int(re.search(r'MAX: (\d+), FULL: (\d+)', src).group(1))


def server_limit():
    m = re.search(r'else (\d+) if self\.path in AUDIO_PATHS', (FLOW / 'app.py').read_text(encoding='utf-8'))
    return int(m.group(1))


class RecordingRoutes(unittest.TestCase):
    def test_every_route_that_reads_a_recording_takes_one(self):
        found = recording_routes()
        self.assertIn('/api/next/assess/speaking', found)  # the one that was missing
        missing = sorted(set(found) - set(app.AUDIO_PATHS) - set(SHARES_A_HANDLER))
        self.assertEqual(missing, [], f'these read a recording but get the 20 KB limit; add them to app.AUDIO_PATHS: {missing}')
        stale = sorted(set(app.AUDIO_PATHS) - set(found))
        self.assertEqual(stale, [], f'app.AUDIO_PATHS lists routes that read no recording: {stale}')
        self.assertEqual(sorted(set(SHARES_A_HANDLER) - set(found)), [], 'SHARES_A_HANDLER is out of date')

    def test_the_limits_fit_together(self):
        biggest = page_max()
        b64 = math.ceil(biggest / 3) * 4
        self.assertLessEqual(biggest, audio_validation.MAX_AUDIO_BYTES)  # the server takes what the page sends
        self.assertLessEqual(b64, 2_000_000)  # validate_audio's base64 length
        self.assertLessEqual(b64 + 20_000, server_limit())  # with the question, the history of a dialog …
        self.assertLessEqual(server_limit(), NGINX)
        # what 75 s (the ability test) and 2 minutes (a retell) come to at the 48 kb/s the page asks for
        self.assertLess(48_000 / 8 * 120 * 1.1, biggest)


class Sizes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        data = Path(self.tmp.name)
        self.patches = [patch.object(app, 'DB', data / 'a.db'), patch.object(app, 'DATA', data),
                        patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0', 'FLOW_DATA_DIR': str(data)})]
        for p in self.patches:
            p.start()
        app.SECURE = False
        app.init()
        self.site = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.site.serve_forever, daemon=True).start()

    def tearDown(self):
        self.site.shutdown(); self.site.server_close()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def post(self, path, body=b'', length=None):
        """Headers first: a size refusal (or a route that answers before reading, /api/lab/audio unsigned) comes back from
        them alone; otherwise the body follows, as a browser sends it."""
        s = socket.create_connection(('127.0.0.1', self.site.server_address[1]), timeout=20)
        n = length if length is not None else len(body)
        s.sendall(f'POST {path} HTTP/1.1\r\nHost: flow.test\r\nContent-Type: application/json\r\nContent-Length: {n}\r\nConnection: close\r\n\r\n'.encode())
        s.settimeout(0.6)
        try:
            data = s.recv(65536)
        except socket.timeout:
            s.settimeout(20); s.sendall(body); data = b''
        s.settimeout(20)
        while True:
            chunk = s.recv(65536)
            if not chunk:
                break
            data += chunk
        s.close()
        head, _, rest = data.partition(b'\r\n\r\n')
        return int(head.split()[1]), json.loads(rest or b'{}')

    def test_the_biggest_recording_the_page_sends_gets_through_every_recording_route(self):
        # about 60 s on an iPhone at its default AAC rate (185 kb/s), the most the page lets through
        audio = {'mime_type': 'audio/webm', 'data': base64.b64encode(b'\x1aE\xdf\xa3' + b'\0' * (page_max() - 4)).decode()}
        for path in app.AUDIO_PATHS:
            body = json.dumps({'audio': audio, 'question': 'Describe something you changed your mind about.', 'request_id': 'size-test'}).encode()
            status, j = self.post(path, body)
            self.assertNotIn(j.get('error'), ('请求大小不正确', app.TOO_LONG), (path, len(body)))
            self.assertNotIn(status, (400, 413), (path, status, j))  # not signed in: 401, after the size has passed

    def test_too_long_a_recording_is_said_plainly(self):
        status, j = self.post('/api/next/assess/speaking', length=2_200_001)
        self.assertEqual((status, j['error'], j.get('code')), (413, '录音太长了，请在 1 分钟内说完再交', 'too_long'))

    def test_other_routes_keep_their_small_limit(self):
        status, j = self.post('/api/next/profile', length=30_000)
        self.assertEqual((status, j['error']), (400, '请求大小不正确'))
        status, j = self.post('/api/next/dialog', json.dumps({'text': 'x' * 60_000}).encode())  # was listed twice: the recording size wins
        self.assertNotEqual(j.get('error'), '请求大小不正确')


if __name__ == '__main__':
    unittest.main()
