import unittest,tempfile,time,sys,json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,graph_service as graph,event_service as events,lexicon_service as lex,coach_service as coach,growth_service as growth
from placement_content import ITEMS

class AtlasTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'atlas.db');self.p.start();app.init();self.c=app.db();self.c.executemany('INSERT INTO users(username,password) VALUES(?,?)',[('one','hash'),('two','hash')]);self.entry=lex.key('suggest','advice');self.node=lex.node_id(self.entry);self.c.commit()
 def tearDown(self):self.c.close();self.p.stop();self.tmp.cleanup()
 def profile(self):
  token=coach.begin(self.c,1)[0]['token'];coach.assess(self.c,1,{'token':token,'goal':'旅行交流','interests':'旅行','minutes':15,'writing':'','answers':{p['id']:{'choice':None,'hinted':False} for p in ITEMS}});growth.stage(self.c,1,{'request_id':'atlas-stage-test-001'});self.c.commit()
 def test_new_user_focus_is_exploration_and_real_edges_only(self):
  g=graph.network(self.c,1);f=g['focus'];self.assertEqual(f['mode'],'explore');self.assertEqual(f['targets'],[]);self.assertLessEqual(len(f['nodes']),30)
  valid={n['id'] for n in f['nodes']}
  for e in f['edges']:
   self.assertIn(e['source'],valid);self.assertIn(e['target'],valid);self.assertTrue(self.c.execute('SELECT 1 FROM kg_edges WHERE source=? AND target=? AND relation=? AND origin=?',tuple(e[k] for k in ('source','target','relation','origin'))).fetchone())
 def test_aliases_share_state_but_summary_deduplicates(self):
  events.record(self.c,1,self.node,'only-pass','meaning','one','one',True,False,'rule');self.c.commit();g=graph.network(self.c,1)
  related=[n for n in g['nodes'] if n['ref']==self.entry and n['kind'] in ('word','sense','pattern')];self.assertGreater(len(related),2)
  self.assertTrue(all(n['status']=='independent' and n['state_node']==self.node for n in related if n['kind']!='pattern'));self.assertTrue(all(n['status']=='unknown' and n['state_node']==n['id'] for n in related if n['kind']=='pattern'));self.assertEqual(g['summary']['independent'],1);self.assertEqual(g['summary']['connected'],1)
 def test_repair_focus_and_details_keep_owner_evidence_separate(self):
  events.record(self.c,1,self.node,'failed','meaning','one','private-context',False,False,'rule');self.c.commit();g=graph.network(self.c,1);f=g['focus'];self.assertEqual(f['targets'][0]['node'],self.node);self.assertEqual(f['targets'][0]['purpose'],'repair')
  d=graph.detail(self.c,1,self.node);self.assertTrue(d['next_check']['ready']);self.assertEqual(d['next_check']['evidence_ids'],f['targets'][0]['evidence_ids'])
  other=graph.network(self.c,2);self.assertEqual(other['focus']['targets'],[]);self.assertEqual(other['summary']['connected'],0);self.assertNotIn('private-context',json.dumps(other));self.assertEqual(graph.detail(self.c,2,self.node)['state']['evidence'],[])
 def test_delay_is_not_offered_before_ready_and_ai_is_not_mastery(self):
  events.record(self.c,1,self.node,'ai','feedback','one','one',True,False,'ai');self.c.commit();self.assertEqual(graph.network(self.c,1)['summary']['independent'],0)
  events.record(self.c,1,self.node,'pass','meaning','one','one',True,False,'rule');self.c.commit();d=graph.detail(self.c,1,self.node);self.assertFalse(d['next_check']['ready']);self.assertEqual(d['next_check']['purpose'],'delayed')
 def test_stage_and_gemini_context_use_same_graph_anchors(self):
  self.profile();f=graph.focus(self.c,1);self.assertEqual(f['mode'],'personal');self.assertEqual(len(f['missions']),6);self.assertEqual(coach.snapshot(self.c,1)['knowledge_focus']['anchors'],f['anchors'])
  messages=coach.prompt_context(self.c,1,'请解释我的知识路线');self.assertIn('knowledge_graph',messages[0]['content']);self.assertLess(sum(len(m['content']) for m in messages),8000)
 def test_private_published_node_never_enters_other_focus(self):
  row=self.c.execute('SELECT * FROM lexicon WHERE id=?',(self.entry,)).fetchone();entry=json.loads(row['content']);entry['word']='myprivateterm';entry['meaning']='private';private=lex.key('myprivateterm','private')
  # Copy a well-formed published entry and graph relation owned by learner one.
  columns=[r[1] for r in self.c.execute('PRAGMA table_info(lexicon)')];data=dict(row);data.update(id=private,owner=1,lemma='myprivateterm',content=json.dumps(entry))
  self.c.execute('INSERT INTO lexicon('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',[data[k] for k in columns]);self.c.execute('INSERT INTO kg_nodes VALUES(?,?,?,?,?)',('sense:'+private,'sense','private title',1,private));self.c.execute('INSERT INTO kg_edges VALUES(?,?,?,?)',('sense:'+private,self.node,'has_sense','test'));self.c.commit()
  self.assertNotIn('private title',json.dumps(graph.network(self.c,2)));self.assertNotIn('private title',json.dumps(graph.detail(self.c,2,self.node)))
  with self.assertRaises(ValueError):graph.detail(self.c,2,'sense:'+private)
if __name__=='__main__':unittest.main()
