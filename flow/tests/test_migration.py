import unittest,tempfile,sys,sqlite3
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import app
from content_v03 import EXTRA_QUESTIONS
class MigrationTest(unittest.TestCase):
 def test_upgrade_is_idempotent_and_retains_custom_data(self):
  with tempfile.TemporaryDirectory() as tmp,patch.object(app,'DB',Path(tmp)/'test.sqlite3'):
   app.init()
   with app.db() as c:
    for q in EXTRA_QUESTIONS:c.execute('DELETE FROM questions WHERE prompt=?',(q[1],))
    c.execute('DELETE FROM migrations')
    c.execute("INSERT INTO users(username,password) VALUES('existing','untouched')")
    c.execute("INSERT INTO questions(topic,prompt,options,answer,explanation) VALUES('tense','custom lesson','[]',0,'custom')")
    qid=c.execute("SELECT id FROM questions WHERE prompt='custom lesson'").fetchone()[0]
    c.execute('INSERT INTO attempts(user_id,question_id,selected,correct,created) VALUES(1,?,0,1,1)',(qid,))
   app.init();app.init()
   with app.db() as c:
    self.assertEqual(c.execute('SELECT COUNT(*) FROM questions').fetchone()[0],73)
    self.assertEqual(c.execute("SELECT id FROM questions WHERE prompt='custom lesson'").fetchone()[0],qid)
    self.assertEqual(c.execute('SELECT password FROM users').fetchone()[0],'untouched')
    self.assertEqual(c.execute('SELECT question_id FROM attempts').fetchone()[0],qid)
 def test_real_v04_database_schema_upgrade(self):
  from seed import TOPICS,QUESTIONS
  import json
  with tempfile.TemporaryDirectory() as tmp,patch.object(app,'DB',Path(tmp)/'old.sqlite3'):
   with sqlite3.connect(app.DB) as c:
    c.executescript("""CREATE TABLE users(id INTEGER PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,admin INTEGER DEFAULT 0);
CREATE TABLE topics(id TEXT PRIMARY KEY,title TEXT,summary TEXT,lesson TEXT,example TEXT,explanation TEXT,prereqs TEXT);
CREATE TABLE questions(id INTEGER PRIMARY KEY,topic TEXT REFERENCES topics(id),prompt TEXT,options TEXT,answer INTEGER,explanation TEXT);
CREATE TABLE attempts(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),question_id INTEGER REFERENCES questions(id),selected INTEGER,correct INTEGER,created REAL);
CREATE TABLE migrations(version TEXT PRIMARY KEY); INSERT INTO migrations VALUES('0.3');""")
    c.executemany('INSERT INTO topics VALUES(?,?,?,?,?,?,?)',[(*t[:6],json.dumps(t[6])) for t in TOPICS])
    c.executemany('INSERT INTO questions(topic,prompt,options,answer,explanation) VALUES(?,?,?,?,?)',[(t,p,json.dumps(o),a,e) for t,p,o,a,e in QUESTIONS+EXTRA_QUESTIONS])
    c.execute("INSERT INTO users VALUES(9,'old-user','original-hash',1)")
    c.execute('INSERT INTO attempts VALUES(1,9,1,1,1,10)')
   app.init();app.init()
   with app.db() as c:
    self.assertEqual(c.execute('SELECT COUNT(*) FROM questions').fetchone()[0],72)
    self.assertEqual(c.execute('SELECT password FROM users WHERE id=9').fetchone()[0],'original-hash')
    self.assertEqual(c.execute('SELECT question_id FROM attempts').fetchone()[0],1)
    self.assertEqual(c.execute('SELECT COUNT(*) FROM question_skill_attempts').fetchone()[0],1)
    self.assertEqual(c.execute('SELECT COUNT(*) FROM review_cards WHERE user_id=9').fetchone()[0],1)
    self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(),[])
if __name__=='__main__':unittest.main()
