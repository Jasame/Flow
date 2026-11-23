#!/bin/bash
# Starts (or updates) the AI gateway in /opt/ai-gateway. Run as root on the Flow server, from this folder:
#
#   bash tools/ai-gateway/setup.sh
#
# Safe to run again: data/ (the console's database, with the vendors' keys) and .env (the session secret) are kept.
# It never prints a secret. Domain, HTTPS, Cloudflare Access and the vendors' keys are README.md steps 2–5.
set -euo pipefail
DIR=${AI_GATEWAY_DIR:-/opt/ai-gateway}
PORT=${AI_GATEWAY_PORT:-3000}
SRC=$(cd "$(dirname "$0")" && pwd)

[ "$(id -u)" = 0 ] || { echo "请用 root 运行"; exit 1; }
command -v docker >/dev/null || { echo "没有 Docker：先在宝塔「Docker」里安装，再运行这个脚本"; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "没有 docker compose 插件：在宝塔「Docker」里更新，或安装 docker-compose-plugin"; exit 1; }
command -v openssl >/dev/null || { echo "没有 openssl"; exit 1; }

# Port: refuse to start if something other than this gateway already listens on it.
if ss -ltnH "( sport = :$PORT )" 2>/dev/null | grep -q . && ! docker ps --format '{{.Names}}' | grep -qx ai-gateway; then
  echo "端口 $PORT 已被其他程序占用。换一个端口：AI_GATEWAY_PORT=3010 bash $0（Flow 的 FLOW_TEXT_AI_URL 也要用同一个端口）"
  exit 1
fi

install -d -m 700 "$DIR" "$DIR/data" "$DIR/logs"
for f in docker-compose.yml check_gateway.py README.md nginx-api.xmc.hk.conf; do
  [ "$SRC/$f" -ef "$DIR/$f" ] || install -m 644 "$SRC/$f" "$DIR/$f"
done

umask 077
if [ ! -s "$DIR/.env" ]; then
  printf 'SESSION_SECRET=%s\n' "$(openssl rand -hex 32)" > "$DIR/.env"
  echo "已生成 $DIR/.env（会话密钥，只存在这台服务器上，不要外传）"
fi
if [ "$PORT" != 3000 ]; then
  grep -q '^AI_GATEWAY_PORT=' "$DIR/.env" && sed -i "s/^AI_GATEWAY_PORT=.*/AI_GATEWAY_PORT=$PORT/" "$DIR/.env" || echo "AI_GATEWAY_PORT=$PORT" >> "$DIR/.env"
fi
chmod 600 "$DIR/.env"

cd "$DIR"
docker compose pull -q
docker compose up -d

for _ in $(seq 1 60); do
  curl -fsS "http://127.0.0.1:$PORT/api/status" >/dev/null 2>&1 && break
  sleep 2
done
if curl -fsS "http://127.0.0.1:$PORT/api/status" | grep -q '"success":\s*true'; then
  echo "网关已启动：http://127.0.0.1:$PORT（只对本机开放）"
  echo "下一步：README.md 第 2 步，给 api.xmc.hk 配域名、HTTPS 和 Cloudflare Access，然后在后台完成初始化。"
else
  echo "网关没有正常响应，看日志：cd $DIR && docker compose logs --tail 80"
  exit 1
fi
