#!/usr/bin/env python3
"""One-time setup of the 内测版 on the 香港 server (2026-11-24). flow.jasa.hk becomes a second Flow site with its own
data, where versions waiting for release run first; flowlang.cn and www.flowlang.cn stay 语流. Run as root on 香港:

    python3 beta_setup.py <commit> <manifest>            look, and say what would change (changes nothing)
    python3 beta_setup.py <commit> <manifest> --apply    do it
    python3 beta_setup.py --undo                         flow.jasa.hk back to 语流; the 内测版 stopped (files kept)

<commit> is the version the 内测版 starts with: a 40-hex commit on GitHub; tools/release_manifest.py <commit> prints
its <manifest>. Each step is skipped when it is already done, so running it again is safe.

1. /www/wwwroot/flow-beta: a copy of 语流's code, not its data (data/ starts empty; the site fills it on first start).
   Narration and word audio are read from 语流's folder (FLOW_AUDIO_DIR).
2. /etc/flow-beta.env: 语流's settings with FLOW_CHANNEL=beta, port 8092, no console port, its own data folder and
   FLOW_PUBLIC_URL=https://flow.jasa.hk (mode 600; only the names of the settings are printed, never their values).
3. flow-beta.service: 语流's unit and drop-ins with the paths changed; started, then checked on 127.0.0.1:8092.
4. <commit> installed on it with flow-pull.sh (every file checked against the manifest), and the 内测版's autodeploy:
   /root/claude-ops/beta and flow-autodeploy-beta.service/.timer, which take tags b<N> (tools/deploy.sh --beta).
5. nginx: a map sends flow.jasa.hk to 8092 and every other name to 8090, and the proxy_pass lines that went to 8090
   use it. Files are backed up first; if nginx -t fails, everything is put back.
6. /etc/flow.env: FLOW_PUBLIC_URL=https://flowlang.cn (the links in 语流's mail), and flow is restarted.
"""
import base64, glob, hashlib, json, os, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

PROD, BETA = Path('/www/wwwroot/flow'), Path('/www/wwwroot/flow-beta')
ENV, BENV = Path('/etc/flow.env'), Path('/etc/flow-beta.env')
UNITS = Path('/etc/systemd/system')
OPS = Path('/root/claude-ops')
VHOSTS = Path('/www/server/panel/vhost/nginx')
MAP = VHOSTS / '0-flow-channel.conf'
PORT, PROD_PORT = 8092, 8090
REPO = 'Jasame/Flow'
HOSTS = ['cdn.jsdelivr.net', 'fastly.jsdelivr.net', 'gcore.jsdelivr.net', 'testingcf.jsdelivr.net']
BETA_SITE = {'FLOW_DIR': str(BETA), 'FLOW_SERVICE': 'flow-beta', 'FLOW_URL': f'http://127.0.0.1:{PORT}', 'FLOW_XMC': '', 'FLOW_ADMIN_URL': ''}
PROXY = f'proxy_pass http://127.0.0.1:{PROD_PORT};'
MAP_TEXT = f"""# Written by tools/beta_setup.py (2026-11-24): flow.jasa.hk is the 内测版 (port {PORT}); every other name is 语流 ({PROD_PORT}).
map $host $flow_site {{
    default 127.0.0.1:{PROD_PORT};
    flow.jasa.hk 127.0.0.1:{PORT};
}}
"""


# ---------- the changes, as text (tests/test_channels.py runs these) ----------

def beta_env(text, audio_dir):
    """语流's settings for the 内测版: its own lines for these names, the rest as they are."""
    own = {'FLOW_CHANNEL': 'beta', 'FLOW_PORT': str(PORT), 'FLOW_ADMIN_PORT': '', 'FLOW_DATA_DIR': str(BETA / 'data'),
           'FLOW_PUBLIC_URL': 'https://flow.jasa.hk', 'FLOW_AUDIO_DIR': audio_dir, 'FLOW_SERVER_LABEL': '香港服务器 · 内测版'}
    keep = [l for l in text.splitlines() if l.split('=', 1)[0].strip() not in own]
    return '\n'.join(keep + ['', '# 内测版 (tools/beta_setup.py)'] + [f'{k}={v}' for k, v in own.items()]) + '\n'


def env_value(text, name):
    for l in text.splitlines():
        k, _, v = l.partition('=')
        if k.strip() == name:
            return v.strip().strip('"\'')
    return None


def with_public_url(text, url):
    lines = [l for l in text.splitlines() if l.split('=', 1)[0].strip() != 'FLOW_PUBLIC_URL']
    return '\n'.join(lines + [f'FLOW_PUBLIC_URL={url}']) + '\n'


def beta_unit(text):
    """语流's unit (or a drop-in) for the 内测版: its folder, its settings, its name."""
    text = re.sub(r'/www/wwwroot/flow(?=[/\s]|$)', str(BETA), text, flags=re.M)
    text = text.replace(str(ENV), str(BENV))
    return re.sub(r'^Description=.*$', 'Description=Flow 内测版 (flow.jasa.hk)', text, flags=re.M)


def beta_timer_unit(text):
    text = text.replace(str(OPS / 'flow-autodeploy.py'), str(OPS / 'beta' / 'flow-autodeploy.py') + ' --beta')
    text = text.replace(str(ENV), str(BENV))  # its end-to-end test runs with the 内测版's settings
    text = text.replace('flow-autodeploy.service', 'flow-autodeploy-beta.service')
    return re.sub(r'^Description=.*$', 'Description=Flow 内测版 autodeploy (tags b<N>)', text, flags=re.M)


def nginx_plan(files):
    """{path: text} of the vhost serving flow.jasa.hk and the files it includes -> ({path: new text}, problems).
    Only the exact line proxy_pass http://127.0.0.1:8090; is changed; anything else that would keep flow.jasa.hk on
    语流 (another form of proxy_pass to 8090, a redirect to flow.jasa.hk) is reported instead of guessed at."""
    new, problems = {}, []
    for path, text in files.items():
        for m in re.finditer(r'proxy_pass\s+[^;]*:%d[^;]*;' % PROD_PORT, text):
            if m.group(0) != PROXY:
                problems.append(f'{path}: {m.group(0)} (only "{PROXY}" can be switched by host)')
        for m in re.finditer(r'\b(return|rewrite)\s[^;]*flow\.jasa\.hk[^;]*;', text):
            problems.append(f'{path}: {m.group(0).strip()} (a redirect to flow.jasa.hk would send 语流 to the 内测版)')
        if PROXY in text:
            new[path] = text.replace(PROXY, 'proxy_pass http://$flow_site;  # tools/beta_setup.py: flow.jasa.hk -> 内测版')
    if not new:
        problems.append(f'no "{PROXY}" found: nothing to switch')
    return new, problems


# ---------- on the server ----------

def run(cmd, env=None, check=True):
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, env=env)
    if check and r.returncode:
        raise SystemExit(f'failed: {cmd}\n{r.stdout[-800:]}{r.stderr[-800:]}')
    return r


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'flow-beta-setup/1'}), timeout=45) as r:
        return r.read()


def verified_tool(sha, path, flat):
    want = flat[path]
    for h in HOSTS:
        try:
            data = fetch(f'https://{h}/gh/{REPO}@{sha}/{path}')
        except Exception:
            continue
        if len(data) == want['size'] and base64.b64encode(hashlib.sha256(data).digest()).decode() == want['hash']:
            return data
    raise SystemExit(f'{path}: no mirror gave the file as listed for {sha[:12]}')


def health(port, tries=20):
    for _ in range(tries):
        try:
            return json.loads(fetch(f'http://127.0.0.1:{port}/api/health'))
        except Exception:
            time.sleep(1.5)
    return None


def nginx_bin():
    return shutil.which('nginx') or '/www/server/nginx/sbin/nginx'


def vhost_files():
    """The vhost that names flow.jasa.hk, and the files it includes."""
    hits = [p for p in sorted(VHOSTS.glob('*.conf')) if re.search(r'server_name[^;]*\bflow\.jasa\.hk\b', p.read_text(errors='replace'))]
    if len(hits) != 1:
        raise SystemExit(f'expected one vhost naming flow.jasa.hk, found {[str(p) for p in hits]}')
    files = {str(hits[0]): hits[0].read_text()}
    for inc in re.findall(r'^\s*include\s+([^;]+);', files[str(hits[0])], re.M):
        for f in sorted(glob.glob(inc.strip())):
            files[f] = Path(f).read_text(errors='replace')
    return files


def main():
    apply, undo = '--apply' in sys.argv, '--undo' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if os.geteuid() != 0:
        raise SystemExit('run as root on 香港')
    if undo:
        return do_undo()
    if len(args) != 2 or not re.fullmatch(r'[0-9a-f]{40}', args[0]) or not re.fullmatch(r'[0-9a-f]{64}', args[1]):
        raise SystemExit(__doc__)
    sha, manifest = args
    say = print
    say(f'== 内测版 setup {"(applying)" if apply else "(looking only; add --apply to change)"}; start with {sha[:12]}')
    backup = OPS / ('beta-setup-' + time.strftime('%Y%m%d-%H%M%S'))

    # 1. code
    if (BETA / 'app.py').exists():
        say(f'1. {BETA}: there already')
    else:
        say(f'1. copy 语流\'s code to {BETA} (not data/, not audio/)')
        if apply:
            shutil.copytree(PROD, BETA, symlinks=True, ignore=lambda d, names: [n for n in names if Path(d) == PROD and n in ('data', 'audio', '.venv')] + [n for n in names if n == '__pycache__'])
    if apply:
        (BETA / 'data').mkdir(mode=0o700, exist_ok=True)
        shutil.chown(BETA / 'data', 'www', 'www')

    # 2. settings
    prod_env = ENV.read_text()
    audio = env_value(prod_env, 'FLOW_AUDIO_DIR') or str(PROD / 'audio')
    if BENV.exists():
        say(f'2. {BENV}: there already')
    else:
        text = beta_env(prod_env, audio)
        say(f'2. write {BENV} with: ' + ', '.join(sorted({l.split("=", 1)[0] for l in text.splitlines() if '=' in l and not l.startswith('#')})))
        if apply:
            BENV.write_text(text); BENV.chmod(0o600)

    # 3. the service
    unit = UNITS / 'flow-beta.service'
    if unit.exists():
        say(f'3. {unit}: there already')
    else:
        say(f'3. {unit} from flow.service (+ drop-ins), then start it on {PORT}')
        if apply:
            unit.write_text(beta_unit((UNITS / 'flow.service').read_text()))
            for d in sorted((UNITS / 'flow.service.d').glob('*.conf')) if (UNITS / 'flow.service.d').is_dir() else []:
                (UNITS / 'flow-beta.service.d').mkdir(exist_ok=True)
                (UNITS / 'flow-beta.service.d' / d.name).write_text(beta_unit(d.read_text()))
            for path in re.findall(r'^ReadWritePaths=(.+)$', unit.read_text(), re.M):  # what the unit may write must exist
                for one in path.split():
                    if one.lstrip('-').startswith(str(BETA)):
                        Path(one.lstrip('-')).mkdir(parents=True, exist_ok=True)
            run('systemctl daemon-reload')
    if apply:
        run('systemctl enable --now flow-beta')
        h = health(PORT)
        if not h:
            raise SystemExit('flow-beta did not answer on 8092: journalctl -u flow-beta -n 50')
        say(f'   flow-beta answers: {h}')

    # 4. the version to start with, and the 内测版's autodeploy
    home = OPS / 'beta'
    say(f'4. install {sha[:12]} on the 内测版 with flow-pull.sh; autodeploy from {home} (tags b<N>)')
    if apply:
        flat = {f['name'].lstrip('/'): f for f in json.loads(fetch(f'https://data.jsdelivr.com/v1/package/gh/{REPO}@{sha}/flat'))['files']}
        home.mkdir(parents=True, exist_ok=True)
        for name in ('flow-pull.sh', 'flow-pull-rollback.sh', 'flow-autodeploy.py', 'qa_e2e.py'):
            (home / name).write_bytes(verified_tool(sha, f'tools/{name}', flat))
        r = run(['bash', str(home / 'flow-pull.sh'), sha, manifest], env={**os.environ, **BETA_SITE}, check=False)
        result = (re.findall(r'^RESULT=(\w+)', r.stdout, re.M) or ['?'])[-1]
        say(f'   flow-pull: {result}')
        if result not in ('DEPLOYED', 'NOTHING_TO_DO'):
            raise SystemExit(r.stdout[-1500:])
        for name, make in (('flow-autodeploy-beta.service', 'flow-autodeploy.service'), ('flow-autodeploy-beta.timer', 'flow-autodeploy.timer')):
            if not (UNITS / name).exists():
                (UNITS / name).write_text(beta_timer_unit((UNITS / make).read_text()))
        ad = OPS / 'autodeploy-beta'; ad.mkdir(parents=True, exist_ok=True)
        if not (ad / 'next').exists():
            (ad / 'next').write_text('1')
        run('systemctl daemon-reload && systemctl enable --now flow-autodeploy-beta.timer')
        h = health(PORT)
        if not h or h.get('channel') != 'beta':
            raise SystemExit(f'the 内测版 does not say it is one: {h}')

    # 5. nginx
    files = vhost_files()
    if MAP.exists() and not any(PROXY in t for t in files.values()):
        say('5. nginx: switched already')
    else:
        new, problems = nginx_plan(files)
        for p in problems:
            say(f'5. STOP: {p}')
        if problems:
            raise SystemExit('nginx was not changed: look at the lines above')
        say(f'5. nginx: add {MAP}; switch by host in {", ".join(new)}')
        if apply:
            backup.mkdir(parents=True)
            for path in new:
                shutil.copy2(path, backup / Path(path).name)
            (backup / 'files.json').write_text(json.dumps(list(new)))
            MAP.write_text(MAP_TEXT)
            for path, text in new.items():
                Path(path).write_text(text)
            t = run([nginx_bin(), '-t'], check=False)
            if t.returncode:
                for path in new:
                    shutil.copy2(backup / Path(path).name, path)
                MAP.unlink()
                raise SystemExit('nginx -t failed, everything put back:\n' + t.stderr[-1200:])
            run([nginx_bin(), '-s', 'reload'])

    # 6. 语流's public address
    if env_value(prod_env, 'FLOW_PUBLIC_URL') == 'https://flowlang.cn':
        say('6. /etc/flow.env: FLOW_PUBLIC_URL is flowlang.cn already')
    else:
        say('6. /etc/flow.env: FLOW_PUBLIC_URL=https://flowlang.cn, then restart flow')
        if apply:
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ENV, backup / 'flow.env'); (backup / 'flow.env').chmod(0o600)
            ENV.write_text(with_public_url(prod_env, 'https://flowlang.cn'))
            run('systemctl restart flow')
            if not health(PROD_PORT):
                raise SystemExit('flow did not come back: journalctl -u flow -n 50')

    if apply:
        for host, want in (('flow.jasa.hk', 'beta'), ('flowlang.cn', None)):
            r = run(['curl', '-s', '-m', '15', '--resolve', f'{host}:443:127.0.0.1', f'https://{host}/api/health'], check=False)
            say(f'== {host}: {r.stdout.strip()[:200]}')
        say(f'== done; backups in {backup}')


def do_undo():
    """flow.jasa.hk back to 语流: nginx from the newest backup, the map removed; the 内测版 and its timer stopped."""
    backups = sorted(OPS.glob('beta-setup-*/files.json'))
    if backups:
        b = backups[-1].parent
        for path in json.loads(backups[-1].read_text()):
            shutil.copy2(b / Path(path).name, path)
    if MAP.exists():
        MAP.unlink()
    t = run([nginx_bin(), '-t'], check=False)
    if t.returncode:
        raise SystemExit('nginx -t failed after undo:\n' + t.stderr[-1200:])
    run([nginx_bin(), '-s', 'reload'])
    run('systemctl disable --now flow-autodeploy-beta.timer flow-beta', check=False)
    print('undone: flow.jasa.hk goes to 语流 again; flow-beta stopped; /www/wwwroot/flow-beta and /etc/flow-beta.env kept')


if __name__ == '__main__':
    main()
