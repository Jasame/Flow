#!/usr/bin/env python3
"""Where a Tests run's heavy jobs (the website and UI shares) run: on the owner's MSI, or on GitHub's machines.

    python3 tools/ci_runner.py pick    # the 'changes' job: writes runner=, where=, reason= to $GITHUB_OUTPUT
    python3 tools/ci_runner.py watch   # the 'msi-watch' job: cancels the run if its MSI jobs never get a machine

GitHub never moves a queued job to another machine, so the choice is made before the jobs are queued. The MSI
(self-hosted runners labelled msi, in WSL2 on the owner's PC; tools/msi-setup.sh) takes them only when
1. the switch is on: the repository variable MSI_RUNNER is "on" (unset or anything else: GitHub's machines);
2. the run is main's (push, Run workflow) or a pull request from this repository, never one from a fork, whose code
   would then run on the owner's machine;
3. the MSI is not full: fewer than MSI_SLOTS of its jobs are queued or running now, and when some are, this run's
   shares fit in what is left (NEED_WEB / NEED_UI from the changes job: 2 website and 5 UI shares). A run that has
   the MSI to itself goes there even with more shares than runners: the last one starts when the first ends. One
   that would wait behind another run's shares goes to GitHub's machines instead, so it is never left waiting
   long enough for `watch` to cancel it;
4. the MSI is there: a probe (.github/workflows/msi-probe.yml) dispatched now starts within MSI_PROBE_WAIT seconds.
Anything that cannot be asked (an API error, no probe workflow on main yet) means GitHub's machines.

If the MSI goes away in the seconds between the probe and the jobs, they would wait for it for up to a day, and on
main (whose runs are never cancelled by the next merge) every later run would wait behind them. `watch` stops that: when
a job sent to the MSI has not started after MSI_WATCH minutes, it cancels the run, and for main asks for a new Tests
run on main, which finds the MSI gone and uses GitHub's machines.

Only the run's own token is used (actions: read and write, in jobs on GitHub's machines). No secret is involved, and
nothing reaches the MSI but the code under test.
"""
import json, os, sys, time, urllib.error, urllib.request

HOSTED = 'ubuntu-24.04'
MSI = ['self-hosted', 'msi']
# how many jobs the MSI runs at once: its runner count, the repository variable MSI_SLOTS (empty or unset: 6;
# tools/msi-setup.sh RUNNERS, which also says how many fit its processors)
SLOTS = int(os.getenv('MSI_SLOTS') or 6)
PROBE_WAIT = int(os.getenv('MSI_PROBE_WAIT', '45'))
WATCH_MINUTES = int(os.getenv('MSI_WATCH', '10'))
WEB_SHARES, UI_SHARES = 2, 5  # tests.yml's backend-share and ui-share matrices (tests/test_ci.py checks)
PROBE = 'msi-probe.yml'


def api_for(env):
    base, repo, token = env.get('GITHUB_API_URL', 'https://api.github.com'), env['GITHUB_REPOSITORY'], env['GITHUB_TOKEN']

    def api(method, path, body=None):
        url = f"{base}/repos/{repo}/{path.lstrip('/')}"
        req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                     headers={'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json',
                                              'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'flow-ci'})
        with urllib.request.urlopen(req, timeout=20) as r:
            text = r.read()
        return json.loads(text) if text else {}
    return api


def on_msi(job):
    return 'msi' in (job.get('labels') or []) and job.get('name') != 'probe'


def msi_load(api, own_run=None):
    """Jobs of other runs that are queued or running on the MSI now."""
    n = 0
    for status in ('in_progress', 'queued'):
        for run in api('GET', f'actions/runs?status={status}&per_page=30').get('workflow_runs', []):
            if str(run['id']) == str(own_run):
                continue
            jobs = api('GET', f"actions/runs/{run['id']}/jobs?per_page=100").get('jobs', [])
            n += sum(1 for j in jobs if on_msi(j) and j.get('status') in ('queued', 'in_progress'))
    return n


def probe(api, nonce, ref, wait=None, sleep=time.sleep):
    """Dispatch the probe and say whether a machine labelled msi picked it up within `wait` (PROBE_WAIT) seconds."""
    api('POST', f'actions/workflows/{PROBE}/dispatches', {'ref': ref, 'inputs': {'nonce': nonce}})
    deadline = time.monotonic() + (PROBE_WAIT if wait is None else wait)
    while time.monotonic() < deadline:
        sleep(3)
        for run in api('GET', f'actions/workflows/{PROBE}/runs?event=workflow_dispatch&per_page=10').get('workflow_runs', []):
            if nonce not in (run.get('display_title') or ''):
                continue
            for j in api('GET', f"actions/runs/{run['id']}/jobs").get('jobs', []):
                if j.get('status') == 'in_progress' or (j.get('status') == 'completed' and j.get('conclusion') == 'success'):
                    return True
    return False


def need(env):
    """How many jobs this run sends to the MSI, from what the changes job found (0: not known)."""
    return WEB_SHARES * (env.get('NEED_WEB') == 'true') + UI_SHARES * (env.get('NEED_UI') == 'true')


def decide(env, api, sleep=time.sleep):
    """(runner labels, 'msi' or 'hosted', reason)."""
    if env.get('MSI_RUNNER') != 'on':
        return HOSTED, 'hosted', 'the switch MSI_RUNNER is not on'
    event = env.get('GITHUB_EVENT_NAME')
    if event == 'pull_request':
        if not env.get('HEAD_REPO') or env.get('HEAD_REPO') != env.get('GITHUB_REPOSITORY'):
            return HOSTED, 'hosted', 'a pull request from a fork runs on GitHub\'s machines only'
    elif event not in ('push', 'workflow_dispatch'):
        return HOSTED, 'hosted', f'a {event} run'
    if api is None:
        return HOSTED, 'hosted', 'no token to ask GitHub with'
    try:
        busy = msi_load(api, env.get('GITHUB_RUN_ID'))
        if busy >= SLOTS:
            return HOSTED, 'hosted', f'the MSI is full ({busy} jobs queued or running there)'
        if busy and busy + need(env) > SLOTS:
            return HOSTED, 'hosted', f'the MSI has room for {SLOTS - busy} more jobs and this run has {need(env)}'
        nonce = f"{env.get('GITHUB_RUN_ID', '0')}-{env.get('GITHUB_RUN_ATTEMPT', '1')}"
        if not probe(api, nonce, env.get('DEFAULT_BRANCH') or 'main', sleep=sleep):
            return HOSTED, 'hosted', f'the MSI did not answer within {PROBE_WAIT} s (off, or all its runners busy)'
    except (urllib.error.URLError, OSError, ValueError, KeyError) as e:
        return HOSTED, 'hosted', f'could not ask GitHub ({str(e)[:120]})'
    return MSI, 'msi', f'the MSI answered ({busy} jobs of other runs on it)'


def watch(env, api, sleep=time.sleep, minutes=WATCH_MINUTES):
    """Wait until every job of this run sent to the MSI has started; past `minutes`, cancel the run (and for main, ask
    for a new Tests run there). Returns what it did."""
    run = env['GITHUB_RUN_ID']
    start = time.monotonic()
    deadline = start + minutes * 60
    while True:
        jobs = [j for j in api('GET', f'actions/runs/{run}/jobs?per_page=100').get('jobs', []) if on_msi(j)]
        waiting = [j['name'] for j in jobs if j.get('status') in ('queued', 'waiting', 'pending', 'requested')]
        if jobs and not waiting:
            return 'every MSI job has a machine'
        if not jobs and time.monotonic() - start > 60:
            return 'no job of this run went to the MSI'
        if time.monotonic() >= deadline:
            break
        sleep(20)
    if env.get('GITHUB_EVENT_NAME') in ('push', 'workflow_dispatch') and env.get('GITHUB_REF_NAME') == (env.get('DEFAULT_BRANCH') or 'main'):
        api('POST', f"actions/workflows/{env.get('WORKFLOW_FILE', 'tests.yml')}/dispatches", {'ref': env.get('GITHUB_REF_NAME')})
        again = 'a new Tests run on main was asked for'
    else:
        again = 'run it again: the next one finds the MSI gone'
    api('POST', f'actions/runs/{run}/cancel')
    return f'MSI jobs {waiting or "(none listed)"} found no machine in {minutes} min: run cancelled; {again}'


def main(argv):
    env = dict(os.environ)
    if argv[:1] == ['pick']:
        runner, where, reason = decide(env, api_for(env) if env.get('GITHUB_TOKEN') else None)
        print(f'{where}: {reason}')
        out = env.get('GITHUB_OUTPUT')
        lines = f'runner={json.dumps(runner)}\nwhere={where}\nreason={reason}\n'
        if out:
            with open(out, 'a') as f:
                f.write(lines)
        else:
            print(lines, end='')
        return 0
    if argv[:1] == ['watch']:
        print(watch(env, api_for(env)))
        return 0
    raise SystemExit(__doc__)


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
