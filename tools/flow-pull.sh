#!/bin/bash
# Deploy a pushed Flow commit on the server, which cannot reach GitHub but can reach jsDelivr.
#
#   bash flow-pull.sh <40-char commit sha> <manifest sha256> [--dry-run]
#
# 1. Lists the commit's files through jsDelivr (data.jsdelivr.com, sha256 per file; after a 404, by the build's tag
#    FLOW_TREE_REF, the same tree) and downloads every
#    release file under flow/ (from tools/release-files.txt at that commit, tests excluded) plus the
#    xmc.hk admin page, checking each against its listed sha256.
# 2. Builds a manifest ("<base64 sha256>  <path>" per line, sorted) and requires its sha256 to equal the
#    value given on the command line, computed beforehand from git with tools/release_manifest.py. So
#    what gets installed is exactly what was pushed, not merely what the CDN says.
# 3. Backs up the files it will replace and the database, installs only changed files, restarts flow,
#    runs health checks, and rolls back automatically if any check fails.
# Audio is not in git; it is still uploaded separately.
#
# Which site: 语流 (flowlang.cn) by default; the 内测版 (flow.jasa.hk) with FLOW_DIR=/www/wwwroot/flow-beta
# FLOW_SERVICE=flow-beta FLOW_URL=http://127.0.0.1:8092 FLOW_XMC= FLOW_ADMIN_URL= (set by flow-autodeploy.py --beta):
# no console files and no console checks there, its own log, backups and deployed-commit file.
SVC=${FLOW_SERVICE:-flow}
exec > >(tee -a "/root/claude-ops/$SVC-pull.log") 2>&1
set -u
SHA=${1:-}; WANT=${2:-}; DRY=${3:-}
REPO=Jasame/Flow; F=${FLOW_DIR:-/www/wwwroot/flow}; XMC=${FLOW_XMC-/www/wwwroot/xmc.hk/flow}; OPS=/root/claude-ops
U=${FLOW_URL:-http://127.0.0.1:8090}; AU=${FLOW_ADMIN_URL-http://127.0.0.1:8091}; HERE=$(cd "$(dirname "$0")" && pwd)
export FLOW_SERVICE=$SVC FLOW_URL=$U  # for the rollback script
[[ $SHA =~ ^[0-9a-f]{40}$ ]] || { echo "usage: flow-pull.sh <40-char sha> <manifest sha256> [--dry-run]"; exit 2; }
[[ $WANT =~ ^[0-9a-f]{64}$ ]] || { echo "need the manifest sha256 from tools/release_manifest.py"; exit 2; }
date; echo "pull $REPO@$SHA"
STAGE=$OPS/pull${SVC#flow}-${SHA:0:12}; BK=$OPS/backup-pull${SVC#flow}-$(date +%Y%m%d-%H%M%S)
PY=$(readlink /proc/$(systemctl show -p MainPID --value "$SVC")/exe 2>/dev/null); [ -x "$PY" ] || PY=/opt/uv-python/cpython-3.11.18-linux-x86_64-gnu/bin/python3.11
rm -rf "$STAGE"; mkdir -p "$STAGE"

"$PY" -I - "$STAGE" "$REPO" "$SHA" "$WANT" "$F" "$XMC" <<'PYEOF' || { echo ABORT_FETCH; exit 1; }
import base64, hashlib, json, os, re, sys, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
stage, repo, sha, want, flow_dir, xmc_dir = Path(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5], sys.argv[6]
# jsDelivr mirrors: connections to any one of them get reset now and then from mainland China. Every file is
# checked against its sha256, so whichever mirror answers is fine.
HOSTS = ['cdn.jsdelivr.net', 'fastly.jsdelivr.net', 'gcore.jsdelivr.net', 'testingcf.jsdelivr.net']
def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'flow-pull/1'}), timeout=45) as r:
        return r.read()
def get_any(path, rounds=4):
    last = None
    for k in range(rounds):
        for h in HOSTS:
            try:
                return fetch(f'https://{h}/gh/{repo}@{sha}/{path}')
            except Exception as e:
                last = e
        time.sleep(2 + 3 * k)
    raise RuntimeError(f'{path}: {last}')
# After a 404 for the commit's listing (jsDelivr can keep an early "not found" for hours: b34, 2026-11-25), the same tree
# by its tag (FLOW_TREE_REF=build-<sha12>, from REQUEST through flow-autodeploy.py). Files are still fetched by the commit.
alt = os.environ.get('FLOW_TREE_REF', '')
alt = alt if re.fullmatch(r'build-[0-9a-f]{12}', alt) else ''
def listing():
    last = None
    for k in range(6):
        for ref in ([sha, alt] if alt else [sha]):
            try:
                return json.loads(fetch(f'https://data.jsdelivr.com/v1/package/gh/{repo}@{ref}/flat'))['files']
            except Exception as e:
                last = e
                if not (isinstance(e, urllib.error.HTTPError) and e.code == 404):
                    break
        time.sleep(2 + 3 * k)
    raise RuntimeError(f'listing: {last}')
flat = {f['name'].lstrip('/'): f for f in listing()}
names = get_any('tools/release-files.txt').decode().split()
names = [n for n in names if n.startswith('flow/') and not n.startswith('flow/tests/')]
# The console's page files are checked on every site (they are part of the release's manifest), installed with 语流's only.
names += [f'xmc-admin/{n}' for n in ('index.html', 'admin.js', 'admin.css') if f'xmc-admin/{n}' in flat]
missing = [n for n in names if n not in flat]
if missing:
    sys.exit(f'not in the commit: {missing[:5]}')
LIVE = {'flow/': Path(flow_dir), **({'xmc-admin/': Path(xmc_dir)} if xmc_dir else {})}
def local(n):
    """The installed copy, when it is already byte-identical to the commit: nothing to download."""
    for prefix, root in LIVE.items():
        if n.startswith(prefix):
            f = root / n[len(prefix):]
            if f.is_file() and f.stat().st_size == flat[n]['size']:
                data = f.read_bytes()
                if base64.b64encode(hashlib.sha256(data).digest()).decode() == flat[n]['hash']:
                    return data
    return None
fetched = []
def one(n):
    data = local(n)
    if data is None:
        data = get_any(n)
        fetched.append(n)
    digest = base64.b64encode(hashlib.sha256(data).digest()).decode()
    if digest != flat[n]['hash'] or len(data) != flat[n]['size']:
        raise RuntimeError(f'{n}: content does not match the listing')
    out = stage / 'files' / n
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(data)
    return f'{digest}  {n}'
with ThreadPoolExecutor(6) as ex:
    lines = sorted(ex.map(one, sorted(names)), key=lambda l: l.split('  ', 1)[1])
manifest = '\n'.join(lines) + '\n'
(stage / 'MANIFEST').write_text(manifest)
got = hashlib.sha256(manifest.encode()).hexdigest()
print(f'{len(lines)} files verified ({len(fetched)} downloaded, the rest already installed); manifest {got}')
if got != want:
    sys.exit(f'manifest mismatch: expected {want}')
PYEOF

# What would change
CHANGED=(); NEWF=()
cd "$STAGE/files"
while IFS= read -r -d '' f; do
  rel=${f#./}
  case $rel in flow/*) dest=$F/${rel#flow/} ;; xmc-admin/*) [ -n "$XMC" ] || continue; dest=$XMC/${rel#xmc-admin/} ;; *) continue ;; esac
  if [ ! -e "$dest" ]; then
    # Only runtime files are added; docs, unit files and build tools are updated if present, never created.
    case $rel in flow/*/*.py|flow/tools/*) continue ;; flow/*.py|flow/public/*|flow/corpus_data/*|xmc-admin/*) ;; *) continue ;; esac
    NEWF+=("$dest"); CHANGED+=("$rel|$dest")
  elif ! cmp -s "$rel" "$dest"; then CHANGED+=("$rel|$dest"); fi
done < <(find . -type f -print0)
echo "${#CHANGED[@]} files to install (${#NEWF[@]} new)"
for x in "${CHANGED[@]}"; do echo "  ${x%%|*}"; done
[ "$DRY" = --dry-run ] && { echo RESULT=DRY_RUN; exit 0; }
[ ${#CHANGED[@]} -eq 0 ] && { echo RESULT=NOTHING_TO_DO; exit 0; }

# Backup and install
mkdir -p "$BK"
for x in "${CHANGED[@]}"; do dest=${x#*|}; [ -e "$dest" ] && { mkdir -p "$BK/files$(dirname "$dest")"; cp -p "$dest" "$BK/files$dest"; }; done
printf '%s\n' "${NEWF[@]}" > "$BK/new-files.txt"
"$PY" - "$F/data/flow.sqlite3" "$BK/flow-before.sqlite3" <<'PYEOF'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as a, sqlite3.connect(sys.argv[2]) as b: a.backup(b)
print('db backup ok')
PYEOF
chmod 600 "$BK/flow-before.sqlite3"
for x in "${CHANGED[@]}"; do src=${x%%|*}; dest=${x#*|}; mkdir -p "$(dirname "$dest")"; install -m 644 -o root -g root "$STAGE/files/$src" "$dest"; done
echo "installed; backup in $BK"
# 隐私说明: a deleted account is gone from every backup within 14 days. This site's own database copies older than that
# go (flow/ops.py prune-deploy; the daily backup does the same for 语流); the code files stay, for a rollback. Each site
# touches only its own folders (backup-pull-<date> for 语流, backup-pull-beta-<date> for the 内测版); the 内测版 only
# lists them unless FLOW_PRUNE_DRY_RUN=0.
case "$SVC" in flow) CH=prod;; flow-beta) CH=beta;; *) CH=;; esac
if [ -n "$CH" ] && [ -f "$F/ops.py" ]; then "$PY" "$F/ops.py" prune-deploy --channel "$CH" 2>&1 || true; fi

rollback() {
  echo "FAIL -> ROLLBACK"; journalctl -u "$SVC" -n 30 --no-pager
  bash "$HERE/flow-pull-rollback.sh" "$BK"
  echo RESULT=ROLLED_BACK; exit 1
}
# Flow serves each request on its own thread; glibc's per-thread malloc arenas fragment, so the process kept memory
# after load spikes (145 -> 233 MB in 8 h). Two arenas keep it compact. A drop-in, so the unit file stays untouched.
DROPIN=/etc/systemd/system/$SVC.service.d/60-flow-malloc.conf
printf '[Service]\nEnvironment=MALLOC_ARENA_MAX=2\n' > "$STAGE/malloc.conf"
if ! cmp -s "$STAGE/malloc.conf" "$DROPIN"; then mkdir -p "$(dirname "$DROPIN")"; install -m 644 "$STAGE/malloc.conf" "$DROPIN"; systemctl daemon-reload; echo "memory setting installed: $DROPIN"; fi
# Server voice (tts_service.py) keeps each sentence it makes in <audio>/tts, shared by both sites (the 内测版 reads 语流's
# audio folder). ProtectSystem=strict leaves that folder read-only unless the unit names it; the leading '-' keeps the
# unit starting even if the folder is missing. Without this every new sentence was paid for and lost (2026-11-24).
# FLOW_AUDIO_DIR as systemd reads the env file: quotes around the value, a trailing / and a CR dropped; anything but an
# absolute path means 语流's folder (语流 2, 2026-11-25: some values on 香港 are double-quoted).
audio_dir() {
  local v; v=$(sed -n 's/^FLOW_AUDIO_DIR=//p' "$1" 2>/dev/null | tail -1 | tr -d '\r')
  v=${v%\"}; v=${v#\"}; v=${v%\'}; v=${v#\'}; v=${v%/}
  case "$v" in /*) printf '%s\n' "$v" ;; *) printf '%s\n' /www/wwwroot/flow/audio ;; esac
}
AUD=$(audio_dir "/etc/$SVC.env")
install -d -o www -g www -m 755 "$AUD/tts"
TTSDROP=/etc/systemd/system/$SVC.service.d/61-flow-tts.conf
printf '[Service]\nReadWritePaths=-%s/tts\n' "$AUD" > "$STAGE/tts.conf"
if ! cmp -s "$STAGE/tts.conf" "$TTSDROP"; then mkdir -p "$(dirname "$TTSDROP")"; install -m 644 "$STAGE/tts.conf" "$TTSDROP"; systemctl daemon-reload; echo "voice folder writable: $TTSDROP"; fi
systemctl restart "$SVC"; sleep 7
c(){ curl -s -m 20 -o /dev/null -w "%{http_code}" "$@"; }
total=$(curl -s -m 20 "$U/api/next/library?featured=1" | "$PY" -c "import json,sys;print(json.load(sys.stdin).get('total',0))" 2>/dev/null)
mid=$(curl -s -m 20 "$U/api/next/library?featured=1" | "$PY" -c "import json,sys;print(json.load(sys.stdin)['items'][0]['id'])" 2>/dev/null)
checks="health=$(c $U/api/health) root=$(c $U/) oldlink=$(c "$U/?classic=1") home=$(c "$U/api/next/home?level=B1") graph=$(c $U/api/next/graph) material=$(c "$U/api/next/material?id=$mid") vocabtest=$(c $U/api/next/vocab/test) survey=$(c $U/survey) sw=$(c $U/sw.js)"
# The console's Access check (#258): with FLOW_ACCESS_AUD and FLOW_ACCESS_TEAM in the env file, the console answers only
# requests that carry the token Cloudflare Access signs, and nothing on this server has one. Then this check turns
# round: a request with the email header alone must get 403 (the console is up and does not take a bare header), and
# its pages are checked by opening xmc.hk/flow after the release. Without this every release after the switch would
# roll itself back. Values as systemd reads them: quotes, a CR and blanks dropped; the last line wins.
access_on() {
  local k v
  for k in FLOW_ACCESS_AUD FLOW_ACCESS_TEAM; do
    v=$(sed -n "s/^$k=//p" "$1" 2>/dev/null | tail -1 | tr -d '\r')
    v=${v%\"}; v=${v#\"}; v=${v%\'}; v=${v#\'}; v=${v//[[:space:]]/}
    [ -n "$v" ] || return 1
  done
}
if [ -n "$AU" ]; then
  if access_on "/etc/$SVC.env"; then checks="$checks admin_needs_token=$(c -H 'Cf-Access-Authenticated-User-Email: flow-pull@localhost' $AU/flow/api/overview)"
  else checks="$checks admin=$(c $AU/flow/api/overview) learning=$(c $AU/flow/api/learning)"; fi
fi
echo "flow: active=$(systemctl is-active "$SVC") featured=$total $checks"
[ "$(systemctl is-active "$SVC")" = active ] || rollback
for kv in $checks; do want=200; [ "${kv%%=*}" = admin_needs_token ] && want=403; [ "${kv#*=}" = "$want" ] || rollback; done
[ "${total:-0}" -gt 0 ] 2>/dev/null || rollback
echo "$SHA" > "$OPS/$SVC-deployed-commit"
echo "rollback later with: FLOW_SERVICE=$SVC FLOW_URL=$U bash $HERE/flow-pull-rollback.sh $BK"
echo RESULT=DEPLOYED; date
