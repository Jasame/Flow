import unittest,tempfile,json,sys,time,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,reference_service as ref,lexicon_service as lex,graph_service as graph,adaptive_service as adaptive,lab_service as lab,growth_service as growth,coach_service as coach
from content_v08 import all_materials
class ReferenceTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'reference.db');self.p.start();app.init();self.c=app.db();self.c.executemany('INSERT INTO users(username,password) VALUES(?,?)',[('one','hash'),('two','hash')]);self.c.commit()
 def tearDown(self):self.c.close();self.p.stop();self.tmp.cleanup()
 def term(self,word):return ref.entry(self.c,1,self.c.execute('SELECT id FROM reference_terms WHERE norm=?',(word,)).fetchone()[0])
 def payload(self,word='suggest'):
  t=self.term(word);v=next(v for v in t['variants'] if v['parsed_examples']);return {'reference':t['id'],'row':v['row'],'example':0,'level':'B1','theme':'life','request_id':'reference-request-00001'}
 def test_all_rows_preserved_and_no_automatic_lexicon_or_graph_explosion(self):
  meta=ref.summary(self.c);self.assertEqual(meta['stats']['rows'],20200);self.assertEqual(meta['stats']['terms'],17634);self.assertEqual(meta['stats']['terms_with_examples'],1010)
  self.assertEqual(sum(len(json.loads(r[0])['variants']) for r in self.c.execute('SELECT content FROM reference_terms')),20200)
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM lexicon').fetchone()[0],107);app.init();self.assertEqual(self.c.execute('SELECT COUNT(*) FROM reference_terms').fetchone()[0],17634)
 def test_bounded_paging_and_safe_search_filters(self):
  out,_=ref.get(self.c,1,'/api/reference',{});self.assertEqual(len(out['items']),30);self.assertEqual(out['total'],17634)
  out,_=ref.get(self.c,1,'/api/reference',{'q':['sugg']});self.assertTrue(all(x['word'].casefold().startswith('sugg') for x in out['items']))
  out,_=ref.get(self.c,1,'/api/reference',{'scope':['examples']});self.assertEqual(out['total'],1010)
  for q in ("' OR 1=1 --",'%','_'):
   out,_=ref.get(self.c,1,'/api/reference',{'q':[q]});self.assertEqual(out['total'],0)
 def test_source_examples_split_without_rewriting_original(self):
  t=self.term('the');v=t['variants'][0];self.assertEqual(len(v['parsed_examples']),3);self.assertEqual(v['parsed_examples'][0]['english'],'The sun rises in the east.');self.assertEqual(v['parsed_examples'][0]['translation'],'太阳从东方升起。');self.assertIn('1. The',v['examples'])
  self.assertTrue(self.term('be')['flags']);self.assertGreater(len(self.term('like')['variants']),1)
 def test_source_adoption_is_private_idempotent_enrolled_and_connected(self):
  data=self.payload();out,status=ref.post(self.c,1,'/api/reference/adopt',data);self.assertEqual(status,200);id=out['entry'];entry=lex.detail(self.c,1,id);self.assertTrue(entry['enrolled']);self.assertEqual(entry['reference']['row'],data['row'])
  self.assertEqual(ref.post(self.c,1,'/api/reference/adopt',data)[0]['entry'],id);self.assertEqual(adaptive.vocab_choice(self.c,1)[0],id)
  g=graph.network(self.c,1);self.assertTrue(any(n['id']==lex.node_id(id) for n in g['nodes']));self.assertFalse(any(n['id']==lex.node_id(id) for n in graph.network(self.c,2)['nodes']))
  self.assertIsNone(ref.entry(self.c,2,data['reference'])['adopted'])
  with self.assertRaises(ValueError):lex.detail(self.c,2,id)
 def test_mismatched_row_invalid_word_and_missing_example_rejected(self):
  d=self.payload();d['row']=999999
  with self.assertRaises(ValueError):ref.post(self.c,1,'/api/reference/adopt',d)
  t=self.term('1');d.update(reference=t['id'],row=t['variants'][0]['row'])
  with self.assertRaises(ValueError):ref.post(self.c,1,'/api/reference/adopt',d)
 def test_source_inflected_example_can_be_selected_without_rewriting_it(self):
  d=self.payload();d['example']=1;t=self.term('suggest');v=next(v for v in t['variants'] if v['row']==d['row']);expected=v['parsed_examples'][1]['english']
  result,status=ref.post(self.c,1,'/api/reference/adopt',d);self.assertEqual(status,200);self.assertEqual(lex.detail(self.c,1,result['entry'])['data']['example'],expected)
 def test_enrollment_failure_rolls_back_word_and_audit(self):
  d=self.payload()
  with patch.object(adaptive,'enroll',side_effect=ValueError('full')):
   with self.assertRaises(ValueError):ref.post(self.c,1,'/api/reference/adopt',d)
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM reference_adoptions').fetchone()[0],0);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM lexicon').fetchone()[0],107)
 def generated(self):
  p=copy.deepcopy(all_materials()[0]);p['level']='B1';p['theme']='life';p['body']='I suggest a walk after lunch. We can meet at the park. We will take some water.';p['dictation_index']=1;p['vocabulary']=[{'term':'suggest','meaning':'建议','example':'I suggest a walk.'}]
  p['questions']=[{'prompt':'What is suggested?','options':['A walk','A car','A book','A bus'],'answer':0,'evidence':'I suggest a walk after lunch.'},{'prompt':'Where can we meet?','options':['At the park','At school','In the office','At home'],'answer':0,'evidence':'We can meet at the park.'}];return p
 def test_gemini_generates_owned_pack_word_graph_and_reuses_job(self):
  d=self.payload();p=self.generated()
  with patch.object(lab,'ai_enabled',return_value=True),patch.object(lab,'request_model',return_value=(json.dumps(p),'stop')) as model:
   out,status=ref.post(self.c,1,'/api/reference/generate',d);self.assertEqual(status,200);self.assertEqual(model.call_count,1)
   cached,_=ref.post(self.c,1,'/api/reference/generate',d);self.assertEqual(cached['pack'],out['pack']);self.assertEqual(model.call_count,1)
  pack=lab.pack_for(self.c,1,out['pack']);self.assertEqual(pack['reference_source']['id'],d['reference']);self.assertTrue(self.c.execute('SELECT 1 FROM kg_edges WHERE source=? AND target=?',(lex.node_id(out['entry']),'material:'+out['pack'])).fetchone())
  with self.assertRaises(ValueError):lab.pack_for(self.c,2,out['pack'])
  self.assertEqual(len(lab.get(self.c,1,'/api/lab/pack',{'id':[out['pack']]})[0]['pack']['questions'][0]),2)
  self.assertEqual(lex.detail(self.c,1,out['entry'])['origin'],'reference-ai');self.assertFalse(__import__('quality_service').recommendable(self.c,self.c.execute('SELECT * FROM lab_packs WHERE id=?',(out['pack'],)).fetchone()))
 def test_generation_can_enrich_previously_adopted_word_without_overwriting_progress(self):
  d=self.payload();old,_=ref.post(self.c,1,'/api/reference/adopt',d);before=lex.detail(self.c,1,old['entry'])['data']
  with patch.object(lab,'ai_enabled',return_value=True),patch.object(lab,'request_model',return_value=(json.dumps(self.generated()),'stop')):
   out,status=ref.post(self.c,1,'/api/reference/generate',d)
  self.assertEqual(status,200);self.assertEqual(out['entry'],old['entry']);self.assertEqual(lex.detail(self.c,1,out['entry'])['data'],before);self.assertTrue(out['pack'])
 def test_wrong_target_model_output_does_not_create_word(self):
  d=self.payload();p=self.generated();p['vocabulary'][0]['term']='walk'
  with patch.object(lab,'ai_enabled',return_value=True),patch.object(lab,'request_model',return_value=(json.dumps(p),'stop')):
   out,status=ref.post(self.c,1,'/api/reference/generate',d)
  self.assertEqual(status,502);self.assertEqual(self.c.execute('SELECT COUNT(*) FROM reference_adoptions').fetchone()[0],0)
if __name__=='__main__':unittest.main()
