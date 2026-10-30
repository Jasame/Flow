import copy,json,os,sqlite3,sys,tempfile,time,unittest,zipfile,subprocess
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,adaptive_service as a,event_service as ev,lexicon_service as lex,graph_service as graph,lab_service as lab
class AdaptiveTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.dbpatch=patch.object(app,'DB',Path(self.tmp.name)/'flow.sqlite3');self.dbpatch.start();app.init();self.c=app.db()
  self.c.executemany('INSERT INTO users(username,password,admin) VALUES(?,?,?)',[('learner','hash',0),('other','hash',0),('teacher','hash',1)]);self.c.commit()
  self.entry=lex.key('suggest','advice')
 def tearDown(self):self.c.close();self.dbpatch.stop();self.tmp.cleanup()
 def start(self,entry=None,uid=1):return a.start(self.c,uid,{'kind':'vocab','entry':entry or self.entry})[0]['task']
 def correct(self,t):return json.loads(self.c.execute('SELECT answer FROM adaptive_tasks WHERE token=?',(t['token'],)).fetchone()[0]).get('correct')
 def answer(self,t,correct=True,uid=1):
  value=self.correct(t) if t['mode']!='spelling' else 'suggest'
  if not correct:value=(value+1)%4 if type(value)==int else 'wrong'
  return a.submit(self.c,uid,{'token':t['token'],'answer':value})
 def test_initial_graph_has_word_sense_pattern_grammar_material_and_skills(self):
  self.assertEqual(self.c.execute("SELECT COUNT(*) FROM lexicon WHERE origin='starter'").fetchone()[0],100)
  n=graph.network(self.c,1);self.assertEqual({v['kind'] for v in n['nodes']},{'word','sense','pattern','grammar','material','skill','lesson'})
  sid=lex.node_id(self.entry);d=graph.detail(self.c,1,sid)
  self.assertTrue(any(e['relation']=='has_pattern' for e in d['network']['edges']));self.assertTrue(any(e['target']=='nonfinite-gerund' for e in d['network']['edges']))
  self.assertEqual(d['state']['independent'],0)
 def test_task_does_not_reveal_answer_and_double_submission_is_idempotent(self):
  t=self.start();self.assertNotIn('correct',t['payload']);self.assertNotIn('answer',t)
  r,code=self.answer(t);self.assertEqual(code,200);self.assertTrue(r['correct']);due=self.c.execute('SELECT due FROM vocab_enroll').fetchone()[0]
  self.assertEqual(self.answer(t)[1],200);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM learning_events').fetchone()[0],1)
  self.assertEqual(a.submit(self.c,1,{'token':t['token'],'answer':(self.correct(t)+1)%4})[1],409)
  self.assertEqual(self.c.execute('SELECT due FROM vocab_enroll').fetchone()[0],due)
 def test_task_ownership_and_paused_tasks(self):
  t=self.start()
  with self.assertRaises(ValueError):a.submit(self.c,2,{'token':t['token'],'answer':0})
  a.post(self.c,1,False,'/api/adaptive/skip',{'token':t['token']})
  self.assertEqual(self.answer(t)[1],409)
 def test_hint_is_server_recorded_and_cannot_establish_independent_mastery(self):
  t=self.start();a.hint(self.c,1,{'token':t['token']});r,_=self.answer(t)
  self.assertTrue(r['assisted']);self.assertEqual(r['state']['state'],'提示后完成');self.assertEqual(r['state']['independent'],0)
 def test_early_repeat_does_not_advance_interval(self):
  t=self.start();self.answer(t);old=dict(self.c.execute('SELECT * FROM vocab_enroll').fetchone());t=self.start();self.assertEqual(t['mode'],'spelling');self.answer(t)
  new=dict(self.c.execute('SELECT * FROM vocab_enroll').fetchone());self.assertEqual(old['due'],new['due']);self.assertEqual(old['stage'],new['stage'])
 def test_self_rating_never_becomes_rule_pass_and_is_idempotent(self):
  body={'entry':self.entry,'rating':'remembered','request_id':'rating-request-0001'}
  for _ in range(2):self.assertEqual(a.post(self.c,1,False,'/api/vocab/rate',body)[1],200)
  s=ev.state(self.c,1,lex.node_id(self.entry));self.assertEqual(s['self_ratings'],1);self.assertEqual(s['independent'],0);self.assertEqual(s['delayed'],0)
 def test_delay_and_transfer_require_time_and_new_context(self):
  base=time.time()-3*86400;node=lex.node_id(self.entry)
  ev.record(self.c,1,node,'s1','meaning','q1','entry',True,False,'rule',created=base)
  ev.record(self.c,1,node,'s2','spelling','q2','news-a',True,False,'rule',created=base+100)
  self.assertEqual(ev.state(self.c,1,node)['transfer'],0)
  ev.record(self.c,1,node,'s3','spelling','q3','news-b',True,False,'rule',created=base+86500)
  self.assertEqual(ev.state(self.c,1,node)['state'],'迁移已有证据')
  ev.record(self.c,1,node,'s4','spelling','q4','news-c',False,False,'rule',created=base+90000)
  self.assertEqual(ev.state(self.c,1,node)['state'],'需要巩固')
 def test_grammar_results_enter_old_and_new_evidence_once(self):
  t=a.start(self.c,1,{'kind':'grammar','node':'nonfinite-gerund'})[0]['task'];self.answer(t)
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],1)
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM learning_events WHERE node=?',('nonfinite-gerund',)).fetchone()[0],1)
  self.assertEqual(ev.state(self.c,1,'nonfinite-gerund')['independent'],1)
  self.answer(t);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],1)
 def test_goal_controls_budget_and_new_words(self):
  a.post(self.c,1,False,'/api/adaptive/goal',{'goal':'travel','minutes':5,'daily_new':1,'level':'A2'})
  p=a.plan(self.c,1);self.assertLessEqual(sum(t['minutes'] for t in p['tasks']),5)
  t=self.start();self.answer(t);self.assertIsNone(a.vocab_choice(self.c,1))
 def test_private_words_and_graph_are_owner_filtered(self):
  self.c.execute('INSERT INTO wordbook(user_id,term,meaning,example,due,created) VALUES(?,?,?,?,?,?)',(1,'privateword','私人含义','A private example.',time.time(),time.time()));wid=self.c.execute('SELECT id FROM wordbook').fetchone()[0];lex.sync_personal(self.c,1,wid);self.c.commit()
  entry='private-1-'+str(wid);self.assertTrue(lex.entry_for(self.c,1,entry))
  with self.assertRaises(ValueError):lex.entry_for(self.c,2,entry)
  self.assertFalse(any('privateword' in n['title'] for n in graph.network(self.c,2)['nodes']))
 def test_drafts_and_reports_are_private(self):
  a.post(self.c,1,False,'/api/vocab/draft',{'entry':self.entry,'answer':'Private draft.'})
  self.assertEqual(a.get(self.c,2,False,'/api/vocab/entry',{'id':[self.entry]})[0]['draft'],'')
  t=self.start();self.answer(t);self.assertEqual(ev.report(self.c,2)['events'],0)
 def test_ai_feedback_is_validated_cached_and_does_not_certify_mastery(self):
  answer='I suggest to rest.';raw={'strength':'表达了建议','priorities':[{'issue':'搭配','evidence':'suggest to rest','suggestion':'使用动名词'}],'revision':'I suggest resting.','next_question':'What else do you suggest?','links':[{'node':'nonfinite-gerund','evidence':'suggest to rest','reason':'验证动名词搭配'}]};body={'entry':self.entry,'answer':answer,'request_id':'feedback-request-0001'}
  with patch.object(lab,'ai_enabled',return_value=True),patch('chat_service.request_model',return_value=(json.dumps(raw),'stop')) as model:
   first=a.feedback(self.c,1,body);second=a.feedback(self.c,1,body);self.assertEqual(first[1],200);self.assertEqual(second[1],200);self.assertEqual(model.call_count,1)
  s=ev.state(self.c,1,lex.node_id(self.entry));self.assertEqual(s['independent'],0);self.assertEqual(s['ai_observations'],1)
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM ai_observations').fetchone()[0],1)
  self.assertEqual(a.get(self.c,1,False,'/api/vocab/entry',{'id':[self.entry]})[0]['last_feedback']['result']['revision'],'I suggest resting.')
  a.post(self.c,1,False,'/api/vocab/draft',{'entry':self.entry,'answer':'I suggest resting.'})
  self.assertNotIn('last_feedback',a.get(self.c,1,False,'/api/vocab/entry',{'id':[self.entry]})[0])
 def test_ai_fabricated_grammar_quote_is_rejected(self):
  raw={'strength':'Good','priorities':[{'issue':'Use','evidence':'suggest','suggestion':'Try'}],'revision':'I suggest resting.','next_question':'Why?','links':[{'node':'nonfinite-gerund','evidence':'never said this','reason':'Wrong'}]}
  with patch.object(lab,'ai_enabled',return_value=True),patch('chat_service.request_model',return_value=(json.dumps(raw),'stop')):
   self.assertEqual(a.feedback(self.c,1,{'entry':self.entry,'answer':'I suggest to rest.','request_id':'feedback-badquote-01'})[1],502)
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM ai_observations').fetchone()[0],0)
 def test_import_review_version_guard_and_disabled_hides_from_graph(self):
  e={'word':'reconsider','sense':'core','meaning':'重新考虑','example':'We should reconsider the plan.'}
  self.assertEqual(a.post(self.c,1,False,'/api/vocab/import',{'items':[e]})[1],403)
  out,code=a.manage(self.c,3,'/api/vocab/import',{'items':[e]});self.assertEqual(code,200);entry=out['ids'][0]
  with self.assertRaises(ValueError):lex.entry_for(self.c,1,entry)
  self.assertFalse(any(n['ref']==entry for n in graph.network(self.c,1)['nodes']))
  self.assertEqual(a.manage(self.c,3,'/api/vocab/publish',{'entry':entry,'version':0,'status':'published'})[1],409)
  a.manage(self.c,3,'/api/vocab/publish',{'entry':entry,'version':1,'status':'published'});self.assertTrue(lex.entry_for(self.c,1,entry))
  a.manage(self.c,3,'/api/vocab/publish',{'entry':entry,'version':2,'status':'disabled'})
  self.assertFalse(any(n['ref']==entry for n in graph.network(self.c,1)['nodes']))
 def test_daily_candidates_are_not_automatically_public(self):
  p=copy.deepcopy(__import__('content_v08').all_materials()[0]);p['id']='daily-candidate';p['vocabulary']=[{'term':'newcandidate','meaning':'候选词','example':'A newcandidate appears.'}]
  self.c.execute('INSERT INTO lab_packs VALUES(?,NULL,?,?,?)',(p['id'],'daily',json.dumps(p),time.time()));lex.collect_candidates(self.c,p['id']);self.c.commit()
  self.assertEqual(self.c.execute('SELECT status FROM lexicon WHERE lemma=?',('newcandidate',)).fetchone()[0],'draft');self.assertFalse(any(w['word']=='newcandidate' for w in lex.catalog(self.c,1)))
 def test_learning_plan_changes_after_completion_and_reuses_active_task(self):
  before=a.plan(self.c,1);first=a.start(self.c,1,{})[0]['task'];resumed=a.start(self.c,1,{})[0];self.assertEqual(first['token'],resumed['task']['token']);self.answer(first);after=a.plan(self.c,1)
  self.assertNotEqual(before['next']['kind'],after['next']['kind'])
 def test_studio_hint_not_mislabelled_independent(self):
  p=__import__('content_v08').all_materials()[0];lab.post(self.c,1,'/api/lab/support',{'pack':p['id'],'skill':'listening','action':'start'})
  lab.post(self.c,1,'/api/lab/support',{'pack':p['id'],'skill':'listening','action':'hint'})
  result,status=lab.post(self.c,1,'/api/lab/comprehension',{'pack':p['id'],'skill':'listening','choices':[q['answer'] for q in p['questions']],'save_id':'studio-hinted-0001'})
  self.assertEqual(status,200);self.assertEqual(result['details']['assisted'],1);self.assertEqual(ev.state(self.c,1,'skill:listening')['independent'],0)
 def test_context_explanation_is_cached_without_mastery(self):
  row=self.c.execute("SELECT l.id,n.ref FROM lexicon l JOIN kg_nodes s ON s.ref=l.id AND s.kind='sense' JOIN kg_edges e ON e.source=s.id AND e.relation='occurs_in' JOIN kg_nodes n ON n.id=e.target LIMIT 1").fetchone();entry=lex.entry_for(self.c,1,row['id']);pack=lab.pack_for(self.c,1,row['ref']);index=next(i for i,s in enumerate(lab.sentences(pack['body'])) if __import__('re').search(r'(?<![a-z])'+__import__('re').escape(entry['lemma'])+r'(?![a-z])',s,__import__('re').I))
  body={'entry':row['id'],'pack':row['ref'],'sentence_index':index,'request_id':'context-explain-0001'};raw={'meaning':'本句词义','explanation':'本句说明','example':'An original example.','translation':'原创例句。'}
  with patch.object(lab,'ai_enabled',return_value=True),patch('chat_service.request_model',return_value=(json.dumps(raw),'stop')) as m:
   self.assertEqual(a.explain(self.c,1,body)[1],200);self.assertTrue(a.explain(self.c,1,dict(body,request_id='context-explain-0002'))[0]['cached']);self.assertEqual(m.call_count,1)
  self.assertEqual(ev.state(self.c,1,lex.node_id(row['id']))['independent'],0)
 def test_restart_preserves_schedule_and_does_not_duplicate_events(self):
  task=self.start();self.answer(task);due=self.c.execute('SELECT due FROM vocab_enroll').fetchone()[0];self.c.close();app.init();app.init();self.c=app.db();self.assertEqual(self.c.execute('SELECT COUNT(*) FROM learning_events').fetchone()[0],1);self.assertEqual(self.c.execute('SELECT due FROM vocab_enroll').fetchone()[0],due);self.assertFalse(self.c.execute('PRAGMA foreign_key_check').fetchall())
if __name__=='__main__':unittest.main()

class PreviousReleaseMigrationTests(unittest.TestCase):
 def test_real_v08_snapshot_preserves_accounts_attempts_words_work_and_due_dates(self):
  archive=Path(__file__).resolve().parents[2]/'Flow-v0.8-Upgrade.zip'
  if not archive.exists():self.skipTest('v0.8 archive fixture is only available in the source workspace')
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);old=root/'old';old.mkdir();data=root/'data'
   with zipfile.ZipFile(archive) as z:
    for name in z.namelist():
     if name.startswith('flow/') and name.count('/')==1 and name.endswith('.py'):(old/Path(name).name).write_bytes(z.read(name))
   script="""import app,time,json
app.init()
with app.db() as c:
 c.execute("INSERT INTO users(id,username,password,admin) VALUES(7,'existing','original-hash',1)")
 c.execute('INSERT INTO attempts(user_id,question_id,selected,correct,created) VALUES(7,1,0,1,10)')
 c.execute('INSERT INTO question_skill_attempts VALUES(1,?)',(c.execute('SELECT node FROM questions WHERE id=1').fetchone()[0],))
 c.execute("INSERT INTO wordbook(user_id,term,meaning,example,stage,due,created) VALUES(7,'example','示例','An example.',3,9999999999,10)")
 c.execute("INSERT INTO wordbook(user_id,term,meaning,example,stage,due,created) VALUES(7,'中文备注','保留旧记录','—',0,9999999998,10)")
 c.execute("INSERT INTO lab_work(user_id,pack,skill,answer,feedback_request,details,save_id,created) VALUES(7,'campus-a2','writing','Old private answer.','','{\\\"kind\\\":\\\"work\\\"}','old-save-0001',20)")
"""
   env={**os.environ,'FLOW_DATA_DIR':str(data)};r=subprocess.run([sys.executable,'-c',script],cwd=old,env=env,capture_output=True,text=True);self.assertEqual(r.returncode,0,r.stderr)
   with patch.object(app,'DB',data/'flow.sqlite3'):
    app.init();app.init()
    with app.db() as c:
     self.assertEqual(c.execute('SELECT password FROM users WHERE id=7').fetchone()[0],'original-hash')
     self.assertEqual(c.execute('SELECT COUNT(*) FROM attempts').fetchone()[0],1);self.assertEqual(c.execute('SELECT COUNT(*) FROM wordbook').fetchone()[0],2)
     self.assertEqual(c.execute('SELECT due FROM vocab_enroll WHERE user_id=7').fetchone()[0],9999999999)
     self.assertEqual(c.execute('SELECT answer FROM lab_work WHERE user_id=7').fetchone()[0],'Old private answer.')
     state=ev.state(c,7,c.execute('SELECT node FROM question_skill_attempts').fetchone()[0]);self.assertEqual(state['independent'],0);self.assertTrue(any(e['evaluator']=='legacy' for e in state['evidence']))
     self.assertFalse(c.execute('PRAGMA foreign_key_check').fetchall())
