"""Manifest hash of what tools/flow-pull.sh will install for a commit, computed from git (not from the CDN).

usage: release_manifest.py <commit>          -> prints the sha256 to pass to flow-pull.sh
       release_manifest.py --tools <commit>  -> prints the TOOLS list of a release request (tools/deploy.sh)
The manifest is "<base64 sha256>  <path>" per file, sorted: release files under flow/ (tests excluded)
plus the xmc.hk admin page (xmc-admin/index.html, admin.js, admin.css).
TOOLS has the same form for what the server runs from a release before installing it (TOOL_FILES and every file
under tools/qa-audio/); REQUEST names its sha256 (tools=), so the request's signature covers these too."""
import base64, hashlib, subprocess, sys

TOOL_FILES = ('tools/flow-pull.sh', 'tools/flow-pull-rollback.sh', 'tools/flow-autodeploy.py', 'tools/qa_e2e.py')
TOOL_DIRS = ('tools/qa-audio/',)

git = lambda *a: subprocess.run(['git', *a], check=True, capture_output=True).stdout


def listing(commit, names):
    return ''.join(f"{base64.b64encode(hashlib.sha256(git('show', f'{commit}:{n}')).digest()).decode()}  {n}\n"
                   for n in sorted(names))


def tracked(commit):
    return set(git('ls-tree', '-r', '--name-only', commit).decode().split('\n')) - {''}


if __name__ == '__main__':
    if sys.argv[1:2] == ['--tools']:
        commit = sys.argv[2]
        have = tracked(commit)
        names = [n for n in TOOL_FILES if n in have] + [n for n in have if n.startswith(TOOL_DIRS)]
        sys.stdout.write(listing(commit, names))
        print(f'{len(names)} tool files', file=sys.stderr)
        sys.exit(0)
    commit = sys.argv[1]
    names = git('show', f'{commit}:tools/release-files.txt').decode().split()
    names = [n for n in names if n.startswith('flow/') and not n.startswith('flow/tests/')]
    names += [f'xmc-admin/{n}' for n in ('index.html', 'admin.js', 'admin.css') if f'xmc-admin/{n}' in tracked(commit)]
    manifest = listing(commit, names)
    print(hashlib.sha256(manifest.encode()).hexdigest())
    print(f'{len(names)} files', file=sys.stderr)
