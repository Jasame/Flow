import sys,tempfile,unittest,json,time,os,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,daily_service as daily,knowledge_service as kg,lab_service as lab
from content_v07 import all_materials
class DailyKnowledgeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'daily.db');self.p.start();app.init();self.c=app.db()
  self.c.executemany('INSERT INTO users(username,password) VALUES(?,?)',[('one','hash'),('two','hash')]);self.c.commit()
  self.env=patch.dict(os.environ,{'FLOW_AI_GROUNDING':'1','FLOW_AI_DAILY_LIMIT':'100'});self.env.start()
  self.brief='A museum has opened a new room. Visitors can read short labels. Staff will collect comments.'
  self.meta={'groundingChunks':[{'web':{'uri':'https://example.org/news','title':'Museum'}}], 'groundingSupports':[{'segment':{'text':'A museum has opened a new room.'},'groundingChunkIndices':[0]}], 'searchEntryPoint':{'renderedContent':'<style>.chip{color:blue}</style><a href="https://google.com/search?q=museum">Museum</a>'},'webSearchQueries':['museum today']}
 def tearDown(self):self.c.close();self.env.stop();self.p.stop();self.tmp.cleanup()
 def raw(self):
  p=copy.deepcopy(all_materials()[0]);p['level']=daily.plan(daily.today())[0];p['theme']='campus';p['knowledge']=[{'node':'tense-present','quote':lab.sentences(p['body'])[0],'explanation':'说明该句的用法'}];return p
 CLEAN=json.dumps({k:False for k in daily.SELF_CHECK})
 def run_mock(self,raw=None,verdict=None):
  """今日一读: one call writes, one call checks; nothing searched (grounding never asked for)."""
  calls=[(json.dumps(raw or self.raw()),'stop'),(verdict or self.CLEAN,'stop')]
  with patch.object(daily,'request_model',side_effect=calls) as model:result=daily.run(self.c)
  self.assertFalse(any(k.kwargs.get('grounding') for k in model.call_args_list))
  return result,model.call_count
 def test_success_is_an_original_topic_text_linked_into_the_graph(self):
  d,count=self.run_mock();self.assertEqual(d['status'],'complete');self.assertEqual(count,2)
  self.assertEqual(daily.run(self.c)['status'],'complete');self.assertEqual(self.c.execute('SELECT SUM(count) FROM ai_usage').fetchone()[0],2)
  p=lab.pack_for(self.c,2,'daily-'+daily.today())
  self.assertEqual((p['kind'],p['ai'],p['source']),('topic','AI 生成','Flow 原创（AI 生成）'));self.assertNotIn('provenance',p)
  self.assertIn(p['topic'],{t[0] for t in daily.TOPIC_LIST}|{f[2] for f in daily.FESTIVALS});self.assertEqual(p['tags'][0],daily.DAILY_NAME)
  self.assertEqual(p['grammar'],['tense-present']);self.assertFalse(daily.retired(p))
  g=kg.graph(self.c,1);node=next(n for n in g['nodes'] if n['id']=='tense-present');self.assertEqual(node['state'],'待建立');self.assertTrue(any(x['id']==p['id'] for x in node['materials']))
 def test_news_or_politics_words_stop_it_before_the_self_check(self):
  raw=self.raw();raw['body']=raw['body']+' The government said the new rule starts next month.'
  d,count=self.run_mock(raw);self.assertEqual(d['status'],'failed');self.assertEqual(count,1)
  self.assertIn('新闻、时政',self.c.execute('SELECT error FROM daily_runs').fetchone()[0])
  raw=self.raw();raw['body']=raw['body']+' In 2019, prices rose by 12 percent.'
  self.assertEqual(self.run_mock(raw)[0]['status'],'failed')
  with patch.object(daily,'request_model') as model:daily.run(self.c);model.assert_not_called()  # two tries a day at most
  self.assertEqual(self.c.execute("SELECT COUNT(*) FROM lab_packs WHERE origin='daily'").fetchone()[0],0)
 def test_the_models_own_check_says_yes_and_nothing_is_published(self):
  for k in daily.SELF_CHECK:
   self.assertFalse(daily.passes(json.dumps(dict(json.loads(self.CLEAN),**{k:True}))),k)
  self.assertFalse(daily.passes('{"politics": false}'));self.assertFalse(daily.passes('not json'))
  d,count=self.run_mock(verdict=json.dumps(dict(json.loads(self.CLEAN),real_person=True)))
  self.assertEqual(d['status'],'failed');self.assertEqual(count,2);self.assertIn('自查',self.c.execute('SELECT error FROM daily_runs').fetchone()[0])
  self.assertEqual(self.c.execute("SELECT COUNT(*) FROM lab_packs WHERE origin='daily'").fetchone()[0],0)
 def test_topics_take_turns_and_festivals_come_once(self):
  kinds=[next(k for k,v in daily.POOL.items() if t in v) for t in daily.TOPIC_LIST[:5]]
  self.assertEqual(len(set(kinds)),5)  # five kinds in turn
  self.assertEqual(daily.plan('2026-12-19')[1][0],'winter-solstice');self.assertEqual(daily.plan('2026-12-21')[1][0],'winter-solstice')
  self.assertNotEqual(daily.plan('2026-12-20',recent=('winter-solstice',))[1][0],'winter-solstice')  # once
  self.assertNotEqual(daily.plan('2026-12-18')[1][0],'winter-solstice')  # three days early: not yet
  a=daily.plan('2026-11-26')[1];self.assertNotEqual(daily.plan('2026-11-26',recent=(a[0],))[1][0],a[0])
  for t in daily.TOPIC_LIST+tuple(f[2:] for f in daily.FESTIVALS):
   self.assertIn(t[3],('campus','travel','life','work','culture','science'));self.assertIn(t[4],('news-commentary','film-culture','workplace','campus-life','daily-life','expository','argumentative','story'))
   self.assertEqual(__import__('topic_guard').hits({'body':t[2]}),[],t)
  msg=daily.write_messages('B1',daily.TOPIC_LIST[0],[])[1]['content']
  for rule in ('时政','新闻','真实人物','具体日期'):self.assertIn(rule,msg)
 def test_invalid_knowledge_evidence_rejected(self):
  raw=self.raw();raw['knowledge'][0]['quote']='This never appeared.'
  self.assertEqual(self.run_mock(raw)[0]['status'],'failed')
 def test_global_quota_blocks_and_running_lease_prevents_duplicate(self):
  self.c.execute('INSERT INTO ai_usage VALUES(0,?,100)',(time.strftime('%Y-%m-%d',time.gmtime()),));self.c.commit()
  with patch.object(daily,'request_model') as m:self.assertEqual(daily.run(self.c)['status'],'failed');m.assert_not_called()
  self.c.execute("UPDATE daily_runs SET status='running',attempts=1,updated=?",(time.time(),));self.c.commit()
  with patch.object(daily,'request_model') as m:self.assertEqual(daily.run(self.c)['status'],'running');m.assert_not_called()
 def test_source_and_support_validation(self):  # provenance() stays for search_eval.py
  for url in ('javascript:alert(1)','http://example.org','https://x:y@example.org'):
   meta=copy.deepcopy(self.meta);meta['groundingChunks'][0]['web']['uri']=url
   with self.assertRaises(ValueError):daily.provenance(self.brief,meta)
  meta=copy.deepcopy(self.meta);meta['groundingSupports'][0]['groundingChunkIndices']=[99]
  with self.assertRaises(ValueError):daily.provenance(self.brief,meta)
 def test_material_exposure_owned_and_does_not_inflate_mastery(self):
  p=all_materials()[0];node=p['grammar'][0]
  self.c.execute('INSERT INTO lab_work(user_id,pack,skill,answer,feedback_request,details,save_id,created) VALUES(?,?,?,?,?,?,?,?)',(1,p['id'],'reading','my answer','','{}','work-001',time.time()));self.c.commit()
  a=next(n for n in kg.graph(self.c,1)['nodes'] if n['id']==node);b=next(n for n in kg.graph(self.c,2)['nodes'] if n['id']==node)
  self.assertEqual(a['practice_count'],1);self.assertEqual(b['practice_count'],0);self.assertEqual(a['distinct'],0);self.assertEqual(a['state'],'待建立')
 def test_every_graph_node_has_an_original_context_with_valid_anchors(self):
  from content_v08 import all_materials,BRIDGES
  from content_v05 import NODES
  packs=all_materials();self.assertEqual(len(packs),46)
  self.assertEqual({n[0] for n in NODES},{n for p in packs for n in p['grammar']})
  for p in BRIDGES:
   lab.validate_pack(copy.deepcopy(p))
   for k in p['knowledge']:self.assertIn(k['quote'],p['body'])
   for q in p['questions']:self.assertIn(q['evidence'],p['body'])
 def test_disabled_does_not_call_ai(self):
  with patch.dict(os.environ,{'FLOW_AI_GROUNDING':'0'}),patch.object(daily,'request_model') as m:self.assertEqual(daily.run(self.c)['status'],'disabled');m.assert_not_called()
if __name__=='__main__':unittest.main()
