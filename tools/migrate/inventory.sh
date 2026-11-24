#!/bin/bash
# 只读盘点：列出这台服务器上和 Flow 有关的东西。什么都不改，不显示任何密钥的值。
#   在旧服务器上：bash inventory.sh > inventory.txt
#   在新服务器上搭好之后也可以再跑一次，两份对比看有没有漏。
# PREFIX 只用于本地演练（把一个目录当成根目录），在真服务器上不要设置。
set -u
P=${PREFIX:-}
say() { printf '\n== %s\n' "$1"; }

say '系统'
grep -E '^PRETTY_NAME=' "$P/etc/os-release" 2>/dev/null | cut -d= -f2- | tr -d '"'
uname -m

say '网站目录（/www/wwwroot）'
ls -1 "$P/www/wwwroot" 2>/dev/null || echo '（没有）'

say 'nginx 站点配置（宝塔）'
ls -1 "$P/www/server/panel/vhost/nginx/"*.conf 2>/dev/null || echo '（没有）'
ls -1d "$P/www/server/panel/vhost/nginx/extension/"* 2>/dev/null

say '证书目录（宝塔）'
ls -1 "$P/www/server/panel/vhost/cert" 2>/dev/null || echo '（没有）'

say 'Flow 的 systemd 单元'
ls -1 "$P/etc/systemd/system" 2>/dev/null | grep -E '^flow' || echo '（没有）'
ls -1 "$P/etc/systemd/system/flow.service.d" 2>/dev/null

say 'Flow 正在用的 Python'
PY=''
if [ -z "$P" ]; then
  PID=$(systemctl show -p MainPID --value flow 2>/dev/null)
  [ -n "$PID" ] && [ "$PID" != 0 ] && PY=$(readlink "/proc/$PID/exe" 2>/dev/null)
fi
[ -z "$PY" ] && PY=$(grep -oE '^ExecStart=[^ ]+' "$P/etc/systemd/system/flow.service" 2>/dev/null | cut -d= -f2)
echo "${PY:-（找不到）}"
if [ -n "$PY" ] && [ -x "$P$PY" ]; then
  "$P$PY" -c 'import sys; print("版本", sys.version.split()[0])'
  "$P$PY" -c 'import google.auth; print("google-auth", google.auth.__version__)' 2>/dev/null || echo 'google-auth：没有安装（不用 Google AI 时不需要）'
fi

say '/etc/flow.env 里的设置名（只列名字，不显示值）'
grep -oE '^[A-Z_][A-Z0-9_]*' "$P/etc/flow.env" 2>/dev/null | sort | tr '\n' ' '; echo

say 'Google AI 凭据文件'
CRED=$(grep -E '^GOOGLE_APPLICATION_CREDENTIALS=' "$P/etc/flow.env" 2>/dev/null | cut -d= -f2- | tr -d '"')
if [ -n "$CRED" ]; then ls -l "$P$CRED" 2>/dev/null || echo "设置了 $CRED，但文件不存在"; else echo '（没有设置 GOOGLE_APPLICATION_CREDENTIALS）'; fi

say '大小'
du -sh "$P/www/wwwroot/flow" "$P/www/wwwroot/flow/data" "$P/www/wwwroot/flow/audio" "$P/root/claude-ops" "$P/opt/uv-python" "$P/www/backup/flow" 2>/dev/null

say '定时器'
if [ -z "$P" ]; then systemctl list-timers --all 2>/dev/null | grep -E 'flow' || echo '（没有）'; fi

say '监听的端口'
if [ -z "$P" ]; then ss -ltnp 2>/dev/null | grep -E 'python|nginx' || echo '（看不到）'; fi

say '自动部署的进度'
cat "$P/root/claude-ops/autodeploy/next" 2>/dev/null && echo '（下一个要处理的版本号）' || echo '（没有）'
