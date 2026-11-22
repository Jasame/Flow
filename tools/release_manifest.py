"""Manifest hash of what tools/flow-pull.sh will install for a commit, computed from git (not from the CDN).

usage: release_manifest.py <commit>     -> prints the sha256 to pass to flow-pull.sh
The manifest is "<base64 sha256>  <path>" per file, sorted: release files under flow/ (tests excluded)
plus the xmc.hk admin page (xmc-admin/index.html, admin.js, admin.css)."""
import base64, hashlib, subprocess, sys

commit = sys.argv[1]
git = lambda *a: subprocess.run(['git', *a], check=True, capture_output=True).stdout
names = git('show', f'{commit}:tools/release-files.txt').decode().split()
names = [n for n in names if n.startswith('flow/') and not n.startswith('flow/tests/')]
tracked = set(git('ls-tree', '-r', '--name-only', commit).decode().split('\n'))
names += [f'xmc-admin/{n}' for n in ('index.html', 'admin.js', 'admin.css') if f'xmc-admin/{n}' in tracked]
lines = [f"{base64.b64encode(hashlib.sha256(git('show', f'{commit}:{n}')).digest()).decode()}  {n}" for n in sorted(names)]
manifest = '\n'.join(lines) + '\n'
print(hashlib.sha256(manifest.encode()).hexdigest())
print(f'{len(lines)} files', file=sys.stderr)
