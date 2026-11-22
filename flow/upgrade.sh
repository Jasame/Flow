#!/usr/bin/env bash
set -euo pipefail
FLOW_SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FLOW_TARGET_DIR=/www/wwwroot/flow
FLOW_PYTHON=/usr/bin/python3.11
if [ "$(id -u)" != 0 ]; then echo '请在宝塔 root 终端运行。'; exit 1; fi
if [ "$FLOW_SOURCE_DIR" = "$FLOW_TARGET_DIR" ]; then echo '请先把新版解压到 /tmp/flow-v03，再运行其中的 upgrade.sh。'; exit 1; fi
if [ ! -f "$FLOW_TARGET_DIR/app.py" ] || [ ! -f "$FLOW_SOURCE_DIR/content_v03.py" ]; then echo '源目录或现有程序目录不正确，已停止。'; exit 1; fi
"$FLOW_PYTHON" -c 'import sqlite3, ssl'
FLOW_BACKUP_DIR="/www/backup/flow/v03-$(date +%Y%m%d-%H%M%S)-$$"
install -d -m 700 "$FLOW_BACKUP_DIR"
umask 077
# Preserve code and database before replacing application files.
tar -czf "$FLOW_BACKUP_DIR/source-before.tar.gz" --exclude='./data' --exclude='./.venv' --exclude='*/__pycache__' -C "$FLOW_TARGET_DIR" .
systemctl stop flow
FLOW_DONE=0
trap 'if [ "$FLOW_DONE" = 0 ]; then echo "升级未完成，备份目录：$FLOW_BACKUP_DIR。请保留错误输出。"; fi' EXIT
"$FLOW_PYTHON" - "$FLOW_TARGET_DIR/data/flow.sqlite3" "$FLOW_BACKUP_DIR/flow-before.sqlite3" <<'PY'
import sqlite3,sys
from pathlib import Path
if not Path(sys.argv[1]).is_file():
    raise SystemExit('未找到现有数据库，停止升级，避免创建空账号库。')
with sqlite3.connect(sys.argv[1]) as source:
    with sqlite3.connect(sys.argv[2]) as target:
        source.backup(target)
PY
# Copy application only: retain data/, .venv, /etc/flow.env and installed systemd unit.
for name in app.py seed.py content_v03.py vertex_auth.py requirements-vertex.txt README.md VERTEX_SETUP.md UPGRADE.md nginx-location.conf flow.service flow.env.example; do
  install -m 644 "$FLOW_SOURCE_DIR/$name" "$FLOW_TARGET_DIR/$name"
done
install -d -m 755 "$FLOW_TARGET_DIR/public"
for name in index.html style.css app.js; do
  install -m 644 "$FLOW_SOURCE_DIR/public/$name" "$FLOW_TARGET_DIR/public/$name"
done
# No dependency changes are required for the current core or Vertex integration.
systemctl start flow
for FLOW_ATTEMPT in {1..10}; do
  if curl -fsS --max-time 3 http://127.0.0.1:8090/api/session >/dev/null; then
    FLOW_DONE=1
    echo "Flow v0.3 已启动。备份：$FLOW_BACKUP_DIR"
    echo '请打开 https://flowlang.cn，按 Ctrl+F5 强制刷新。'
    exit 0
  fi
  sleep 1
done
journalctl -u flow -n 30 --no-pager
exit 1
