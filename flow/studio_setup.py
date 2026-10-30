#!/usr/bin/env python3
"""BaoTa audio route and capability flag. Run only from the backed-up upgrade."""
import json,re,shlex,urllib.request
from pathlib import Path
from urllib.parse import urlsplit
VHOST=Path('/www/server/panel/vhost/nginx/flowlang.cn.conf')
EXTENSION=Path('/www/server/panel/vhost/nginx/extension/flowlang.cn/flow-studio.conf')
ROUTE='''# Flow v0.6: bounded audio in memory, no Nginx request-body spool.
location = /api/lab/audio {
    client_max_body_size 3m;
    client_body_buffer_size 3m;
    proxy_request_buffering off;
    proxy_pass http://127.0.0.1:8090;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 120s;
    proxy_buffering off;
    gzip off;
    proxy_cache off;
}
'''
from ai_stream import PATHS
ROUTE+='\n'.join(ROUTE[ROUTE.index('location ='):].replace('/api/lab/audio',path) for path in sorted(PATHS) if path!='/api/lab/audio')
def update_vhost(source):
 if not re.search(r'server_name\s+[^;]*\bflowlang\.cn\b',source):raise ValueError('站点配置与 flowlang.cn 不匹配')
 if re.search(r'location\s*=\s*/api/lab/audio\s*\{',source):raise ValueError('站点主配置已包含音频路由，请先检查冲突配置')
 include='include /www/server/panel/vhost/nginx/extension/flowlang.cn/*.conf;'
 if include not in source and str(EXTENSION) not in source:source=re.sub(r'(server_name\s+[^;]+;)',lambda m:m[0]+'\n    include '+str(EXTENSION)+';',source,count=1)
 return source

def read_env(source):
 values={}
 for line in source.splitlines():
  if '=' not in line or line.lstrip().startswith('#'):continue
  k,v=line.split('=',1)
  try:pieces=shlex.split(v,comments=True);values[k.strip()]=' '.join(pieces)
  except ValueError:continue
 return values

def setup():
 source=VHOST.read_text();VHOST.write_text(update_vhost(source));EXTENSION.parent.mkdir(parents=True,exist_ok=True);EXTENSION.write_text(ROUTE);EXTENSION.chmod(0o644)
 p=Path('/etc/flow.env');source=p.read_text();env=read_env(source);enabled=False;grounding=False
 if env.get('FLOW_AI_PROVIDER','openai')=='openai':
  url=urlsplit(env.get('FLOW_AI_URL',''))
  if url.scheme=='https' and url.netloc:
   try:
    with urllib.request.urlopen('https://'+url.netloc+'/health',timeout=8) as r:health=json.load(r)
    grounding=health.get('search_grounding') is True
    enabled=health.get('audio_input') is True and health.get('version') in ('0.6','0.8','2.0','2.1','2.2')
   except Exception:pass
 if env.get('FLOW_AI_PROVIDER')=='vertex':enabled=bool(env.get('GOOGLE_CLOUD_PROJECT') and env.get('FLOW_AI_MODEL','').startswith('google/'));grounding=enabled
 source=re.sub(r'^FLOW_AI_AUDIO=.*\n?','',source,flags=re.M).rstrip()+'\nFLOW_AI_AUDIO='+('1' if enabled else '0')+'\n'
 source=re.sub(r'^FLOW_AI_GROUNDING=.*\n?','',source,flags=re.M).rstrip()+'\nFLOW_AI_GROUNDING='+('1' if grounding else '0')+'\n'
 source=re.sub(r'^FLOW_AI_DAILY_LIMIT=.*\n?','',source,flags=re.M).rstrip()+'\nFLOW_AI_DAILY_LIMIT=0\n'
 p.write_text(source);p.chmod(0o600)
 if env.get('FLOW_AI_PROVIDER')=='vertex':print('Vertex原生音频与检索已按配置启用，须运行ai_check.py实测。' if enabled else 'Vertex配置不完整，未启用音频或检索。');return
 print('录音分析：已检测到网关能力并启用。' if enabled else '网关音频能力未确认，保留文字训练；先升级网关后可重跑升级。')
if __name__=='__main__':setup()
