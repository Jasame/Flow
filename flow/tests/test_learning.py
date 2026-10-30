import unittest,tempfile,time,json,sys,os,sqlite3
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,learning_service as learning,account_service as account,chat_service as chat,ops
class LearningTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patch=patch.object(app,'DB',Path(self.tmp.name)/'flow.sqlite3');self.patch.start();app.init();self.c=app.db()
  for name in ['owner','other']:self.c.execute('INSERT INTO users(username,password) VALUES(?,?)',(name,app.password('strongtest123')))
  self.c.commit()
 def tearDown(self):self.c.close();self.patch.stop();self.tmp.cleanup()
 def attempt(self,q,correct):
  self.c.execute('INSERT INTO attempts(user_id,question_id,selected,correct,created) VALUES(1,?,0,?,?)',(q,correct,time.time()));learning.observe(self.c,1,[q]);self.c.commit()
 def test_schedule_evidence_and_budget(self):
  q=self.c.execute("SELECT id FROM questions WHERE node='tense-perfect'").fetchone()[0]
  self.attempt(q,0);card=self.c.execute('SELECT * FROM review_cards').fetchone();self.assertEqual(card['stage'],0)
  self.assertAlmostEqual(card['due']-time.time(),86400,delta=5)
  self.attempt(q,1);card=self.c.execute('SELECT * FROM review_cards').fetchone();self.assertEqual(card['stage'],0)
  self.c.execute('UPDATE review_cards SET due=?',(time.time()-1,));self.c.commit();self.attempt(q,1)
  self.assertEqual(self.c.execute('SELECT stage FROM review_cards').fetchone()[0],1)
  self.attempt(q,0);self.assertEqual(self.c.execute('SELECT stage FROM review_cards').fetchone()[0],0)
  d=learning.summary(self.c,1);n=next(n for n in d['nodes'] if n['id']=='tense-perfect');self.assertEqual(n['distinct'],1);self.assertEqual(n['state'],'证据不足');self.assertEqual(d['first'],{'total':1,'correct':0});self.assertEqual(d['repeat']['total'],3)
  self.assertEqual(learning.summary(self.c,2)['coverage'],0)
  for minutes in [5,10,15,20,30]:
   learning.post(self.c,1,False,'/api/study/preferences',{'minutes':minutes},None);d=learning.summary(self.c,1);self.assertLessEqual(d['plan_minutes'],minutes)
 def test_immutable_items_review_selection_and_atomic_import(self):
  q=self.c.execute("SELECT * FROM questions WHERE node='tense-perfect'").fetchone();old=q['prompt'];self.attempt(q['id'],0)
  data=dict(q);data.update(options=json.loads(q['options']),prompt='Changed ____ item',status='draft')
  new=learning.save_question(self.c,1,data);self.c.commit();self.assertNotEqual(new,q['id'])
  self.assertEqual(self.c.execute('SELECT prompt FROM questions WHERE id=?',(q['id'],)).fetchone()[0],old)
  rows=learning.quiz_rows(self.c,1,{'node':'tense-perfect'});self.assertNotIn(new,[r['id'] for r in rows]);self.assertNotIn(q['id'],[r['id'] for r in rows])
  # Unseen items are preferred, with no answer leaked to the quiz response.
  self.assertNotIn('answer',rows[0].keys())
  count=self.c.execute('SELECT COUNT(*) FROM questions').fetchone()[0]
  with self.assertRaises(ValueError):learning.post(self.c,1,True,'/api/manage/import',{'items':[data,{**data,'answer':9}]},None)
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM questions').fetchone()[0],count)
  result,status=learning.post(self.c,1,True,'/api/manage/import',{'items':[{**data,'status':'published'}]},None);self.assertEqual(status,200)
  self.assertEqual(self.c.execute('SELECT status FROM questions WHERE id=?',(result['ids'][0],)).fetchone()[0],'draft')
  self.assertEqual(learning.get(self.c,1,False,'/api/manage/questions',{})[1],403)
 def test_generation_and_portfolio_validation(self):
  def model(c,uid,d):return {'reply':json.dumps({'prompt':'Test ____','options':['a','b','c','d'],'answer':0,'explanation':'Explanation'}),'request_id':d['request_id'],'mode':'ai'},200
  data={'node':'tense-perfect','request_id':'generated-request-123'}
  a=learning.post(self.c,1,True,'/api/manage/generate',data,model);b=learning.post(self.c,1,True,'/api/manage/generate',data,model);self.assertEqual(a,b)
  self.assertEqual(self.c.execute('SELECT status FROM questions WHERE id=?',(a[0]['id'],)).fetchone()[0],'draft')
  self.assertEqual(learning.post(self.c,1,False,'/api/practices/save',{'task':'writing-1','answer':'Hello','chat_request':'nonowned'},None)[1],400)
  self.assertEqual(learning.post(self.c,1,False,'/api/practices/save',{'task':'writing-1','answer':'Hello'},None)[1],200)
  self.assertEqual(len(learning.get(self.c,2,False,'/api/practices',{})[0]['history']),0)
  topic=self.c.execute("SELECT * FROM topics WHERE id='clause'").fetchone();messages=chat.context(self.c,1,topic,'【训练任务:reading-1】My answer')
  self.assertIn('Lina',messages[0]['content'])
 def test_backup_restore_drill(self):
  root=Path(self.tmp.name);(root/'data').mkdir();self.c.commit();self.c.close();self.c=app.db()
  with app.db() as src,sqlite3.connect(root/'data/flow.sqlite3') as dst:src.backup(dst)
  with patch.object(ops,'ROOT',root),patch.object(ops,'BACKUPS',root/'backups'):
   folder=ops.backup();self.assertTrue((folder/'manifest.json').exists());ops.restore(folder,False)
   self.assertTrue(json.loads((root/'data/backup-status.json').read_text())['ok'])
   with sqlite3.connect(root/'data/flow.sqlite3') as live:live.execute("UPDATE users SET username='changed' WHERE id=1")
   with patch('pwd.getpwnam',return_value=SimpleNamespace(pw_uid=os.getuid(),pw_gid=os.getgid())),patch.object(ops.subprocess,'run') as service:
    ops.restore(folder,True)
    self.assertEqual(service.call_args_list[0].args[0],['systemctl','stop','flow'])
    self.assertEqual(service.call_args_list[-1].args[0],['systemctl','start','flow'])
   with sqlite3.connect(root/'data/flow.sqlite3') as restored:self.assertEqual(restored.execute('SELECT username FROM users WHERE id=1').fetchone()[0],'owner')
 def test_migration_no_duplicate_seed(self):
  before=self.c.execute('SELECT COUNT(*) FROM questions').fetchone()[0];self.c.close();app.init();self.c=app.db();self.assertEqual(self.c.execute('SELECT COUNT(*) FROM questions').fetchone()[0],before)

class RecoveryTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'recovery.db');self.p.start();app.init();self.c=app.db()
  self.c.execute('INSERT INTO users(username,password) VALUES(?,?)',('recover',app.password('strongtest123')));self.c.commit()
  self.env=patch.dict(os.environ,{'FLOW_SMTP_HOST':'mail.test','FLOW_SMTP_FROM':'flow@test.example','FLOW_SMTP_USER':'flow','FLOW_SMTP_PASSWORD':'test'});self.env.start()
 def tearDown(self):self.c.close();self.p.stop();self.env.stop();self.tmp.cleanup()
 def test_binding_reset_expiry_and_session_invalidation(self):
  u={'id':1};self.assertEqual(account.private(self.c,u,'/api/account/email/request',{'email':'me@example.com','password':'bad'},app.verify)[1],400)
  with patch.object(account,'mail') as send:
   self.assertEqual(account.private(self.c,u,'/api/account/email/request',{'email':'me@example.com','password':'strongtest123'},app.verify)[1],200)
   token=send.call_args[0][2].split('\n')[1]
  # Tokens must not be stored as plaintext.
  self.assertNotEqual(self.c.execute('SELECT digest FROM recovery_tokens').fetchone()[0],token)
  self.assertEqual(account.private(self.c,u,'/api/account/email/confirm',{'token':token},app.verify)[1],200)
  self.assertEqual(account.private(self.c,u,'/api/account/email/confirm',{'token':token},app.verify)[1],400)
  self.c.execute("INSERT INTO sessions VALUES('session',1,'csrf',?)",(time.time()+100,));self.c.commit()
  with patch.object(account,'mail') as send:
   self.assertEqual(account.public(self.c,'/api/recovery/request',{'email':'me@example.com'},app.password,'1.2.3.4')[1],200)
   token=send.call_args[0][2].split('#reset=')[1].split('\n')[0]
  self.assertEqual(account.public(self.c,'/api/recovery/reset',{'token':token,'password':'newstrong1234'},app.password,'ip')[1],200)
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM sessions').fetchone()[0],0)
  self.assertTrue(app.verify('newstrong1234',self.c.execute('SELECT password FROM users').fetchone()[0]))
  self.assertEqual(account.public(self.c,'/api/recovery/reset',{'token':token,'password':'newstrong1234'},app.password,'ip')[1],400)
 def test_expired_and_unknown_email(self):
  with patch.object(account,'mail') as send:
   account.public(self.c,'/api/recovery/request',{'email':'unknown@example.com'},app.password,'ip');send.assert_not_called()
   account.issue(self.c,1,'me@example.com','bind');token=send.call_args[0][2].split('\n')[1]
  self.c.execute('UPDATE recovery_tokens SET expires=0');self.c.commit()
  self.assertEqual(account.private(self.c,{'id':1},'/api/account/email/confirm',{'token':token},app.verify)[1],400)
if __name__=='__main__':unittest.main()
