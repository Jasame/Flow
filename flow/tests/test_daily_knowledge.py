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
  p=copy.deepcopy(all_materials()[0]);p['level']=['A2','B1','B2'][__import__('datetime').date.fromisoformat(daily.today()).toordinal()%3];p['theme']='campus';p['knowledge']=[{'node':'tense-present','quote':lab.sentences(p['body'])[0],'explanation':'说明该句的用法'}];return p
 def run_mock(self,raw=None,meta=None):
  calls=[(self.brief,'stop',self.meta if meta is None else meta),(json.dumps(raw or self.raw()),'stop')]
  with patch.object(daily,'request_model',side_effect=calls) as model:result=daily.run(self.c)
  return result,model.call_count
 def test_success_cached_public_source_and_knowledge_evidence(self):
  d,count=self.run_mock();self.assertEqual(d['status'],'complete');self.assertEqual(count,2)
  self.assertEqual(daily.run(self.c)['status'],'complete');self.assertEqual(self.c.execute('SELECT SUM(count) FROM ai_usage').fetchone()[0],2)
  p=lab.pack_for(self.c,2,'daily-'+daily.today());self.assertEqual(p['provenance']['sources'][0]['url'],'https://example.org/news')
  self.assertEqual(p['grammar'],['tense-present']);self.assertIn('suggestions',p['provenance'])
  g=kg.graph(self.c,1);node=next(n for n in g['nodes'] if n['id']=='tense-present');self.assertEqual(node['state'],'待测评');self.assertTrue(any(x['id']==p['id'] for x in node['materials']))
 def test_no_grounding_never_publishes_and_retry_bounded(self):
  for i in range(2):self.assertEqual(self.run_mock(meta={})[0]['status'],'failed')
  with patch.object(daily,'request_model') as model:daily.run(self.c);model.assert_not_called()
  self.assertEqual(self.c.execute("SELECT COUNT(*) FROM lab_packs WHERE origin='daily'").fetchone()[0],0)
 def test_invalid_knowledge_evidence_rejected(self):
  raw=self.raw();raw['knowledge'][0]['quote']='This never appeared.'
  self.assertEqual(self.run_mock(raw)[0]['status'],'failed')
 def test_global_quota_blocks_and_running_lease_prevents_duplicate(self):
  self.c.execute('INSERT INTO ai_usage VALUES(0,?,100)',(time.strftime('%Y-%m-%d',time.gmtime()),));self.c.commit()
  with patch.object(daily,'request_model') as m:self.assertEqual(daily.run(self.c)['status'],'failed');m.assert_not_called()
  self.c.execute("UPDATE daily_runs SET status='running',attempts=1,updated=?",(time.time(),));self.c.commit()
  with patch.object(daily,'request_model') as m:self.assertEqual(daily.run(self.c)['status'],'running');m.assert_not_called()
 def test_source_and_support_validation(self):
  for url in ('javascript:alert(1)','http://example.org','https://x:y@example.org'):
   meta=copy.deepcopy(self.meta);meta['groundingChunks'][0]['web']['uri']=url
   with self.assertRaises(ValueError):daily.provenance(self.brief,meta)
  meta=copy.deepcopy(self.meta);meta['groundingSupports'][0]['groundingChunkIndices']=[99]
  with self.assertRaises(ValueError):daily.provenance(self.brief,meta)
 def test_material_exposure_owned_and_does_not_inflate_mastery(self):
  p=all_materials()[0];node=p['grammar'][0]
  self.c.execute('INSERT INTO lab_work(user_id,pack,skill,answer,feedback_request,details,save_id,created) VALUES(?,?,?,?,?,?,?,?)',(1,p['id'],'reading','my answer','','{}','work-001',time.time()));self.c.commit()
  a=next(n for n in kg.graph(self.c,1)['nodes'] if n['id']==node);b=next(n for n in kg.graph(self.c,2)['nodes'] if n['id']==node)
  self.assertEqual(a['practice_count'],1);self.assertEqual(b['practice_count'],0);self.assertEqual(a['distinct'],0);self.assertEqual(a['state'],'待测评')
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
