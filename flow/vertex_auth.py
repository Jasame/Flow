"""Optional Vertex AI ADC integration; credentials never reach the browser."""
import os,re,threading
_lock=threading.Lock()
_credentials=None

class AIConfigurationError(ValueError):pass

def vertex_enabled():
 return os.getenv('FLOW_AI_PROVIDER','').lower()=='vertex'

def ai_enabled():
 return vertex_enabled() or bool(os.getenv('FLOW_AI_KEY'))

def vertex_connection():
 project=os.getenv('GOOGLE_CLOUD_PROJECT','')
 location=os.getenv('GOOGLE_CLOUD_LOCATION','global')
 model=os.getenv('FLOW_AI_MODEL','')
 if not re.fullmatch(r'[a-z][a-z0-9-]{4,61}[a-z0-9]',project):
  raise ValueError('Set GOOGLE_CLOUD_PROJECT to a valid project ID')
 if not re.fullmatch(r'[a-z][a-z0-9-]{0,40}',location):
  raise ValueError('Invalid location')
 if not model.startswith('google/') or len(model)>150:
  raise ValueError('Set FLOW_AI_MODEL to google/<available model ID>')
 import google.auth
 from google.auth.transport.requests import Request
 global _credentials
 with _lock:
  try:
   if _credentials is None:
    _credentials,_=google.auth.default(scopes=['https://www.googleapis.com/auth/cloud-platform'])
   if not _credentials.valid:
    _credentials.refresh(Request())
  except Exception as exc:
   raise AIConfigurationError('ADC credentials could not be loaded or refreshed') from exc
  token=_credentials.token
 host='aiplatform.googleapis.com' if location=='global' else location+'-aiplatform.googleapis.com'
 endpoint=f'https://{host}/v1/projects/{project}/locations/{location}/endpoints/openapi/chat/completions'
 return endpoint,token
