#!/usr/bin/env bash
# Run on the Alibaba BaoTa server after uploading the private client env.
set -euo pipefail
if [ "$(id -u)" != 0 ]; then echo '请在宝塔 root 终端运行'; exit 1; fi
flow_client="${1:-/root/flow-gateway-client.env}"
if [ ! -f "$flow_client" ]; then echo '未找到私有连接文件'; exit 1; fi
chmod 600 "$flow_client"
# Check network and TLS before changing the existing site configuration.
curl --fail --silent --show-error --connect-timeout 8 --max-time 15 https://ai.flowlang.cn/health
/usr/bin/python3.11 - "$flow_client" <<'PY'
from pathlib import Path
import sys,os,datetime,urllib.request,json
source=Path(sys.argv[1]);dest=Path('/etc/flow.env')
config={}
for line in source.read_text().splitlines():
 if '=' in line and not line.startswith('#'):
  k,v=line.split('=',1);config[k]=v
required={'FLOW_AI_PROVIDER','FLOW_AI_URL','FLOW_AI_MODEL','FLOW_AI_KEY'}
if set(config)!=required or config['FLOW_AI_PROVIDER']!='openai' or config['FLOW_AI_URL']!='https://ai.flowlang.cn/v1/chat/completions' or len(config['FLOW_AI_KEY'])<40:raise SystemExit('连接文件格式不正确，未修改配置')
# One short real model request, without printing the shared secret.
request=urllib.request.Request(config['FLOW_AI_URL'],data=json.dumps({'model':config['FLOW_AI_MODEL'],'messages':[{'role':'user','content':'只回复：Flow连接成功'}],'max_tokens':1024}).encode(),headers={'Authorization':'Bearer '+config['FLOW_AI_KEY'],'Content-Type':'application/json'})
try:
 with urllib.request.urlopen(request,timeout=65) as r:reply=json.load(r)
 print('\n模型测试：',reply['choices'][0]['message']['content'])
except Exception as e:raise SystemExit('模型验证失败，未修改网站配置：'+str(e))
if not dest.exists():raise SystemExit('/etc/flow.env 不存在，未写入')
backup=Path('/etc/flow.env.before-gateway-'+datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
backup.write_bytes(dest.read_bytes());os.chmod(backup,0o600)
lines=[line for line in dest.read_text().splitlines() if line.split('=',1)[0].strip() not in required]
lines.extend(k+'='+config[k] for k in sorted(required))
dest.write_text('\n'.join(lines)+'\n');os.chmod(dest,0o600)
app=Path('/www/wwwroot/flow/app.py')
text=app.read_text()
if 'urlopen(req,timeout=35)' in text:
 app.with_name('app.py.before-gateway').write_text(text)
 app.write_text(text.replace('urlopen(req,timeout=35)','urlopen(req,timeout=65)'))
print('模型验证通过，服务端配置已更新。')
PY
systemctl restart flow
for flow_check in {1..10}; do
  if curl --fail --silent --show-error --max-time 3 http://127.0.0.1:8090/api/session; then
    printf '\n请刷新 flowlang.cn，进入学习中心测试答疑。\n'
    exit 0
  fi
  sleep 1
done
journalctl -u flow -n 20 --no-pager
exit 1
