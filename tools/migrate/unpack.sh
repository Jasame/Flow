#!/bin/bash
# 在新服务器上解开 pack.sh 打的包，把 Flow 放到和旧服务器完全相同的位置，并启动网站和备份。
# 不会启用自动部署（切换那天再开），也不会动宝塔的站点和证书（在宝塔里照 reference 重建）。
#
#   bash unpack.sh /root/flow-migrate-XXXX.tar.gz            全量（第一次）
#   bash unpack.sh /root/flow-migrate-XXXX-db.tar.gz --db    切换那天：只换数据库
#
# 前提：已经装好宝塔（有 www 用户和 nginx）、和旧服务器同样的 CPU 架构。
# PREFIX 只用于本地演练（把一个目录当成根目录），在真服务器上不要设置。
set -euo pipefail
P=${PREFIX:-}
PKG=${1:?用法：bash unpack.sh 包的路径 [--db]}
DB_ONLY=0; [ "${2:-}" = --db ] && DB_ONLY=1
FORCE=0; [ "${2:-}" = --force ] || [ "${3:-}" = --force ] && FORCE=1
if [ -z "$P" ] && [ "$(id -u)" != 0 ]; then echo '请用 root 运行'; exit 1; fi
[ -f "$PKG" ] || { echo "找不到 $PKG"; exit 1; }
F=$P/www/wwwroot/flow
STAGE=$P/root/flow-migrate-stage
run() { [ -z "$P" ] && "$@" || echo "（演练，跳过）$*"; }

if [ -z "$P" ]; then
  id www >/dev/null 2>&1 || { echo '没有 www 用户：先装宝塔面板（它会创建 www 用户和 nginx）'; exit 1; }
fi

if [ $DB_ONLY = 0 ]; then
  if [ -f "$F/data/flow.sqlite3" ] && [ $FORCE = 0 ]; then
    echo "$F/data/flow.sqlite3 已经存在：这台像是已经解过包。只换数据库请加 --db，确定要全部覆盖请加 --force。"; exit 1
  fi
  mkdir -p "${P:-/}"
  tar -xzpf "$PKG" -C "${P:-/}"
  echo '程序、录音、配置、凭据、后台服务、自动部署工具已放回原位置。'
  # The Python each service starts with must exist here too (the packed one under /opt/uv-python came along).
  for unit in "$P"/etc/systemd/system/flow*.service; do
    exe=$(grep -oE '^ExecStart=[^ ]+' "$unit" 2>/dev/null | cut -d= -f2)
    [ -n "$exe" ] && [ ! -x "$P$exe" ] && echo "注意：$(basename "$unit") 要用 $exe，这台服务器上没有。装上同版本的 Python，或把服务里的路径改成 /opt/uv-python 下的那个。"
  done
else
  run systemctl stop flow
  tar -xzpf "$PKG" -C "${P:-/}" root/flow-migrate-stage
fi

# 数据库：先检查快照，再换上，权限交给 www
PY=$(cat "$STAGE/python" 2>/dev/null || true)
[ -n "$PY" ] && [ -x "$P$PY" ] && PYX="$P$PY" || PYX=$(command -v python3)
mkdir -p "$F/data"
"$PYX" - "$STAGE/flow.sqlite3" <<'PYEOF'
import sqlite3, sys
with sqlite3.connect(sys.argv[1]) as c:
    ok = c.execute('PRAGMA integrity_check').fetchone()[0]
    users = c.execute('SELECT COUNT(*) FROM users').fetchone()[0]
if ok != 'ok':
    sys.exit('数据库快照完整性检查失败，没有换上：' + ok)
print(f'数据库快照完整：{users} 个账号')
PYEOF
rm -f "$F/data/flow.sqlite3-wal" "$F/data/flow.sqlite3-shm"
cp "$STAGE/flow.sqlite3" "$F/data/flow.sqlite3"
if [ -z "$P" ]; then
  chown -R www:www "$F/data"; chmod 700 "$F/data"; chmod 600 "$F/data/flow.sqlite3"
  chmod 600 /etc/flow.env
fi
echo "快照时间：$(date -d @"$(cat "$STAGE/created")" 2>/dev/null || cat "$STAGE/created")"

# 后台服务：网站、每日备份、每日任务。自动部署先不开，切换那天再开（避免两台服务器同时处理同一个版本）
run systemctl daemon-reload
run systemctl enable --now flow.service
for t in flow-backup.timer flow-daily.timer; do
  [ -e "$P/etc/systemd/system/$t" ] && run systemctl enable --now "$t"
done
run systemctl disable --now flow-autodeploy.timer 2>/dev/null || true

if [ -z "$P" ]; then
  sleep 5
  PORT=$(grep -E '^FLOW_PORT=' /etc/flow.env | cut -d= -f2 | tr -d '"'); PORT=${PORT:-8090}
  echo "网站：$(systemctl is-active flow)，健康检查：$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/api/health")（200 才对）"
fi
rm -rf "$STAGE/flow.sqlite3"
echo
[ $DB_ONLY = 1 ] && echo '数据库已换成最新快照，网站已重新启动。' || {
  echo '接下来（见 tools/migrate/README.md 第二步）：'
  echo '  1. 在宝塔里新建站点，照 /root/flow-migrate-stage/reference/nginx 里的配置填反向代理；'
  echo '  2. 申请 HTTPS 证书（用 Cloudflare DNS 验证，切换前就能申请）；'
  echo '  3. python3 check_ai.py 检查 AI；跑一遍线上自动测试；'
  echo '  4. 确认都通过后再按第三步切换。参考文件看完可以删：rm -rf /root/flow-migrate-stage'
}
