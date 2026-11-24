#!/usr/bin/env python3
"""Push-to-deploy for the Flow server, run every minute by flow-autodeploy.timer.

A release is a git tag r<N> on GitHub whose REQUEST file reads "<commit sha> <manifest sha256> [e2e [light]]"
(tools/deploy.sh writes and pushes it). The server cannot reach GitHub, only jsDelivr, and jsDelivr caches
branch heads for hours, but a tag it has never seen resolves fresh. So the server only ever asks for the next
tag number: it handles r<N> once, then waits for r<N+1>.

For each request it
1. takes flow-pull.sh, its rollback script, this script and the end-to-end test from that commit, each checked
   against the sha256 in jsDelivr's listing of the commit;
2. runs flow-pull.sh (every release file checked against its sha256 and the manifest; backup; health checks;
   automatic rollback);
3. if asked ("e2e") and the deploy held, runs tools/qa_e2e.py: internal test accounts, real AI, cleaned up after
   ("e2e light": QA_LIGHT=1, no recordings sent to the AI; the automatic 内测版 releases ask for that);
4. writes the outcome to data/deploy-status.json, which the app serves at /api/deploy-status
   (tag, commit, result, health checks, test counts and the names of failed checks; nothing else).

Once a day (04:00–05:00 server time, when no release is waiting) it also runs the end-to-end test against what is
deployed, from the copy kept by the last release that ran it, and writes data/e2e-daily.json (shown as "daily" in
/api/deploy-status, which the GitHub monitor checks).

With --beta it does the same for the 内测版 (flow.jasa.hk: /www/wwwroot/flow-beta, its own data, service flow-beta
on port 8092, no console files): tags b<N>, its own state in /root/claude-ops/autodeploy-beta, its own copies of these
tools in /root/claude-ops/beta (a version on trial never replaces the ones 语流's releases run with), no daily run.
"""
import base64, datetime, fcntl, hashlib, json, os, re, shutil, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

REPO = 'Jasame/Flow'
OPS = Path('/root/claude-ops')
BETA = '--beta' in sys.argv[1:]
SITE = {  # where each site lives on the server; flow-pull.sh and qa_e2e.py read the same names
    False: {'prefix': 'r', 'ad': OPS / 'autodeploy', 'home': OPS, 'data': Path('/www/wwwroot/flow/data'), 'env': {}},
    True: {'prefix': 'b', 'ad': OPS / 'autodeploy-beta', 'home': OPS / 'beta', 'data': Path('/www/wwwroot/flow-beta/data'),
           'env': {'FLOW_DIR': '/www/wwwroot/flow-beta', 'FLOW_SERVICE': 'flow-beta', 'FLOW_URL': 'http://127.0.0.1:8092',
                   'FLOW_XMC': '', 'FLOW_ADMIN_URL': '', 'QA_BASE': 'http://127.0.0.1:8092', 'QA_DB': '/www/wwwroot/flow-beta/data/flow.sqlite3'}},
}[BETA]
AD = SITE['ad']
STATUS = SITE['data'] / 'deploy-status.json'
ENV = {**os.environ, **SITE['env']}
HOSTS = ['cdn.jsdelivr.net', 'fastly.jsdelivr.net', 'gcore.jsdelivr.net', 'testingcf.jsdelivr.net']
TOOLS = ['tools/flow-pull.sh', 'tools/flow-pull-rollback.sh', 'tools/flow-autodeploy.py', 'tools/qa_e2e.py']
AUDIO = 'tools/qa-audio/'
DAILY = AD / 'daily'  # the end-to-end test and its clips, kept from the last release that ran it
DAILY_STATUS = Path('/www/wwwroot/flow/data/e2e-daily.json')
DAILY_HOUR = 4


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


def fetch(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'flow-autodeploy/1'}), timeout=timeout) as r:
        return r.read()


def request_for(tag):
    """The tag's REQUEST text; None when no mirror has the tag (yet); raises when no mirror could be asked."""
    missing, errors = 0, []
    for h in HOSTS:
        try:
            return fetch(f'https://{h}/gh/{REPO}@{tag}/REQUEST', 20).decode('utf-8', 'replace')
        except urllib.error.HTTPError as e:
            if e.code == 404:
                missing += 1
            else:
                errors.append(e)
        except Exception as e:
            errors.append(e)
    if missing:
        return None
    raise RuntimeError(f'no mirror answered: {errors[-1]!r}')


def listing(sha):
    last = None
    for k in range(5):
        try:
            return {f['name'].lstrip('/'): f for f in json.loads(fetch(f'https://data.jsdelivr.com/v1/package/gh/{REPO}@{sha}/flat'))['files']}
        except Exception as e:
            last = e
            time.sleep(2 + 3 * k)
    raise RuntimeError(f'listing: {last!r}')


def verified(sha, path, flat):
    want = flat[path]
    last = None
    for k in range(3):
        for h in HOSTS:
            try:
                data = fetch(f'https://{h}/gh/{REPO}@{sha}/{path}')
            except Exception as e:
                last = e
                continue
            if len(data) == want['size'] and base64.b64encode(hashlib.sha256(data).digest()).decode() == want['hash']:
                return data
            last = RuntimeError(f'{path}: content does not match the listing')
        time.sleep(2 + 3 * k)
    raise RuntimeError(f'{path}: {last!r}')


def short(detail, n=160):
    """A failed check's detail on one line, at most n characters: its start (the status, the error the app sent) and its
    end (the last line of a traceback)."""
    text = ' '.join(str(detail).split())
    return text if len(text) <= n else text[:n - 50] + ' … ' + text[-47:]


def e2e_summary(work):
    try:
        r = json.loads((work / 'report.json').read_text())
        return {'checks': r['checks']['total'], 'failed': r['checks']['failed'], 'failed_names': [f['who'] + ': ' + f['name'] for f in r['failed']][:40],
                # why each failed, short (the status code, the error the app sent): readable in /api/deploy-status and in
                # the release's Actions log, so a failure needs no look at the server (b12's two failures did, 2026-11-25).
                # Test accounts only, and their rows are gone by now.
                'failed_details': [f"{f['who']}: {f['name']}: {short(f.get('detail', ''))}" for f in r['failed']][:10],
                'light': bool(r.get('light')),
                'server_errors': len(r['server_errors']), 'ai_calls': r['ai_calls_used'], 'seconds': r['seconds'],
                'cleanup_ok': not any(f['who'] == 'cleanup' for f in r['failed'])}
    except (OSError, ValueError, KeyError) as e:
        return {'error': 'no report: ' + str(e)[:200]}


def run_e2e(work, log, light=False):
    with log.open('w') as out:
        try:
            subprocess.run([sys.executable, '-I', str(work / 'qa_e2e.py')], cwd=work, env={**ENV, **({'QA_LIGHT': '1'} if light else {})},
                           stdout=out, stderr=subprocess.STDOUT, timeout=1500)
        except subprocess.TimeoutExpired:
            pass
    return e2e_summary(work)


def daily():
    """The once-a-day end-to-end run against what is deployed (语流 only)."""
    if BETA or time.localtime().tm_hour != DAILY_HOUR:
        return
    src = DAILY if (DAILY / 'qa_e2e.py').exists() else next(  # before any release kept a copy: the newest one that ran it
        (d for d in sorted(AD.glob('r*'), key=lambda d: d.stat().st_mtime, reverse=True)
         if (d / 'qa_e2e.py').exists() and (d / 'qa-audio').is_dir() and any((d / 'qa-audio').iterdir())), None)
    if src is None:
        return
    today = time.strftime('%Y-%m-%d')
    try:
        if json.loads(DAILY_STATUS.read_text()).get('day') == today:
            return
    except (OSError, ValueError):
        pass
    commit = (OPS / 'flow-deployed-commit').read_text().strip() if (OPS / 'flow-deployed-commit').exists() else ''
    st = {'day': today, 'started': now(), 'commit': commit, **run_e2e(src, src / 'e2e.log'), 'finished': now()}
    tmp = DAILY_STATUS.with_suffix('.tmp')
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1)); tmp.chmod(0o644); tmp.replace(DAILY_STATUS)


def write_status(d):
    tmp = STATUS.with_suffix('.tmp')
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1))
    tmp.chmod(0o644)
    tmp.replace(STATUS)


def main():
    AD.mkdir(parents=True, exist_ok=True)
    lock = open(AD / 'lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    n = int((AD / 'next').read_text().strip()) if (AD / 'next').exists() else 1
    tag = f"{SITE['prefix']}{n}"
    try:
        req = request_for(tag)
    except Exception:
        return  # network trouble: ask again next minute
    if req is None:
        daily()
        return
    (AD / 'next').write_text(str(n + 1))  # each tag is handled once, even if this run fails
    words = (req.strip().splitlines() or [''])[0].split()
    st = {'tag': tag, 'state': 'running', 'started': now()}
    if not words or words[0] == 'noop':
        write_status({**st, 'state': 'done', 'result': 'NOOP', 'finished': now()})
        return
    sha, manifest = words[0], words[1] if len(words) > 1 else ''
    if not re.fullmatch(r'[0-9a-f]{40}', sha) or not re.fullmatch(r'[0-9a-f]{64}', manifest):
        write_status({**st, 'state': 'done', 'result': 'BAD_REQUEST', 'finished': now()})
        return
    e2e = 'e2e' in words[2:]
    light = e2e and 'light' in words[2:]  # no recordings sent to the AI (tools/qa_e2e.py QA_LIGHT)
    st.update(commit=sha, e2e_requested=e2e, **({'e2e_light': True} if light else {}))
    write_status(st)
    work = AD / tag
    shutil.rmtree(work, ignore_errors=True)
    (work / 'qa-audio').mkdir(parents=True)
    try:
        flat = listing(sha)
        for p in TOOLS + sorted(x for x in flat if e2e and x.startswith(AUDIO)):
            if p in flat:
                (work / (('qa-audio/' if p.startswith(AUDIO) else '') + Path(p).name)).write_bytes(verified(sha, p, flat))
    except Exception as e:
        write_status({**st, 'state': 'done', 'result': 'ABORT_FETCH', 'error': str(e)[:300], 'finished': now()})
        return
    if BETA and b'F=${FLOW_DIR:-' not in (work / 'flow-pull.sh').read_bytes():
        # a commit from before the two sites: its flow-pull.sh knows only 语流's folder and service
        write_status({**st, 'state': 'done', 'result': 'ABORT_OLD_TOOLS', 'error': 'this commit cannot be installed on the 内测版: merge main into it first', 'finished': now()})
        return
    log = work / 'deploy.log'
    with log.open('w') as out:
        try:
            subprocess.run(['bash', str(work / 'flow-pull.sh'), sha, manifest], env=ENV, stdout=out, stderr=subprocess.STDOUT, timeout=1800)
        except subprocess.TimeoutExpired:
            pass
    text = log.read_text(errors='replace')
    results = re.findall(r'^RESULT=(\w+)', text, re.M)
    st['result'] = results[-1] if results else ('ABORT_FETCH' if 'ABORT' in text else 'UNKNOWN')
    st['checks'] = next((l.strip() for l in text.splitlines() if l.startswith('flow: active=')), '')
    st['files'] = next((l.strip() for l in text.splitlines() if 'files to install' in l), '')
    st['manifest_ok'] = 'manifest mismatch' not in text
    write_status(st)
    if st['result'] in ('DEPLOYED', 'NOTHING_TO_DO'):
        # keep the server's copies of the tools in step with what was just deployed (the 内测版 keeps its own)
        SITE['home'].mkdir(parents=True, exist_ok=True)
        for name in ('flow-pull.sh', 'flow-pull-rollback.sh', 'flow-autodeploy.py'):
            if (work / name).exists():
                shutil.copy2(work / name, SITE['home'] / name)
    if e2e and st['result'] in ('DEPLOYED', 'NOTHING_TO_DO') and (work / 'qa_e2e.py').exists():
        st['state'] = 'testing'
        write_status(st)
        st['e2e'] = run_e2e(work, work / 'e2e.log', light)
        if not BETA and (work / 'qa-audio').is_dir() and any((work / 'qa-audio').iterdir()):  # keep this release's test for the daily run
            shutil.rmtree(DAILY, ignore_errors=True)
            DAILY.mkdir(parents=True)
            shutil.copy2(work / 'qa_e2e.py', DAILY / 'qa_e2e.py')
            shutil.copytree(work / 'qa-audio', DAILY / 'qa-audio')
    st.update(state='done', finished=now())
    write_status(st)


if __name__ == '__main__':
    main()
