#!/usr/bin/env python3
"""Does this branch quietly undo a pull request that was merged recently? (2026-11-26: a squash made with
`git reset --soft origin/main` after origin/main had moved took #450 back out of main inside #456.)

    python3 tools/check_undo.py [--head REV] [--base origin/main] [--hours 48]

The branch's change is merge-base(head, base)..head. For every pull request merged into base's first-parent line in the
last <hours> that the merge-base already contains, it counts the lines that pull request added which the branch now
removes, and the lines it had replaced which the branch puts back. A real rewrite removes another's lines but writes new
ones; undoing removes them AND puts the old ones back (or removes nearly all of them). That is reported and the exit
status is 1; smaller overlaps are listed as a note, exit 0. tools/msi-run.sh runs this before it sends a snapshot.
"""
import collections, re, subprocess, sys, time


def opt(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


HEAD, BASE, HOURS = opt('--head', 'HEAD'), opt('--base', 'origin/main'), float(opt('--hours', '48'))


def git(*a):
    r = subprocess.run(['git', *a], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ''


def change(a, b):
    """{file: (added lines, removed lines)} between two commits, blank lines left out."""
    add, rem, f = collections.defaultdict(list), collections.defaultdict(list), None
    for line in git('diff', '-U0', '--no-renames', a, b).split('\n'):
        if line.startswith('diff --git'):
            f = line.split(' b/', 1)[1]
        elif line.startswith('+') and not line.startswith('+++') and f and line[1:].strip():
            add[f].append(line[1:].strip())
        elif line.startswith('-') and not line.startswith('---') and f and line[1:].strip():
            rem[f].append(line[1:].strip())
    return add, rem


def undone(mine, theirs):
    """(lines of theirs I remove, lines theirs added, lines theirs replaced that I restore, lines theirs replaced, per file)."""
    (madd, mrem), (tadd, trem) = mine, theirs
    removed = added = restored = replaced = 0; files = []
    for f in set(tadd) | set(trem):
        a, r = collections.Counter(tadd.get(f, [])), collections.Counter(trem.get(f, []))
        x = sum((a & collections.Counter(mrem.get(f, []))).values()); y = sum((r & collections.Counter(madd.get(f, []))).values())
        removed += x; added += sum(a.values()); restored += y; replaced += sum(r.values())
        if x or y:
            files.append(f)
    return removed, added, restored, replaced, sorted(files)


def main():
    base = git('merge-base', HEAD, BASE).strip()
    if not base:
        print(f'check_undo: no merge-base between {HEAD} and {BASE}; nothing checked'); return 0
    mine = change(base, HEAD)
    if not any(mine[1].values()):
        print('check_undo: this branch removes no lines; nothing to check'); return 0
    since = time.time() - HOURS * 3600
    bad = notes = 0
    shown = 0
    for line in git('log', '--first-parent', '--format=%H %ct %s', base, '--max-count=600').split('\n'):
        if not line:
            continue
        sha, ct, subj = line.split(' ', 2)
        if int(ct) < since:
            break
        m = re.search(r'#(\d+)', subj)
        if not m:
            continue
        parent = git('rev-parse', '-q', '--verify', f'{sha}^1').strip()
        if not parent:
            continue
        removed, added, restored, replaced, files = undone(mine, change(parent, sha))
        if not removed:
            continue
        share = removed / max(added, 1)
        looks_undone = (share >= 0.5 and restored > 0) or (share >= 0.9 and replaced == 0)
        if not looks_undone and (removed < 5 or shown >= 8):
            continue
        shown += not looks_undone
        tag = 'UNDOES' if looks_undone else 'note: also edits'
        print(f'check_undo: {tag} #{m.group(1)} ({subj[:60]}): removes {removed}/{added} of its added lines'
              + (f', puts back {restored}/{replaced} it had replaced' if replaced else '') + f' — {", ".join(files[:4])}')
        bad += looks_undone; notes += not looks_undone
    if bad:
        print('check_undo: this branch takes back what another pull request merged. If that is not on purpose, the branch was\n'
              '  squashed onto a base that had moved: squash onto your own merge-base (git merge-base HEAD origin/main), or\n'
              '  merge origin/main into the branch, and check `git diff origin/main...HEAD` again. On purpose: FLOW_ALLOW_UNDO=1.')
        return 1
    if not notes:
        print(f'check_undo: nothing from the last {HOURS:.0f} h is taken back')
    return 0


if __name__ == '__main__':
    sys.exit(main())
