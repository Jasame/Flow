#!/usr/bin/env python3
"""Hand pack of new narration for 香港, until R2 serves it (tools/media/README.md).

    python3 tools/narration_pack.py <audio dir> <out dir> <name> <material id> [...]

<audio dir> is the master copy (~/Flow-media/tts/audio). The pack in <out dir> holds <name>.tar (every voice's .m4a
and timing .json of the given ids), ids.txt, SHA256SUMS and <name>.sh. Put the four files in /root/claude-ops/<name>/
on 香港 and run `bash /root/claude-ops/<name>/<name>.sh`; the log is /root/claude-ops/<name>.log and ends with
RESULT=DONE. The script checks the sha, refuses if any file already exists, backs up index.json, adds the ids to it
(every old entry kept as it was), checks one new file on 语流 (8090) and the 内测版 (8092), and prints how to undo.
Installing on 香港 needs the user's OK.
"""
import hashlib, os, re, subprocess, sys
from pathlib import Path

VOICES = ('us-f', 'us-m', 'uk-f', 'uk-m')
ID = re.compile(r'(?:v5|graded|graph|campus|travel|life|work|culture|science)-[a-z0-9]+(?:-[a-z0-9]+)*')  # = next_service.NARRATION_ID

SCRIPT = r'''#!/bin/bash
# {name}: narration for {n} materials x 4 voices ({files} files). Made by tools/narration_pack.py.
# Put {name}.tar, ids.txt, SHA256SUMS and this script in /root/claude-ops/{name}, then: bash /root/claude-ops/{name}/{name}.sh
exec > /root/claude-ops/{name}.log 2>&1
set -u
S=/root/claude-ops/{name}
A=$(grep -s '^FLOW_AUDIO_DIR=' /etc/flow.env | tail -1 | cut -d= -f2-); A=${{A:-/www/wwwroot/flow/audio}}
BK=/root/claude-ops/backup-{name}-$(date +%Y%m%d-%H%M%S)
L=/tmp/{name}.txt
date; echo "audio dir: $A"
cd $S && sha256sum -c --quiet SHA256SUMS && echo "sha ok" || {{ echo ABORT_SHA; exit 1; }}
tar -tf {name}.tar > $L || {{ echo ABORT_LIST; exit 1; }}
grep -qvE '^(us|uk)-(f|m)/(v5|graded|graph|campus|travel|life|work|culture|science)-[a-z0-9-]+\.(m4a|json)$' $L && {{ echo ABORT_NAMES; exit 1; }}
[ $(( $(wc -l < $L) )) -eq {files} ] || {{ echo ABORT_COUNT; exit 1; }}
while read -r f; do [ -e "$A/$f" ] && {{ echo "ABORT_EXISTS $f"; exit 1; }}; done < $L
mkdir -p $BK && cp -p $A/index.json $BK/index.json && cp $L $BK/added.txt && echo "backup $BK"
own=$(stat -c %u:%g $A/index.json)
tar -xf {name}.tar -C $A --no-same-owner --no-same-permissions || {{ echo ABORT_TAR; xargs -a $BK/added.txt -I{{}} rm -f "$A/{{}}"; exit 1; }}
while read -r f; do chown $own "$A/$f"; chmod 644 "$A/$f"; done < $BK/added.txt
python3 - "$A/index.json" "$S/ids.txt" <<'PY' || {{ echo ABORT_INDEX; cp -p $BK/index.json $A/index.json; exit 1; }}
import json, os, sys
path, ids = sys.argv[1], [l.strip() for l in open(sys.argv[2]) if l.strip()]
idx = json.load(open(path))
old = dict(idx)
for i in ids:
    idx[i] = ['us-f', 'us-m', 'uk-f', 'uk-m']
assert all(idx[k] == v for k, v in old.items())
open(path + '.new', 'w').write(json.dumps(idx, separators=(',', ':')))
os.replace(path + '.new', path)
print('index', len(old), '->', len(idx))
PY
chown $own $A/index.json; chmod 644 $A/index.json
c(){{ curl -s -m 15 -o /dev/null -w "%{{http_code}}" "$@"; }}
for port in 8090 8092; do
  echo "port $port: new file -> $(c -H 'Range: bytes=0-99' http://127.0.0.1:$port/audio/us-f/{probe}.mp4) (206 = served)"
done
echo "added $(wc -l < $BK/added.txt) files"
echo "undo: xargs -a $BK/added.txt -I{{}} rm -f \"$A/{{}}\"; cp -p $BK/index.json $A/index.json"
echo RESULT=DONE; date
'''


def main(argv):
    if len(argv) < 4:
        sys.exit(__doc__)
    src, out, name, ids = Path(argv[0]).expanduser(), Path(argv[1]), argv[2], argv[3:]
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]*', name):
        sys.exit('name: lower-case letters, digits and dashes')
    bad = [i for i in ids if not ID.fullmatch(i)]
    if bad:
        sys.exit('not narration ids: ' + ' '.join(bad))
    files = [f'{v}/{i}.{ext}' for i in ids for v in VOICES for ext in ('m4a', 'json')]
    missing = [f for f in files if not (src / f).is_file()]
    if missing:
        sys.exit('missing in the master copy: ' + ' '.join(missing[:10]))
    out.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, COPYFILE_DISABLE='1')  # no macOS ._ files in the tar
    subprocess.run(['tar', '-cf', str(out / f'{name}.tar'), *files], cwd=src, env=env, check=True)
    (out / 'ids.txt').write_text(''.join(i + '\n' for i in ids))
    (out / f'{name}.sh').write_text(SCRIPT.format(name=name, n=len(ids), files=len(files), probe=ids[0]))
    sums = ''.join(f'{hashlib.sha256((out / f).read_bytes()).hexdigest()}  {f}\n' for f in (f'{name}.tar', 'ids.txt'))
    (out / 'SHA256SUMS').write_text(sums)
    size = (out / f'{name}.tar').stat().st_size / 1e6
    print(f'{out}: {name}.tar ({len(files)} files, {size:.1f} MB), ids.txt, SHA256SUMS, {name}.sh')


if __name__ == '__main__':
    main(sys.argv[1:])
