import os,sys,types,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vertex_auth
class VertexTest(unittest.TestCase):
 def test_adc_refresh_and_reuse(self):
  creds=types.SimpleNamespace(valid=False,token=None)
  calls=[]
  def refresh(request):calls.append(request);creds.valid=True;creds.token='simulated-token'
  creds.refresh=refresh
  google=types.ModuleType('google');auth=types.ModuleType('google.auth');transport=types.ModuleType('google.auth.transport');requests=types.ModuleType('google.auth.transport.requests')
  auth.default=lambda **kw:(creds,'test-project');google.auth=auth;requests.Request=lambda:'request-adapter'
  modules={'google':google,'google.auth':auth,'google.auth.transport':transport,'google.auth.transport.requests':requests}
  vertex_auth._credentials=None
  with patch.dict(sys.modules,modules),patch.dict(os.environ,{'GOOGLE_CLOUD_PROJECT':'test-project','GOOGLE_CLOUD_LOCATION':'global','FLOW_AI_MODEL':'google/test-model'}):
   url,token=vertex_auth.vertex_connection();self.assertEqual(token,'simulated-token');self.assertEqual(url,'https://aiplatform.googleapis.com/v1/projects/test-project/locations/global/endpoints/openapi/chat/completions')
   vertex_auth.vertex_connection();self.assertEqual(len(calls),1)
   creds.valid=False;vertex_auth.vertex_connection();self.assertEqual(len(calls),2)
  vertex_auth._credentials=None
 def test_invalid_config(self):
  with patch.dict(os.environ,{'GOOGLE_CLOUD_PROJECT':'not a project'}):
   with self.assertRaises(ValueError):vertex_auth.vertex_connection()
if __name__=='__main__':unittest.main()
