"""tools/ai-gateway: the AI gateway kit (New API in front of DeepSeek, Qwen, Gemini …). The check script is run
against a stand-in gateway that speaks the same API; the compose file and the nginx snippet are checked for the
things that keep the model relay private."""
import contextlib, importlib.util, io, json, re, subprocess, sys, tempfile, threading, unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KIT = ROOT / 'tools' / 'ai-gateway'
spec = importlib.util.spec_from_file_location('check_gateway', KIT / 'check_gateway.py')
cg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cg)
KEY = 'sk-test-0123456789abcdef'


def gateway(models=('flow-text',), json_ok=True, public_open=False):
    """A stand-in for New API on 127.0.0.1: /api/status, /v1/models, /v1/chat/completions (plain and streamed)."""
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def send(self, code, obj, ctype='application/json'):
            body = json.dumps(obj).encode() if not isinstance(obj, bytes) else obj
            self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

        def authed(self):
            return self.headers.get('Authorization') == 'Bearer ' + KEY

        def do_GET(self):
            if self.path == '/api/status':
                return self.send(200, {'success': True, 'data': {}})
            if self.path == '/v1/models':
                if not self.authed():
                    return self.send(401, {'error': {'message': 'no token'}})
                return self.send(200, {'object': 'list', 'data': [{'id': m} for m in models]})
            self.send(404, b'not found', 'text/html')

        def do_POST(self):
            if not self.authed():
                return self.send(401, {'error': {'message': 'no token'}})
            req = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if req.get('stream'):
                self.send_response(200); self.send_header('Content-Type', 'text/event-stream'); self.end_headers()
                for i, w in enumerate(['one', ' two', ' three']):
                    self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': w}, 'finish_reason': 'stop' if i == 2 else None}]})}\n\n".encode())
                self.wfile.write(b'data: [DONE]\n\n'); return
            asks_json = 'JSON' in req['messages'][-1]['content']
            text = ('```json\n{"strength": "很好", "revision": "I like apples."}\n```' if json_ok else 'Sure! The sentence is fine.') if asks_json else 'Hello there!'
            self.send(200, {'model': 'deepseek-chat', 'choices': [{'message': {'content': text}, 'finish_reason': 'stop'}]})

    class Public(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            body = json.dumps({'error': {'message': 'no token'}}).encode() if public_open else b'<html>404</html>'
            self.send_response(401 if public_open else 404); self.send_header('Content-Type', 'application/json' if public_open else 'text/html')
            self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)

    servers = [ThreadingHTTPServer(('127.0.0.1', 0), H), ThreadingHTTPServer(('127.0.0.1', 0), Public)]
    for s in servers:
        threading.Thread(target=s.serve_forever, daemon=True).start()
    return servers


class CheckScriptTests(unittest.TestCase):
    def run_check(self, servers, model='flow-text', public=True):
        gw, pub = servers
        env = {'FLOW_TEXT_AI_URL': f'http://127.0.0.1:{gw.server_address[1]}/v1/chat/completions', 'FLOW_TEXT_AI_KEY': KEY, 'FLOW_TEXT_AI_MODEL': model}
        lines = []
        try:
            res = cg.run(env, f'http://127.0.0.1:{pub.server_address[1]}' if public else None, out=lines.append)
        finally:
            for s in servers:
                s.shutdown(); s.server_close()
        return res, '\n'.join(lines)

    def test_a_healthy_private_gateway_passes_every_check_and_no_key_is_printed(self):
        res, text = self.run_check(gateway())
        self.assertTrue(res and all(r['ok'] for r in res), text)
        self.assertEqual(len(res), 9)
        self.assertNotIn(KEY, text); self.assertNotIn(KEY, json.dumps(res))
        self.assertIn('deepseek-chat', text)  # which model really answered

    def test_a_token_without_the_flow_model_fails_with_what_to_tick(self):
        res, text = self.run_check(gateway(models=('deepseek-chat',)))
        bad = [r for r in res if not r['ok']]
        self.assertTrue(bad); self.assertIn('flow-text', bad[0]['check']); self.assertIn('模型限制', bad[0]['detail'])

    def test_a_model_that_ignores_the_json_instruction_is_flagged(self):
        res, _ = self.run_check(gateway(json_ok=False))
        self.assertEqual([r['check'] for r in res if not r['ok']], ['按要求只回 JSON（批改、出题都靠它）'])

    def test_a_relay_open_to_the_internet_is_flagged(self):
        res, _ = self.run_check(gateway(public_open=True))
        self.assertEqual([r['check'] for r in res if not r['ok']], ['模型接口不对公网开放'])

    def test_missing_flow_settings_stop_early_and_say_which(self):
        lines = []
        res = cg.run({'FLOW_TEXT_AI_URL': 'http://127.0.0.1:9/v1/chat/completions'}, out=lines.append)
        self.assertEqual(len(res), 1); self.assertFalse(res[0]['ok'])
        self.assertIn('FLOW_TEXT_AI_KEY', res[0]['detail']); self.assertIn('FLOW_TEXT_AI_MODEL', res[0]['detail'])

    def test_a_stopped_gateway_is_reported_not_crashed_on(self):
        lines = []
        res = cg.run({'FLOW_TEXT_AI_URL': 'http://127.0.0.1:9/v1/chat/completions', 'FLOW_TEXT_AI_KEY': KEY, 'FLOW_TEXT_AI_MODEL': 'flow-text'}, out=lines.append)
        self.assertFalse(res[-1]['ok']); self.assertEqual(res[-1]['check'], '网关在运行')

    def test_env_file_is_read_like_flow_reads_it(self):
        with tempfile.NamedTemporaryFile('w', suffix='.env', delete=False) as f:
            f.write('# comment\nFLOW_TEXT_AI_URL="http://127.0.0.1:3000/v1/chat/completions"\nFLOW_TEXT_AI_MODEL=flow-text\n\nFLOW_TEXT_AI_KEY=abc\n')
        env = cg.read_env(f.name); Path(f.name).unlink()
        self.assertEqual(env['FLOW_TEXT_AI_URL'], 'http://127.0.0.1:3000/v1/chat/completions'); self.assertEqual(env['FLOW_TEXT_AI_KEY'], 'abc')


class KitFilesTests(unittest.TestCase):
    def test_compose_pins_the_image_and_keeps_the_gateway_on_this_machine(self):
        c = (KIT / 'docker-compose.yml').read_text()
        image = re.search(r'^\s*image:\s*(\S+)', c, re.M).group(1)
        self.assertRegex(image, r'^calciumion/new-api:v\d+\.\d+\.\d+(-rc\.\d+)?$')
        self.assertIn('"127.0.0.1:${AI_GATEWAY_PORT:-3000}:3000"', c)
        ports = re.findall(r'^\s*-\s*"?([^"\s]*:3000)"?\s*$', c, re.M)
        self.assertEqual(ports, ['127.0.0.1:${AI_GATEWAY_PORT:-3000}:3000'])  # the only published port, never on 0.0.0.0
        for line in ('./data:/data', 'env_file: .env', 'SESSION_COOKIE_SECURE=true', 'SESSION_COOKIE_TRUSTED_URL=https://api.xmc.hk'):
            self.assertIn(line, c)
        self.assertNotIn('SESSION_SECRET=', c)  # the secret lives only in .env on the server

    def test_nginx_closes_the_relay_and_proxies_the_console_to_loopback(self):
        n = (KIT / 'nginx-api.xmc.hk.conf').read_text()
        block = re.search(r'location ~ \^/\(([^)]*)\)\(/\|\$\) \{\s*return 404;', n)
        self.assertTrue(block)
        self.assertIn('v1', block.group(1).split('|'))
        self.assertIn('proxy_pass http://127.0.0.1:3000;', n); self.assertIn('proxy_buffering off;', n)

    def test_setup_script_parses_and_never_echoes_the_secret(self):
        s = (KIT / 'setup.sh').read_text()
        self.assertEqual(subprocess.run(['bash', '-n', str(KIT / 'setup.sh')], capture_output=True).returncode, 0)
        self.assertNotRegex(s, r'echo[^\n]*SESSION_SECRET')
        self.assertIn('chmod 600 "$DIR/.env"', s)

    def test_flow_env_example_and_the_kit_agree_on_the_address_and_model(self):
        env = (ROOT / 'flow' / 'flow.env.example').read_text(); readme = (KIT / 'README.md').read_text()
        for line in ('FLOW_TEXT_AI_URL=http://127.0.0.1:3000/v1/chat/completions', 'FLOW_TEXT_AI_MODEL=flow-text'):
            self.assertIn(line, env); self.assertIn(line, readme)
        sys.path.insert(0, str(ROOT / 'flow'))
        import chat_service
        self.assertTrue(chat_service.endpoint_ok('http://127.0.0.1:3000/v1/chat/completions'))


if __name__ == '__main__':
    unittest.main()
