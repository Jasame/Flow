#!/usr/bin/env python3
"""Push-to-deploy for the Flow server, run every minute by flow-autodeploy.timer.

A release is a git tag r<N> on GitHub whose REQUEST file reads "<commit sha> <manifest sha256> [e2e [light]] [ref=<tag>]
tag=<tag> tools=<sha256 of TOOLS>", with TOOLS (what the server runs from the release, as "<base64 sha256>  <path>"
lines) and REQUEST.sig (`ssh-keygen -Y sign` over REQUEST) beside it; tools/deploy.sh writes and pushes them. The server
cannot reach GitHub, only jsDelivr, and jsDelivr caches branch heads for hours, but a tag it has never seen resolves
fresh. So the server only ever asks for the next tag number: it handles r<N> once, then waits for r<N+1>.

For each request it
0. checks the request (发版请求签名校验), once this site's key is in /etc/flow-release/allowed_signers (one line per
   key, `flow-release namespaces="flow-release" ssh-ed25519 …` for 语流, `flow-beta-release …` for the 内测版; both
   sites read the one file, so each is switched on by its own line). REQUEST.sig must be a signature of REQUEST by that
   key in that namespace (ssh-keygen -Y verify); REQUEST must name this tag (tag=) and a number above the last release
   installed here (the same number again: installed already, nothing to do); TOOLS must be the list REQUEST names
   (tools=) and have every tool below. Otherwise BAD_SIGNATURE, and nothing is taken from the commit. A missing or bad
   signature alone goes through while /etc/flow-release/unsigned-until holds a Unix time at most 24 hours ahead (root's
   emergency switch): signature UNSIGNED_ALLOWED in the status, and a mail to the console's 管理员. No line for this
   site (or no file): as before, nothing checked, and the journal says 本站没开签名校验. Taking the feature back is
   deleting the site's line, or the file;
1. takes flow-pull.sh, its rollback script, this script and the end-to-end test from that commit, each checked
   against its line in the signed TOOLS (without signatures: against the sha256 in jsDelivr's listing of the commit);
2. runs flow-pull.sh (every release file checked against its sha256 and the manifest; backup; health checks;
   automatic rollback); only then are its copies of these tools on the server (this script among them) replaced by
   the ones just checked;
3. if asked ("e2e") and the deploy held, runs tools/qa_e2e.py: internal test accounts, real AI, cleaned up after
   ("e2e light": QA_LIGHT=1, no recordings sent to the AI; the automatic 内测版 releases ask for that);
4. writes the outcome to data/deploy-status.json, which the app serves at /api/deploy-status
   (tag, commit, result, the signature check's outcome, health checks, test counts and the names of failed checks;
   nothing else).

Once a day (04:00–05:00 server time, when no release is waiting) it also runs the end-to-end test against what is
deployed, from the copy kept by the last release that ran it, and writes data/e2e-daily.json (shown as "daily" in
/api/deploy-status, which the GitHub monitor checks).

With --beta it does the same for the 内测版 (flow.jasa.hk: /www/wwwroot/flow-beta, its own data, service flow-beta
on port 8092, its console at xmc.hk/flow-beta on admin port 8093): tags b<N>, its own state in /root/claude-ops/autodeploy-beta, its own copies of these
tools in /root/claude-ops/beta (a version on trial never replaces the ones 语流's releases run with), no daily run.
"""
import base64, datetime, fcntl, fnmatch, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time, urllib.error, urllib.request
from pathlib import Path

REPO = 'Jasame/Flow'
OPS = Path('/root/claude-ops')
BETA = '--beta' in sys.argv[1:]
SITE = {  # where each site lives on the server; flow-pull.sh and qa_e2e.py read the same names
    # signer: the name of the site's signing key in SIGNERS, which is also the namespace its signatures are made in
    False: {'prefix': 'r', 'ad': OPS / 'autodeploy', 'home': OPS, 'data': Path('/www/wwwroot/flow/data'), 'env': {},
            'signer': 'flow-release', 'name': '语流', 'url': 'https://flowlang.cn'},
    True: {'prefix': 'b', 'ad': OPS / 'autodeploy-beta', 'home': OPS / 'beta', 'data': Path('/www/wwwroot/flow-beta/data'),
           'env': {'FLOW_DIR': '/www/wwwroot/flow-beta', 'FLOW_SERVICE': 'flow-beta', 'FLOW_URL': 'http://127.0.0.1:8092',
                   'FLOW_XMC': '/www/wwwroot/xmc.hk/flow-beta', 'FLOW_ADMIN_URL': 'http://127.0.0.1:8093', 'QA_BASE': 'http://127.0.0.1:8092', 'QA_DB': '/www/wwwroot/flow-beta/data/flow.sqlite3'},
           'signer': 'flow-beta-release', 'name': '内测版', 'url': 'https://flow.jasa.hk'},
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
SIGNERS = Path('/etc/flow-release/allowed_signers')  # root's (644): whose signatures each site takes (0. above)
UNSIGNED_UNTIL = Path('/etc/flow-release/unsigned-until')  # root's emergency switch: a Unix time, at most UNSIGNED_MAX ahead
UNSIGNED_MAX = 24 * 3600


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec='seconds')


def stamp(t):
    return datetime.datetime.fromtimestamp(t).astimezone().isoformat(timespec='minutes')


def journal(text):
    """A line in the journal (journalctl -u flow-autodeploy, or flow-autodeploy-beta)."""
    print(f"{SITE['name']} {text}", flush=True)


def fetch(url, timeout=40):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'flow-autodeploy/1'}), timeout=timeout) as r:
        return r.read()


def tag_file(tag, name):
    """A file of the tag's request (REQUEST, REQUEST.sig, TOOLS) as it is; None when no mirror has it; raises when no
    mirror could be asked."""
    missing, errors = 0, []
    for h in HOSTS:
        try:
            return fetch(f'https://{h}/gh/{REPO}@{tag}/{name}', 20)
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


def request_for(tag):
    """The tag's REQUEST text; None when no mirror has the tag (yet); raises when no mirror could be asked."""
    data = tag_file(tag, 'REQUEST')
    return None if data is None else data.decode('utf-8', 'replace')


class Stop(Exception):
    """A request that ends before anything is taken from its commit: the result to report (BAD_SIGNATURE, or
    NOTHING_TO_DO for a release installed already) and why."""

    def __init__(self, result, why):
        super().__init__(why)
        self.result = result


def signing_on():
    """Whether this site checks signatures: SIGNERS has a line for its key (the line's first word, comma-separated
    patterns as ssh-keygen reads them). Both sites read the one file, so the 内测版's line can go in first and 语流 keeps
    going as before until its own line is there. A file that is there but cannot be read counts as on: its check fails."""
    try:
        text = SIGNERS.read_text(encoding='utf-8', errors='replace')
    except FileNotFoundError:
        return False
    except OSError:
        return True
    for line in text.splitlines():
        words = line.split()
        if words and not words[0].startswith('#') and any(
                fnmatch.fnmatchcase(SITE['signer'], p) for p in words[0].split(',') if p and not p.startswith('!')):
            return True
    return False


def signature_problem(request, sig):
    """'' when `sig` is a good signature of `request` (REQUEST's bytes) by this site's key in this site's namespace
    (ssh-keygen -Y verify against SIGNERS), else why not."""
    if not sig:
        return 'REQUEST.sig missing'
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / 'REQUEST.sig').write_bytes(sig)
        try:
            r = subprocess.run(['ssh-keygen', '-Y', 'verify', '-f', str(SIGNERS), '-I', SITE['signer'], '-n', SITE['signer'],
                                '-s', str(Path(d) / 'REQUEST.sig')], input=request, capture_output=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            return f'ssh-keygen did not run: {type(e).__name__}'
    if r.returncode == 0:
        return ''
    said = [l.strip() for l in (r.stderr + r.stdout).decode('utf-8', 'replace').splitlines() if l.strip()]
    # ssh-keygen ends every refusal with this line; the one before it says why (namespace, signature, format)
    why = next((l for l in said if l != 'Could not verify signature.'), said[0] if said else f'exit {r.returncode}')
    return f'signature does not verify: {why[:160]}'


def unsigned_until(at):
    """The end of the emergency window: UNSIGNED_UNTIL's Unix time when it is after `at` and at most UNSIGNED_MAX
    ahead. A file that is there but expired, too far ahead or not a time counts as none, and the journal says so."""
    try:
        text = UNSIGNED_UNTIL.read_text().strip()
    except FileNotFoundError:
        return None
    except OSError as e:
        journal(f'{UNSIGNED_UNTIL}: unreadable ({type(e).__name__}), ignored')
        return None
    try:
        until = int(text)
    except ValueError:
        journal(f'{UNSIGNED_UNTIL}: not a Unix time, ignored')
        return None
    if until <= at:
        journal(f'{UNSIGNED_UNTIL}: expired at {stamp(until)}, ignored (delete it)')
        return None
    if until - at > UNSIGNED_MAX:
        journal(f'{UNSIGNED_UNTIL}: {stamp(until)} is more than 24 hours ahead, ignored')
        return None
    return until


def installed():
    """The number of the last release installed on this site (0 before any was recorded)."""
    try:
        return int((AD / 'installed').read_text().strip())
    except (OSError, ValueError):
        return 0


TOOL_LINE = re.compile(r'([A-Za-z0-9+/]{43}=)  (\S.*)')


def tool_lines(data):
    """TOOLS, as tools/release_manifest.py --tools writes it ("<base64 sha256>  <path>" a line), as {path: sha256}."""
    out = {}
    for k, line in enumerate(data.decode('utf-8').splitlines(), 1):
        m = TOOL_LINE.fullmatch(line)
        if not m or m.group(2) in out:
            raise ValueError(f'TOOLS line {k} is not "<sha256>  <path>" (or names its file twice)')
        out[m.group(2)] = m.group(1)
    return out


def check_request(tag, n, request, words, sig, tools, st):
    """With signatures on: REQUEST signed by this site's key (or the emergency window open), for this tag, numbered above
    the last release installed here, and TOOLS the list it names, with every tool this script takes. Returns TOOLS as
    {path: sha256}; raises Stop otherwise. Notes the outcome in st (signature: ok or UNSIGNED_ALLOWED)."""
    problem = signature_problem(request, sig)
    if problem:
        until = unsigned_until(time.time())
        if until is None:
            raise Stop('BAD_SIGNATURE', problem)
        st.update(signature='UNSIGNED_ALLOWED', signature_error=problem, unsigned_until=stamp(until))
    else:
        st['signature'] = 'ok'
    named = {}
    for w in words[2:]:
        key, eq, value = w.partition('=')
        if eq:
            named.setdefault(key, []).append(value)
    for key in ('tag', 'tools'):
        if len(named.get(key, ())) != 1:
            raise Stop('BAD_SIGNATURE', f'REQUEST has no {key}=' if key not in named else f'REQUEST has {key}= twice')
    if named['tag'][0] != tag:  # a request signed for another tag, put under this one
        raise Stop('BAD_SIGNATURE', f"REQUEST is for {named['tag'][0][:20]}, not {tag}")
    last = installed()
    if n < last:
        raise Stop('BAD_SIGNATURE', f"{tag} is older than {SITE['prefix']}{last}, the last release installed here")
    if n == last:
        raise Stop('NOTHING_TO_DO', f'{tag} is installed already')
    if not re.fullmatch(r'[0-9a-f]{64}', named['tools'][0]):
        raise Stop('BAD_SIGNATURE', 'REQUEST tools= is not a sha256')
    if tools is None:
        raise Stop('BAD_SIGNATURE', 'TOOLS missing')
    if hashlib.sha256(tools).hexdigest() != named['tools'][0]:
        raise Stop('BAD_SIGNATURE', 'TOOLS does not match tools=')
    try:
        listed = tool_lines(tools)
    except ValueError as e:
        raise Stop('BAD_SIGNATURE', str(e))
    missing = [p for p in TOOLS if p not in listed]
    if missing:
        raise Stop('BAD_SIGNATURE', 'not in TOOLS: ' + ', '.join(missing))
    return listed


def mail_admins(subject, text):
    """One mail to each of the console's 管理员 (FLOW_ADMIN_EMAILS), by the app's own way out (account_service.mail:
    FLOW_SMTP_*, then its fallback), from the installed copy of the site. How many took it; a failure only goes to
    the journal."""
    to = [e.strip() for e in os.environ.get('FLOW_ADMIN_EMAILS', '').split(',') if e.strip()]
    if not to:
        journal('no FLOW_ADMIN_EMAILS: nobody to tell')
        return 0
    sys.path.insert(0, ENV.get('FLOW_DIR', '/www/wwwroot/flow'))
    write_bytecode, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # no root-owned __pycache__ in the site's folder
    try:
        import account_service
    except Exception as e:
        journal(f'no mail ({type(e).__name__})')
        return 0
    finally:
        sys.path.pop(0)
        sys.dont_write_bytecode = write_bytecode
    sent = 0
    for addr in to:
        try:
            account_service.mail(addr, subject, text)
            sent += 1
        except Exception as e:
            journal(f'a mail to a 管理员 failed ({type(e).__name__})')
    return sent


TREE_REF = re.compile(r'ref=(build-[0-9a-f]{12})')  # REQUEST's name of the build's tag (tools/deploy.sh)


def listing(sha, alt=None):
    """jsDelivr's list of the commit's files with their sha256 ({path: file}), and the name it was asked by.

    jsDelivr can keep an early "not found" for a commit for hours: b34's build 39d16ba got 404 for its listing while the
    same tree by its tag, and every file by the commit, came back fine (2026-11-25). So after a 404 for the commit the
    same tree is asked for by its tag, `alt` (REQUEST's ref=build-<sha12>). Every file is still fetched by the commit
    and checked against this list, and flow-pull.sh checks the whole manifest, so a tag on another tree only fails."""
    last = None
    for k in range(5):
        for ref in (sha, alt) if alt else (sha,):
            try:
                return {f['name'].lstrip('/'): f for f in json.loads(fetch(f'https://data.jsdelivr.com/v1/package/gh/{REPO}@{ref}/flat'))['files']}, ref
            except Exception as e:
                last = e
                if not (isinstance(e, urllib.error.HTTPError) and e.code == 404):
                    break  # only a 404 asks by the tag; anything else is asked again after a pause
        time.sleep(2 + 3 * k)
    raise RuntimeError(f'listing: {last!r}')


def verified(sha, path, flat, want=None):
    """The commit's file from whichever mirror gives the right bytes: those whose sha256 is `want` (the file's line in
    the signed TOOLS) when given, else those of jsDelivr's listing."""
    last = None
    for k in range(3):
        for h in HOSTS:
            try:
                data = fetch(f'https://{h}/gh/{REPO}@{sha}/{path}')
            except Exception as e:
                last = e
                continue
            digest = base64.b64encode(hashlib.sha256(data).digest()).decode()
            if want is not None:
                if digest == want:
                    return data
                last = RuntimeError(f'{path}: content does not match TOOLS')
            elif len(data) == flat[path]['size'] and digest == flat[path]['hash']:
                return data
            else:
                last = RuntimeError(f'{path}: content does not match the listing')
        time.sleep(2 + 3 * k)
    raise RuntimeError(f'{path}: {last!r}')


ERROR_TEXT = re.compile(r"""['"]error['"]:\s*(['"])(.*?)\1""")
JOB_KIND = re.compile(r"""['"]kind['"]:\s*['"]([\w-]+)['"]""")


def reason(detail):
    """Why a check failed, without anything anyone wrote: the error text the app answered with (with an AI job's kind),
    an HTTP status, or an exception's type. An answer's content is left out, even a test account's (2026-11-25)."""
    d = str(detail).strip()
    errors = [e for _, e in ERROR_TEXT.findall(d)]
    if errors:
        kinds = JOB_KIND.findall(d)
        return '; '.join((kinds[k] + ': ' if k < len(kinds) else '') + e for k, e in enumerate(errors))[:160]
    if re.fullmatch(r'\d{3}|0', d):
        return f'HTTP {d}'
    routes = re.findall(r'(/[\w/.-]+) HTTP (\d{3}|0)', d)  # requests and their statuses (qa_e2e: "<route> HTTP <status>")
    if routes:
        return '; '.join(f'{path} HTTP {code}' for path, code in routes)[:160]
    found = re.findall(r'\b([A-Z]\w*(?:Error|Exception))\b', d)
    return found[-1] if found else ''


def e2e_summary(work):
    try:
        r = json.loads((work / 'report.json').read_text())
        return {'checks': r['checks']['total'], 'failed': r['checks']['failed'], 'failed_names': [f['who'] + ': ' + f['name'] for f in r['failed']][:40],
                # why each failed (the app's error text, a status, an exception type; never what was written): readable in
                # /api/deploy-status and the release's Actions log without a look at the server (b12 needed one, 2026-11-25)
                'failed_details': [f"{f['who']}: {f['name']}: {reason(f.get('detail', ''))}" for f in r['failed']][:10],
                'light': bool(r.get('light')),
                'server_errors': len(r['server_errors']), 'ai_calls': r['ai_calls_used'], 'seconds': r['seconds'],
                # which requests got a 5xx (or no answer): method, route (no query) and status, nothing else (b38, 2026-11-25)
                'server_error_routes': [f"{x.get('method', '?')} {x.get('path', '?')} {x.get('status', '?')}" for x in r['server_errors']][:10],
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
    signed = signing_on()
    try:
        req = request_for(tag)
        # with signatures on, the signature and the tool list come from the tag too, before anything from its commit
        sig, tools = (tag_file(tag, 'REQUEST.sig'), tag_file(tag, 'TOOLS')) if signed and req is not None else (None, None)
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
    alt = next((m.group(1) for m in map(TREE_REF.fullmatch, words[2:]) if m), None)  # the build's tag, if listed
    st.update(commit=sha, e2e_requested=e2e, **({'e2e_light': True} if light else {}))
    listed = None  # the signed TOOLS ({path: sha256}); None without signatures
    if signed:
        try:
            # REQUEST's bytes again: it was read as UTF-8, which tools/deploy.sh writes (anything else fails the check)
            listed = check_request(tag, n, req.encode('utf-8'), words, sig, tools, st)
        except Stop as e:
            journal(f'{tag}: {e.result}: {e}')
            write_status({**st, 'state': 'done', 'result': e.result, ('error' if e.result == 'BAD_SIGNATURE' else 'note'): str(e)[:300],
                          'finished': now()})
            return
        if st['signature'] == 'UNSIGNED_ALLOWED':
            journal(f"{tag}: UNSIGNED_ALLOWED until {st['unsigned_until']}: {st['signature_error']}")
            st['mailed'] = mail_admins(
                f"{SITE['name']} {tag} 没有通过签名校验，按应急开关照装",
                f"{SITE['name']} {tag}（提交 {sha[:12]}）的发版请求没有通过签名校验：{st['signature_error']}。\n"
                f"服务器上的应急开关 {UNSIGNED_UNTIL} 开着（到 {st['unsigned_until']} 失效），所以这一版照装；"
                f"结果看 {SITE['url']}/api/deploy-status 。\n签名恢复以后请删掉这个文件。\n")
        else:
            journal(f'{tag}: signature ok')
    else:
        journal(f"{tag}: 本站没开签名校验（{SIGNERS} 里没有 {SITE['signer']} 这一行），照旧安装")
    write_status(st)
    work = AD / tag
    shutil.rmtree(work, ignore_errors=True)
    (work / 'qa-audio').mkdir(parents=True)
    try:
        flat, listed_by = listing(sha, alt)
        if listed_by != sha:
            st['listed_by'] = listed_by
        if listed is None:  # without signatures, as before: what jsDelivr lists, checked against its listing
            todo = [(p, None) for p in TOOLS + sorted(x for x in flat if e2e and x.startswith(AUDIO)) if p in flat]
        else:  # what the signed TOOLS lists (each of TOOLS is there: check_request), checked against its line there
            todo = [(p, listed[p]) for p in TOOLS + sorted(x for x in listed if e2e and x.startswith(AUDIO))]
        for p, want in todo:
            (work / (('qa-audio/' if p.startswith(AUDIO) else '') + Path(p).name)).write_bytes(verified(sha, p, flat, want))
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
            subprocess.run(['bash', str(work / 'flow-pull.sh'), sha, manifest], env={**ENV, **({'FLOW_TREE_REF': alt} if alt else {})},
                           stdout=out, stderr=subprocess.STDOUT, timeout=1800)
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
        if n > installed():
            (AD / 'installed').write_text(str(n))  # with signatures on, the next request must be numbered above it
        # keep the server's copies of the tools in step with what was just deployed (the 内测版 keeps its own): the
        # copies taken above, so with signatures on, the ones checked against the signed TOOLS (this script among them)
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
