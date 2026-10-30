"""Real local HTTP chain: browser protocol -> Flow -> gateway -> controlled Google SSE."""
import sys,os,io,json,time,tempfile,threading,unittest,urllib.request,urllib.error
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'flow-gateway'))
import app,ai_stream,gateway
from test_ai_stream import Reply

class AIIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.old_db=app.DB;app.DB=Path(cls.tmp.name)/'flow.db';app.init()
        with app.db() as c:
            c.execute("INSERT INTO users(username,password) VALUES('ai-test','hash')")
            cls.uid=c.execute("SELECT id FROM users WHERE username='ai-test'").fetchone()[0]
            c.execute('INSERT INTO sessions VALUES(?,?,?,?)',('test-session',cls.uid,'test-csrf',time.time()+3600))
        cls.server=app.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.gateway=gateway.ThreadingHTTPServer(('127.0.0.1',0),gateway.Handler)
        cls.gt=threading.Thread(target=cls.gateway.serve_forever,daemon=True);cls.gt.start()
        cls.orig_open=staticmethod(urllib.request.urlopen)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.gateway.shutdown();cls.gateway.server_close();cls.gt.join();app.DB=cls.old_db;cls.tmp.cleanup()
    def setUp(self):
        self.patches=[patch.dict(os.environ,{'FLOW_AI_PROVIDER':'openai','FLOW_AI_URL':'https://gateway.test/v1/chat/completions','FLOW_AI_KEY':'s'*64,'FLOW_AI_MODEL':'test-model','FLOW_AI_DAILY_LIMIT':'0'}),patch.multiple(gateway,SECRET='s'*64,MODEL='test-model',PROJECT='test-project',DATA=Path(self.tmp.name)/'gateway',LIMIT=0),patch.object(gateway,'access_token',return_value='test-google-token')]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        gateway.init();self.calls=[];self.broken=False;self.google_started=threading.Event()
        owner=self
        class GoogleReply(Reply):
            def __iter__(self):
                owner.google_started.set()
                pieces=['{"reply":"先练一句：', 'Hello. 现在换一个词再试一次。"}']
                for i,piece in enumerate(pieces):
                    if i:time.sleep(.35)
                    chunk={'candidates':[{'content':{'parts':[{'text':'private thought','thought':True},{'text':piece}]},**({'finishReason':'STOP'} if i==1 and not owner.broken else {})}]}
                    yield ('data: '+json.dumps(chunk,ensure_ascii=False)+'\n').encode();yield b'\n'
        def route(req,*args,**kwargs):
            url=req.full_url if hasattr(req,'full_url') else str(req)
            if url.startswith('https://gateway.test/'):
                return self.orig_open(urllib.request.Request('http://127.0.0.1:'+str(self.gateway.server_port)+'/v1/chat/completions',data=req.data,headers=dict(req.header_items())),timeout=5)
            if url.startswith('https://aiplatform.googleapis.com/'):
                self.calls.append(json.loads(req.data));return GoogleReply(b'')
            return self.orig_open(req,*args,**kwargs)
        p=patch.object(urllib.request,'urlopen',side_effect=route);p.start();self.addCleanup(p.stop)
    def request(self,rid,csrf='test-csrf',cookie=True,target='campus-a2'):
        req=urllib.request.Request('http://127.0.0.1:'+str(self.server.server_port)+'/api/ai/help',data=json.dumps({'kind':'material','target':target,'mode':'hint','request_id':rid}).encode(),headers={'Content-Type':'application/json','Accept':'text/event-stream','X-CSRF-Token':csrf,**({'Cookie':'flow_session=test-session'} if cookie else {})})
        return self.orig_open(req,timeout=8)
    def test_01_auth_and_csrf_precede_stream_headers(self):
        for kw,code in [({'cookie':False},401),({'csrf':'wrong'},403)]:
            with self.assertRaises(urllib.error.HTTPError) as exc:self.request('integration-auth-01',**kw)
            self.assertEqual(exc.exception.code,code);self.assertNotIn('event-stream',exc.exception.headers['Content-Type']);exc.exception.close()
        self.assertEqual(len(self.calls),0)
    def test_02_incremental_chain_and_idempotent_replay(self):
        seen=[];start=time.monotonic()
        with self.request('integration-live-01') as response:
            for event in ai_stream.events(response):seen.append((time.monotonic()-start,json.loads(event)))
        previews=[x for x in seen if x[1]['type']=='preview'];final=seen[-1]
        self.assertTrue(previews);self.assertGreater(final[0]-previews[0][0],.2)
        self.assertEqual(final[1]['status'],200);self.assertNotIn('private thought',str(seen))
        self.assertEqual(final[1]['data']['result']['reply'],'先练一句：Hello. 现在换一个词再试一次。')
        with self.request('integration-live-01') as response:cached=[json.loads(x) for x in ai_stream.events(response)]
        self.assertEqual(cached[-1]['status'],200);self.assertEqual(len(self.calls),1)
        with app.db() as c:self.assertEqual(c.execute("SELECT COUNT(*) FROM lab_jobs WHERE request_id='integration-live-01' AND status='complete'").fetchone()[0],1)
    def test_03_truncated_upstream_is_not_saved_as_valid(self):
        self.broken=True
        with self.request('integration-broken-01') as response:events=[json.loads(x) for x in ai_stream.events(response)]
        self.assertEqual(events[-1]['status'],502)
        with app.db() as c:
            job=c.execute("SELECT status,result FROM lab_jobs WHERE request_id='integration-broken-01'").fetchone()
            self.assertEqual(job['status'],'failed');self.assertEqual(job['result'],'')
    def test_04_private_material_not_visible_to_other_user(self):
        with self.request('integration-private-01',target='unknown-private-pack') as response:events=[json.loads(x) for x in ai_stream.events(response)]
        self.assertEqual(events[-1]['status'],400);self.assertFalse(self.calls)
    def test_05_disconnected_browser_does_not_cancel_persistence(self):
        response=self.request('integration-disconnect-01');next(ai_stream.events(response));response.close()
        until=time.monotonic()+5
        while time.monotonic()<until:
            with app.db() as c:row=c.execute("SELECT status FROM lab_jobs WHERE request_id='integration-disconnect-01'").fetchone()
            if row and row[0]=='complete':break
            time.sleep(.05)
        self.assertIsNotNone(row);self.assertEqual(row[0],'complete')
    def test_06_every_index_asset_is_served_with_correct_type(self):
        import re
        page=(app.ROOT/'public/index.html').read_text()
        for asset in re.findall(r'(?:src|href)="/([^"?]+)',page):
            with self.orig_open('http://127.0.0.1:'+str(self.server.server_port)+'/'+asset,timeout=5) as response:
                self.assertEqual(response.status,200,asset)
                self.assertIn('javascript' if asset.endswith('.js') else 'text/css',response.headers['Content-Type'],asset)
    def test_07_context_hint_is_saved_recoverably_and_marks_assistance_only(self):
        import ai_help_service,lab_service
        with app.db() as c:
            before=c.execute('SELECT COUNT(*) FROM learning_events').fetchone()[0]
            with patch.object(ai_help_service,'request_model',return_value=('{"reply":"只给一个小提示。"}','stop')):
                result,status=ai_help_service.help(c,self.uid,{'kind':'material','target':'campus-a2','skill':'writing','mode':'hint','request_id':'integration-hint-01'})
            self.assertEqual(status,200)
            self.assertEqual(c.execute('SELECT assisted FROM studio_support WHERE user_id=? AND pack=? AND skill=?',(self.uid,'campus-a2','writing')).fetchone()[0],1)
            self.assertEqual(c.execute('SELECT COUNT(*) FROM learning_events').fetchone()[0],before)
            jobs=lab_service.get(c,self.uid,'/api/lab/history',{})[0]['jobs']
            self.assertTrue(any(j['request_id']=='integration-hint-01' and j['result']['reply']=='只给一个小提示。' for j in jobs))
    def test_08_parallel_http_requests_queue_instead_of_rejecting(self):
        first=[]
        def consume():
            with self.request('integration-queue-01') as response:first.extend(json.loads(x) for x in ai_stream.events(response))
        worker=threading.Thread(target=consume);worker.start();self.assertTrue(self.google_started.wait(3))
        with self.request('integration-queue-02') as response:second=[json.loads(x) for x in ai_stream.events(response)]
        worker.join(5)
        self.assertEqual(first[-1]['status'],200);self.assertEqual(second[-1]['status'],200)
        self.assertTrue(any(e.get('type')=='status' and e.get('position',0)>0 for e in second));self.assertEqual(len(self.calls),2)
if __name__=='__main__':unittest.main()
