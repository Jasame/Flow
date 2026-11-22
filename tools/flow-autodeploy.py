#!/usr/bin/env python3
"""Push-to-deploy for the Flow server, run every minute by flow-autodeploy.timer.

A release is a git tag r<N> on GitHub whose REQUEST file reads "<commit sha> <manifest sha256> [e2e]"
(tools/deploy.sh writes and pushes it). The server cannot reach GitHub, only jsDelivr, and jsDelivr caches
branch heads for hours, but a tag it has never seen resolves fresh. So the server only ever asks for the next
tag number: it handles r<N> once, then waits for r<N+1>.

For each request it
1. takes flow-pull.sh, its rollback script, this script and the end-to-end test from that commit, each checked
   against the sha256 in jsDelivr's listing of the commit;
2. runs flow-pull.sh (every release file checked against its sha256 and the manifest; backup; health checks;
   automatic rollback);
3. if asked ("e2e") and the deploy held, runs tools/qa_e2e.py: internal test accounts, real AI, cleaned up after;
4. writes the outcome to data/deploy-status.json, which the app serves at /api/deploy-status
   (tag, commit, result, health checks, test counts and the names of failed checks; nothing else).
"""
import base64, datetime, fcntl, hashlib, json, re, shutil, subprocess, sys, time, urllib.error, urllib.request
from pathlib import Path

REPO = 'Jasame/Flow'
OPS = Path('/root/claude-ops')
AD = OPS / 'autodeploy'
STATUS = Path('/www/wwwroot/flow/data/deploy-status.json')
HOSTS = ['cdn.jsdelivr.net', 'fastly.jsdelivr.net', 'gcore.jsdelivr.net', 'testingcf.jsdelivr.net']
TOOLS = ['tools/flow-pull.sh', 'tools/flow-pull-rollback.sh', 'tools/flow-autodeploy.py', 'tools/qa_e2e.py']
AUDIO = 'tools/qa-audio/'


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
    tag = f'r{n}'
    try:
        req = request_for(tag)
    except Exception:
        return  # network trouble: ask again next minute
    if req is None:
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
    st.update(commit=sha, e2e_requested=e2e)
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
    log = work / 'deploy.log'
    with log.open('w') as out:
        try:
            subprocess.run(['bash', str(work / 'flow-pull.sh'), sha, manifest], stdout=out, stderr=subprocess.STDOUT, timeout=1800)
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
        # keep the server's copies of the tools in step with what was just deployed
        for name in ('flow-pull.sh', 'flow-pull-rollback.sh', 'flow-autodeploy.py'):
            if (work / name).exists():
                shutil.copy2(work / name, OPS / name)
    if e2e and st['result'] in ('DEPLOYED', 'NOTHING_TO_DO') and (work / 'qa_e2e.py').exists():
        st['state'] = 'testing'
        write_status(st)
        with (work / 'e2e.log').open('w') as out:
            try:
                subprocess.run([sys.executable, '-I', str(work / 'qa_e2e.py')], cwd=work, stdout=out, stderr=subprocess.STDOUT, timeout=1500)
            except subprocess.TimeoutExpired:
                pass
        try:
            r = json.loads((work / 'report.json').read_text())
            st['e2e'] = {'checks': r['checks']['total'], 'failed': r['checks']['failed'], 'failed_names': [f['who'] + ': ' + f['name'] for f in r['failed']][:40],
                         'server_errors': len(r['server_errors']), 'ai_calls': r['ai_calls_used'], 'seconds': r['seconds'],
                         'cleanup_ok': not any(f['who'] == 'cleanup' for f in r['failed'])}
        except (OSError, ValueError, KeyError) as e:
            st['e2e'] = {'error': 'no report: ' + str(e)[:200]}
    st.update(state='done', finished=now())
    write_status(st)


if __name__ == '__main__':
    main()
