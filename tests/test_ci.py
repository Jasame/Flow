"""What lets pull requests be tested and merged side by side (2026-11-24).

- tools/run_tests.py splits the suites into the shares CI runs at once: every website test file and every UI group of
  tools/ui_test.py runs in one share, and .github/workflows/tests.yml runs every share under the check names main's
  protection rule asks for (backend, ui, frontend).
- The lists many changes add to are one name per line and sorted (tools/release-files.txt is checked in
  test_release.py, flow/upgrade.sh here), so two additions touch different lines and git merges them.
- tools/settle_merge.py settles what is left over when main is merged into a branch: files that are built at release
  now, and additions on both sides of those lists.
"""
import importlib.util, os, re, subprocess, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools' / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


rt = load('run_tests')
LISTS = re.compile(r'^FLOW_(?:PUBLIC_)?FILES=\(\n(.*?)^\)', re.S | re.M)


class ShareTests(unittest.TestCase):
    def test_every_website_test_file_runs_in_exactly_one_share(self):
        files = rt.test_files()
        self.assertGreater(len(files), 40)
        for n in (1, 2, 3, 4):
            shares = rt.shares(files, n)
            self.assertEqual(sorted(sum(shares, [])), files, n)
            self.assertTrue(all(shares), n)

    def test_every_ui_group_runs_in_a_share(self):
        src = (ROOT / 'tools' / 'ui_test.py').read_text(encoding='utf-8')
        groups = set(re.findall(r"'([a-z0-9-]+)' in ONLY", src)) | set(re.findall(r"^    '([a-z-]+)': dict\(viewport=", src, re.M))
        self.assertTrue({'about', 'phone', 'desktop', 'layout', 'a11y'} <= groups, groups)
        named = [g for share in rt.UI_SHARDS for g in share]
        self.assertEqual(len(named), len(set(named)), 'a group in two shares runs twice')
        self.assertEqual(sorted(groups - set(named)), [], 'add these ui_test.py groups to UI_SHARDS in tools/run_tests.py')

    def test_the_workflow_runs_every_share_under_the_protected_check_names(self):
        wf = (ROOT / '.github' / 'workflows' / 'tests.yml').read_text(encoding='utf-8')
        jobs = dict(re.findall(r'^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)', wf, re.S | re.M))
        self.assertTrue({'backend', 'ui', 'frontend', 'backend-share', 'ui-share'} <= set(jobs), sorted(jobs))
        for gate, shares, count in (('backend', 'backend-share', 2), ('ui', 'ui-share', len(rt.UI_SHARDS))):
            matrix = re.search(r'share: \[([\d, ]+)\]', jobs[shares]).group(1)
            self.assertEqual([int(x) for x in matrix.split(',')], list(range(1, count + 1)), shares)
            self.assertIn(f'--shard ${{{{ matrix.share }}}}/{count}', jobs[shares])
            # the gate runs when a share failed (a skipped required check would count as passed)
            self.assertRegex(jobs[gate], rf'needs: (\[changes, )?{shares}\]?\n'); self.assertIn('!cancelled()', jobs[gate])
            self.assertIn(f'needs.{shares}.result }}}}" = success', jobs[gate])
            self.assertNotIn('\n    name:', jobs[gate])  # the check is named after the job: backend, ui
        self.assertIn('tools/build_release.py --here', jobs['backend-share'])  # the guide PDF the guide tests check


class MainFirstTests(unittest.TestCase):
    """main's runs finish (the next merge does not cancel them), and a pull request that cannot change the UI skips the
    UI shares, so main is not starved of runners (2026-11-25: b12 stayed for hours while PRs filled all 20)."""

    def setUp(self):
        wf = (ROOT / '.github' / 'workflows' / 'tests.yml').read_text(encoding='utf-8')
        self.wf = wf
        self.jobs = dict(re.findall(r'^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)', wf.split('\njobs:\n', 1)[1], re.S | re.M))

    def test_only_a_pull_requests_older_run_is_cancelled(self):
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", self.wf)
        self.assertNotIn('cancel-in-progress: true', self.wf)

    def test_the_ui_shares_are_skipped_only_when_changes_says_so(self):
        self.assertIn("needs: changes\n    if: needs.changes.outputs.ui == 'true'", self.jobs['ui-share'])
        gate = self.jobs['ui']
        self.assertIn('test "${{ needs.changes.result }}" = success', gate)  # a failed check of the paths fails the gate
        self.assertIn('if [ "${{ needs.changes.outputs.ui }}" = false ]; then', gate)  # only an explicit false skips
        self.assertIn('else test "${{ needs.ui-share.result }}" = success; fi', gate)
        ch = self.jobs['changes']
        self.assertIn('if [ "${{ github.event_name }}" != pull_request ]; then printf \'ui=true\\nweb=true\\n\'', ch)  # main: always
        self.assertIn('git diff --name-only HEAD^1 HEAD', ch); self.assertIn('fetch-depth: 2', ch)
        self.assertNotIn('\n    if:', self.jobs['frontend'])  # always
        self.assertNotIn('outputs.ui', self.jobs['backend-share'])  # the website tests do not depend on the UI decision
        self.assertIn("if: needs.changes.outputs.web == 'true'", self.jobs['backend-share'])  # only a native-apps-only PR skips them

    def test_a_pull_request_that_touches_only_the_native_apps_skips_the_website_tests(self):
        for paths in ([], [''], ['ios/Flow/App.swift', 'flow/app.py'], ['tools/run_tests.py'], ['README.md'], ['iosx/a'],
                      ['.github/workflows/tests.yml'], ['desktop2/x'], ['nativex/a'], ['native/flowapp.js', 'docs/native-bridge.md']):
            self.assertTrue(rt.web_needed(paths), paths)
        for paths in (['ios/Flow/App.swift'], ['ios/a', '.github/workflows/ios.yml'], ['desktop/src/main.rs', '.github/workflows/desktop.yml'],
                      ['android/app/build.gradle'], ['native/flowapp.js'], ['native/flowapp.js', 'ios/Flow/Bridge/Bridge.swift']):
            self.assertFalse(rt.web_needed(paths), paths)
            self.assertFalse(rt.ui_needed(paths), paths)
        r = subprocess.run([sys.executable, str(ROOT / 'tools' / 'run_tests.py'), '--needs'], input='ios/Flow/App.swift\n',
                           capture_output=True, text=True)
        self.assertEqual(r.stdout.split(), ['ui=false', 'web=false'])
        gate = self.jobs['backend']
        self.assertIn('needs: [changes, backend-share]', gate)
        self.assertIn('test "${{ needs.changes.result }}" = success', gate)
        self.assertIn('if [ "${{ needs.changes.outputs.web }}" = false ]; then', gate)  # only an explicit false skips
        self.assertIn('else test "${{ needs.backend-share.result }}" = success; fi', gate)
        self.assertIn("printf 'ui=true\\nweb=true\\n'", self.jobs['changes'])  # main and Run workflow: everything

    def test_what_counts_as_a_ui_change(self):
        for paths in ([], [''], ['flow/app.py'], ['flow/public/guide/guide.md'], ['docs/x.md', 'flow/corpus_data/v5/a.json'],
                      ['tools/ui_test.py'], ['tools/ui_server.py'], ['tools/ui-fixtures/wordbooks.json'], ['tools/build_front.py'],
                      ['tools/run_tests.py'], ['.github/workflows/tests.yml']):
            self.assertTrue(rt.ui_needed(paths), paths)
        for paths in (['tools/qa_e2e.py'], ['tools/README.md', 'CONTRIBUTING.md'], ['tools/deploy.sh', 'tools/flow-autodeploy.py'],
                      ['.github/workflows/beta.yml'], ['tests/test_ci.py'], ['tools/ai-gateway/README.md']):
            self.assertFalse(rt.ui_needed(paths), paths)
        r = subprocess.run([sys.executable, str(ROOT / 'tools' / 'run_tests.py'), '--ui-needed'], input='tools/qa_e2e.py\n',
                           capture_output=True, text=True)
        self.assertEqual(r.stdout.strip(), 'ui=false')


class MsiRunnerTests(unittest.TestCase):
    """The owner's MSI takes the heavy shares only when switched on, never for a fork, and only when it answers; the
    gates, frontend and releases stay on GitHub's machines; nothing secret goes there (tools/ci_runner.py)."""

    def setUp(self):
        self.cr = load('ci_runner')
        self.wf = (ROOT / '.github' / 'workflows' / 'tests.yml').read_text(encoding='utf-8')
        self.jobs = dict(re.findall(r'^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)', self.wf.split('\njobs:\n', 1)[1], re.S | re.M))

    def test_the_msi_s_slots_come_from_the_repository_variable_and_default_to_6(self):
        self.assertIn('MSI_SLOTS: ${{ vars.MSI_SLOTS }}', self.jobs['changes'])
        for value, slots in (('', 6), ('7', 7), (None, 6)):
            env = {k: v for k, v in os.environ.items() if k != 'MSI_SLOTS'}
            if value is not None:
                env['MSI_SLOTS'] = value
            r = subprocess.run([sys.executable, '-c', 'import ci_runner; print(ci_runner.SLOTS)'], cwd=ROOT / 'tools',
                               env=env, capture_output=True, text=True)
            self.assertEqual(r.stdout.strip(), str(slots), (value, r.stderr))

    def fake(self, load=0, starts=True, fail=None):
        calls = []

        def api(method, path, body=None):
            calls.append((method, path, body))
            if fail:
                raise fail
            if path.startswith('actions/runs?status=in_progress'):
                return {'workflow_runs': [{'id': 7}]}
            if path.startswith('actions/runs?status='):
                return {'workflow_runs': []}
            if path.startswith('actions/runs/7/jobs'):
                return {'jobs': [{'name': f'ui {k}/5', 'labels': ['self-hosted', 'msi'], 'status': 'in_progress'} for k in range(load)]
                        + [{'name': 'backend', 'labels': ['ubuntu-24.04'], 'status': 'queued'}]}
            if path.endswith('/dispatches'):
                return {}
            if 'msi-probe.yml/runs' in path:
                return {'workflow_runs': [{'id': 99, 'display_title': 'MSI probe 5-1'}]}
            if path.startswith('actions/runs/99/jobs'):
                return {'jobs': [{'name': 'probe', 'labels': ['self-hosted', 'msi'], 'status': 'in_progress' if starts else 'queued'}]}
            raise AssertionError(path)
        return api, calls

    def env(self, **kw):
        return {'MSI_RUNNER': 'on', 'GITHUB_EVENT_NAME': 'pull_request', 'GITHUB_REPOSITORY': 'Jasame/Flow',
                'HEAD_REPO': 'Jasame/Flow', 'GITHUB_RUN_ID': '5', 'GITHUB_RUN_ATTEMPT': '1', 'DEFAULT_BRANCH': 'main', **kw}

    def decide(self, env, api):
        old = self.cr.PROBE_WAIT
        self.cr.PROBE_WAIT = 0.05
        try:
            return self.cr.decide(env, api, sleep=lambda s: None)
        finally:
            self.cr.PROBE_WAIT = old

    def test_github_machines_unless_switched_on_ours_and_answering(self):
        hosted = self.cr.HOSTED
        api, calls = self.fake()
        self.assertEqual(self.decide(self.env(MSI_RUNNER=''), api)[:2], (hosted, 'hosted'))
        self.assertEqual(self.decide(self.env(HEAD_REPO='stranger/Flow'), api)[:2], (hosted, 'hosted'))  # a fork
        self.assertEqual(self.decide(self.env(HEAD_REPO=''), api)[:2], (hosted, 'hosted'))
        self.assertEqual(self.decide(self.env(GITHUB_EVENT_NAME='schedule'), api)[:2], (hosted, 'hosted'))
        self.assertEqual(calls, [])  # none of these even asks GitHub, let alone dispatches a probe
        self.assertEqual(self.decide(self.env(), None)[:2], (hosted, 'hosted'))
        self.assertEqual(self.decide(self.env(), self.fake(load=6)[0])[:2], (hosted, 'hosted'))  # full
        self.assertEqual(self.decide(self.env(), self.fake(starts=False)[0])[:2], (hosted, 'hosted'))  # off: no answer
        import urllib.error
        self.assertEqual(self.decide(self.env(), self.fake(fail=urllib.error.URLError('x'))[0])[:2], (hosted, 'hosted'))
        api, calls = self.fake(load=2)
        runner, where, reason = self.decide(self.env(), api)
        self.assertEqual((runner, where), (['self-hosted', 'msi'], 'msi'), reason)
        self.assertIn(('POST', 'actions/workflows/msi-probe.yml/dispatches', {'ref': 'main', 'inputs': {'nonce': '5-1'}}), calls)
        self.assertEqual(self.decide(self.env(GITHUB_EVENT_NAME='push', HEAD_REPO=''), self.fake()[0])[1], 'msi')  # main

    def test_a_run_goes_to_a_busy_msi_only_if_its_shares_fit_in_what_is_left(self):
        full_run = dict(NEED_WEB='true', NEED_UI='true')
        self.assertEqual(self.cr.need(self.env(**full_run)), 7)
        self.assertEqual(self.cr.need(self.env(NEED_WEB='true', NEED_UI='false')), 2)
        self.assertEqual(self.decide(self.env(**full_run), self.fake(load=0)[0])[1], 'msi')  # the MSI to itself: 7 on 6
        where, reason = self.decide(self.env(**full_run), self.fake(load=2)[0])[1:]
        self.assertEqual(where, 'hosted', reason)  # 2 + 7 > 6: it would wait behind the other run
        self.assertIn('room for 4 more jobs and this run has 7', reason)
        self.assertEqual(self.decide(self.env(NEED_WEB='true', NEED_UI='false'), self.fake(load=2)[0])[1], 'msi')  # 2 + 2
        old = self.cr.SLOTS
        self.cr.SLOTS = 10
        try:
            self.assertEqual(self.decide(self.env(**full_run), self.fake(load=3)[0])[1], 'msi')  # 3 + 7 = 10
            self.assertEqual(self.decide(self.env(**full_run), self.fake(load=4)[0])[1], 'hosted')
        finally:
            self.cr.SLOTS = old
        self.assertIn('NEED_WEB: ${{ steps.paths.outputs.web }}', self.jobs['changes'])
        self.assertIn('NEED_UI: ${{ steps.paths.outputs.ui }}', self.jobs['changes'])
        bs, us = self.jobs['backend-share'], self.jobs['ui-share']
        self.assertIn(f"share: [{', '.join(str(k) for k in range(1, self.cr.WEB_SHARES + 1))}]", bs)
        self.assertIn(f"share: [{', '.join(str(k) for k in range(1, self.cr.UI_SHARES + 1))}]", us)

    def test_the_watch_cancels_a_run_whose_msi_jobs_find_no_machine(self):
        calls = []
        state = {'status': 'queued'}

        def api(method, path, body=None):
            calls.append((method, path, body))
            if path.startswith('actions/runs/5/jobs'):
                return {'jobs': [{'name': 'ui 1/5', 'labels': ['self-hosted', 'msi'], 'status': state['status']}]}
            return {}
        env = self.env(GITHUB_EVENT_NAME='push', GITHUB_REF_NAME='main')
        state['status'] = 'in_progress'
        self.assertEqual(self.cr.watch(env, api, sleep=lambda s: None, minutes=0), 'every MSI job has a machine')
        state['status'] = 'queued'
        out = self.cr.watch(env, api, sleep=lambda s: None, minutes=0)
        self.assertIn('run cancelled', out)
        self.assertIn(('POST', 'actions/runs/5/cancel', None), calls)
        self.assertIn(('POST', 'actions/workflows/tests.yml/dispatches', {'ref': 'main'}), calls)  # main gets a new run
        calls.clear()
        self.cr.watch(self.env(), api, sleep=lambda s: None, minutes=0)  # a pull request: cancelled, not re-run
        self.assertEqual([c[1] for c in calls if c[0] == 'POST'], ['actions/runs/5/cancel'])

    def test_only_the_shares_can_go_to_the_msi_and_nothing_secret_goes_with_them(self):
        for job in ('backend-share', 'ui-share'):
            self.assertIn('runs-on: ${{ fromJSON(needs.changes.outputs.runner) }}', self.jobs[job], job)
            self.assertIn('echo "TMPDIR=$RUNNER_TEMP" >> "$GITHUB_ENV"', self.jobs[job], job)  # each runner its own temp
            self.assertIn("if: needs.changes.outputs.where == 'msi'", self.jobs[job])  # the MSI's own Python 3.11
        for job in ('changes', 'msi-watch', 'backend', 'ui', 'frontend'):
            self.assertIn('runs-on: ubuntu-24.04', self.jobs[job], job)
        self.assertIn('/tmp', self.jobs['ui-share'].replace('$RUNNER_TEMP/ui-out', '').replace('runner.temp }}/ui-out', '') + '/tmp')
        self.assertNotIn('--out /tmp/', self.wf)
        self.assertIn('MSI_RUNNER: ${{ vars.MSI_RUNNER }}', self.jobs['changes'])
        self.assertIn('HEAD_REPO: ${{ github.event.pull_request.head.repo.full_name }}', self.jobs['changes'])
        self.assertIn('\npermissions:\n  contents: read\n', self.wf)  # what a job on the MSI gets: read, nothing else
        for job in ('backend-share', 'ui-share'):
            self.assertNotIn('permissions:', self.jobs[job])
        for name in ('tests.yml', 'msi-probe.yml', 'msi-setup-check.yml'):
            self.assertNotIn('secrets.', (ROOT / '.github' / 'workflows' / name).read_text())
        probe = (ROOT / '.github' / 'workflows' / 'msi-probe.yml').read_text()
        self.assertIn('permissions: {}', probe); self.assertIn('cancel-in-progress: true', probe)
        self.assertIn('runs-on: [self-hosted, msi]', probe); self.assertNotIn('actions/checkout', probe)
        for name in ('beta.yml', 'monitor.yml', 'msi-setup-check.yml'):  # releases and checks never run on the MSI
            self.assertNotIn('self-hosted', (ROOT / '.github' / 'workflows' / name).read_text(), name)

    def test_the_setup_script_never_handles_a_token(self):
        sh = (ROOT / 'tools' / 'msi-setup.sh').read_text()
        self.assertEqual(subprocess.run(['bash', '-n', str(ROOT / 'tools' / 'msi-setup.sh')]).returncode, 0)
        self.assertNotIn('--token "$', sh.split('cat <<EOF', 1)[0])  # only in the commands it prints for the owner
        self.assertIn('read -rs -p "token: " T', sh)
        self.assertIn('RUNNERS=${RUNNERS:-6}', sh)
        self.assertIn('sha256sum -c', sh)
        self.assertNotIn('api.github.com', sh)  # unauthenticated API calls get 403 now and then (PR #128's first check)
        self.assertRegex(sh, r'RUNNER_SHA256=\$\{RUNNER_SHA256:-[0-9a-f]{64}\}')
        # a proxy from the shell reaches what does not read it: apt, sudo, the runners (systemd services)
        self.assertIn('PROXY=${https_proxy:-${HTTPS_PROXY:-}}', sh)
        self.assertIn('/etc/apt/apt.conf.d/95flow-proxy', sh)
        self.assertIn('Acquire::http::Proxy', sh); self.assertIn('Acquire::https::Proxy', sh)
        self.assertIn('psudo add-apt-repository', sh); self.assertNotIn('\n  sudo add-apt-repository', sh)
        self.assertIn("NO_PROXY_LIST=localhost,127.0.0.1,::1,100.64.0.0/10", sh)
        self.assertIn("grep -vE '^(https?_proxy|HTTPS?_PROXY|no_proxy|NO_PROXY)=' \"$d/.env\"", sh)
        self.assertIn('curl -sSI -m 20 -o /dev/null https://github.com', sh); self.assertIn('先开 v2rayN 的系统代理', sh)
        self.assertNotRegex(sh, r'(vmess|vless|trojan|ss)://')  # no node link, ever


class MsiRunTests(unittest.TestCase):
    """tools/msi-run.sh: the pre-push tests on the MSI from the Mac, without touching the checkout or blocking."""

    def test_it_never_waits_touches_the_checkout_or_keeps_a_slot(self):
        sh = (ROOT / 'tools' / 'msi-run.sh').read_text()
        self.assertEqual(subprocess.run(['bash', '-n', str(ROOT / 'tools' / 'msi-run.sh')]).returncode, 0)
        self.assertIn('BatchMode=yes', sh)  # no password or host-key question can hang a session
        self.assertNotRegex(sh, r'(^|[\s;(&|])ssh "\$HOST"')  # every ssh goes through the batch-mode options
        self.assertIn('exit 3', sh)  # the MSI unreachable, told apart from failing tests
        self.assertIn('GIT_INDEX_FILE=', sh)  # the snapshot is made in a throwaway index
        self.assertIn('nice -n 10', sh)  # CI's runners keep priority
        self.assertIn('</dev/null 9>&-', sh)  # the script on stdin is not eaten, the lock is not inherited
        for word in ('git stash', 'git checkout', 'git reset', 'sudo', 'secrets.'):
            self.assertNotIn(word, sh)


class BetaReleaseTests(unittest.TestCase):
    """.github/workflows/beta.yml releases each main commit that passed Tests to the 内测版, unless BETA_AUTO is off."""

    def setUp(self):
        self.wf = (ROOT / '.github' / 'workflows' / 'beta.yml').read_text(encoding='utf-8')
        self.jobs = dict(re.findall(r'^  ([a-z-]+):\n(.*?)(?=^  [a-z-]+:\n|\Z)', self.wf.split('\njobs:\n', 1)[1], re.S | re.M))

    def test_it_follows_main_after_tests_pass_unless_paused(self):
        tests_name = re.search(r'^name: (.+)$', (ROOT / '.github' / 'workflows' / 'tests.yml').read_text(), re.M).group(1)
        self.assertIn(f'workflow_run:\n    workflows: [{tests_name}]\n    types: [completed]\n    branches: [main]', self.wf)
        cond = self.jobs['release']
        for part in ("vars.BETA_AUTO != 'off'", "github.event.workflow_run.conclusion == 'success'",
                     "github.event.workflow_run.event == 'push'", "github.event_name == 'workflow_dispatch'",
                     "github.event.workflow_run.head_branch == 'main'"):
            self.assertIn(part, cond)
        self.assertIn('ref: ${{ github.event.workflow_run.head_sha', cond)  # the commit that passed, not main's newest
        # with the end-to-end test (never --no-e2e), the light one unless a Run workflow asks for the full one
        self.assertIn('bash tools/deploy.sh --beta $light "$(git rev-parse HEAD)"', cond)
        self.assertIn("E2E_MODE: ${{ inputs.e2e == 'full' && 'full' || 'light' }}", cond)
        self.assertIn('if [ "$E2E_MODE" = full ]; then light=""; else light="--light"; fi', cond)
        self.assertIn('options: [light, full]\n        default: light', self.wf)
        self.assertNotIn('--no-e2e', self.wf)
        self.assertIn('-r tools/requirements-release.txt', cond); self.assertIn('cache: pip', cond)  # Playwright, cached

    def test_only_the_release_job_may_push_and_releases_run_one_at_a_time(self):
        self.assertIn('\npermissions:\n  contents: read\n', self.wf)
        self.assertIn('permissions:\n      contents: write', self.jobs['release'])
        self.assertNotIn('contents: write', self.jobs['dry-run'])
        self.assertIn('group: beta-release\n      cancel-in-progress: false', self.jobs['release'])
        self.assertNotIn('secrets.', self.wf)  # nothing but the workflow's own token

    def test_the_guide_pdf_is_printed_with_a_chinese_font(self):
        for job in ('release', 'dry-run'):
            self.assertIn('fonts-noto-cjk', self.jobs[job], job)
        br = load('build_release')
        import zlib
        def pdf(name):
            body = zlib.compress(b'<< /Type /FontDescriptor /FontName /ABCDEF+' + name + b' >>')
            return b'%PDF-1.4\n1 0 obj << /Length 9 /Filter /FlateDecode >>\nstream\n' + body + b'\nendstream\n/BaseFont /GHIJKL+Helvetica\n'
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'g.pdf'
            f.write_bytes(pdf(b'NotoSansCJKsc-Regular'))
            self.assertEqual(br.pdf_fonts(f), ['Helvetica', 'NotoSansCJKsc-Regular'])
            self.assertTrue(any(c.lower() in n.lower() for n in br.pdf_fonts(f) for c in br.CHINESE_FONTS))
            f.write_bytes(pdf(b'DejaVuSans'))
            self.assertFalse(any(c.lower() in n.lower() for n in br.pdf_fonts(f) for c in br.CHINESE_FONTS))


class QuietBrowserTests(unittest.TestCase):
    """The owner's rule (2026-11-25): what runs in the background makes no sound. Every tool that starts a browser calls
    quiet.silent(pw) once: Chrome gets --mute-audio, and every context and page gets MUTE_JS (media and Web Audio at volume
    0, the browser voice at volume 0, which on a Mac is the system's speech and beyond --mute-audio)."""

    def test_every_tool_that_starts_a_browser_makes_it_silent(self):
        for path in sorted((ROOT / 'tools').glob('*.py')):
            text = path.read_text(encoding='utf-8')
            if path.name == 'quiet.py' or not re.search(r'\b(chromium|webkit|firefox)\.launch\(', text):
                continue
            self.assertIn('from quiet import silent', text, path.name)
            self.assertRegex(text, r'with sync_playwright\(\) as (\w+):\n\s+silent\(\1\)', path.name)

    def test_silent_mutes_chrome_and_every_context_and_page(self):
        quiet = load('quiet')
        js = quiet.MUTE_JS
        for part in ("addEventListener('play'", 'volume = 0', 'AudioDestinationNode', 'g.gain.value = 0', 'speechSynthesis.speak = u =>'):
            self.assertIn(part, js)
        self.assertNotIn('.muted', js)  # the app sets muted itself

        class Target:
            def __init__(self):
                self.scripts = []

            def add_init_script(self, script):
                self.scripts.append(script)

        class Browser:
            def new_context(self, **kw):
                return Target()

            def new_page(self, **kw):
                return Target()

        class BrowserType:
            def __init__(self):
                self.calls = []

            def launch(self, **kw):
                self.calls.append(kw)
                return Browser()

        class PW:
            chromium, webkit = BrowserType(), BrowserType()
        pw = PW()
        quiet.silent(pw); quiet.silent(pw)  # twice: wrapped once
        b = pw.chromium.launch(channel='chrome', args=['--use-fake-ui-for-media-stream', '--mute-audio'])
        self.assertEqual(pw.chromium.calls[-1]['args'], ['--mute-audio', '--use-fake-ui-for-media-stream'])
        pw.chromium.launch(channel='chrome')
        self.assertEqual(pw.chromium.calls[-1]['args'], ['--mute-audio'])
        self.assertEqual(b.new_context(locale='zh-CN').scripts, [js]); self.assertEqual(b.new_page().scripts, [js])
        w = pw.webkit.launch()
        self.assertNotIn('args', pw.webkit.calls[-1])  # WebKit has no --mute-audio: the script does it
        self.assertEqual(w.new_context().scripts, [js])


class MergeFriendlyListTests(unittest.TestCase):
    def test_the_upgrade_lists_are_one_name_per_line_and_sorted(self):
        script = (ROOT / 'flow' / 'upgrade.sh').read_text()
        lists = LISTS.findall(script)
        self.assertEqual(len(lists), 2)
        for block in lists:
            lines = block.splitlines()
            self.assertTrue(all(re.fullmatch(r'  [\w./-]+', line) for line in lines), lines[:3])
            names = [line.strip() for line in lines]
            self.assertEqual(names, sorted(set(names)), 'keep the lists in flow/upgrade.sh sorted, one name per line')
        self.assertIn('for name in "${FLOW_FILES[@]}"; do', script)
        self.assertIn('for name in "${FLOW_PUBLIC_FILES[@]}"; do', script)


class SettleMergeTests(unittest.TestCase):
    """A branch from before the change merges main: its edits to built files and to the lists are settled."""

    def git(self, *a, check=True):
        return subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', *a], cwd=self.repo,
                              capture_output=True, text=True, check=check).stdout

    def write(self, name, text):
        p = Path(self.repo) / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def test_built_files_and_both_sides_list_additions_are_settled(self):
        old_upgrade = ('set -e\nfor name in b.py d.py; do\n  install "$name"\ndone\nfor name in next.html next.js; do\n  install "$name"\ndone\n')
        with tempfile.TemporaryDirectory() as tmp:
            self.repo = tmp
            self.git('init', '-q', '-b', 'main')
            self.write('tools/release-files.txt', 'flow/d.py\nflow/b.py\nflow/public/next.js\n')
            self.write('flow/upgrade.sh', old_upgrade)
            self.write('flow/public/next.js', 'one\n')
            self.write('flow/public/guide/guide.md', 'text\n')
            self.git('add', '-A'); self.git('commit', '-qm', 'base')
            self.git('checkout', '-qb', 'feature')
            self.write('tools/release-files.txt', 'flow/d.py\nflow/b.py\nflow/c.py\nflow/public/next.js\n')
            self.write('flow/upgrade.sh', old_upgrade.replace('b.py d.py', 'b.py c.py d.py'))
            self.write('flow/public/next.js', 'two\n')
            self.git('commit', '-qam', 'feature adds c.py')
            self.git('checkout', '-q', 'main')
            self.write('tools/release-files.txt', 'flow/a.py\nflow/b.py\nflow/d.py\nflow/public/next.js\n')
            self.write('flow/upgrade.sh', 'set -e\n# sorted\nFLOW_FILES=(\n  a.py\n  b.py\n  d.py\n)\nfor name in "${FLOW_FILES[@]}"; do\n  install "$name"\ndone\n'
                       '# public\nFLOW_PUBLIC_FILES=(\n  next.html\n  next.js\n)\nfor name in "${FLOW_PUBLIC_FILES[@]}"; do\n  install "$name"\ndone\n')
            self.write('.gitignore', '/flow/public/next.js\n')
            self.git('rm', '-q', '--cached', 'flow/public/next.js'); self.git('add', '-A'); self.git('commit', '-qm', 'main: built at release, lists sorted')
            self.git('checkout', '-q', 'feature')
            self.git('merge', '-q', '--no-commit', '--no-ff', 'main', check=False)
            self.assertTrue(self.git('diff', '--name-only', '--diff-filter=U'))  # stopped on conflicts
            r = subprocess.run([sys.executable, str(ROOT / 'tools' / 'settle_merge.py')], cwd=tmp, capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            self.assertEqual(self.git('diff', '--name-only', '--diff-filter=U'), '')
            self.assertEqual((Path(tmp) / 'tools/release-files.txt').read_text(), 'flow/a.py\nflow/b.py\nflow/c.py\nflow/d.py\nflow/public/next.js\n')
            upgrade = (Path(tmp) / 'flow/upgrade.sh').read_text()
            self.assertEqual([b.split() for b in LISTS.findall(upgrade)], [['a.py', 'b.py', 'c.py', 'd.py'], ['next.html', 'next.js']])
            self.assertIn('# sorted\n', upgrade)
            self.assertNotIn('flow/public/next.js', self.git('ls-files'))
            self.assertTrue((Path(tmp) / 'flow/public/next.js').exists())  # the local copy stays, ignored


if __name__ == '__main__':
    unittest.main()
