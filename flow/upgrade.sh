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
install -d -m 755 "$FLOW_TARGET_DIR/corpus_data" "$FLOW_TARGET_DIR/corpus_data/v5" "$FLOW_TARGET_DIR/corpus_data/pilot" "$FLOW_TARGET_DIR/corpus_data/pilot/audio"
for name in ai_jobs.py vertex_native.py learning_insights.py ai_stream.py ai_help_service.py ai_check.py AI-VERIFICATION.md foundation_service.py pedagogy_service.py content_v30.py corpus_data/revised-packs.json loop_service.py practice_service.py content_v09.py corpus_data/graded-packs.json reference_service.py corpus_data/yl-reference.json corpus_data/ecdict-flow.json corpus_data/ECDICT-LICENSE.txt corpus_data/wordbooks-open.json corpus_data/NGSL-LICENSE.txt WORDBOOKS-OPEN.md app.py seed.py content_v03.py content_v05.py content_v06.py content_v07.py content_v08.py corpus_service.py daily_service.py knowledge_service.py event_service.py lexicon_service.py graph_service.py adaptive_service.py coach_service.py growth_service.py quality_service.py placement_content.py lab_service.py audio_validation.py studio_setup.py learning_service.py account_service.py ops.py chat_service.py vertex_auth.py requirements-vertex.txt README.md ARCHITECTURE.md DESIGN.md UI-INTEGRATION.md GRAPH-INTEGRATION.md SOURCE-CORPUS.md GRADED-CORPUS.md MOBILE-UI.md LEARNING-REDESIGN.md VERTEX_SETUP.md UPGRADE.md nginx-location.conf flow.service flow.env.example attempt_service.py auth_service.py content_subskills.py core_words.py corpus_import.py guest_first.py meeting_path.py meeting_service.py migration_35.py pilot_service.py settings_service.py state_service.py corpus_data/pilot/flow-pack-001.json corpus_data/pilot/pilot-001-audio.json corpus_data/pilot/audio/18593289706a0b4e622f.m4a corpus_data/pilot/audio/2c5c6c444fee70d0c859.m4a corpus_data/pilot/audio/3d2ec649a75a8b8242af.m4a corpus_data/pilot/audio/534fbc8e49b9dc00e6bf.m4a corpus_data/pilot/audio/5d3ac09d12b1ff6eda98.m4a corpus_data/pilot/audio/8db91967d4b2a6bedaa4.m4a corpus_data/pilot/audio/a6901c317bf6934158bf.m4a corpus_data/pilot/audio/a904bfaf7828b0877581.m4a corpus_data/pilot/audio/beb0a51ff56de9919d50.m4a corpus_data/pilot/audio/c0606b1a7c2575135d74.m4a corpus_data/pilot/audio/c67814163b74dcfcffbd.m4a corpus_data/pilot/audio/cbe83da54b5578a2889b.m4a survey_service.py flow_admin.py next_service.py ops_errors.py fsrs.py vocab_service.py NEXT.md content_v50.py corpus_data/v5/campus.A2.json corpus_data/v5/campus.B1.json corpus_data/v5/campus.B2.json corpus_data/v5/campus.C1.json corpus_data/v5/culture.A2.json corpus_data/v5/culture.B1.json corpus_data/v5/culture.B2.json corpus_data/v5/culture.C1.json corpus_data/v5/life.A2.json corpus_data/v5/life.B1.json corpus_data/v5/life.B2.json corpus_data/v5/life.C1.json corpus_data/v5/science.A2.json corpus_data/v5/science.B1.json corpus_data/v5/science.B2.json corpus_data/v5/science.C1.json corpus_data/v5/travel.A2.json corpus_data/v5/travel.B1.json corpus_data/v5/travel.B2.json corpus_data/v5/travel.C1.json corpus_data/v5/work.A2.json corpus_data/v5/work.B1.json corpus_data/v5/work.B2.json corpus_data/v5/work.C1.json corpus_data/v5/SPEC.md corpus_data/v5/campus.A2.2.json corpus_data/v5/campus.B1.2.json corpus_data/v5/campus.B2.2.json corpus_data/v5/campus.C1.2.json corpus_data/v5/culture.A2.2.json corpus_data/v5/culture.B1.2.json corpus_data/v5/culture.B2.2.json corpus_data/v5/culture.C1.2.json corpus_data/v5/life.A2.2.json corpus_data/v5/life.B1.2.json corpus_data/v5/life.B2.2.json corpus_data/v5/life.C1.2.json corpus_data/v5/science.A2.2.json corpus_data/v5/science.B1.2.json corpus_data/v5/science.B2.2.json corpus_data/v5/science.C1.2.json corpus_data/v5/travel.A2.2.json corpus_data/v5/travel.B1.2.json corpus_data/v5/travel.B2.2.json corpus_data/v5/travel.C1.2.json corpus_data/v5/work.A2.2.json corpus_data/v5/work.B1.2.json corpus_data/v5/work.B2.2.json corpus_data/v5/work.C1.2.json corpus_data/wordroots-flow.json corpus_data/irregular-flow.json corpus_data/meaning-fixes.json corpus_data/wordroots-zh.json corpus_data/dictionary-flow.json corpus_data/v5/campus.B2.3.json corpus_data/v5/campus.C1.3.json corpus_data/v5/culture.B2.3.json corpus_data/v5/culture.C1.3.json corpus_data/v5/life.B2.3.json corpus_data/v5/life.C1.3.json corpus_data/v5/science.B2.3.json corpus_data/v5/science.C1.3.json corpus_data/v5/travel.B2.3.json corpus_data/v5/travel.C1.3.json corpus_data/v5/work.B2.3.json corpus_data/v5/work.C1.3.json corpus_data/v5/culture.C1.4.json corpus_data/v5/campus.B1.3.json skills_service.py output_service.py import_service.py sounds.py grammar_more.py grammar_bank.py exam_service.py graph_links.py LEARNING-SYSTEM.md word_links.py scenarios.py easy_reading.py growth_report.py ability_radar.py user_guide.py media.py feedback_service.py field_service.py account_data.py slim.py; do
  install -m 644 "$FLOW_SOURCE_DIR/$name" "$FLOW_TARGET_DIR/$name"
done
install -d -m 755 "$FLOW_TARGET_DIR/public"
for name in literata.woff2 survey.html survey.js survey.css next.html next.js next.css sw.js manifest.webmanifest icon-192.png icon-512.png apple-touch-icon.png; do
  install -m 644 "$FLOW_SOURCE_DIR/public/$name" "$FLOW_TARGET_DIR/public/$name"
done
# the 操作指南: its source, screenshots and PDF (user_guide.py reads them)
install -d -m 755 "$FLOW_TARGET_DIR/public/guide"
for guide_file in "$FLOW_SOURCE_DIR"/public/guide/*; do
  if [ -f "$guide_file" ]; then install -m 644 "$guide_file" "$FLOW_TARGET_DIR/public/guide/"; fi
done
install -d -m 755 "$FLOW_TARGET_DIR/tests"
for flow_test in "$FLOW_SOURCE_DIR"/tests/*.py; do
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
