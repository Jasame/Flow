#!/bin/bash
# The nightly whole-site check on the MSI (语流 A2, 2026-11-26): tools/nightly_check.py on the newest main.
#
# cron on the MSI (crontab -l):
#   0 1 * * * git -C $HOME/ci-cache/flow.git show main:tools/nightly-msi.sh > $HOME/nightly/run.sh && bash $HOME/nightly/run.sh
# so each night runs this file as it is on main. Code from the runners' local mirror (~/ci-cache/flow.git, kept current by
# ~/ci-cache/update.sh), Python from msi-run's venv (~/.local/share/flow-ci/venv: Playwright, the installed Chrome).
# Four of the 20 cores (taskset), the lowest CPU and disk priority, and nightly_check.py waits while a CI job runs.
# The report and the shots of what went wrong go to ~/nightly/publish/<date>/, read from the Mac over the LAN in the
# morning (ssh msi-flow cat ~/nightly/publish/$(date +%F)/report.md); a night's whole output is kept 7 days. Undo: remove the crontab line; `rm -rf ~/nightly`.
set -u
day=$(date +%F)
base=$HOME/nightly; out=$base/out/$day; w=$base/w; pub=$base/publish/$day
venv=$HOME/.local/share/flow-ci/venv
mkdir -p "$base/out" "$base/publish"
exec >>"$base/cron.log" 2>&1
echo "== $(date '+%F %T') nightly start"
"$HOME/ci-cache/update.sh"
rm -rf "${w:?}"
git clone -q --shared --branch main "$HOME/ci-cache/flow.git" "$w" || { echo "no checkout"; exit 1; }
cd "$w" || exit 1
echo "main $(git rev-parse --short HEAD)"
TMPDIR=$base/tmp; mkdir -p "$TMPDIR"; export TMPDIR
OMP_NUM_THREADS=2 taskset -c 16-19 nice -n 19 ionice -c 3 "$venv/bin/python" tools/nightly_check.py "$out" --deadline 06:30
# what is read in the morning: the report and the shots it names
rm -rf "${pub:?}"; mkdir -p "$pub"
cp "$out/report.md" "$out/summary.json" "$pub/" 2>/dev/null
grep -o '`[^`]*\.jpg`' "$out/report.md" 2>/dev/null | tr -d '`' | sort -u | while read -r f; do
  [ -f "$out/shots/$f" ] && cp "$out/shots/$f" "$pub/"
done
find "$base/out" "$base/publish" -mindepth 1 -maxdepth 1 -type d -mtime +7 -exec rm -rf {} +
rm -rf "${TMPDIR:?}"/* "${w:?}"
echo "== $(date '+%F %T') nightly done"
