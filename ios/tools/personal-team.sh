#!/bin/sh
# 免费账号装到自己的 iPhone 之前跑一次：找到 Xcode 里已登录的「Personal Team」，写进 ios/Config/Local.xcconfig
# （不提交），Bundle ID 用 cn.flowlang.app.beta.<缩写>，免得占用以后付费账号要用的 cn.flowlang.app.beta。
#   sh ios/tools/personal-team.sh lx
set -e
tag=$(printf '%s' "${1:-me}" | tr -cd 'a-zA-Z0-9' | tr 'A-Z' 'a-z')
[ -n "$tag" ] || tag=me
out="$(cd "$(dirname "$0")/.." && pwd)/Config/Local.xcconfig"
team=$(/usr/bin/python3 - <<'PY'
import os, plistlib, sys
p = os.path.expanduser('~/Library/Preferences/com.apple.dt.Xcode.plist')
try:
    d = plistlib.load(open(p, 'rb'))
except OSError:
    sys.exit(0)
teams = [t for ts in (d.get('IDEProvisioningTeamByIdentifier') or {}).values() for t in ts]
free = [t for t in teams if t.get('isFreeProvisioningTeam')] or teams
if free:
    print(free[0].get('teamID', ''))
PY
)
if [ -z "$team" ]; then
  echo "Xcode 里还没有登录 Apple ID：先在 Xcode → Settings → Apple Accounts 里登录，再运行一次。"
  exit 1
fi
cat > "$out" <<CFG
// 你自己的签名设置（免费 Personal Team），只在这台 Mac 上，不提交（ios/.gitignore）。由 ios/tools/personal-team.sh 生成。
DEVELOPMENT_TEAM = $team
FLOW_BUNDLE_ID = cn.flowlang.app.beta.$tag
CFG
echo "好了：Bundle ID 是 cn.flowlang.app.beta.$tag，团队用 Xcode 里已登录的 Personal Team。"
echo "现在打开 ios/Flow.xcodeproj，scheme 选 Flow-Beta，设备选你的 iPhone，点 ▶。"
