"""3.5 migration: labels, dictation evidence, settings and attempt sessions.

Rules (all idempotent, recorded in migrations):
- Historical attempts and learning_events are never upgraded to 'independent'. Rows whose hint
  state was unknown stay evaluator='legacy'.
- Question relabels only change questions.node. Earlier attempts keep their recorded node in
  question_skill_attempts; the change is logged in content_audit so it can be reverted.
- Earlier dictation rows move from listening comprehension to the dictation node, with the original
  placement kept in details.reclassified.
"""
import time
import event_service as events
# (prompt, old node, new node): checked by hand against content_subskills.PAGES.
RELABEL=[
 ('Not only the students but also their teacher ____ ready.','agreement-each','agreement-either'),
 ('Neither of the two answers ____ correct.','agreement-either','agreement-each'),
 ('This is the café ____ we first met.','clause-noun','clause-relative'),
 ('If I had more free time now, I ____ another language.','subjunctive-mixed','subjunctive-now'),
]

def run(c):
 import settings_service,attempt_service
 attempt_service.schema(c);settings_service.schema(c)
 if c.execute("SELECT 1 FROM migrations WHERE version='3.5-content'").fetchone():return
 for prompt,old,new in RELABEL:
  for (qid,) in c.execute('SELECT id FROM questions WHERE prompt=? AND node=?',(prompt,old)).fetchall():
   c.execute('UPDATE questions SET node=? WHERE id=?',(new,qid))
   c.execute('INSERT INTO content_audit(actor,action,question_id,created) VALUES(?,?,?,?)',(None,'relabel:'+old+'->'+new,qid,time.time()))
 events.reclassify_dictation(c)
 c.execute("INSERT INTO migrations VALUES('3.5-content')")

def rollback_labels(c):
 """Reverse only the relabels this migration made (used by the rollback notes)."""
 for prompt,old,new in RELABEL:
  c.execute('UPDATE questions SET node=? WHERE prompt=? AND node=?',(old,prompt,new))
