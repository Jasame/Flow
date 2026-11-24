#!/usr/bin/env bash
# Set how many requests the gateway sends to Google at once, on the gateway VM, without replacing anything else:
#     sudo bash set_slots.sh [N]          N = 1–32, default 6
# Up to v2.2 gateway.py hard-coded 2 slots (SLOTS=threading.BoundedSemaphore(2)); a third request waited up to 25 s,
# then got 503 "Gateway queue timed out". This backs up gateway.py and /etc/flow-gateway.env, changes only that one
# line so it reads GATEWAY_SLOTS (a gateway.py that already reads it is left as it is), writes GATEWAY_SLOTS=N into
# the env file, restarts flow-gateway and checks /health. If anything fails, both files are put back.
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo '请使用 sudo bash set_slots.sh [并发数]'; exit 1; fi
N=${1:-6}
if ! [[ $N =~ ^[0-9]+$ ]] || [ "$N" -lt 1 ] || [ "$N" -gt 32 ]; then echo "并发数要在 1 到 32 之间：$N"; exit 1; fi
G=/opt/flow-gateway/gateway.py; E=/etc/flow-gateway.env
if [ ! -f "$G" ] || [ ! -f "$E" ]; then echo '未找到网关（/opt/flow-gateway/gateway.py）：请在网关 VM 上运行，不要在宝塔服务器上运行。'; exit 1; fi
B=/var/backups/flow-gateway-slots-$(date +%Y%m%d-%H%M%S)
install -d -m 700 "$B"; cp -p "$G" "$B/gateway.py"; cp -p "$E" "$B/gateway.env"
restore() {
  cp -p "$B/gateway.py" "$G"; cp -p "$B/gateway.env" "$E"
  systemctl restart flow-gateway || true
  echo "没有改成，已恢复原来的文件并重启。备份：$B"
}
if grep -q 'GATEWAY_SLOTS' "$G"; then
  echo "gateway.py 已经读 GATEWAY_SLOTS，不用改代码"
elif grep -q 'SLOTS=threading.BoundedSemaphore(2)' "$G"; then
  sed -i 's/SLOTS=threading.BoundedSemaphore(2)/SLOTS=threading.BoundedSemaphore(max(1,min(int(os.environ.get("GATEWAY_SLOTS","6") or 6),32)))/' "$G"
  if ! grep -q 'GATEWAY_SLOTS' "$G"; then restore; exit 1; fi
  echo "gateway.py：并发改成读 GATEWAY_SLOTS（只改了这一处）"
else
  echo "gateway.py 里没找到 SLOTS=threading.BoundedSemaphore(2)，什么都没改。请把 gateway.py 第 12 行发给 Claude 看看。"
  exit 1
fi
python3 - "$E" "$N" <<'PY'
import re, sys
from pathlib import Path
p, n = Path(sys.argv[1]), sys.argv[2]
s = re.sub(r'^GATEWAY_SLOTS=.*\n?', '', p.read_text(), flags=re.M).rstrip() + '\nGATEWAY_SLOTS=%s\n' % n
p.write_text(s)
p.chmod(0o600)
PY
if ! python3 -m py_compile "$G"; then restore; exit 1; fi
systemctl restart flow-gateway
for i in $(seq 1 15); do
  if curl -fsS --max-time 3 http://127.0.0.1:8088/health >/dev/null 2>&1; then
    echo "网关已重启，同时最多 $N 个请求。备份：$B"
    echo "撤销：sudo cp -p $B/gateway.py $G && sudo cp -p $B/gateway.env $E && sudo systemctl restart flow-gateway"
    exit 0
  fi
  sleep 1
done
journalctl -u flow-gateway -n 20 --no-pager || true
restore
exit 1
