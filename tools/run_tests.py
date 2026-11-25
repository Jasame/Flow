#!/usr/bin/env python3
"""Runs the test suites in parallel: the same split CI uses, and the quick runs to make before pushing.

    python3 tools/run_tests.py                        # every website test (flow/tests), several files at once (~3 min on a laptop)
    python3 tools/run_tests.py test_vocab test_next   # these test files only (names as in flow/tests)
    python3 tools/run_tests.py --changed              # the test files for what this branch changed (against origin/main)
    python3 tools/run_tests.py --shard 1/2            # CI: one share of the website tests, balanced by measured time
    python3 tools/run_tests.py --ui [groups…]         # tools/ui_test.py, its groups in parallel (needs Playwright)
    python3 tools/run_tests.py --ui --shard 3/5       # CI: one share of the UI groups
    python3 tools/run_tests.py --list [--ui] [--shard K/N]   # print what would run, run nothing
    git diff --name-only … | python3 tools/run_tests.py --ui-needed   # CI: ui=true unless no path can change the UI
    options: --jobs N (processes at once; default: the number of CPUs, at most 8)
             --out DIR (UI screenshots and ui-report.json, one folder per process; default /tmp/flow-ui-out)

Each website test file runs in its own process, loaded the way `python -m unittest discover -s tests` loads it (the
tests folder is on the import path, so one test file can import another), each with its own temporary database.
The front end is built first (tools/build_front.py), because a few tests read next.js and next.css.

The UI groups are the switches of tools/ui_test.py (phone, about, sprint …); UI_SHARDS puts each in one CI job, and
tests/test_ci.py fails when a group of ui_test.py is in none of them. Each UI process starts its own local server.
Everything CI runs is still run by CI on every pull request; this only makes the same runs shorter.
"""
import os, re, subprocess, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FLOW = ROOT / 'flow'
TESTS = FLOW / 'tests'
# Seconds each file took in CI with 4 files at once on a 4-CPU hosted runner (PR #60, 2026-11-24): only used to
# balance the shares. A file not listed (new, or under 3 s) counts as DEFAULT_SECONDS; a wrong guess only makes one
# share a little longer.
SECONDS = {
    'test_ability_radar': 37, 'test_account_data': 28, 'test_adaptive': 124, 'test_admin_roles': 53,
    'test_ai_eval': 37, 'test_ai_stream': 3, 'test_atlas': 23, 'test_channels': 12, 'test_chat': 15, 'test_coach': 64,
    'test_continuity': 67, 'test_corpus': 34, 'test_corpus_v5': 3, 'test_daily_knowledge': 42, 'test_daily_line': 21,
    'test_exam_sprint': 21, 'test_feedback': 43, 'test_field': 76, 'test_fill_examples': 52,
    'test_flow_admin_console': 90, 'test_foundation': 52, 'test_growth': 118, 'test_guide': 7,
    'test_ielts_speaking': 33, 'test_lab': 46, 'test_learner': 116, 'test_learner_round': 15, 'test_learning': 26,
    'test_learning_loop': 36, 'test_learning_more': 42, 'test_learning_system': 39, 'test_login': 74, 'test_loop': 31,
    'test_media': 12, 'test_migration': 4, 'test_next': 169, 'test_pedagogy': 30, 'test_practice': 61,
    'test_practice_hub': 8, 'test_progress': 55, 'test_quota': 31, 'test_reference': 51, 'test_reliability': 49,
    'test_relisten': 37, 'test_rewrite_minimal': 26, 'test_survey': 33, 'test_ux_round': 15, 'test_vocab': 114,
    'test_welcome': 18, 'test_wordbook_registry': 19,
}
DEFAULT_SECONDS = 30
# The groups of tools/ui_test.py, one list per CI job (4.4–5.9 minutes each on a hosted runner, PR #60, 2026-11-24).
# Every group ui_test.py has must be in one (tests/test_ci.py checks): a new group goes into the shortest share.
# A name ui_test.py does not have yet is allowed: 'privacy' and 'trial-survey' arrive with PRs #58 and #59.
UI_SHARDS = [
    ['about', 'wait', 'home-app', 'ios-audio', 'review-side'],
    ['phone', 'phone-land', 'privacy', 'trial-survey'],
    ['tablet', 'desktop', 'platforms', 'wechat', 'ux'],
    ['learner', 'progress', 'swipe', 'listen-speak', 'start', 'sprint', 'backlog', 'class'],
    ['a11y', 'layout'],
]


# What the UI tests depend on: the website (flow/, its pages, guide.md, corpus) and the tools that serve and drive it.
# A pull request that changes none of these (docs, the release and evaluation tools, …) skips the UI shares; any doubt
# (no list of paths, a path under flow/) runs them.
UI_INPUTS = ('flow/', 'tools/ui_test.py', 'tools/ui_server.py', 'tools/ui-fixtures/', 'tools/build_front.py',
             'tools/run_tests.py', '.github/workflows/tests.yml')


def ui_needed(paths):
    paths = [p.strip() for p in paths if p.strip()]
    return not paths or any(p.startswith(UI_INPUTS) for p in paths)


def test_files():
    return sorted(p.stem for p in TESTS.glob('test_*.py'))


def shares(names, n):
    """names split into n shares of about the same measured time: longest first, each into the lightest share."""
    out = [[] for _ in range(n)]
    load = [0] * n
    for name in sorted(names, key=lambda m: (-SECONDS.get(m, DEFAULT_SECONDS), m)):
        k = load.index(min(load))
        out[k].append(name)
        load[k] += SECONDS.get(name, DEFAULT_SECONDS)
    return [sorted(s) for s in out]


def shard_arg(argv):
    if '--shard' not in argv:
        return None
    m = re.fullmatch(r'(\d+)/(\d+)', argv[argv.index('--shard') + 1])
    if not m or not 1 <= int(m.group(1)) <= int(m.group(2)):
        sys.exit('--shard K/N with 1 <= K <= N')
    return int(m.group(1)), int(m.group(2))


def changed_files(base='origin/main'):
    def git(*a):
        return subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True).stdout.split('\n')
    merge_base = (git('merge-base', base, 'HEAD') or [''])[0].strip()
    names = git('diff', '--name-only', merge_base) if merge_base else []
    names += git('ls-files', '--others', '--exclude-standard')
    return sorted({n for n in names if n})


def tests_for(paths):
    """The website test files that check what these paths changed: a changed test file itself, and every test file
    that imports a changed module of flow/ by name (one level: app.py imports nearly everything, so following
    imports through app would select the whole suite). Front-end parts select the tests that read next.js / next.css."""
    files = test_files()
    text = {m: (TESTS / f'{m}.py').read_text(encoding='utf-8') for m in files}
    pick = set()
    for p in paths:
        path = Path(p)
        if p.startswith('flow/tests/test_') and path.stem in text:
            pick.add(path.stem)
        elif p.startswith('flow/') and path.suffix == '.py' and path.parent.name == 'flow':
            mod = re.escape(path.stem)
            pick |= {m for m, t in text.items() if re.search(rf'^\s*(?:import [\w ,]*\b{mod}\b|from {mod} import)', t, re.M)}
        elif p.startswith('flow/public/'):
            pick |= {m for m, t in text.items() if re.search(r'next\.(?:js|css)|src/next|public/', t)}
        elif p.startswith('flow/corpus_data/'):
            pick |= {m for m, t in text.items() if 'corpus_data' in t} | {'test_corpus_v5', 'test_package'} & set(files)
        elif p.startswith(('tools/release-files.txt', 'flow/upgrade.sh')):
            pick |= {'test_package', 'test_guide', 'test_wordbooks_open'} & set(files)
    return sorted(pick)


def jobs(argv):
    if '--jobs' in argv:
        return max(1, int(argv[argv.index('--jobs') + 1]))
    return max(1, min(8, os.cpu_count() or 2))


def run_files(names, workers):
    """Each file in its own process; prints one line per file as it finishes and the full output of a failed one."""
    def one(m):
        t = time.time()
        r = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-p', f'{m}.py', '-v'],
                           cwd=FLOW, capture_output=True, text=True)
        out = r.stdout + r.stderr
        ran = re.search(r'^Ran (\d+) tests?', out, re.M)
        return m, r.returncode, time.time() - t, int(ran.group(1)) if ran else 0, out
    t0, results = time.time(), []
    order = sorted(names, key=lambda m: -SECONDS.get(m, DEFAULT_SECONDS))  # the long ones first, so none is left for last
    with ThreadPoolExecutor(workers) as ex:
        for m, rc, dt, ran, out in ex.map(one, order):
            results.append((m, rc, ran))
            print(f"{'ok  ' if rc == 0 else 'FAIL'} {m:<28} {ran:4d} tests {dt:6.1f}s", flush=True)
            if rc or ran == 0:
                print(out[-12000:], flush=True)
    failed = [m for m, rc, ran in results if rc or ran == 0]
    total = sum(ran for _, _, ran in results)
    print(f'\n{total} tests in {len(results)} files, {time.time() - t0:.0f}s with {workers} at once; '
          + (f'FAILED: {" ".join(failed)}' if failed else 'all passed'), flush=True)
    return 1 if failed else 0


def run_ui(out, groups_per_process, workers):
    """tools/ui_test.py once per list of groups, each process with its own server and out dir."""
    import json

    def one(k_groups):
        k, groups = k_groups
        d = Path(out) / f'shard-{k}'
        t = time.time()
        r = subprocess.run([sys.executable, str(ROOT / 'tools' / 'ui_test.py'), str(d), *groups], capture_output=True, text=True)
        try:
            rep = json.loads((d / 'ui-report.json').read_text())
        except (OSError, ValueError):
            rep = {'total': 0, 'failed': []}
        return k, groups, r.returncode, time.time() - t, rep, r.stdout + r.stderr
    bad = []
    with ThreadPoolExecutor(workers) as ex:
        for k, groups, rc, dt, rep, text in ex.map(one, list(enumerate(groups_per_process, 1))):
            ok = rc == 0 and rep['total'] > 0  # a share that checked nothing is a mistake, not a pass
            print(text if not ok or workers == 1 else '', end='')
            print(f"{'ok  ' if ok else 'FAIL'} ui {' '.join(groups)}: {rep['total'] - len(rep['failed'])}/{rep['total']} checks, {dt:.0f}s", flush=True)
            if not ok:
                bad.append(' '.join(groups))
                for f in rep['failed'][:40]:
                    print(f"  FAIL [{f.get('device')}] {f.get('check')}: {str(f.get('detail', ''))[:300]}")
    print('UI: ' + (f'FAILED: {"; ".join(bad)}' if bad else 'all passed') + f' (screenshots and ui-report.json in {out}/shard-*)')
    return 1 if bad else 0


def main(argv):
    if '--ui-needed' in argv:
        print('ui=' + ('true' if ui_needed(sys.stdin.read().splitlines()) else 'false'))
        return 0
    shard, listing = shard_arg(argv), '--list' in argv
    words = [a for k, a in enumerate(argv) if not a.startswith('--') and (k == 0 or argv[k - 1] not in ('--shard', '--jobs', '--out'))]
    if '--ui' in argv:
        out = argv[argv.index('--out') + 1] if '--out' in argv else '/tmp/flow-ui-out'
        if shard:
            plan = [UI_SHARDS[shard[0] - 1]] if shard[1] == len(UI_SHARDS) else sys.exit(f'--ui --shard K/{len(UI_SHARDS)}')
        else:
            plan = [[g] for g in words] if words else UI_SHARDS
        if listing:
            print('\n'.join(' '.join(p) for p in plan)); return 0
        workers = 1 if shard else min(jobs(argv), len(plan))
        # built once here, so the servers the processes start (tools/ui_server.py builds too) find it current
        subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_front.py')], check=True, stdout=subprocess.DEVNULL)
        return run_ui(out, plan, workers)
    if '--changed' in argv:
        paths = changed_files()
        names = tests_for(paths)
        print(f'{len(paths)} changed files -> {len(names)} test files: {" ".join(names) or "(none)"}')
    elif words:
        names = [w if w.startswith('test_') else 'test_' + w for w in words]
        unknown = [n for n in names if not (TESTS / f'{n}.py').exists()]
        if unknown:
            sys.exit(f'no such test file in flow/tests: {unknown}')
    else:
        names = test_files()
    if shard:
        names = shares(names, shard[1])[shard[0] - 1]
    if listing:
        print('\n'.join(names)); return 0
    if not names:
        return 0
    subprocess.run([sys.executable, str(ROOT / 'tools' / 'build_front.py')], check=True, stdout=subprocess.DEVNULL)
    return run_files(names, jobs(argv))


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
