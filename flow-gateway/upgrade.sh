#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo '请使用 sudo bash upgrade.sh'; exit 1; fi
flow_source="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -f /etc/flow-gateway.env ] || [ ! -f /opt/flow-gateway/gateway.py ]; then
  echo '未找到现有网关，请勿在宝塔服务器运行这个脚本。'; exit 1
fi
python3 -m py_compile "$flow_source/gateway.py" "$flow_source/audio_validation.py" "$flow_source/nginx_update.py"
flow_backup="/var/backups/flow-gateway-$(date +%Y%m%d-%H%M%S)-$$"
install -d -m 700 "$flow_backup"
cp /opt/flow-gateway/gateway.py "$flow_backup/gateway.py"
cp /etc/flow-gateway.env "$flow_backup/gateway.env"
cp /etc/nginx/sites-available/flow-gateway "$flow_backup/nginx.conf"
if [ -f /opt/flow-gateway/audio_validation.py ]; then cp /opt/flow-gateway/audio_validation.py "$flow_backup/audio_validation.py"; fi
flow_done=0
flow_rollback() {
 if [ "$flow_done" = 1 ]; then return; fi
 cp "$flow_backup/gateway.env" /etc/flow-gateway.env
 cp "$flow_backup/gateway.py" /opt/flow-gateway/gateway.py
 cp "$flow_backup/nginx.conf" /etc/nginx/sites-available/flow-gateway
 if [ -f "$flow_backup/audio_validation.py" ]; then cp "$flow_backup/audio_validation.py" /opt/flow-gateway/audio_validation.py; fi
 if nginx -t; then systemctl reload nginx || true; fi
 systemctl restart flow-gateway || true
 echo "升级失败，已尝试恢复原网关。备份：$flow_backup"
}
trap flow_rollback EXIT
install -m 644 "$flow_source/audio_validation.py" /opt/flow-gateway/audio_validation.py
install -m 644 "$flow_source/gateway.py" /opt/flow-gateway/gateway.py
python3 - <<'CONFIG'
import re
from pathlib import Path
p=Path('/etc/flow-gateway.env');s=p.read_text();s=re.sub(r'^GATEWAY_DAILY_LIMIT=.*\n?','',s,flags=re.M).rstrip()+'\nGATEWAY_DAILY_LIMIT=0\n';p.write_text(s);p.chmod(0o600)
CONFIG
python3 "$flow_source/nginx_update.py"
nginx -t
systemctl reload nginx
systemctl restart flow-gateway
for flow_attempt in {1..10}; do
 if curl -fsS --max-time 3 http://127.0.0.1:8088/health 2>/dev/null | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get("version")=="2.2" and d.get("audio_input") is True and d.get("search_grounding") is True and d.get("streaming") is True' 2>/dev/null; then
  flow_done=1
  printf '网关 v2.2 已更新，音频与联网检索能力就绪。密钥、证书、每日计数均保留。备份：%s\n' "$flow_backup"
  exit 0
 fi
 sleep 1
done
journalctl -u flow-gateway -n 25 --no-pager
exit 1
