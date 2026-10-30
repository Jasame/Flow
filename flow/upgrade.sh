#!/usr/bin/env bash
set -euo pipefail
FLOW_SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
FLOW_TARGET_DIR=/www/wwwroot/flow
FLOW_PYTHON=/usr/bin/python3.11
if [ "$(id -u)" != 0 ]; then echo '请在宝塔 root 终端运行。'; exit 1; fi
if [ "$FLOW_SOURCE_DIR" = "$FLOW_TARGET_DIR" ]; then echo '请先把新版解压到 /tmp/flow-v34，再运行其中的 upgrade.sh。'; exit 1; fi
if [ ! -f "$FLOW_TARGET_DIR/app.py" ] || [ ! -f "$FLOW_SOURCE_DIR/content_v03.py" ]; then echo '源目录或现有程序目录不正确，已停止。'; exit 1; fi
"$FLOW_PYTHON" -c 'import sqlite3, ssl'
FLOW_BACKUP_DIR="/www/backup/flow/v34-$(date +%Y%m%d-%H%M%S)-$$"
install -d -m 700 "$FLOW_BACKUP_DIR"
umask 077
# Preserve code and database before replacing application files.
tar -czf "$FLOW_BACKUP_DIR/source-before.tar.gz" --exclude='./data' --exclude='./.venv' --exclude='*/__pycache__' -C "$FLOW_TARGET_DIR" .
FLOW_NGINX=/www/server/nginx/sbin/nginx
if [ ! -x "$FLOW_NGINX" ]; then FLOW_NGINX="$(command -v nginx)"; fi
cp /etc/flow.env "$FLOW_BACKUP_DIR/flow.env"
cp /www/server/panel/vhost/nginx/flowlang.cn.conf "$FLOW_BACKUP_DIR/vhost.conf"
FLOW_AUDIO_ROUTE=/www/server/panel/vhost/nginx/extension/flowlang.cn/flow-studio.conf
if [ -f "$FLOW_AUDIO_ROUTE" ]; then cp "$FLOW_AUDIO_ROUTE" "$FLOW_BACKUP_DIR/audio-route.conf"; fi
if systemctl is-active --quiet flow-daily.timer; then touch "$FLOW_BACKUP_DIR/daily-was-active"; fi
if [ -f /etc/systemd/system/flow-daily.service ]; then cp /etc/systemd/system/flow-daily.service "$FLOW_BACKUP_DIR/daily.service"; fi
if [ -f /etc/systemd/system/flow-daily.timer ]; then cp /etc/systemd/system/flow-daily.timer "$FLOW_BACKUP_DIR/daily.timer"; fi
systemctl stop flow-daily.timer flow-daily.service 2>/dev/null || true
systemctl stop flow
FLOW_DONE=0
flow_rollback() {
  if [ "$FLOW_DONE" = 1 ]; then return; fi
  echo "升级检查失败，恢复升级前程序与数据库。备份：$FLOW_BACKUP_DIR"
  systemctl stop flow-daily.timer flow-daily.service || true
  systemctl stop flow || true
  tar -xzf "$FLOW_BACKUP_DIR/source-before.tar.gz" -C "$FLOW_TARGET_DIR"
  if [ -f "$FLOW_BACKUP_DIR/flow-before.sqlite3" ]; then
    rm -f "$FLOW_TARGET_DIR/data/flow.sqlite3-wal" "$FLOW_TARGET_DIR/data/flow.sqlite3-shm"
    install -o www -g www -m 600 "$FLOW_BACKUP_DIR/flow-before.sqlite3" "$FLOW_TARGET_DIR/data/flow.sqlite3"
  fi
  cp "$FLOW_BACKUP_DIR/flow.env" /etc/flow.env
  cp "$FLOW_BACKUP_DIR/vhost.conf" /www/server/panel/vhost/nginx/flowlang.cn.conf
  if [ -f "$FLOW_BACKUP_DIR/audio-route.conf" ]; then
    cp "$FLOW_BACKUP_DIR/audio-route.conf" "$FLOW_AUDIO_ROUTE"
  else
    "$FLOW_PYTHON" -c 'from pathlib import Path; Path("/www/server/panel/vhost/nginx/extension/flowlang.cn/flow-studio.conf").unlink(missing_ok=True)'
  fi
  if "$FLOW_NGINX" -t; then "$FLOW_NGINX" -s reload || true; fi
  if [ -f "$FLOW_BACKUP_DIR/daily.service" ]; then cp "$FLOW_BACKUP_DIR/daily.service" /etc/systemd/system/flow-daily.service; fi
  if [ -f "$FLOW_BACKUP_DIR/daily.timer" ]; then cp "$FLOW_BACKUP_DIR/daily.timer" /etc/systemd/system/flow-daily.timer; fi
  systemctl daemon-reload
  systemctl start flow || true
  if [ -f "$FLOW_BACKUP_DIR/daily-was-active" ]; then systemctl start flow-daily.timer || true; fi
}
trap flow_rollback EXIT
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
install -d -m 755 "$FLOW_TARGET_DIR/corpus_data"
for name in ai_jobs.py vertex_native.py learning_insights.py ai_stream.py ai_help_service.py ai_check.py AI-VERIFICATION.md foundation_service.py pedagogy_service.py content_v30.py corpus_data/revised-packs.json loop_service.py practice_service.py content_v09.py corpus_data/graded-packs.json reference_service.py corpus_data/yl-reference.json app.py seed.py content_v03.py content_v05.py content_v06.py content_v07.py content_v08.py corpus_service.py daily_service.py knowledge_service.py event_service.py lexicon_service.py graph_service.py adaptive_service.py coach_service.py growth_service.py quality_service.py placement_content.py lab_service.py audio_validation.py studio_setup.py learning_service.py account_service.py ops.py chat_service.py vertex_auth.py requirements-vertex.txt README.md ARCHITECTURE.md DESIGN.md UI-INTEGRATION.md GRAPH-INTEGRATION.md SOURCE-CORPUS.md GRADED-CORPUS.md MOBILE-UI.md LEARNING-REDESIGN.md VERTEX_SETUP.md UPGRADE.md nginx-location.conf flow.service flow.env.example; do
  install -m 644 "$FLOW_SOURCE_DIR/$name" "$FLOW_TARGET_DIR/$name"
done
install -d -m 755 "$FLOW_TARGET_DIR/public"
for name in ai-live.js ai-live.css index.html style.css layout.css app.js tutor.js advanced.js studio.js knowledge.js adaptive.js adaptive.css coach.js coach.css growth.js growth.css design-bridge.css atlas.js atlas.css reference.js reference.css practice.js practice.css mobile.js mobile.css foundation.js foundation.css continuity.js continuity.css; do
  install -m 644 "$FLOW_SOURCE_DIR/public/$name" "$FLOW_TARGET_DIR/public/$name"
done
install -d -m 755 "$FLOW_TARGET_DIR/tests"
for flow_test in "$FLOW_SOURCE_DIR"/tests/*.py "$FLOW_SOURCE_DIR"/tests/*.cjs; do
  if [ -f "$flow_test" ]; then install -m 644 "$flow_test" "$FLOW_TARGET_DIR/tests/"; fi
done
install -m 644 "$FLOW_SOURCE_DIR/flow-backup.service" /etc/systemd/system/flow-backup.service
install -m 644 "$FLOW_SOURCE_DIR/flow-backup.timer" /etc/systemd/system/flow-backup.timer
install -m 644 "$FLOW_SOURCE_DIR/flow-daily.service" /etc/systemd/system/flow-daily.service
install -m 644 "$FLOW_SOURCE_DIR/flow-daily.timer" /etc/systemd/system/flow-daily.timer
systemctl daemon-reload
"$FLOW_PYTHON" "$FLOW_TARGET_DIR/studio_setup.py"
"$FLOW_NGINX" -t
"$FLOW_NGINX" -s reload
# No dependency changes are required for the current core or Vertex integration.
systemctl start flow
for FLOW_ATTEMPT in {1..10}; do
  if curl -fsS --max-time 3 http://127.0.0.1:8090/api/health 2>/dev/null | "$FLOW_PYTHON" -c 'import json,sys; d=json.load(sys.stdin); assert d.get("ok") and d.get("version")=="3.4"' 2>/dev/null; then
    /usr/bin/python3.11 "$FLOW_TARGET_DIR/ops.py" backup
    systemctl enable --now flow-backup.timer
    systemctl enable --now flow-daily.timer
    FLOW_DONE=1
    echo "Flow v3.4 已启动。备份：$FLOW_BACKUP_DIR"
    echo '请打开 https://flowlang.cn，按 Ctrl+F5 强制刷新。'
    exit 0
  fi
  sleep 1
done
journalctl -u flow -n 30 --no-pager
exit 1
