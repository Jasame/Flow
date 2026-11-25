"""Make a desktop update from a Release build (desktop/README.md「自动更新」). The private key never comes here:
the owner signs the two files in their own terminal between the two steps.

  1. python3 tools/make_update.py prepare --version 0.1.1 --dmg <语流_…_universal.dmg> --setup <语流_…_x64-setup.exe> --out <dir>
     → <dir>/flow-mac-<v>.dmg            the Mac download (manual installs)
       <dir>/flow-mac-<v>.app.tar.gz     what the Mac app's updater downloads (the .app from the dmg)
       <dir>/flow-windows-<v>-setup.exe  the Windows download, which the updater runs as well
     and prints the two signing commands.
  2. The owner: npx tauri signer sign -f ~/.tauri/flow-updater.key <file>   (each asks for the key's password)
  3. python3 tools/make_update.py manifest --version 0.1.1 --dir <dir> [--notes "…"] [--base-url https://flowlang.cn/download/]
     → <dir>/latest.json (goes to https://flowlang.cn/desktop/latest.json) and <dir>/SHA256SUMS.txt
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile


def names(v):
    return {'dmg': f'flow-mac-{v}.dmg', 'tar': f'flow-mac-{v}.app.tar.gz', 'exe': f'flow-windows-{v}-setup.exe'}


def prepare(a):
    n = names(a.version)
    os.makedirs(a.out, exist_ok=True)
    shutil.copyfile(a.dmg, os.path.join(a.out, n['dmg']))
    shutil.copyfile(a.setup, os.path.join(a.out, n['exe']))
    with tempfile.TemporaryDirectory() as mnt:
        subprocess.run(['hdiutil', 'attach', '-nobrowse', '-readonly', '-mountpoint', mnt, a.dmg], check=True, capture_output=True)
        try:
            apps = [x for x in os.listdir(mnt) if x.endswith('.app')]
            if len(apps) != 1:
                sys.exit(f'expected one .app in the dmg, found {apps}')
            # the updater replaces the installed 语流.app with the one in this archive (top level: 语流.app). No Mac
            # metadata: macOS tar would add AppleDouble ._ entries, which the updater cannot unpack (tested 0.1.1)
            env = dict(os.environ, COPYFILE_DISABLE='1')
            subprocess.run(['tar', '--no-mac-metadata', '-czf', os.path.join(a.out, n['tar']), '-C', mnt, apps[0]], check=True, env=env)
        finally:
            subprocess.run(['hdiutil', 'detach', mnt], check=False, capture_output=True)
    print('ready in', a.out)
    print('now sign, in your own terminal (each asks for the key password):')
    for k in ('tar', 'exe'):
        print(f'  npx tauri signer sign -f ~/.tauri/flow-updater.key "{os.path.join(a.out, n[k])}"')


def manifest(a):
    n = names(a.version)
    base = a.base_url if a.base_url.endswith('/') else a.base_url + '/'
    plat = {}
    sig = lambda f: open(os.path.join(a.dir, f + '.sig'), encoding='utf-8').read().strip()
    if os.path.exists(os.path.join(a.dir, n['tar'] + '.sig')):
        mac = {'signature': sig(n['tar']), 'url': base + n['tar']}
        plat['darwin-aarch64'] = mac
        plat['darwin-x86_64'] = mac  # one universal app for both
    if os.path.exists(os.path.join(a.dir, n['exe'] + '.sig')):
        plat['windows-x86_64'] = {'signature': sig(n['exe']), 'url': base + n['exe']}
    if not plat:
        sys.exit('no .sig files: sign first (step 2)')
    doc = {
        'version': a.version,
        'notes': a.notes,
        'pub_date': datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z'),
        'platforms': plat,
    }
    with open(os.path.join(a.dir, 'latest.json'), 'w', encoding='utf-8') as f:
        json.dump(doc, f, ensure_ascii=False, indent=2)
        f.write('\n')
    lines = []
    for k in ('exe', 'dmg', 'tar'):
        p = os.path.join(a.dir, n[k])
        if os.path.exists(p):
            lines.append(f'{hashlib.sha256(open(p, "rb").read()).hexdigest()}  {n[k]}')
    with open(os.path.join(a.dir, 'SHA256SUMS.txt'), 'w') as f:
        f.write('\n'.join(lines) + '\n')
    print(json.dumps(doc, ensure_ascii=False, indent=2))
    print('\n'.join(lines))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('prepare')
    p.add_argument('--version', required=True)
    p.add_argument('--dmg', required=True)
    p.add_argument('--setup', required=True)
    p.add_argument('--out', required=True)
    m = sub.add_parser('manifest')
    m.add_argument('--version', required=True)
    m.add_argument('--dir', required=True)
    m.add_argument('--notes', default='')
    m.add_argument('--base-url', default='https://flowlang.cn/download/')
    a = ap.parse_args()
    prepare(a) if a.cmd == 'prepare' else manifest(a)


if __name__ == '__main__':
    main()
