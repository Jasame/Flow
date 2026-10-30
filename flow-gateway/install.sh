#!/usr/bin/env bash
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo '请使用 sudo bash install.sh'; exit 1; fi
flow_source_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
flow_owner="${SUDO_USER:-}"
if [ -z "$flow_owner" ] || [ "$flow_owner" = root ]; then echo '请从普通 SSH 用户使用 sudo 运行，以生成私有连接文件。'; exit 1; fi
flow_owner_home="$(getent passwd "$flow_owner" | cut -d: -f6)"
if [ ! -f "$flow_source_dir/gateway.py" ]; then echo 'gateway.py 缺失'; exit 1; fi
# This installer is for the dedicated Debian gateway VM only.
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 nginx certbot python3-certbot-nginx
if ! id flowgateway >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/flow-gateway --shell /usr/sbin/nologin flowgateway
fi
install -d -m 755 /opt/flow-gateway
install -d -o flowgateway -g flowgateway -m 700 /var/lib/flow-gateway
install -m 644 "$flow_source_dir/audio_validation.py" /opt/flow-gateway/audio_validation.py
install -m 644 "$flow_source_dir/gateway.py" /opt/flow-gateway/gateway.py
# Re-running preserves the shared secret and daily usage database.
python3 - <<'PY'
from pathlib import Path
import secrets,os
p=Path('/etc/flow-gateway.env')
if not p.exists():
 p.write_text('GOOGLE_CLOUD_PROJECT=project-8c5a66f7-07f1-4ea9-af7\nGATEWAY_MODEL=gemini-3.8-flash\nGATEWAY_DAILY_LIMIT=0\nGATEWAY_SECRET='+secrets.token_urlsafe(48)+'\n')
os.chmod(p,0o600)
PY
cat > /etc/systemd/system/flow-gateway.service <<'SERVICE'
[Unit]
Description=Flow Gemini Gateway
After=network-online.target
Wants=network-online.target
[Service]
User=flowgateway
Group=flowgateway
WorkingDirectory=/opt/flow-gateway
EnvironmentFile=/etc/flow-gateway.env
ExecStart=/usr/bin/python3 /opt/flow-gateway/gateway.py
Restart=on-failure
RestartSec=5
UMask=0077
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/flow-gateway
[Install]
WantedBy=multi-user.target
SERVICE
systemctl daemon-reload
systemctl enable flow-gateway
systemctl restart flow-gateway
cat > /etc/nginx/conf.d/flow-gateway-rate.conf <<'NGINX'
limit_req_zone $binary_remote_addr zone=flow_gateway:1m rate=5r/s;
NGINX
# Preserve Certbot changes on reinstallation.
if [ ! -f /etc/nginx/sites-available/flow-gateway ]; then
cat > /etc/nginx/sites-available/flow-gateway <<'NGINX'
server {
    listen 80;
    server_name ai.flowlang.cn;
    server_tokens off;
    client_max_body_size 24k;
    location = /health {
        proxy_pass http://127.0.0.1:8088;
    }
    location = /v1/chat/completions {
        client_max_body_size 3m;
        client_body_buffer_size 3m;
        proxy_request_buffering off;
        allow 121.40.203.104;
        allow 127.0.0.1;
        deny all;
        limit_req zone=flow_gateway burst=10 nodelay;
        proxy_pass http://127.0.0.1:8088;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 5s;
        proxy_read_timeout 120s;
        proxy_buffering off;
        gzip off;
        proxy_cache off;
    }
    location / { return 404; }
}
NGINX
fi
ln -sfn /etc/nginx/sites-available/flow-gateway /etc/nginx/sites-enabled/flow-gateway
nginx -t
systemctl enable nginx
systemctl restart nginx
# HTTP-01 verifies the DNS record and issues a certificate for the gateway domain.
certbot --nginx -d ai.flowlang.cn --non-interactive --agree-tos --register-unsafely-without-email --redirect
systemctl enable --now certbot.timer
# A private client configuration is created for the SSH user; never print its contents.
python3 - "$flow_owner_home/flow-gateway-client.env" <<'PY'
from pathlib import Path
import sys,os
config=dict(line.split('=',1) for line in Path('/etc/flow-gateway.env').read_text().splitlines() if '=' in line and not line.startswith('#'))
p=Path(sys.argv[1])
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
with os.fdopen(fd,'w') as f:
 f.write('FLOW_AI_PROVIDER=openai\nFLOW_AI_URL=https://ai.flowlang.cn/v1/chat/completions\nFLOW_AI_MODEL='+config['GATEWAY_MODEL']+'\nFLOW_AI_KEY='+config['GATEWAY_SECRET']+'\n')
os.chmod(p,0o600)
PY
chown "$flow_owner:$(id -gn "$flow_owner")" "$flow_owner_home/flow-gateway-client.env"
for flow_check in {1..10}; do
  if curl --fail --silent --show-error --max-time 5 https://ai.flowlang.cn/health; then
    printf '\n网关已安装。私有连接文件：%s/flow-gateway-client.env\n请勿将文件内容或截图发送到聊天中。\n' "$flow_owner_home"
    exit 0
  fi
  sleep 1
done
journalctl -u flow-gateway -n 20 --no-pager
exit 1
