"""Two sites from one code base (2026-11-24): flowlang.cn is 语流, flow.jasa.hk is the 内测版 (FLOW_CHANNEL=beta, its
own data). The 内测版 says so on every page and in every mail, keeps out of search results, and its releases go
through their own tags and server copies (tools/deploy.sh --beta, tools/flow-autodeploy.py --beta)."""
import json, os, subprocess, sys, tempfile, threading, unittest, urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app, account_service  # noqa: E402

ROOT = Path(app.ROOT)
TOOLS = ROOT.parent / 'tools'
JS = (ROOT / 'public' / 'next.js').read_text(encoding='utf-8')
CSS = (ROOT / 'public' / 'next.css').read_text(encoding='utf-8')


class Site(unittest.TestCase):
    channel = 'prod'

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patches = [patch.object(app, 'DB', Path(self.tmp.name) / 'a.db'), patch.object(app, 'DATA', Path(self.tmp.name)),
                        patch.object(app, 'CHANNEL', self.channel), patch.dict(os.environ, {'FLOW_COOKIE_SECURE': '0'})]
        for p in self.patches:
            p.start()
        app.init()
        self.srv = ThreadingHTTPServer(('127.0.0.1', 0), app.Handler)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def tearDown(self):
        self.srv.shutdown(); self.srv.server_close()
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def get(self, path):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.srv.server_address[1]}{path}', timeout=10) as r:
            return r.read(), dict(r.headers)


class MainSiteTests(Site):
    def test_flowlang_is_the_site_and_may_be_found(self):
        page, h = self.get('/')
        self.assertIn(b'<html lang="zh-CN" data-channel="prod">', page)
        self.assertNotIn('X-Robots-Tag', h)
        self.assertEqual(json.loads(self.get('/api/health')[0])['channel'], 'prod')
        robots = self.get('/robots.txt')[0].decode()
        self.assertIn('Allow: /', robots); self.assertIn('Disallow: /api/', robots)
        self.assertEqual(json.loads(self.get('/manifest.webmanifest')[0])['name'], '语流 Flow')


class BetaSiteTests(Site):
    channel = 'beta'

    def test_the_beta_says_so_and_stays_out_of_search(self):
        page, h = self.get('/')
        self.assertIn(b'data-channel="beta"', page)
        self.assertEqual(h['X-Robots-Tag'], 'noindex, nofollow')
        self.assertEqual(self.get('/robots.txt')[0].decode(), 'User-agent: *\nDisallow: /\n')
        self.assertEqual(json.loads(self.get('/api/health')[0])['channel'], 'beta')
        m = json.loads(self.get('/manifest.webmanifest')[0])
        self.assertEqual((m['name'], m['short_name']), ('语流 Flow 内测版', '语流内测'))  # its home-screen app is told apart


class MailTests(unittest.TestCase):
    def test_the_mail_server_is_greeted_with_the_sites_domain(self):
        """EHLO says the site's domain (FLOW_PUBLIC_URL), never the machine's internal name, on both kinds of connection."""
        seen = []

        class Fake:
            def __init__(self, host, port, local_hostname=None, **kw): seen.append((port, local_hostname))
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def ehlo(self): pass
            def starttls(self, **kw): pass
            def login(self, *a): pass
            def send_message(self, msg): pass

        env = {'FLOW_SMTP_HOST': 'smtp.example.com', 'FLOW_SMTP_FROM': 'x@example.com', 'FLOW_SMTP_USER': 'u', 'FLOW_SMTP_PASSWORD': 'p',
               'FLOW_CHANNEL': ''}
        with patch.dict(os.environ, env), patch.object(account_service.smtplib, 'SMTP_SSL', Fake), patch.object(account_service.smtplib, 'SMTP', Fake):
            os.environ.pop('FLOW_MAIL_OUTBOX', None)
            for url, port in (('https://flow.jasa.hk', '465'), ('', '465'), ('https://flowlang.cn/', '587'), ('http://127.0.0.1:8090', '465'),
                              ('http://localhost:8090', '465')):
                os.environ['FLOW_PUBLIC_URL'], os.environ['FLOW_SMTP_PORT'] = url, port
                account_service.mail('a@example.com', 's', 't')
        self.assertEqual(seen, [(465, 'flow.jasa.hk'), (465, 'flowlang.cn'), (587, 'flowlang.cn'), (465, 'flowlang.cn'), (465, 'flowlang.cn')])

    def test_beta_mail_is_marked_once(self):
        with tempfile.TemporaryDirectory() as out:
            for channel, want in (('', 'Flow 登录验证码 123456'), ('beta', '【内测版】Flow 登录验证码 123456')):
                with patch.dict(os.environ, {'FLOW_MAIL_OUTBOX': out, 'FLOW_CHANNEL': channel}):
                    account_service.mail('a@example.com', 'Flow 登录验证码 123456', 'x')
                    account_service.mail('a@example.com', '【内测版】Flow 登录验证码 123456', 'x')  # never twice
            subjects = sorted(l[9:] for f in Path(out).iterdir() for l in f.read_text(encoding='utf-8').splitlines() if l.startswith('Subject: '))
        self.assertEqual(subjects.count('【内测版】Flow 登录验证码 123456'), 3)
        self.assertEqual(subjects.count('Flow 登录验证码 123456'), 1)

    def test_links_written_for_outside_the_page_point_at_flowlang(self):
        import vocab_service, skills_service
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop('FLOW_PUBLIC_URL', None)
            self.assertIn('URL:https://flowlang.cn/#/', vocab_service.ics(20, 'vocab', 10))
        for f in ('vocab_service.py', 'skills_service.py', 'account_service.py'):
            self.assertNotIn("'https://flow.jasa.hk'", (ROOT / f).read_text(encoding='utf-8'), f)
        self.assertNotIn("'https://flow.jasa.hk'", (TOOLS / 'build_guide.py').read_text(encoding='utf-8'))


class PageTests(unittest.TestCase):
    def test_the_beta_bar_the_moving_sheet_and_the_sign_in_note(self):
        for s in ("const BETA = document.documentElement.dataset.channel === 'beta'", "const MAIN_SITE = 'https://flowlang.cn'", 'id="betaBar"',
                  "'flow-snap', 'flow-offline', 'flow-next-outbox', 'flow-next-review-cache'", "save('flow-channel', 'beta')", '这里是语流内测版',
                  "document.title = '内测 · ' + document.title", 'data-tap="beta-main"'):
            self.assertIn(s, JS)
        self.assertIn("html[data-channel=beta] .auth::before", CSS)
        self.assertLess(JS.index('const BETA_BEFORE'), JS.index('(async function boot()'))  # cleared before the page starts
        import flow_admin
        self.assertIn('beta-main', flow_admin.TAP_LABEL)


class SetupTests(unittest.TestCase):
    """tools/beta_setup.py, the one-time setup on 香港: its text changes, on made-up copies of the server's files."""
    def setUp(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location('beta_setup', TOOLS / 'beta_setup.py')
        self.bs = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.bs)

    def test_settings_unit_and_timer(self):
        env = 'FLOW_AI_KEY=secret\nFLOW_PORT=8090\nFLOW_SERVER_LABEL=香港服务器\nFLOW_SMTP_HOST=smtp.example.com\n'
        b = self.bs.beta_env(env, '/www/wwwroot/flow/audio')
        self.assertEqual(self.bs.env_value(b, 'FLOW_PORT'), '8092')
        self.assertEqual(self.bs.env_value(b, 'FLOW_CHANNEL'), 'beta')
        self.assertEqual(self.bs.env_value(b, 'FLOW_ADMIN_PORT'), '')  # no console port on the 内测版
        self.assertEqual(self.bs.env_value(b, 'FLOW_DATA_DIR'), '/www/wwwroot/flow-beta/data')
        self.assertEqual(self.bs.env_value(b, 'FLOW_AUDIO_DIR'), '/www/wwwroot/flow/audio')
        self.assertEqual(self.bs.env_value(b, 'FLOW_AI_KEY'), 'secret')  # the rest as it is
        self.assertEqual(b.count('FLOW_PORT='), 1)
        unit = ('[Unit]\nDescription=Flow English Learning Pilot\n[Service]\nWorkingDirectory=/www/wwwroot/flow\nEnvironmentFile=/etc/flow.env\n'
                'ExecStart=/usr/bin/python3.11 /www/wwwroot/flow/app.py\nReadWritePaths=/www/wwwroot/flow/data\n')
        u = self.bs.beta_unit(unit)
        for want in ('WorkingDirectory=/www/wwwroot/flow-beta\n', 'EnvironmentFile=/etc/flow-beta.env', '/www/wwwroot/flow-beta/app.py',
                     'ReadWritePaths=/www/wwwroot/flow-beta/data', 'Description=Flow 内测版'):
            self.assertIn(want, u)
        self.assertEqual(self.bs.beta_unit(u), u)  # the 内测版's paths are not changed again
        t = self.bs.beta_timer_unit('[Service]\nEnvironmentFile=/etc/flow.env\nExecStart=/opt/uv-python/bin/python3.11 -I /root/claude-ops/flow-autodeploy.py\n[Timer]\nUnit=flow-autodeploy.service\n')
        self.assertIn('-I /root/claude-ops/beta/flow-autodeploy.py --beta', t); self.assertIn('Unit=flow-autodeploy-beta.service', t)
        self.assertIn('EnvironmentFile=/etc/flow-beta.env', t)
        self.assertEqual(self.bs.env_value(self.bs.with_public_url('A=1\nFLOW_PUBLIC_URL=https://flow.jasa.hk\n', 'https://flowlang.cn'), 'FLOW_PUBLIC_URL'), 'https://flowlang.cn')

    def test_nginx_switches_by_host_or_says_why_not(self):
        vhost = ('server {\n listen 443 ssl http2;\n server_name flow.jasa.hk flowlang.cn www.flowlang.cn;\n'
                 ' location / {\n  proxy_pass http://127.0.0.1:8090;\n  proxy_set_header Host $host;\n }\n'
                 ' location /flow/api/ { return 404; }\n}\n')
        new, problems = self.bs.nginx_plan({'/v/flow.jasa.hk.conf': vhost, '/v/ext/audio.conf': 'location /audio/ { alias /www/wwwroot/flow/audio/; }'})
        self.assertEqual(problems, [])
        self.assertEqual(list(new), ['/v/flow.jasa.hk.conf'])
        self.assertIn('proxy_pass http://$flow_site;', new['/v/flow.jasa.hk.conf'])
        self.assertNotIn('127.0.0.1:8090', new['/v/flow.jasa.hk.conf'])
        self.assertIn('flow.jasa.hk 127.0.0.1:8092;', self.bs.MAP_TEXT); self.assertIn('default 127.0.0.1:8090;', self.bs.MAP_TEXT)
        _, problems = self.bs.nginx_plan({'/v/a.conf': vhost.replace('8090;', '8090/;')})
        self.assertTrue(any('only' in p for p in problems))  # another form: told, not guessed
        _, problems = self.bs.nginx_plan({'/v/a.conf': vhost + 'server { server_name flowlang.cn; return 301 https://flow.jasa.hk$request_uri; }\n'})
        self.assertTrue(any('redirect' in p for p in problems))


class LightEndToEndTests(unittest.TestCase):
    """REQUEST "e2e light" runs tools/qa_e2e.py with QA_LIGHT=1, which sends no recording to the AI (the Gemini relay's
    two places are shared with 语流's learners), and the test never has more than QA_AI_SLOTS AI requests in flight."""

    def autodeploy(self):
        import importlib.util
        with patch.object(sys, 'argv', ['flow-autodeploy.py', '--beta']):
            spec = importlib.util.spec_from_file_location('autodeploy_light', TOOLS / 'flow-autodeploy.py')
            mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        return mod

    def test_the_request_word_light_reaches_the_test_as_qa_light(self):
        mod = self.autodeploy()
        src = (TOOLS / 'flow-autodeploy.py').read_text()
        self.assertIn("light = e2e and 'light' in words[2:]", src)
        self.assertIn("st['e2e'] = run_e2e(work, work / 'e2e.log', light)", src)
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            failed = [{'who': 'b1', 'name': 'dialog end gives feedback', 'detail': str({'error': 'AI 这次的回答不完整，没有保存。', 'request_id': 'e2e-dg-1', 'remaining': 41})},
                      {'who': 'db', 'name': 'no AI job failed', 'detail': str([{'kind': 'next-dialog', 'error': 'AI 这次的回答不完整，没有保存。'}])},
                      {'who': 'exam', 'name': 'AI scores an essay', 'detail': str({'summary': 'what the learner wrote, never shown', 'score': 0.4})},
                      {'who': 'guard', 'name': 'oversized essay body refused', 'detail': '502'},
                      {'who': 'a2', 'name': 'persona finished without crashing', 'detail': 'Traceback (most recent call last):\n  File "x"\nKeyError: \'reply\''}]
            (work / 'report.json').write_text(json.dumps({'checks': {'total': 3, 'failed': 1}, 'failed': failed, 'server_errors': [],
                                                          'ai_calls_used': 1, 'seconds': 1, 'light': True}))
            seen = []
            with patch.object(mod.subprocess, 'run', lambda *a, **k: seen.append(k['env'])):
                summary = mod.run_e2e(work, work / 'e2e.log', True)
                self.assertTrue(summary['light'])
                mod.run_e2e(work, work / 'e2e.log')
        # why it failed travels with the name: the app's error text, a status, an exception type; never an answer's content
        self.assertEqual(summary['failed_details'], [
            'b1: dialog end gives feedback: AI 这次的回答不完整，没有保存。',
            'db: no AI job failed: next-dialog: AI 这次的回答不完整，没有保存。',
            'exam: AI scores an essay: ',
            'guard: oversized essay body refused: HTTP 502',
            'a2: persona finished without crashing: KeyError'])
        self.assertNotIn('learner wrote', json.dumps(summary, ensure_ascii=False))
        self.assertEqual(seen[0].get('QA_LIGHT'), '1')
        self.assertNotIn('QA_LIGHT', seen[1])
        self.assertEqual(seen[0].get('FLOW_SERVICE'), 'flow-beta')  # the 内测版's settings are kept

    def test_every_recording_sent_to_the_ai_is_skipped_in_a_light_run(self):
        lines = (TOOLS / 'qa_e2e.py').read_text().splitlines()
        sends = [k for k, l in enumerate(lines) if 'cl.ai(' in l and 'audio(' in l]
        self.assertGreaterEqual(len(sends), 5)
        for k in sends:
            depth = len(lines[k]) - len(lines[k].lstrip())
            opener = next(l for l in reversed(lines[:k]) if l.strip() and len(l) - len(l.lstrip()) < depth)
            while not opener.lstrip().startswith(('if spoken(', 'def ')):
                depth = len(opener) - len(opener.lstrip())
                opener = next(l for l in reversed(lines[:lines.index(opener)]) if l.strip() and len(l) - len(l.lstrip()) < depth)
            self.assertTrue(opener.lstrip().startswith('if spoken('), f'qa_e2e.py line {k + 1} sends a recording outside `if spoken(...)`')
        src = '\n'.join(lines)
        self.assertIn("AI_SLOTS = threading.BoundedSemaphore(AI_SLOT_COUNT)", src)
        self.assertIn("with AI_SLOTS if slot else contextlib.nullcontext():", src)


class ToolTests(unittest.TestCase):
    def test_releases_for_each_site_go_their_own_way(self):
        for f in ('deploy.sh', 'flow-pull.sh', 'flow-pull-rollback.sh'):
            r = subprocess.run(['bash', '-n', str(TOOLS / f)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, f + r.stderr)
        deploy = (TOOLS / 'deploy.sh').read_text()
        # a commit whose flow-pull.sh predates the two sites would install into 语流: refused on both ends
        self.assertIn("git show \"$SHA:tools/flow-pull.sh\" | grep -qF 'F=${FLOW_DIR:-'", deploy)
        # next.js, next.css and the guide PDF are built once per commit for the 内测版 (tools/build_release.py), and 语流
        # installs that same build commit, only after it was requested on the 内测版 (unless --skip-beta)
        self.assertIn('BUILD=$(python3 tools/build_release.py "$SHA")', deploy)
        self.assertIn('BUILD=$(python3 tools/build_release.py --reuse "$SHA")', deploy)
        # grep without -q: under pipefail, grep -q stopping early would make git log's broken pipe count as "not found"
        self.assertIn('git log -p --format= origin/release-beta -- REQUEST | grep "^+$BUILD " >/dev/null', deploy)
        self.assertNotIn('| grep -q "^+$BUILD "', deploy)
        # the automatic 内测版 releases ask for the light end-to-end test (no recordings to the AI); 语流 never does
        self.assertIn('--light) LIGHT=" light" ;;', deploy)
        self.assertIn('if [ -n "$LIGHT" ] && [ $P = r ]; then echo', deploy)
        self.assertIn('if [ -n "$E2E" ]; then E2E="$E2E$LIGHT"; fi', deploy)
        self.assertIn('MAN=$(python3 tools/release_manifest.py "$BUILD" 2>/dev/null)', deploy)
        self.assertNotIn('build_front.py --check', deploy)
        # REQUEST names main when main has the commit, not the first branch that happens to contain it
        self.assertIn('if printf \'%s\\n\' "$BRS" | grep -qx main; then BR=main;', deploy)  # it checked the laptop's files, not the commit's
        self.assertIn("if BETA and b'F=${FLOW_DIR:-' not in (work / 'flow-pull.sh').read_bytes():", (TOOLS / 'flow-autodeploy.py').read_text())
        self.assertIn('F=${FLOW_DIR:-', (TOOLS / 'flow-pull.sh').read_text())
        self.assertIn('--beta) P=b; BRANCH=release-beta; SITE=https://flow.jasa.hk', deploy)
        self.assertIn('P=r; BRANCH=release; SITE=https://flowlang.cn', deploy)
        pull = (TOOLS / 'flow-pull.sh').read_text()
        self.assertNotIn('if xmc_dir:', pull)  # one manifest per commit: the 内测版 checks the console files too, it only skips installing them
        # both services may write the shared voice folder (ProtectSystem=strict), set before the restart
        self.assertLess(pull.index("ReadWritePaths=-%s/tts"), pull.index('systemctl restart "$SVC"'))
        self.assertIn('AUD=$(audio_dir "/etc/$SVC.env")', pull)
        # the folder as systemd reads it: quoted or not, with or without a trailing slash; anything else means 语流's folder
        import re as _re, tempfile as _tf
        fn = _re.search(r'^audio_dir\(\) \{.*?^\}', pull, _re.S | _re.M).group(0)
        cases = {'FLOW_AUDIO_DIR=/www/wwwroot/flow/audio\n': '/www/wwwroot/flow/audio', 'FLOW_AUDIO_DIR="/data/audio/"\n': '/data/audio',
                 "A=1\nFLOW_AUDIO_DIR='/srv/a b'\r\n": '/srv/a b', 'FLOW_SMTP_HOST="x"\n': '/www/wwwroot/flow/audio',
                 'FLOW_AUDIO_DIR=audio\n': '/www/wwwroot/flow/audio', '': '/www/wwwroot/flow/audio'}
        for text, want in cases.items():
            with _tf.NamedTemporaryFile('w', suffix='.env', delete=False) as f:
                f.write(text)
            got = subprocess.run(['bash', '-c', fn + '\naudio_dir "$1"', '_', f.name], capture_output=True, text=True).stdout.strip()
            os.unlink(f.name)
            self.assertEqual(got, want, text)
        for s in ('F=${FLOW_DIR:-/www/wwwroot/flow}', 'XMC=${FLOW_XMC-/www/wwwroot/xmc.hk/flow}', 'SVC=${FLOW_SERVICE:-flow}', 'U=${FLOW_URL:-http://127.0.0.1:8090}',
                  'echo "$SHA" > "$OPS/$SVC-deployed-commit"', 'bash "$HERE/flow-pull-rollback.sh" "$BK"',
                  "names += [f'xmc-admin/{n}'", 'xmc-admin/*) [ -n "$XMC" ] || continue;'):
            self.assertIn(s, pull)
        import importlib.util
        for argv, prefix, status in (([], 'r', '/www/wwwroot/flow/data/deploy-status.json'), (['--beta'], 'b', '/www/wwwroot/flow-beta/data/deploy-status.json')):
            with patch.object(sys, 'argv', ['flow-autodeploy.py', *argv]):
                spec = importlib.util.spec_from_file_location('autodeploy_' + prefix, TOOLS / 'flow-autodeploy.py')
                mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
            self.assertEqual((mod.SITE['prefix'], str(mod.STATUS)), (prefix, status))
            self.assertEqual(mod.ENV.get('FLOW_SERVICE', 'flow'), 'flow-beta' if argv else 'flow')
            self.assertEqual(mod.ENV.get('QA_BASE', 'http://127.0.0.1:8090'), 'http://127.0.0.1:8092' if argv else 'http://127.0.0.1:8090')
        monitor = (ROOT.parent / '.github' / 'workflows' / 'monitor.yml').read_text()
        self.assertIn('check https://flowlang.cn/api/deploy-status', monitor)
        self.assertNotIn('check https://flow.jasa.hk', monitor)


if __name__ == '__main__':
    unittest.main()
