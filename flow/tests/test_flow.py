import base64
import unittest,subprocess,tempfile,os,sys,time,urllib.request,urllib.error,http.cookiejar,json,socket,sqlite3
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
class FlowTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1];sock.close();cls.base=f'http://127.0.0.1:{port}/api/'
  env={**os.environ,'FLOW_PORT':str(port),'FLOW_COOKIE_SECURE':'0','FLOW_DATA_DIR':cls.tmp.name};env.pop('FLOW_AI_KEY',None)
  cls.proc=subprocess.Popen([sys.executable,str(ROOT/'app.py')],env=env,stdout=subprocess.DEVNULL)
  deadline=time.monotonic()+45
  while time.monotonic()<deadline:
   if cls.proc.poll() is not None:raise RuntimeError('Server exited during startup')
   try:
    with urllib.request.urlopen(cls.base+'session',timeout=1) as response:json.load(response)
    break
   except (urllib.error.URLError,TimeoutError,socket.timeout):time.sleep(.1)
  else:
   cls.proc.terminate();cls.proc.wait();raise RuntimeError('Server did not become ready within 45 seconds')
 @classmethod
 def tearDownClass(cls):cls.proc.terminate();cls.proc.wait();cls.tmp.cleanup()
 def setUp(self):self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 def request(self,path,data=None,csrf=None,client=None):
  req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json',**({'X-CSRF-Token':csrf} if csrf else {})})
  try:
   with (client or self.client).open(req) as r:return r.status,json.load(r)
  except urllib.error.HTTPError as e:return e.code,json.load(e)
 def register(self,name):
  self.assertEqual(self.request('register',{'username':name,'password':'strongtest123'})[0],200)
  return self.request('session')[1]['user']
 def test_growth_http_auth_stage_and_evidence_privacy(self):
  self.assertEqual(self.request('growth')[0],401)
  u=self.register('growth-http');csrf=u['csrf']
  self.assertEqual(self.request('growth/settings',{'theme':'travel','hotspots':True})[0],403)
  self.assertEqual(self.request('growth/settings',{'theme':'travel','hotspots':True},csrf)[0],200)
  self.assertEqual(self.request('growth/quality')[0],403)
  code,d=self.request('growth');self.assertEqual(code,200);self.assertEqual(len(d['diagnostics']['dimensions']),6)
  token=self.request('coach/placement/start',{},csrf)[1]['token']
  from placement_content import ITEMS
  self.assertEqual(self.request('coach/placement/submit',{'token':token,'answers':{p['id']:{'choice':None,'hinted':False} for p in ITEMS},'goal':'旅行交流','interests':'文化','minutes':10,'writing':''},csrf)[0],200)
  code,p=self.request('growth/plan');self.assertEqual(code,200);self.assertEqual(len(p['tasks']),6)
  self.assertEqual(self.request('growth/stage',{'request_id':'http-stage-rules-001'},csrf)[0],200)
  self.assertEqual(len(self.request('coach')[1]['missions']),6)
  self.assertEqual(self.request('growth/weekly')[0],200)
  for asset in ('growth.js','growth.css','design-bridge.css'):
   with urllib.request.urlopen(self.base.replace('/api/','/')+asset) as r:self.assertEqual(r.status,200)
 def test_full_learning_and_auth(self):
  self.assertEqual(self.request('dashboard')[0],401)
  u=self.register('student');csrf=u['csrf']
  self.assertNotIn('token',u)
  self.assertEqual(self.request('quiz',{})[0],403)
  status,q=self.request('quiz',{},csrf);self.assertEqual(status,200);self.assertEqual(len(q['questions']),12)
  self.assertNotIn('answer',q['questions'][0])
  self.assertEqual(self.request('submit',{'token':q['token'],'answers':{}},csrf)[0],400)
  self.assertEqual(self.request('submit',{'token':q['token'],'answers':{str(x['id']):9 for x in q['questions']}},csrf)[0],400)
  status,result=self.request('submit',{'token':q['token'],'answers':{str(x['id']):0 for x in q['questions']}},csrf)
  self.assertEqual(status,200);self.assertEqual(len(result['results']),12)
  self.assertEqual(self.request('submit',{'token':q['token'],'answers':{str(x['id']):0 for x in q['questions']}},csrf)[0],400)
  d=self.request('dashboard')[1];self.assertEqual(d['total'],12);self.assertTrue(d['recommended']);self.assertEqual(len(self.request('history')[1]['items']),12)
  self.assertEqual(self.request('admin')[0],403)
  self.assertEqual(self.request('admin/question',{},csrf)[0],403)
  self.assertEqual(self.request('chat',{'topic':'tense','message':'test'},csrf)[1]['mode'],'lesson')
  other=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
  self.assertEqual(self.request('register',{'username':'second','password':'strongtest123'},client=other)[0],200)
  self.assertEqual(self.request('dashboard',client=other)[1]['total'],0)
  self.assertEqual(self.request('logout',{},csrf)[0],200);self.assertEqual(self.request('dashboard')[0],401)
 def test_admin_and_persistence(self):
  u=self.register('teacher')
  with sqlite3.connect(Path(self.tmp.name)/'flow.sqlite3') as c:c.execute('UPDATE users SET admin=1 WHERE id=?',(u['id'],))
  q={'topic':'tense','prompt':'Test ____ question','options':['a','b','c','d'],'answer':1,'explanation':'A reviewed explanation'}
  self.assertEqual(self.request('admin/question',q,u['csrf'])[0],200)
  self.assertEqual(self.request('admin')[1]['questions'],73)
  self.assertEqual(self.request('login',{'username':'teacher','password':'wrongpassword'})[0],401)
  self.assertEqual(self.request('login',{'username':'teacher','password':'strongtest123'})[0],200)
  self.assertEqual(self.request('session')[1]['user']['admin'],1)
 def test_wrongs_and_balanced_quiz(self):
  u=self.register('reviewer');csrf=u['csrf']
  q=self.request('quiz',{},csrf)[1]
  counts={}
  for item in q['questions']:counts[item['topic']]=counts.get(item['topic'],0)+1
  self.assertEqual(len(counts),6);self.assertEqual(set(counts.values()),{2})
  with sqlite3.connect(Path(self.tmp.name)/'flow.sqlite3') as c:
   correct=dict(c.execute('SELECT id,answer FROM questions'))
  answers={str(x['id']):(correct[x['id']]+1)%4 for x in q['questions']}
  self.assertEqual(self.request('submit',{'token':q['token'],'answers':answers},csrf)[0],200)
  self.assertEqual(len(self.request('wrongs')[1]['items']),12)
  retry=self.request('quiz',{'mode':'wrongs'},csrf)[1]
  self.assertNotIn('answer',retry['questions'][0]);self.assertNotIn('explanation',retry['questions'][0])
  self.assertEqual(self.request('submit',{'token':retry['token'],'answers':{str(x['id']):correct[x['id']] for x in retry['questions']}},csrf)[0],200)
  self.assertEqual(len(self.request('wrongs')[1]['items']),0)
  self.assertEqual(self.request('dashboard')[1]['wrong_count'],0)
 def test_password_and_reading(self):
  u=self.register('reader');csrf=u['csrf']
  self.assertEqual(self.request('lesson/complete',{'topic':'tense'},csrf)[0],200)
  self.assertEqual(self.request('lesson/complete',{'topic':'tense'},csrf)[0],200)
  d=self.request('dashboard')[1];self.assertEqual(d['completed'],1)
  t=next(t for t in d['topics'] if t['id']=='tense');self.assertTrue(t['completed']);self.assertIsNone(t['mastery']);self.assertEqual(len(t['details']),3)
  self.assertEqual(self.request('password',{'old_password':'wrong','new_password':'newstrongpass123'},csrf)[0],400)
  self.assertEqual(self.request('password',{'old_password':'strongtest123','new_password':'newstrongpass123'},csrf)[0],200)
  self.assertEqual(self.request('dashboard')[0],401)
  self.assertEqual(self.request('login',{'username':'reader','password':'strongtest123'})[0],401)
  self.assertEqual(self.request('login',{'username':'reader','password':'newstrongpass123'})[0],200)
  self.assertEqual(self.request('dashboard')[1]['completed'],1)
 def test_static_and_privacy(self):
  for path in ['../data/flow.sqlite3','data/flow.sqlite3','.env','app.py']:
   try:urllib.request.urlopen(self.base.replace('/api/','/')+path);self.fail('File exposed')
   except urllib.error.HTTPError as e:self.assertEqual(e.code,404)
  with urllib.request.urlopen(self.base.replace('/api/','/')) as r:self.assertEqual(r.status,200);self.assertIn("script-src 'self'",r.headers['Content-Security-Policy'])
 def test_v05_learning_portfolio_and_permissions(self):
  u=self.register('v05-learner');csrf=u['csrf']
  status,d=self.request('study');self.assertEqual(status,200);self.assertEqual(len(d['nodes']),18)
  self.assertEqual(self.request('study/preferences',{'minutes':5},csrf)[0],200)
  self.assertLessEqual(self.request('study')[1]['plan_minutes'],5)
  q=self.request('quiz',{'node':'tense-perfect'},csrf)[1];self.assertTrue(q['questions'])
  self.assertTrue(all('answer' not in item for item in q['questions']))
  self.assertEqual(self.request('submit',{'token':q['token'],'answers':{str(x['id']):0 for x in q['questions']}},csrf)[0],200)
  d=self.request('study')[1];self.assertGreater(d['coverage'],0)
  self.assertEqual(self.request('manage/monitor')[0],403);self.assertEqual(self.request('manage/backup')[0],403)
  self.assertEqual(self.request('manage/import',{'items':[]},csrf)[0],403)
  self.assertIsNone(self.request('account')[1]['email'])
  task=self.request('practices')[1]['tasks'][0]
  payload={'task':task['id'],'answer':'My example is here.','save_id':'portfolio-save-001'}
  self.assertEqual(self.request('practices/save',payload,csrf)[0],200)
  self.assertEqual(self.request('practices/save',payload,csrf)[0],200)
  self.assertEqual(len(self.request('practices')[1]['history']),1)
  with urllib.request.urlopen(self.base.replace('/api/','/')+'advanced.js') as response:self.assertEqual(response.status,200)
 def test_v05_teacher_edit_and_import(self):
  u=self.register('v05-teacher');csrf=u['csrf']
  with sqlite3.connect(Path(self.tmp.name)/'flow.sqlite3') as c:c.execute('UPDATE users SET admin=1 WHERE id=?',(u['id'],))
  self.assertEqual(self.request('manage/monitor')[0],200)
  self.assertEqual(self.request('manage/backup')[0],200)
  old=self.request('manage/questions?topic=tense')[1]['items'][0]
  changed={**old,'prompt':'Replacement question ____','status':'draft'}
  status,out=self.request('manage/question',changed,csrf);self.assertEqual(status,200);self.assertNotEqual(out['id'],old['id'])
  rows=self.request('manage/questions?status=draft')[1]['items'];self.assertIn(out['id'],[r['id'] for r in rows])
  self.assertEqual(self.request('manage/status',{'id':out['id'],'status':'published'},csrf)[0],200)
  self.assertEqual(self.request('manage/import',{'items':[{**changed,'answer':10}]},csrf)[0],400)
  self.assertEqual(self.request('manage/import',{'items':[changed]},csrf)[0],200)

 def test_v06_lab_http_and_audio_access(self):
  self.assertEqual(self.request('lab')[0],401)
  payload={'pack':'travel-a2','skill':'speaking','request_id':'http-audio-000001','audio':{'mime_type':'audio/webm','data':base64.b64encode(b'\x1aE\xdf\xa3'+b'x'*30000).decode()}}
  self.assertEqual(self.request('lab/audio',payload)[0],401)
  u=self.register('v06-learner');csrf=u['csrf'];self.assertEqual(len(self.request('lab')[1]['packs']),154)
  self.assertEqual(self.request('lab/audio',payload)[0],403)
  self.assertEqual(self.request('lab/audio',payload,csrf)[0],503)
  pack=self.request('lab/pack?id=travel-a2')[1]['pack'];self.assertNotIn('answer',pack['questions'][0])
  self.assertEqual(self.request('lab/draft',{'pack':'travel-a2','skill':'writing','answer':'My first draft.'},csrf)[0],200)
  self.assertEqual(self.request('lab/save',{'pack':'travel-a2','skill':'writing','answer':'My first draft.','save_id':'http-save-v06-001'},csrf)[0],200)
  self.assertEqual(len(self.request('lab/history')[1]['items']),1)
  self.assertEqual(self.request('lab/pack?id=unknown')[0],400)
  with urllib.request.urlopen(self.base.replace('/api/','/')+'studio.js') as r:self.assertEqual(r.status,200)
 def test_v20_coach_http_auth_placement_and_drafts(self):
  self.assertEqual(self.request('coach')[0],401)
  u=self.register('coach-http-user');csrf=u['csrf']
  code,state=self.request('coach');self.assertEqual(code,200);self.assertIsNone(state['profile']);self.assertIsNone(state['personal_limit'])
  self.assertEqual(self.request('coach/placement/start',{})[0],403)
  code,baseline=self.request('coach/placement/start',{},csrf);self.assertEqual(code,200);self.assertTrue(all('answer' not in p for p in baseline['items']))
  answers={p['id']:{'choice':None,'hinted':False} for p in baseline['items']}
  code,result=self.request('coach/placement/submit',{'token':baseline['token'],'answers':answers,'goal':'旅行交流','interests':'文化','minutes':15,'writing':''},csrf);self.assertEqual(code,200);self.assertIn('不',result['note'])
  self.assertEqual(self.request('coach/draft',{'message':'我的长期学习问题'},csrf)[0],200)
  self.assertEqual(self.request('coach')[1]['draft'],'我的长期学习问题')
  for asset in ('coach.js','coach.css'):
   with urllib.request.urlopen(self.base.replace('/api/','/')+asset) as response:self.assertEqual(response.status,200)
 def test_v10_adaptive_api_permissions_task_and_typed_graph(self):
  self.assertEqual(self.request('adaptive')[0],401)
  u=self.register('adaptive-http-user');csrf=u['csrf']
  self.assertEqual(self.request('adaptive/next',{})[0],403)
  code,p=self.request('adaptive');self.assertEqual(code,200);self.assertLessEqual(p['minutes'],p['goal']['minutes'])
  code,words=self.request('vocab');self.assertEqual(code,200);self.assertEqual(len(words['items']),107)
  entry=words['items'][0]['id'];code,t=self.request('adaptive/next',{'kind':'vocab','entry':entry},csrf);self.assertEqual(code,200);self.assertNotIn('correct',t['task']['payload'])
  self.assertEqual(self.request('adaptive/hint',{'token':t['task']['token']},csrf)[0],200)
  code,result=self.request('adaptive/submit',{'token':t['task']['token'],'answer':0},csrf);self.assertEqual(code,200);self.assertTrue(result['assisted'])
  self.assertEqual(self.request('vocab/manage')[0],403);self.assertEqual(self.request('vocab/generate',{'words':['suggest'],'request_id':'http-generate-0001'},csrf)[0],403)
  code,g=self.request('graph');self.assertEqual(code,200);self.assertIn('has_sense',{e['relation'] for e in g['edges']})
  self.assertEqual(self.request('graph/node?id=not-a-node')[0],400)
  self.assertEqual(self.request('adaptive/report')[0],200)
  for asset in ('adaptive.js','adaptive.css'):
   with urllib.request.urlopen(self.base.replace('/api/','/')+asset) as r:self.assertEqual(r.status,200)
 def test_v08_knowledge_daily_auth_and_static(self):
  self.assertEqual(self.request('knowledge')[0],401)
  self.request('register',{'username':'graphlearner','password':'testing-password-08'})
  status,session=self.request('login',{'username':'graphlearner','password':'testing-password-08'});self.assertEqual(status,200);csrf=self.request('session')[1]['user']['csrf']
  code,graph=self.request('knowledge');self.assertEqual(code,200);self.assertEqual(len(graph['nodes']),18);self.assertTrue(graph['edges']);self.assertTrue(all(n['distinct']==0 for n in graph['nodes']))
  self.assertEqual(self.request('daily')[0],200)
  self.assertEqual(self.request('daily/run',{},csrf=csrf)[0],403)
  self.assertEqual(self.request('daily/suggestions?id=absent')[0],404)
  with sqlite3.connect(Path(self.tmp.name)/'flow.sqlite3') as c:
   p=json.loads(c.execute('SELECT content FROM lab_packs LIMIT 1').fetchone()[0]);p['id']='daily-test-source';suggestions='<style>a{color:blue}</style><a href="https://google.com/search?q=test">Google Search</a>';p['provenance']={'suggestions':suggestions}
   c.execute('INSERT INTO lab_packs VALUES(?,NULL,?,?,?)',(p['id'],'daily',json.dumps(p),time.time()))
  try:
   with self.client.open(self.base+'daily/suggestions?id=daily-test-source') as r:
    self.assertEqual(r.read().decode(),suggestions);self.assertIn("default-src 'none'",r.headers['Content-Security-Policy']);self.assertIn('sandbox allow-popups',r.headers['Content-Security-Policy'])
  finally:
   with sqlite3.connect(Path(self.tmp.name)/'flow.sqlite3') as c:c.execute("DELETE FROM lab_packs WHERE id='daily-test-source'")
  with urllib.request.urlopen(self.base.replace('/api/','/')+'knowledge.js') as r:self.assertEqual(r.status,200);self.assertIn(b'renderKnowledge',r.read())
 def test_v07_corpus_http_notes_bookmarks_and_stylesheet(self):
  u=self.register('v07-reader');csrf=u['csrf']
  catalog=self.request('lab')[1];self.assertEqual(len(catalog['packs']),154)
  self.assertEqual(len({p['theme'] for p in catalog['packs']}),6)
  self.assertEqual(self.request('lab/bookmark',{'pack':'travel-a2','saved':True})[0],403)
  self.assertEqual(self.request('lab/bookmark',{'pack':'travel-a2','saved':True},csrf)[0],200)
  self.assertEqual(self.request('lab/note',{'pack':'travel-a2','note':'Ask a clear question.'},csrf)[0],200)
  detail=self.request('lab/pack?id=travel-a2')[1];self.assertTrue(detail['bookmark']);self.assertEqual(detail['note'],'Ask a clear question.')
  self.assertEqual(self.request('lab/report',{'pack':'travel-a2','category':'difficulty','note':'Please check the target difficulty.'},csrf)[0],200)
  self.assertEqual(self.request('lab/report/resolve',{'id':1},csrf)[0],403)
  with urllib.request.urlopen(self.base.replace('/api/','/')+'layout.css') as r:self.assertEqual(r.status,200)
if __name__=='__main__':unittest.main(verbosity=2)
