#!/usr/bin/env bash
# Runs Flow's tests on the owner's MSI from the Mac, instead of on the Mac: the branch as it is now (committed or not)
# goes over SSH, tools/run_tests.py runs there, its output streams back, and the UI report and screenshots come back.
#
#   bash tools/msi-run.sh                          # before pushing: run_tests.py --changed --checks, the test files for
#                                                  # what this branch changed and CI's checks that need no browser
#   bash tools/msi-run.sh test_vocab test_next     # these website test files (names as in flow/tests), with the checks
#   bash tools/msi-run.sh --all                    # every website test file   } CI runs these on every pull request:
#   bash tools/msi-run.sh --ui phone desktop       # these UI groups           } only to look into a CI failure
#   bash tools/msi-run.sh --ui --shard 3/5         # anything else run_tests.py takes is passed through
#
# The rule (the owner, 2026-11-25: 96 test runs that day, most of them the UI and the whole suite run twice, here
# before pushing and again in CI): before pushing, only the default. The UI and the whole suite are CI's, the one gate
# before a merge; --ui and --all are for re-running what failed there. The checks (run_tests.py --checks, ~15 s:
# tools/release-files.txt, the CI setup, the front end, the guide's test) catch here what used to fail a CI round.
#
#   MSI_HOST (default msi-flow, the ~/.ssh/config entry)   MSI_RUN_JOBS (default 4: processes at once on the MSI)
#
# The exit status is run_tests.py's, so `bash tools/msi-run.sh && git push` works as before; 3 means the MSI could
# not be reached (switched off, asleep, Tailscale down): then run the same tests on the Mac.
#
# What goes over: a snapshot commit of the working tree, made in a throwaway index (`git add -A` there: the tracked
# files with their uncommitted changes, and new files .gitignore does not exclude). The real index, the working tree and
# the branch are not touched. Nothing ignored is sent (.env, *.pem, *.key, data/ … are in .gitignore), and the run
# stops before sending anything when a new file's name looks like a key or a secret. The snapshot is pushed, with the
# Mac's origin/main (which --changed compares against), to a bare repository on the MSI (~/msi-run/flow.git, cloned
# from GitHub the first time), checked out in a worktree of its own, and both are removed when the run ends.
#
# Sharing the MSI with CI (its runners, tools/msi-setup.sh): these runs start at nice 10 and idle I/O priority so CI's
# jobs keep theirs,
# use at most MSI_RUN_JOBS processes, keep their temporary files in a folder of their own under /tmp, and at most
# two run at once, four while CI has at most 3 jobs there (the next waits its turn, first come first served). Needs: `ssh msi-flow` working (Tailscale), and the MSI set up
# with tools/msi-setup.sh (Python 3.11 venv with Playwright, Google Chrome, the Chinese fonts).
set -euo pipefail

HOST=${MSI_HOST:-msi-flow}
JOBS=${MSI_RUN_JOBS:-4}
# Never wait for a password or a host-key question: there is no terminal to answer them in a session.
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10)
export GIT_SSH_COMMAND='ssh -o BatchMode=yes -o ConnectTimeout=10'
ROOT=$(git rev-parse --show-toplevel)
cd "$ROOT"
[ -f tools/run_tests.py ] || { echo "msi-run: run it in a checkout of Jasame/Flow" >&2; exit 2; }

args=("$@")
if ! "${SSH[@]}" "$HOST" true 2>/dev/null; then
  echo "msi-run: MSI 连不上（关机、睡眠或 Tailscale 断了）: $HOST; run the tests here instead: python3 tools/run_tests.py ${*:---changed}" >&2
  exit 3
fi
# --no-checks: leave out run_tests.py --checks (CI's checks that need no browser), which every website run gets
checks=1; kept=()
for a in ${args[@]+"${args[@]}"}; do if [ "$a" = --no-checks ]; then checks=; else kept+=("$a"); fi; done
args=(${kept[@]+"${kept[@]}"})
case " ${args[*]-} " in
  *" --ui "*|*" --all "*) echo "msi-run: 界面测试和全套交给 CI；只在查 CI 失败时用 --ui / --all（推送前默认那一步就够了）" >&2 ;;
esac
if [ ${#args[@]} -eq 0 ]; then args=(--changed); elif [ "${args[0]}" = --all ]; then args=("${args[@]:1}"); fi
case " ${args[*]-} " in *" --ui "*) ;; *) if [ -n "$checks" ]; then args+=(--checks); fi ;; esac

# New files that would go over: refuse names that look like keys or secrets, even if .gitignore missed them.
new=$(git ls-files --others --exclude-standard)
bad=$(printf '%s\n' "$new" | grep -iE '(^|/)(\.env([.].*)?|id_(rsa|ed25519|ecdsa|dsa)[^/]*|[^/]*\.(pem|key|p12|pfx|jks|keystore)|[^/]*(secret|credential|token)[^/]*)$' || true)
if [ -n "$bad" ]; then
  printf 'msi-run: not sending; these new files look like keys or secrets (add them to .gitignore or move them):\n%s\n' "$bad" >&2
  exit 2
fi
[ -n "$new" ] && printf 'msi-run: new files going over too:\n%s\n' "$new" | sed 's/^/  /'

# The snapshot: a commit of the working tree, made in a throwaway index.
idx=$(mktemp "${TMPDIR:-/tmp}/msi-run-index.XXXXXX")
trap 'rm -f "$idx"' EXIT
cp "$(git rev-parse --git-path index)" "$idx" 2>/dev/null || true
GIT_INDEX_FILE=$idx git add -A
tree=$(GIT_INDEX_FILE=$idx git write-tree)
branch=$(git branch --show-current || true)
snap=$(git commit-tree "$tree" -p HEAD -m "msi-run snapshot of ${branch:-HEAD} at $(git rev-parse --short HEAD)")
id="$(date +%Y%m%d-%H%M%S)-$(printf '%s' "${branch:-head}" | tr -c 'A-Za-z0-9._-' '-' | cut -c1-40)-$$"

"${SSH[@]}" "$HOST" 'set -e; mkdir -p ~/msi-run; [ -d ~/msi-run/flow.git ] || git clone -q --bare https://github.com/Jasame/Flow.git ~/msi-run/flow.git'
pushes=("$snap:refs/msi-run/$id")
git rev-parse -q --verify refs/remotes/origin/main >/dev/null && pushes+=("+refs/remotes/origin/main:refs/remotes/origin/main")
git push -q --no-verify "$HOST:msi-run/flow.git" "${pushes[@]}"
echo "msi-run: $id ($(git rev-parse --short HEAD)${branch:+ on $branch}) -> $HOST: run_tests.py ${args[*]-}"

set +e
"${SSH[@]}" "$HOST" "bash -s -- $(printf '%q ' "$id" "$JOBS" ${args[@]+"${args[@]}"})" <<'REMOTE'
set -uo pipefail
id=$1; jobs=$2; shift 2
base=~/msi-run; repo=$base/flow.git; w=$base/w/$id; out=$base/out/$id
venv=~/.local/share/flow-ci/venv
mkdir -p "$base/w" "$base/out"
# leftovers of runs stopped from the Mac (the cleanup below only starts with a slot): snapshots, worktrees and outputs
# older than a day go; a run waiting or going now is younger than that
old=$(( $(date +%s) - 86400 ))
git -C "$repo" for-each-ref --format='%(committerdate:unix) %(refname)' refs/msi-run/ | while read -r t ref; do
  [ "$t" -lt "$old" ] && git -C "$repo" update-ref -d "$ref"
done
find "$base/w" "$base/out" -mindepth 1 -maxdepth 1 -mtime +0 -exec rm -rf {} + 2>/dev/null
git -C "$repo" worktree prune
# at most 2 runs at once (4 while CI is light, below): hold one lock file for the whole run. First come, first served (语流 B5,
# 2026-11-25: a run waited 37 minutes while later ones went first): a waiting run leaves a ticket in queue/, and only
# the oldest ticket tries for a place; a ticket whose run has gone (stopped from the Mac) is dropped, so none blocks.
mkdir -p "$base/queue"
ticket=$base/queue/$(date +%s%N)-$$; : > "$ticket"
trap 'rm -f "$ticket"' EXIT
slot=; said=
while [ -z "$slot" ]; do
  for q in "$base/queue"/*; do [ -e "$q" ] || continue; kill -0 "${q##*-}" 2>/dev/null || rm -f "$q"; done
  # places: 4 while CI has at most 3 jobs on the MSI (its runners' Runner.Worker processes), else 2 (语流 A4, 18:03: CI
  # idle, CPU at 20 %, and 4 runs waiting); these runs are at nice 10 and idle I/O, so CI's jobs come first anyway
  places=2; [ "$(ps -eo comm | grep -c '^Runner.Worker')" -le 3 ] && places=4
  if [ "$(ls "$base/queue" | sort | head -1)" = "${ticket##*/}" ]; then
    for s in $(seq 1 "$places"); do exec 9>"$base/slot-$s.lock"; if flock -n 9; then slot=$s; break; fi; done
  fi
  if [ -z "$slot" ]; then
    [ -n "$said" ] || echo "msi-run: $places runs are going on the MSI; $(ls "$base/queue" | sort | awk -v me="${ticket##*/}" '$0 < me' | wc -l) more waiting ahead of this one…"
    said=1; sleep 5
  fi
done
rm -f "$ticket"
tmp=$(mktemp -d /tmp/msi-run.XXXXXX)
cleanup() {
  cd "$base"
  git -C "$repo" worktree remove --force "$w" >/dev/null 2>&1 || rm -rf "$w"
  git -C "$repo" worktree prune
  git -C "$repo" update-ref -d "refs/msi-run/$id" 2>/dev/null
  rm -rf "$tmp"
}
trap cleanup EXIT
git -C "$repo" worktree add -q --detach "$w" "refs/msi-run/$id" 9>&- || exit 4
cd "$w"
extra=()
case " $* " in *" --jobs "*) ;; *) extra+=(--jobs "$jobs") ;; esac
case " $* " in *" --ui "*) case " $* " in *" --out "*) ;; *) extra+=(--out "$out") ;; esac ;; esac
# </dev/null: bash -s reads this script from stdin, so a child reading stdin would eat the lines below.
# 9>&-: the lock is fd 9; a test process left running (Chrome, ui_server) must not keep the slot taken.
TMPDIR=$tmp nice -n 10 ionice -c 3 "$venv/bin/python" tools/run_tests.py "$@" "${extra[@]}" </dev/null 9>&-
rc=$?
[ -d "$out" ] && [ -n "$(ls -A "$out" 2>/dev/null)" ] && echo "msi-run-out:$out"
exit $rc
REMOTE
rc=$?
set -e

# Bring a UI run's report and screenshots back, then free the MSI's copy.
if "${SSH[@]}" "$HOST" "test -d ~/msi-run/out/$id" 2>/dev/null; then
  mkdir -p msi-out
  rsync -a -e "$GIT_SSH_COMMAND" "$HOST:msi-run/out/$id" msi-out/ && "${SSH[@]}" "$HOST" "rm -rf ~/msi-run/out/$id" \
    && echo "msi-run: UI report and screenshots in msi-out/$id/"
fi
exit $rc
