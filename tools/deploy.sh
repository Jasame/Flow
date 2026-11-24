#!/bin/bash
# Deploy the current commit to the Flow server and wait for the outcome.
#
#   tools/deploy.sh                    deploy HEAD, then run the end-to-end test on the server (real AI, about 25 calls)
#   tools/deploy.sh --no-e2e           deploy only
#   tools/deploy.sh [--no-e2e] <commit>  deploy a commit that is already on GitHub (the working tree may be dirty)
#   tools/deploy.sh --beta [--no-e2e] [<commit>]   the same for the 内测版 (flow.jasa.hk, its own data): versions
#                                      waiting for release go there first; tags b<N> on the release-beta branch
#   tools/deploy.sh --skip-beta <commit>  语流 without the 内测版 first: only when the owner says so (an urgent fix)
#
# Pushes HEAD. The files git does not keep (next.js, next.css, the guide PDF) are built for the commit by
# tools/build_release.py: --beta builds and checks them and pushes the build (the commit plus those files) as tag
# build-<sha12>; 语流 installs the same build commit, which must have been requested on the 内测版 first. Then it
# computes the build commit's manifest hash from git (tools/release_manifest.py), writes "<build sha> <manifest> [e2e]"
# to REQUEST on the release branch and tags it r<N+1> (语流, flowlang.cn) or b<N+1> (内测版). The server's timer for
# that site (tools/flow-autodeploy.py [--beta]) picks the tag up through jsDelivr within a few minutes, deploys
# with flow-pull.sh and reports at that site's /api/deploy-status.
set -euo pipefail
E2E=" e2e"; WANT=""; P=r; BRANCH=release; SITE=https://flowlang.cn; SKIPBETA=""
for a in "$@"; do case $a in --no-e2e) E2E="" ;; --beta) P=b; BRANCH=release-beta; SITE=https://flow.jasa.hk ;; --skip-beta) SKIPBETA=1 ;; *) WANT=$a ;; esac; done
STATUS_URL=${FLOW_STATUS_URL:-$SITE/api/deploy-status}
cd "$(git rev-parse --show-toplevel)"
python3 tools/build_dictionary.py --check || exit 1  # corpus_data/dictionary-flow.json must match its sources
if [ -n "$WANT" ]; then
  SHA=$(git rev-parse "$WANT^{commit}"); git fetch -q origin
  BR=$(git branch -r --contains "$SHA" | sed -n 's#^ *origin/##p' | grep -v '^HEAD' | head -1)
  [ -n "$BR" ] || { echo "$SHA is not on GitHub yet: push it first"; exit 1; }
else
  [ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "uncommitted changes: commit first (or pass a pushed commit)"; exit 1; }
  SHA=$(git rev-parse HEAD); BR=$(git rev-parse --abbrev-ref HEAD)
  git push -q origin "HEAD:refs/heads/$BR"
fi
# The 内测版 runs the commit's own flow-pull.sh: one from before the two sites (2026-11-24) would install into 语流.
if [ $P = b ] && ! git show "$SHA:tools/flow-pull.sh" | grep -qF 'F=${FLOW_DIR:-'; then
  echo "$SHA has the old flow-pull.sh (it would install into 语流): merge main (PR #25, the two sites) into it first"; exit 1
fi
# The build to install: made and checked now for the 内测版, the same one again for 语流 (both sites get the same bytes)
if [ $P = b ] || [ -n "$SKIPBETA" ]; then BUILD=$(python3 tools/build_release.py "$SHA") || exit 1
else BUILD=$(python3 tools/build_release.py --reuse "$SHA") || exit 1; fi
if [ $P = r ] && [ -z "$SKIPBETA" ]; then
  git fetch -q origin release-beta
  git log -p --format= origin/release-beta -- REQUEST | grep -q "^+$BUILD " || {
    echo "${BUILD:0:12} (for ${SHA:0:12}) was never requested on the 内测版: tools/deploy.sh --beta ${SHA:0:12} first"; exit 1; }
fi
MAN=$(python3 tools/release_manifest.py "$BUILD" 2>/dev/null)
[[ $MAN =~ ^[0-9a-f]{64}$ ]] || { echo "manifest failed"; exit 1; }
LAST=$(git ls-remote --tags origin "refs/tags/$P*" | sed -n "s#.*refs/tags/$P\([0-9][0-9]*\)\$#\1#p" | sort -n | tail -1)
N=$(( ${LAST:-0} + 1 ))
WT=$(mktemp -d)
trap 'git worktree remove --force "$WT" >/dev/null 2>&1 || rm -rf "$WT"' EXIT
# the request branch holds only REQUEST; the 内测版's starts from the release branch the first time
git fetch -q origin "$BRANCH" 2>/dev/null || git fetch -q origin "release:refs/remotes/origin/$BRANCH"
git worktree add -q --detach "$WT" "origin/$BRANCH"
FROM=""; [ "$BUILD" = "$SHA" ] || FROM=" = build of ${SHA:0:12}"
printf '%s %s%s\n# %s%s %s: %s%s\n# Format: <commit sha> <manifest sha256> [e2e]. Written by tools/deploy.sh, read by tools/flow-autodeploy.py.\n' \
  "$BUILD" "$MAN" "$E2E" "$P" "$N" "$BR" "$(git log -1 --format=%s "$SHA")" "$FROM" > "$WT/REQUEST"
git -C "$WT" add REQUEST
git -C "$WT" commit -qm "release $P$N: ${BUILD:0:12}$FROM ($BR)"
git -C "$WT" push -q origin "HEAD:refs/heads/$BRANCH"
git -C "$WT" tag "$P$N"
git -C "$WT" push -q origin "$P$N"
curl -s -m 20 -o /dev/null "https://purge.jsdelivr.net/gh/Jasame/Flow@$P$N/REQUEST" || true
echo "requested $P$N for ${BUILD:0:12}$FROM (manifest ${MAN:0:12}…) on $SITE${E2E:+, with end-to-end test}"
# Wait for the server (deploy ~1–3 min after the tag is visible; the test adds ~2 min)
deadline=$(( $(date +%s) + 2400 )); last=""
while [ "$(date +%s)" -lt "$deadline" ]; do
  s=$(curl -s -m 20 "$STATUS_URL" || true)
  line=$(printf '%s' "$s" | python3 -c '
import json, sys
try: d = json.load(sys.stdin)
except Exception: print("waiting"); sys.exit()
if d.get("tag") != sys.argv[1]: print("waiting"); sys.exit()
print(d.get("state"), d.get("result", ""), d.get("checks", "")[:120])' "$P$N")
  [ "$line" != "$last" ] && { echo "$(date +%T) $line"; last=$line; }
  case $line in done*) break ;; esac
  sleep 15
done
printf '%s' "$s" | python3 -c '
import json, sys
d = json.load(sys.stdin)
print(json.dumps(d, ensure_ascii=False, indent=1))
ok = d.get("result") in ("DEPLOYED", "NOTHING_TO_DO") and (not d.get("e2e_requested") or (d.get("e2e", {}).get("failed") == 0 and d.get("e2e", {}).get("cleanup_ok")))
sys.exit(0 if ok else 1)'
