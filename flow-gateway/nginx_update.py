"""Modify only the fixed chat route; retain certificates, allowlist and rate limits."""
import re
from pathlib import Path

def update(source):
 pattern=r'(location\s*=\s*/v1/chat/completions\s*\{)([^{}]*)(\})'
 def replace(m):
  body=re.sub(r'\s*(?:client_max_body_size|client_body_buffer_size|proxy_request_buffering|proxy_buffering|gzip)\s+[^;]+;','',m[2])
  body=re.sub(r'proxy_read_timeout\s+\d+s;','proxy_read_timeout 95s;',body)
  return m[1]+'\n        client_max_body_size 3m;\n        client_body_buffer_size 3m;\n        proxy_request_buffering off;\n        proxy_buffering off;\n        gzip off;'+body+m[3]
 result,count=re.subn(pattern,replace,source)
 if count<1:raise ValueError('未找到固定聊天代理，请保留原配置并人工检查')
 return result
if __name__=='__main__':
 p=Path('/etc/nginx/sites-available/flow-gateway');p.write_text(update(p.read_text()))
