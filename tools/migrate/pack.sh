#!/bin/bash
# 在旧服务器上打包 Flow，交给新服务器的 unpack.sh。旧网站照常运行，不停服务、不改任何东西。
#
#   bash pack.sh            全量包：程序、录音、配置、凭据、后台服务、自动部署、Python、数据库快照、宝塔站点配置（参考）
#   bash pack.sh --db-only  只打数据库快照：切换那天停服后用，几秒钟
#
# 包里有密钥（/etc/flow.env、AI 凭据），权限是 600。只在两台服务器之间直接传（scp / rsync），
# 不要下载到电脑、不要发到聊天里；新服务器解包后删掉。
# PREFIX 只用于本地演练（把一个目录当成根目录），在真服务器上不要设置。
set -euo pipefail
P=${PREFIX:-}
DB_ONLY=0; [ "${1:-}" = --db-only ] && DB_ONLY=1
if [ -z "$P" ] && [ "$(id -u)" != 0 ]; then echo '请用 root 运行'; exit 1; fi
F=$P/www/wwwroot/flow
[ -f "$F/app.py" ] || { echo "找不到 $F/app.py，这台不是 Flow 服务器？"; exit 1; }

# Flow 正在用的 Python（数据库快照也用它做）
PY=''
if [ -z "$P" ]; then
  PID=$(systemctl show -p MainPID --value flow 2>/dev/null || true)
  [ -n "$PID" ] && [ "$PID" != 0 ] && PY=$(readlink "/proc/$PID/exe" 2>/dev/null || true)
fi
[ -z "$PY" ] && PY=$(grep -oE '^ExecStart=[^ ]+' "$P/etc/systemd/system/flow.service" 2>/dev/null | cut -d= -f2 || true)
[ -n "$PY" ] && [ -x "$P$PY" ] || PY=$(command -v python3)
[ -x "$P$PY" ] && PYX="$P$PY" || PYX="$PY"

STAMP=$(date +%Y%m%d-%H%M%S)
STAGE=$P/root/flow-migrate-stage
SUFFIX=; if [ $DB_ONLY = 1 ]; then SUFFIX=-db; fi
OUT=$P/root/flow-migrate-$STAMP$SUFFIX.tar.gz
rm -rf "$STAGE"; mkdir -p "$STAGE"; chmod 700 "$STAGE"
trap 'rm -rf "$STAGE"' EXIT
umask 077

# 1. 数据库：在线一致快照（SQLite backup），再做完整性检查；失败就停下，不出包
"$PYX" - "$F/data/flow.sqlite3" "$STAGE/flow.sqlite3" <<'PYEOF'
import sqlite3, sys
src, dst = sys.argv[1], sys.argv[2]
with sqlite3.connect('file:' + src + '?mode=ro', uri=True) as a, sqlite3.connect(dst) as b:
    a.backup(b)
with sqlite3.connect(dst) as c:
    ok = c.execute('PRAGMA integrity_check').fetchone()[0]
    users = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
if ok != 'ok':
    sys.exit('数据库快照完整性检查失败：' + ok)
print(f'数据库快照完整：{users} 个账号')
PYEOF
date +%s > "$STAGE/created"

if [ $DB_ONLY = 1 ]; then
  tar -czpf "$OUT" -C "${P:-/}" "${STAGE#$P/}"
else
  # 2. 宝塔的站点配置和证书只作参考：新服务器上在宝塔里重建站点时照着填，解包不会覆盖新面板的配置
  mkdir -p "$STAGE/reference"
  [ -d "$P/www/server/panel/vhost/nginx" ] && cp -a "$P/www/server/panel/vhost/nginx" "$STAGE/reference/nginx"
  [ -d "$P/www/server/panel/vhost/cert" ] && cp -a "$P/www/server/panel/vhost/cert" "$STAGE/reference/cert"
  [ -z "$P" ] && bash "$(dirname "$0")/inventory.sh" > "$STAGE/reference/inventory.txt" 2>&1 || true
  echo "$PY" > "$STAGE/python"

  # 3. 要原样放到新服务器同一位置的东西
  LIST=$STAGE/list; : > "$LIST"
  add() { [ -e "$P$1" ] && echo "${1#/}" >> "$LIST" || echo "（没有，跳过）$1"; }
  add /www/wwwroot/flow
  add /etc/flow.env
  CRED=$(grep -E '^GOOGLE_APPLICATION_CREDENTIALS=' "$P/etc/flow.env" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
  [ -n "$CRED" ] && add "$CRED"
  for u in "$P"/etc/systemd/system/flow*; do [ -e "$u" ] && add "${u#$P}"; done
  add /root/claude-ops
  add /www/wwwroot/xmc.hk/flow
  # The self-contained Python the deploy tools run on (and often the app too), with its installed packages.
  [ -d "$P/opt/uv-python" ] && add /opt/uv-python
  echo "${STAGE#$P/}" >> "$LIST"
  tar -czpf "$OUT" -C "${P:-/}" --exclude='www/wwwroot/flow/data/flow.sqlite3*' --exclude='__pycache__' -T "$LIST"
fi

chmod 600 "$OUT"
echo
echo "打好了：$OUT（$(du -h "$OUT" | cut -f1)）"
echo "校验值：$(sha256sum "$OUT" 2>/dev/null | cut -d' ' -f1 || shasum -a 256 "$OUT" | cut -d' ' -f1)"
echo "传到新服务器（在这台服务器上执行，把 NEW_IP 换成新服务器的 IP）："
echo "  scp $OUT root@NEW_IP:/root/"
