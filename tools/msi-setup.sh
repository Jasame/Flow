#!/usr/bin/env bash
# Makes the MSI's WSL2 Ubuntu 24.04 a test machine for Flow's GitHub Actions (self-hosted runners labelled msi), and
# checks it can run the tests. Safe to run again: whatever is already there is kept.
#
#   git clone https://github.com/Jasame/Flow.git ~/Flow && cd ~/Flow && bash tools/msi-setup.sh
#
# It asks for your Linux password (sudo) to install packages. It never asks for, reads or keeps a GitHub token, a key
# or a password of any service: registering the runners needs the token from the GitHub page, and the commands it prints
# at the end let you type that yourself.
#
# 1. packages: Python 3.11 (deadsnakes), Google Chrome (Google's signed apt repository), Chinese and emoji fonts (the
#    guide PDF and the pages), git, jq
# 2. a Python 3.11 venv with Playwright for the self-check (a CI job makes its own venv each time)
# 3. RUNNERS (default 6) runner folders ~/actions-runner/msi-1 … msi-N: GitHub's runner, sha256-checked, and a hook that
#    empties a job's workspace after every job
# 4. the self-check: the front end builds, the 操作指南 PDF prints with a Chinese font, two website test files and one UI
#    share pass (about 5 minutes; SKIP_CHECK=1 skips it)
#
# Why 6 runners: WSL has 16 processors (.wslconfig). A website share keeps 4 of them busy, a UI share about 2. A Tests
# run sends 7 shares here (2 website, 5 UI): 6 start at once (2×4 + 4×2 = 16) and the 7th when a website share ends.
# More would squeeze the UI tests, which wait on animations and time-outs. RUNNERS=4 for a smaller share of the PC.
set -euo pipefail
RUNNERS=${RUNNERS:-6}
REPO=$(cd "$(dirname "$0")/.." && pwd)
STATE=$HOME/.local/share/flow-ci
VENV=$STATE/venv
HOOK=$STATE/job-completed.sh
say() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" != 0 ] || { echo "run this as your own Linux user, not root (it uses sudo where it must)"; exit 1; }
grep -q 'VERSION_ID="24.04"' /etc/os-release || echo "note: written for Ubuntu 24.04; this is $(. /etc/os-release; echo "$PRETTY_NAME")"
[ -f "$REPO/tools/run_tests.py" ] || { echo "run it from a checkout of Jasame/Flow (bash tools/msi-setup.sh)"; exit 1; }
mkdir -p "$STATE" "$HOME/.cache/flow-ci"

say "1/4 packages"
sudo apt-get update -qq
sudo apt-get install -y -qq software-properties-common ca-certificates curl gnupg git jq fonts-noto-cjk fonts-noto-color-emoji >/dev/null
if ! command -v python3.11 >/dev/null; then
  sudo add-apt-repository -y ppa:deadsnakes/ppa >/dev/null
  sudo apt-get update -qq
fi
dpkg -s python3.11-venv >/dev/null 2>&1 || sudo apt-get install -y -qq python3.11 python3.11-venv >/dev/null
if [ ! -x /opt/google/chrome/chrome ]; then
  sudo install -d -m 0755 /etc/apt/keyrings
  curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | sudo gpg --dearmor --yes -o /etc/apt/keyrings/google-chrome.gpg
  echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/google-chrome.gpg] https://dl.google.com/linux/chrome/deb/ stable main" \
    | sudo tee /etc/apt/sources.list.d/google-chrome.list >/dev/null
  sudo apt-get update -qq
  sudo apt-get install -y -qq google-chrome-stable >/dev/null
fi
echo "python: $(python3.11 --version)   chrome: $(/opt/google/chrome/chrome --version)"
echo "fonts: $(fc-list :lang=zh family | grep -c 'Noto Sans CJK' || true) Noto Sans CJK faces"

say "2/4 Python venv for the self-check ($VENV)"
[ -x "$VENV/bin/python" ] || python3.11 -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip
"$VENV/bin/python" -m pip install --quiet -r "$REPO/tools/requirements-release.txt"
"$VENV/bin/python" -c 'import playwright, sys; print("playwright ok, python", sys.version.split()[0])'

say "3/4 runner folders: $RUNNERS × ~/actions-runner/msi-N"
cat > "$HOOK" <<'EOF'
#!/usr/bin/env bash
# After every job on this runner (ACTIONS_RUNNER_HOOK_JOB_COMPLETED, tools/msi-setup.sh): empty the job's workspace, so
# nothing of one job (a checkout, built files, screenshots) is left for the next. The runner clears _work/_temp itself.
ws=${GITHUB_WORKSPACE:-}
case "$ws" in
  "$HOME"/actions-runner/msi-*/_work/?*) find "$ws" -mindepth 1 -maxdepth 1 -exec rm -rf {} + ;;
esac
exit 0
EOF
chmod 755 "$HOOK"
if [ "$RUNNERS" -gt 0 ]; then
  rel=$(curl -fsSL https://api.github.com/repos/actions/runner/releases/latest)
  ver=$(jq -r .tag_name <<<"$rel"); ver=${ver#v}
  sha=$(jq -r .body <<<"$rel" | sed -n 's/.*<!-- BEGIN SHA linux-x64 -->\([0-9a-f]\{64\}\)<!-- END SHA linux-x64 -->.*/\1/p' | head -1)
  [[ $sha =~ ^[0-9a-f]{64}$ ]] || { echo "could not read the runner's sha256 from its release notes"; exit 1; }
  tgz=$HOME/.cache/flow-ci/actions-runner-linux-x64-$ver.tar.gz
  [ -f "$tgz" ] || curl -fsSL -o "$tgz" "https://github.com/actions/runner/releases/download/v$ver/actions-runner-linux-x64-$ver.tar.gz"
  echo "$sha  $tgz" | sha256sum -c --quiet - || { rm -f "$tgz"; echo "runner download does not match its sha256: removed, run again"; exit 1; }
  for i in $(seq 1 "$RUNNERS"); do
    d=$HOME/actions-runner/msi-$i
    mkdir -p "$d"
    if [ -f "$d/.runner" ]; then state="registered, kept"
    elif [ -x "$d/config.sh" ]; then state="unpacked, not registered yet"
    else tar -xzf "$tgz" -C "$d"; state="unpacked (runner $ver), not registered yet"; fi
    touch "$d/.env"
    grep -q '^ACTIONS_RUNNER_HOOK_JOB_COMPLETED=' "$d/.env" || echo "ACTIONS_RUNNER_HOOK_JOB_COMPLETED=$HOOK" >> "$d/.env"
    echo "msi-$i: $state"
  done
  sudo "$HOME/actions-runner/msi-1/bin/installdependencies.sh" >/dev/null
fi

if [ "${SKIP_CHECK:-}" != 1 ]; then
  say "4/4 self-check (about 5 minutes)"
  check_tmp=$(mktemp -d); export TMPDIR=$check_tmp
  cd "$REPO"
  "$VENV/bin/python" tools/build_release.py --here
  "$VENV/bin/python" - <<'EOF'
import sys
sys.path.insert(0, 'tools')
import build_release as b
fonts = b.pdf_fonts(b.ROOT / b.GUIDE[0])
print('guide PDF fonts:', ', '.join(fonts))
if not any(c.lower() in f.lower() for f in fonts for c in b.CHINESE_FONTS):
    sys.exit('the guide PDF has no Chinese font: is fonts-noto-cjk installed?')
EOF
  "$VENV/bin/python" tools/run_tests.py test_guide test_channels --jobs 4
  "$VENV/bin/python" tools/run_tests.py --ui --shard 2/5 --out "$check_tmp/ui-out"
  rm -rf "$check_tmp"
  echo "self-check passed"
fi

registered=0
for f in "$HOME"/actions-runner/msi-*/.runner; do [ -f "$f" ] && registered=$((registered + 1)); done
say "done: $registered of $RUNNERS runners registered"
if [ "$registered" -lt "$RUNNERS" ]; then
  cat <<EOF

Next: register the runners with GitHub (once). Open
  https://github.com/Jasame/Flow/settings/actions/runners/new
copy the token shown after --token in its "Configure" step, then paste this here. It asks for the token without
showing it, uses it for these runners, and forgets it; each runner then starts by itself with WSL (a systemd service).

read -rs -p "token: " T; echo
for i in \$(seq 1 $RUNNERS); do (cd ~/actions-runner/msi-\$i && [ -f .runner ] || { ./config.sh --url https://github.com/Jasame/Flow --token "\$T" --name msi-\$i --labels msi --work _work --unattended --replace && sudo ./svc.sh install && sudo ./svc.sh start; }); done; unset T

The runners then show as Idle under Settings → Actions → Runners. Tests still use GitHub's machines until the switch is
on (the repository variable, set once): gh variable set MSI_RUNNER --body on -R Jasame/Flow
EOF
fi
[ "$(ps -p 1 -o comm=)" = systemd ] || echo "note: systemd is not running in WSL; the runner services need it ([boot] systemd=true in /etc/wsl.conf, then wsl --shutdown)"
