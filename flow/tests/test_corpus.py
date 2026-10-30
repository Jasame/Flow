import unittest,tempfile,sys,time,json,os
from pathlib import Path
from unittest.mock import patch
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app,lab_service as lab,corpus_service as corpus
from content_v07 import all_materials,THEMES
from content_v05 import NODES
class CorpusTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(app,'DB',Path(self.tmp.name)/'corpus.db');self.p.start();app.init();self.c=app.db()
  for name in ['learner','other','teacher']:self.c.execute('INSERT INTO users(username,password,admin) VALUES(?,?,?)',(name,'hash',int(name=='teacher')))
  self.c.commit()
 def tearDown(self):self.c.close();self.p.stop();self.tmp.cleanup()
 def get(self,path='/api/lab',uid=1,query=None):return lab.get(self.c,uid,path,query or {})
 def post(self,path,data,uid=1):return lab.post(self.c,uid,path,data)
 def test_curated_corpus_quality_and_coverage(self):
  packs=all_materials();self.assertEqual(len(packs),36);self.assertEqual(len({p['body'] for p in packs}),36)
  self.assertEqual(Counter(p['level'] for p in packs),{'A2':12,'B1':12,'B2':12})
  self.assertEqual(set(p['theme'] for p in packs),set(THEMES));self.assertEqual(len({p['genre'] for p in packs}),6)
  grammar={n[0] for n in NODES}
  for p in packs:
   lab.validate_pack(dict(p));self.assertTrue(p['tags']);self.assertTrue(set(p['grammar'])<=grammar)
   for q in p['questions']:
    self.assertIn(q['evidence'],p['body']);self.assertEqual(len(set(q['options'])),4)
   self.assertEqual(len(p['vocabulary']),3)
  choices=Counter(q['answer'] for p in packs for q in p['questions']);self.assertEqual(set(choices),{0,1,2,3})
 def test_catalog_search_metadata_bookmark_and_ownership(self):
  d,status=self.get();self.assertEqual(status,200);self.assertEqual(len(d['packs']),154)
  p=next(p for p in d['packs'] if p['id']=='work-intro-a2');self.assertIn('customer messages',p['search_text']);self.assertIn('职场沟通',p['search_text']);self.assertEqual(p['genre'],'dialogue');self.assertNotIn('questions',p)
  self.assertEqual(self.post('/api/lab/bookmark',{'pack':p['id'],'saved':True})[1],200)
  self.post('/api/lab/bookmark',{'pack':p['id'],'saved':True})
  self.assertTrue(next(x for x in self.get()[0]['packs'] if x['id']==p['id'])['saved'])
  self.assertFalse(next(x for x in self.get(uid=2)[0]['packs'] if x['id']==p['id'])['saved'])
  self.post('/api/lab/bookmark',{'pack':p['id'],'saved':False});self.assertEqual(self.c.execute('SELECT COUNT(*) FROM lab_bookmarks').fetchone()[0],0)
  with self.assertRaises(ValueError):self.post('/api/lab/bookmark',{'pack':'missing','saved':True})
 def test_note_resume_and_exact_feedback_restore(self):
  pack='travel-a2';answer='Could you check my booking?'
  self.post('/api/lab/note',{'pack':pack,'note':'Try a polite request.'})
  self.post('/api/lab/draft',{'pack':pack,'skill':'writing','answer':answer})
  self.assertEqual(self.get()[0]['resume']['pack'],pack);self.assertEqual(next(p for p in self.get()[0]['packs'] if p['id']==pack)['resume_skill'],'writing')
  result={'strength':'Clear request','priorities':[{'issue':'Detail','evidence':answer,'suggestion':'Add a date'}],'revision':'Could you check my booking for Tuesday?','next_question':'When will you arrive?'}
  fp=lab.fingerprint({'pack':pack,'skill':'writing','answer':answer})
  self.c.execute("INSERT INTO lab_jobs(user_id,request_id,kind,pack,skill,fingerprint,status,result,created,updated) VALUES(1,'restored-feedback','feedback',?,?,?,'complete',?,?,?)",(pack,'writing',fp,json.dumps(result),time.time(),time.time()));self.c.commit()
  d=self.get('/api/lab/pack',query={'id':[pack]})[0];self.assertEqual(d['note'],'Try a polite request.');self.assertIn('writing',d['feedback'])
  other=self.get('/api/lab/pack',uid=2,query={'id':[pack]})[0];self.assertEqual(other['note'],'');self.assertEqual(other['feedback'],{})
  self.post('/api/lab/draft',{'pack':pack,'skill':'writing','answer':'A completely new draft.'})
  self.assertNotIn('writing',self.get('/api/lab/pack',query={'id':[pack]})[0]['feedback'])
 def test_reports_admin_resolution_and_limit(self):
  data={'pack':'travel-a2','category':'answer','note':'Please check the answer evidence.'}
  self.assertEqual(self.post('/api/lab/report',data)[1],200)
  reports=corpus.reports(self.c);self.assertEqual(len(reports),1);self.assertEqual(reports[0]['material']['title'],lab.pack_for(self.c,1,'travel-a2')['title'])
  self.assertEqual(self.post('/api/lab/report/resolve',{'id':reports[0]['id']},uid=2)[1],403)
  self.assertEqual(self.post('/api/lab/report/resolve',{'id':reports[0]['id']},uid=3)[1],200);self.assertEqual(corpus.reports(self.c),[])
  for _ in range(4):self.post('/api/lab/report',data)
  self.assertEqual(self.post('/api/lab/report',data)[1],429)
 def test_v06_upgrade_keeps_old_text_drafts_and_records(self):
  old=lab.pack_for(self.c,1,'travel-a2');self.post('/api/lab/draft',{'pack':'travel-a2','skill':'writing','answer':'Original draft.'})
  self.post('/api/lab/save',{'pack':'travel-a2','skill':'writing','answer':'Original work.','save_id':'old-work-v06-001'})
  from content_v06 import PACKS
  oldids={r[0] for r in PACKS}
  for p in all_materials():
   if p['id'] not in oldids:self.c.execute('DELETE FROM lab_packs WHERE id=?',(p['id'],))
  for table in ('lab_bookmarks','lab_notes','lab_content_reports'):self.c.execute('DROP TABLE '+table)
  self.c.execute("DELETE FROM migrations WHERE version='0.7'");self.c.commit();self.c.close();app.init();app.init();self.c=app.db()
  self.assertEqual(self.c.execute('SELECT COUNT(*) FROM lab_packs').fetchone()[0],262)
  self.assertEqual(lab.pack_for(self.c,1,'travel-a2')['body'],old['body'])
  self.assertEqual(self.get('/api/lab/history')[0]['items'][0]['answer'],'Original work.')
  self.assertEqual(self.get('/api/lab/pack',query={'id':['travel-a2']})[0]['drafts'][0]['answer'],'Original draft.')
  self.assertEqual(self.c.execute('PRAGMA foreign_key_check').fetchall(),[])
if __name__=='__main__':unittest.main()
