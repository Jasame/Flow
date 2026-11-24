#!/usr/bin/env python3
"""After `git merge origin/main` (into your branch), settles the parts of the merge that are bookkeeping, not edits:

    git merge origin/main          # stops on conflicts, or not
    python3 tools/settle_merge.py  # settles and stages what it can, lists what is left for you
    python3 tools/build_release.py --here && git commit

- The files a release builds (next.js, next.css, the guide PDF and its manifest.json; tools/build_release.py) are
  no longer kept in git: they leave the index. Your local copies stay (git ignores them); rebuild them afterwards.
- tools/release-files.txt and the two lists in flow/upgrade.sh (FLOW_FILES, FLOW_PUBLIC_FILES): every name either
  side added stays, a name either side removed goes, and the list is written sorted, one name per line. A branch from
  before 2026-11-24 still has the old one-line lists in upgrade.sh: its names are carried into main's layout, as long
  as the branch changed nothing else in upgrade.sh.
Anything else that conflicts is a real edit on both sides: it is listed, and left for you.
"""
import re, subprocess, sys
from pathlib import Path

ROOT = Path(subprocess.run(['git', 'rev-parse', '--show-toplevel'], capture_output=True, text=True, check=True).stdout.strip())
GENERATED = ('flow/public/next.js', 'flow/public/next.css', 'flow/public/guide/flow-guide.pdf', 'flow/public/guide/manifest.json')
RELEASE, UPGRADE = 'tools/release-files.txt', 'flow/upgrade.sh'
ARRAY = re.compile(r'^(?:#[^\n]*\n)?(FLOW_(?:PUBLIC_)?FILES)=\(\n(.*?)^\)\nfor name in "\$\{\1\[@\]\}"; do\n', re.S | re.M)
OLD = re.compile(r'^for name in ([^;"$]+); do\n', re.M)


def git(*a, check=True):
    r = subprocess.run(['git', *a], cwd=ROOT, capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(a)}: {r.stderr.strip()}")
    return r.stdout if r.returncode == 0 else None


def stage(n, path):
    """The file as it is on one side of the conflict: 1 the common base, 2 your branch, 3 the branch merged in."""
    return git('show', f':{n}:{path}', check=False)


def lists(text):
    """The two name lists of an upgrade.sh, in the new layout or the old one-line one."""
    if text is None:
        return None
    new = ARRAY.findall(text)
    found = [b.split() for _, b in new] if new else [x.split() for x in OLD.findall(text)]
    return found if len(found) == 2 else None


def skeleton(text):
    """upgrade.sh without its lists, to see whether anything else changed."""
    return OLD.sub('for name in LIST; do\n', ARRAY.sub('for name in LIST; do\n', text))


def merged(base, ours, theirs):
    base, ours, theirs = set(base or []), set(ours or []), set(theirs or [])
    return sorted((ours | theirs) - (base - ours) - (base - theirs))


def write_lists(template, names):
    """template (main's upgrade.sh, new layout) with its two arrays holding names."""
    k = iter(names)

    def one(m):
        body = ''.join(f'  {n}\n' for n in next(k))
        return m.group(0)[:m.start(2) - m.start()] + body + m.group(0)[m.end(2) - m.start():]
    return ARRAY.sub(one, template)


def main():
    merging = git('rev-parse', '-q', '--verify', 'MERGE_HEAD', check=False) is not None
    conflicted = set((git('diff', '--name-only', '--diff-filter=U') or '').split())
    done, left = [], []
    for n in GENERATED:
        if n in set(git('ls-files', '--', n).split()) and (n in conflicted or merging):
            git('rm', '-q', '--cached', '--', n)
            done.append(f'{n}: built at release now, out of git (your copy stays)')
            conflicted.discard(n)
    if RELEASE in conflicted:
        names = merged(*((stage(k, RELEASE) or '').split() for k in (1, 2, 3)))
        (ROOT / RELEASE).write_text('\n'.join(names) + '\n')
        git('add', '--', RELEASE); conflicted.discard(RELEASE)
        done.append(f'{RELEASE}: both sides kept, sorted ({len(names)} files)')
    elif (ROOT / RELEASE).exists():
        names = [x for x in (ROOT / RELEASE).read_text().splitlines() if x]
        if names != sorted(set(names)):
            (ROOT / RELEASE).write_text('\n'.join(sorted(set(names))) + '\n'); git('add', '--', RELEASE)
            done.append(f'{RELEASE}: sorted')
    if UPGRADE in conflicted:
        base, ours, theirs = (stage(k, UPGRADE) for k in (1, 2, 3))
        lb, lo, lt = lists(base), lists(ours), lists(theirs)
        if theirs and ARRAY.search(theirs) and lo and lt and (base is None or skeleton(ours) == skeleton(base)):
            text = write_lists(theirs, [merged(lb and lb[i], lo[i], lt[i]) for i in (0, 1)])
            (ROOT / UPGRADE).write_text(text)
            git('add', '--', UPGRADE); conflicted.discard(UPGRADE)
            done.append(f'{UPGRADE}: your names carried into the sorted lists')
        elif ours and ARRAY.search(ours) and lo and lt and theirs and (base is None or skeleton(theirs) == skeleton(base)):
            text = write_lists(ours, [merged(lb and lb[i], lo[i], lt[i]) for i in (0, 1)])
            (ROOT / UPGRADE).write_text(text)
            git('add', '--', UPGRADE); conflicted.discard(UPGRADE)
            done.append(f'{UPGRADE}: both sides kept in the sorted lists')
        else:
            left.append(f'{UPGRADE}: other lines changed on both sides; keep main\'s layout, add your names to FLOW_FILES / FLOW_PUBLIC_FILES')
            conflicted.discard(UPGRADE)
    for line in done:
        print('settled ', line)
    for n in sorted(conflicted):
        left.append(f'{n}: edited on both sides')
    for line in left:
        print('YOURS   ', line)
    if any('built at release' in line for line in done):
        print('then: python3 tools/build_release.py --here   (next.js, next.css and the guide PDF from the merged sources)')
    return 1 if left else 0


if __name__ == '__main__':
    sys.exit(main())
