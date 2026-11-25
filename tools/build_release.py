#!/usr/bin/env python3
"""The files a release installs that git does not keep: made from their sources, once per commit, when it is released.

    python3 tools/build_release.py --here           # build them in this checkout (tests, the local site); the PDF
                                                    #   only when guide.md or a screenshot changed since it was made
    python3 tools/build_release.py --front          # only next.js and next.css (no browser needed)
    python3 tools/build_release.py <commit>         # a release build (tools/deploy.sh --beta): prints the commit to deploy
    python3 tools/build_release.py --reuse <commit> # the release build made earlier for <commit> (tools/deploy.sh for 语流)
    python3 tools/build_release.py --dry-run <commit>  # build and check, commit locally, push and tag nothing

GENERATED are next.js and next.css (tools/build_front.py joins flow/public/src/next/*) and the 操作指南 PDF with its
manifest.json (tools/build_guide.py prints guide.md and its screenshots with Chrome). They are listed in
tools/release-files.txt like every other file the server installs, but .gitignore keeps them out of commits, so two
pull requests can no longer conflict over them.

A release build of <commit>
1. checks <commit> out in a temporary worktree and builds the generated files there;
2. checks them the way the tests checked them while they were committed: tools/build_front.py --check, the guide's
   manifest matches guide.md and every screenshot and the PDF's hash, header and size (flow/tests/test_guide.py with
   FLOW_REQUIRE_BUILT=1), and node --check on next.js when Node is installed; and the PDF embeds a Chinese font (a
   machine without one prints boxes: .github/workflows/beta.yml installs Noto Sans CJK on the runner);
3. commits them on top of <commit>: one commit whose parent is <commit> and which adds only these files, pushed as
   the tag build-<first 12 hex of commit>.
deploy.sh then deploys that build commit like any other commit: the server's flow-pull.sh fetches it through jsDelivr and
checks every file against the manifest computed from git (tools/release_manifest.py), unchanged. The 内测版 gets the
build first; 语流 later gets the same build commit (--reuse), so both sites install the same bytes. Building the same
commit again reuses its tag, so a retried release installs the same bytes too.

A commit from before this (the generated files still in git) is released as it is, after the same checks.
Output: the commit to deploy on stdout, everything else on stderr.
"""
import hashlib, json, os, re, shutil, subprocess, sys, tempfile, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ('flow/public/next.js', 'flow/public/next.css')
GUIDE = ('flow/public/guide/flow-guide.pdf', 'flow/public/guide/manifest.json')
GENERATED = FRONT + GUIDE


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def git(*a, cwd=ROOT, check=True):
    r = subprocess.run(['git', *a], cwd=str(cwd), capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"git {' '.join(a)}: {r.stderr.strip()}")
    return r.stdout.strip() if r.returncode == 0 else None


def run(cmd, cwd, env=None):
    r = subprocess.run(cmd, cwd=str(cwd), env=env, stdout=sys.stderr, stderr=sys.stderr)
    if r.returncode:
        raise SystemExit(f"failed ({r.returncode}): {' '.join(map(str, cmd))}")


def tag_of(sha):
    return 'build-' + sha[:12]


def python_with_playwright():
    """Python 3.11+ with Playwright: build_guide.py prints with it, and the guide's tests import the app."""
    seen = []
    for c in (os.environ.get('FLOW_PLAYWRIGHT_PYTHON'), sys.executable, shutil.which('python3.11'), shutil.which('python3')):
        if c and c not in seen:
            seen.append(c)
            ok = subprocess.run([c, '-c', 'import sys, playwright.sync_api; assert sys.version_info >= (3, 11)'], capture_output=True)
            if ok.returncode == 0:
                return c
    raise SystemExit('no Python 3.11 with Playwright to print the guide PDF: python3.11 -m pip install playwright==1.49.1 '
                     '(it drives the installed Google Chrome), or set FLOW_PLAYWRIGHT_PYTHON to one')


def guide_is_current(tree):
    """The PDF and manifest in `tree` were made from its guide.md and screenshots as they are now."""
    d = Path(tree) / 'flow/public/guide'
    try:
        m = json.loads((d / 'manifest.json').read_text())
        pdf = (d / 'flow-guide.pdf').read_bytes()
    except (OSError, ValueError):
        return False
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    shots = {p.stem for p in d.glob('*.jpg')}
    return (m.get('source_sha256') == sha(d / 'guide.md') and m.get('pdf_sha256') == hashlib.sha256(pdf).hexdigest()
            and set(m.get('shots', {})) <= shots and all(sha(d / f'{s}.jpg') == h for s, h in m.get('shots', {}).items()))


def build(tree, front=True, guide=True):
    if front:
        run([sys.executable, 'tools/build_front.py'], tree)
    if guide:
        run([python_with_playwright(), 'tools/build_guide.py'], tree)


def pdf_fonts(path):
    """The font names a PDF embeds (Chrome writes most of them inside compressed streams)."""
    data = Path(path).read_bytes()
    blobs = [data]
    for m in re.finditer(rb'stream\r?\n', data):
        try:
            blobs.append(zlib.decompress(data[m.end():data.find(b'endstream', m.end())]))
        except zlib.error:
            pass
    return sorted({n.split(b'+')[-1].decode('latin1') for b in blobs for n in re.findall(rb'/(?:BaseFont|FontName)\s*/([^\s/>\]]+)', b)})


CHINESE_FONTS = ('PingFang', 'Hiragino', 'CJK', 'SourceHan', 'NotoSansSC', 'NotoSerifSC', 'YaHei', 'WenQuanYi')


def verify(tree):
    """The checks the tests made on these files while they were committed, made on the files about to ship."""
    pdf = Path(tree) / GUIDE[0]
    fonts = pdf_fonts(pdf)
    log(f'guide PDF: {pdf.stat().st_size // 1024} KB, fonts: {", ".join(fonts)}')
    if not any(c.lower() in f.lower() for f in fonts for c in CHINESE_FONTS):
        raise SystemExit('the guide PDF embeds no Chinese font (its text would print as boxes): install one, e.g. fonts-noto-cjk')
    run([sys.executable, 'tools/build_front.py', '--check'], tree)
    if (Path(tree) / 'tools' / 'check_compat.py').exists():  # the scripts still run in Safari 15.0 (from 2026-11-25)
        run([sys.executable, 'tools/check_compat.py'], tree)
    if shutil.which('node'):
        for name in FRONT:
            if name.endswith('.js'):
                run(['node', '--check', name], tree)
    env = {**os.environ, 'FLOW_REQUIRE_BUILT': '1'}  # test_guide: a missing PDF fails instead of being skipped
    run([python_with_playwright(), '-m', 'unittest', 'discover', '-s', 'tests', '-p', 'test_guide.py'], Path(tree) / 'flow', env)


def existing_build(sha):
    """The build commit tagged for sha on GitHub, checked: its parent is sha and it adds only generated files."""
    tag = tag_of(sha)
    if not git('ls-remote', '--tags', 'origin', f'refs/tags/{tag}'):
        return None
    git('fetch', '-q', 'origin', f'+refs/tags/{tag}:refs/tags/{tag}')
    build_sha = git('rev-parse', f'{tag}^{{commit}}')
    parent = git('rev-parse', f'{build_sha}^')
    extra = set(git('diff', '--name-only', sha, build_sha).split()) - set(GENERATED)
    if parent != sha or extra:
        raise SystemExit(f'tag {tag} is not a build of {sha[:12]} (parent {parent[:12]}, other files {sorted(extra)[:5]}): '
                         f'delete the tag on GitHub and release again')
    return build_sha


def tracked_at(sha):
    return set(git('ls-tree', '-r', '--name-only', sha, '--', *GENERATED).split())


def release(sha, reuse_only=False, push=True):
    sha = git('rev-parse', f'{sha}^{{commit}}')
    found = existing_build(sha) if push else None
    if found:
        log(f'{tag_of(sha)}: the build of {sha[:12]} made earlier ({found[:12]}), installed as it is')
        return found
    missing = [n for n in GENERATED if n not in tracked_at(sha)]
    if reuse_only and missing:
        raise SystemExit(f'no release build of {sha[:12]} yet (tag {tag_of(sha)}): it is made by tools/deploy.sh --beta {sha[:12]}')
    tmp = tempfile.mkdtemp(prefix='flow-build-')
    tree = Path(tmp) / 'tree'
    try:
        git('worktree', 'add', '-q', '--detach', str(tree), sha)
        if not missing:
            log(f'{sha[:12]} still has the generated files in git: checking them, then it is released as it is')
            verify(tree)
            return sha
        log(f'building for {sha[:12]}: {", ".join(Path(n).name for n in missing)}')
        build(tree, front=any(n in FRONT for n in missing), guide=any(n in GUIDE for n in missing))
        verify(tree)
        git('add', '-f', '--', *missing, cwd=tree)
        subject = git('log', '-1', '--format=%s', sha)
        git('commit', '-q', '--no-verify', '-m', f'build {sha[:12]}: the files a release builds ({subject})'[:200], '-m',
            f'Source: {sha}\nBuilt by tools/build_release.py: {", ".join(missing)}', cwd=tree)
        build_sha = git('rev-parse', 'HEAD', cwd=tree)
        if not push:
            log(f'dry run: build {build_sha[:12]} made and checked, not pushed: {git("diff", "--stat", sha, build_sha, cwd=tree)}')
            return build_sha
        git('push', '-q', 'origin', f'{build_sha}:refs/tags/{tag_of(sha)}', cwd=tree)
        git('tag', '-f', tag_of(sha), build_sha)
        log(f'pushed {tag_of(sha)} = {build_sha[:12]} (adds {len(missing)} files to {sha[:12]})')
        return build_sha
    finally:
        git('worktree', 'remove', '--force', str(tree), check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    if '--here' in argv or '--front' in argv:
        guide = '--here' in argv and not guide_is_current(ROOT)
        build(ROOT, front=True, guide=guide)
        log('next.js, next.css built' + ('; guide PDF printed' if guide else '; guide PDF already matches guide.md' if '--here' in argv else ''))
        return 0
    words = [a for a in argv if not a.startswith('--')]
    if len(words) != 1:
        raise SystemExit(__doc__)
    print(release(words[0], reuse_only='--reuse' in argv, push='--dry-run' not in argv))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
