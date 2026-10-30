"""Versioned word senses and typed graph. Generated content enters review, not public mastery."""
import hashlib,json,re,time
from content_v30 import all_materials

def key(word,sense='core'):return 'v-'+hashlib.sha256((word.strip().casefold()+'|'+sense).encode()).hexdigest()[:20]
def node_id(entry):return 'sense:'+entry

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS lexicon(id TEXT PRIMARY KEY,owner INTEGER REFERENCES users(id),lemma TEXT NOT NULL,sense TEXT NOT NULL,content TEXT NOT NULL,status TEXT NOT NULL,origin TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,created REAL,updated REAL);
 CREATE INDEX IF NOT EXISTS lexicon_lemma ON lexicon(lemma,status);
 CREATE TABLE IF NOT EXISTS lexicon_versions(id INTEGER PRIMARY KEY,entry TEXT,version INTEGER,content TEXT,status TEXT,actor INTEGER,created REAL);
 CREATE TABLE IF NOT EXISTS kg_nodes(id TEXT PRIMARY KEY,kind TEXT NOT NULL,title TEXT NOT NULL,owner INTEGER REFERENCES users(id),ref TEXT NOT NULL DEFAULT '');
 CREATE TABLE IF NOT EXISTS kg_edges(source TEXT REFERENCES kg_nodes(id),target TEXT REFERENCES kg_nodes(id),relation TEXT,origin TEXT,PRIMARY KEY(source,target,relation));
 CREATE INDEX IF NOT EXISTS kg_edge_target ON kg_edges(target);
 CREATE TABLE IF NOT EXISTS vocab_enroll(user_id INTEGER REFERENCES users(id),entry TEXT REFERENCES lexicon(id),stage INTEGER DEFAULT 0,due REAL,last REAL,created REAL,PRIMARY KEY(user_id,entry));
 CREATE TABLE IF NOT EXISTS lexicon_audit(id INTEGER PRIMARY KEY,actor INTEGER,entry TEXT,action TEXT,created REAL);
 CREATE TABLE IF NOT EXISTS lexicon_pack_index(pack TEXT PRIMARY KEY,content_hash TEXT);''')
 for r in c.execute('SELECT id,title FROM subskills').fetchall():c.execute('INSERT OR IGNORE INTO kg_nodes VALUES(?,?,?,NULL,?)',(r['id'],'grammar',r['title'],r['id']))
 for skill,title in [('listening','听力'),('speaking','口语'),('reading','阅读'),('writing','写作')]:c.execute('INSERT OR IGNORE INTO kg_nodes VALUES(?,?,?,NULL,?)',('skill:'+skill,'skill',title,skill))
 for r in c.execute('SELECT id,prereq FROM subskills WHERE prereq IS NOT NULL').fetchall():c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',(r['prereq'],r['id'],'prerequisite','curriculum'))
 if not c.execute("SELECT 1 FROM migrations WHERE version='1.0-lexicon'").fetchone():
  entries=[{'word':'suggest','sense':'advice','pos':'verb','meaning':'建议；提议','definition':'to offer an idea for someone to consider','example':'She suggested taking a short break.','translation':'她建议短暂休息一下。','level':'B1','theme':'campus','patterns':[{'text':'suggest doing something','node':'nonfinite-gerund'}],'related':['suggestion'],'mnemonic':'把 suggest 与自己的休息建议联系起来；这是记忆联想，不是词源解释。'},
   {'word':'distract','sense':'attention','pos':'verb','meaning':'使分心；分散注意力','definition':'to draw attention away from something','example':'Please do not distract me from studying.','translation':'请不要让我学习时分心。','level':'B1','theme':'campus','patterns':[{'text':'distract somebody from doing something','node':'nonfinite-gerund'}],'related':['distraction','attention'],'mnemonic':'把 distract 与学习时收到消息的场景联系起来；这是记忆联想。'}]
  seen={p['word'] for p in entries}
  for pack in all_materials():
   for w in pack['vocabulary']:
    term=w['term'].casefold()
    if term in seen or len(entries)>=100:continue
    seen.add(term);entries.append({'word':term,'sense':'core','pos':'','meaning':w['meaning'],'definition':'','example':w['example'],'translation':'','level':pack['level'],'theme':pack['theme'],'patterns':[],'related':[],'mnemonic':'','source_pack':pack['id']})
  assert len(entries)==100
  for e in entries:
   e['source']='Flow 原创教学示例；待人工校对';save(c,e,'published','starter')
  c.execute("INSERT INTO migrations VALUES('1.0-lexicon')")
 # Migrate private wordbook entries without disclosing or regrading their contents.
 if not c.execute("SELECT 1 FROM migrations WHERE version='1.0-personal-words'").fetchone():
  for w in c.execute('SELECT * FROM wordbook').fetchall():
   entry='private-'+str(w['user_id'])+'-'+str(w['id']);e={'word':w['term'],'sense':'personal','pos':'','meaning':w['meaning'],'example':w['example'],'level':'B1','theme':'life','source':'个人生词本迁移；未经核验','definition':'','translation':'','patterns':[],'related':[],'mnemonic':''}
   try:save(c,e,'published','personal',owner=w['user_id'],entry=entry)
   except ValueError:continue
   c.execute('INSERT OR IGNORE INTO vocab_enroll VALUES(?,?,?,?,?,?)',(w['user_id'],entry,w['stage'],w['due'],None,w['created']))
  c.execute("INSERT INTO migrations VALUES('1.0-personal-words')")
 for row in c.execute("SELECT id FROM lab_packs WHERE owner IS NULL AND origin='daily' ORDER BY created DESC LIMIT 50").fetchall():collect_candidates(c,row[0])
 sync_packs(c)

def validate(raw):
 from lab_service import text
 if not isinstance(raw,dict):raise ValueError('词条格式不正确')
 out={k:text(raw.get(k),maximum=n) for k,n in [('word',80),('meaning',300),('example',500)]}
 if not re.fullmatch(r"[a-zA-Z][a-zA-Z '\-]{0,79}",out['word']):raise ValueError('词条需为英文单词或词组')
 out['word']=out['word'].casefold();out['sense']=text(raw.get('sense','core'),maximum=40)
 if not re.fullmatch(r'[a-z0-9_-]{1,40}',out['sense']):raise ValueError('义项标识需为英文小写、数字、下划线或连字符')
 if raw.get('level','B1') not in ('A2','B1','B2') or raw.get('theme','life') not in ('campus','travel','life','work','culture','science'):raise ValueError('难度或主题不正确')
 out.update(level=raw.get('level','B1'),theme=raw.get('theme','life'))
 for k,n in [('pos',40),('definition',500),('translation',500),('mnemonic',600),('source',300)]:
  value=raw.get(k,'')
  if not isinstance(value,str) or len(value)>n:raise ValueError('词条字段过长或类型不正确')
  out[k]=value.strip()
 patterns=raw.get('patterns',[]);related=raw.get('related',[])
 if not isinstance(patterns,list) or len(patterns)>5 or not isinstance(related,list) or len(related)>8:raise ValueError('关联条目过多')
 out['patterns']=[]
 for p in patterns:
  if not isinstance(p,dict):raise ValueError('搭配格式不正确')
  if not isinstance(p.get('node',''),str) or len(p.get('node',''))>100:raise ValueError('语法关联标识不正确')
  out['patterns'].append({'text':text(p.get('text'),maximum=180),'node':p.get('node','')})
 out['related']=[text(w,maximum=80) for w in related]
 if raw.get('source_pack'):out['source_pack']=text(raw['source_pack'],maximum=100)
 return out

def save(c,raw,status,origin,owner=None,entry=None,actor=None):
 e=validate(raw);entry=entry or key(e['word'],e['sense']);old=c.execute('SELECT * FROM lexicon WHERE id=?',(entry,)).fetchone()
 if old:
  if old['owner']!=owner or old['lemma']!=e['word'] or old['sense']!=e['sense']:raise ValueError('不能改变既有词条的单词、义项或归属')
  c.execute('INSERT INTO lexicon_versions(entry,version,content,status,actor,created) VALUES(?,?,?,?,?,?)',(entry,old['version'],old['content'],old['status'],actor,time.time()))
 version=old['version']+1 if old else 1
 for p in e['patterns']:
  if p['node'] and not c.execute('SELECT 1 FROM subskills WHERE id=?',(p['node'],)).fetchone():raise ValueError('搭配关联的语法点不存在')
 c.execute('INSERT INTO lexicon VALUES(?,?,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET content=excluded.content,status=excluded.status,origin=excluded.origin,version=excluded.version,updated=excluded.updated',(entry,owner,e['word'],e['sense'],json.dumps(e,ensure_ascii=False),status,origin,version,old['created'] if old else time.time(),time.time()))
 c.execute('INSERT INTO lexicon_audit(actor,entry,action,created) VALUES(?,?,?,?)',(actor,entry,status+':'+origin,time.time()))
 index_entry(c,entry,e,owner,status);return entry

def index_entry(c,entry,e,owner,status):
 sid=node_id(entry);wid='word:'+hashlib.sha256((str(owner)+'|'+e['word']).encode()).hexdigest()[:20]
 c.execute("INSERT INTO kg_nodes VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET ref=CASE WHEN ?='published' THEN excluded.ref ELSE kg_nodes.ref END",(wid,'word',e['word'],owner,entry,status))
 c.execute('INSERT INTO kg_nodes VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title',(sid,'sense',e['word']+' · '+e['meaning'][:40],owner,entry))
 c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',(wid,sid,'has_sense',status))
 c.execute("DELETE FROM kg_edges WHERE source IN (SELECT id FROM kg_nodes WHERE kind='pattern' AND ref=?)",(entry,))
 c.execute("DELETE FROM kg_edges WHERE source=? AND relation='has_pattern'",(sid,))
 for p in e['patterns']:
  pid='pattern:'+hashlib.sha256((sid+'|'+p['text']).encode()).hexdigest()[:20]
  c.execute('INSERT OR IGNORE INTO kg_nodes VALUES(?,?,?,?,?)',(pid,'pattern',p['text'],owner,entry));c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',(sid,pid,'has_pattern',status))
  if p['node']:c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',(pid,p['node'],'uses_grammar',status))
 if e.get('source_pack') and c.execute('SELECT 1 FROM lab_packs WHERE id=?',(e['source_pack'],)).fetchone():
  material='material:'+e['source_pack'];p=json.loads(c.execute('SELECT content FROM lab_packs WHERE id=?',(e['source_pack'],)).fetchone()[0]);c.execute('INSERT OR IGNORE INTO kg_nodes VALUES(?,?,?,NULL,?)',(material,'material',p['title'],p['id']));c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',(sid,material,'introduced_by',status))
 return sid

def sync_packs(c):
 words=[dict(r) for r in c.execute("SELECT id,lemma,content FROM lexicon WHERE owner IS NULL AND status='published'")]
 digest=hashlib.sha256('|'.join(w['id'] for w in words).encode()).hexdigest()
 for r in c.execute('SELECT id,owner,content FROM lab_packs').fetchall():
  fingerprint=hashlib.sha256((r['content']+digest).encode()).hexdigest();old=c.execute('SELECT content_hash FROM lexicon_pack_index WHERE pack=?',(r['id'],)).fetchone()
  if old and old[0]==fingerprint:continue
  p=json.loads(r['content']);mid='material:'+r['id'];c.execute('INSERT OR IGNORE INTO kg_nodes VALUES(?,?,?,?,?)',(mid,'material',p['title'],r['owner'],r['id']))
  from content_v07 import metadata
  for n in metadata(p)['grammar']:
   if c.execute('SELECT 1 FROM kg_nodes WHERE id=?',(n,)).fetchone():c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',(n,mid,'practised_in','curriculum'))
  for skill in ('listening','speaking','reading','writing'):c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',(mid,'skill:'+skill,'trains','curriculum'))
  for w in words:
   if re.search(r'(?<![a-z])'+re.escape(w['lemma'])+r'(?![a-z])',p['body'],re.I):c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',(node_id(w['id']),mid,'occurs_in','literal-match'))
  c.execute('INSERT OR REPLACE INTO lexicon_pack_index VALUES(?,?)',(r['id'],fingerprint))

def entry_for(c,uid,entry):
 r=c.execute("SELECT * FROM lexicon WHERE id=? AND status='published' AND (owner IS NULL OR owner=?)",(entry,uid)).fetchone()
 if not r:raise ValueError('词条不存在或尚未发布')
 return dict(r)|{'data':json.loads(r['content'])}

def catalog(c,uid):
 from event_service import state
 rows=[]
 for r in c.execute("SELECT l.*,e.due,e.stage,e.created enrolled FROM lexicon l LEFT JOIN vocab_enroll e ON e.entry=l.id AND e.user_id=? WHERE l.status='published' AND (l.owner IS NULL OR l.owner=?) ORDER BY l.owner IS NOT NULL DESC,l.rowid LIMIT 1000",(uid,uid)):
  e=json.loads(r['content']);s=state(c,uid,node_id(r['id']));rows.append({'id':r['id'],'word':e['word'],'meaning':e['meaning'],'level':e['level'],'theme':e['theme'],'pos':e['pos'],'enrolled':r['enrolled'] is not None,'due':r['due'],'stage':r['stage'],'state':s['state'],'origin':r['origin'],'version':r['version']})
 return rows

def detail(c,uid,entry):
 from event_service import state
 r=entry_for(c,uid,entry);enroll=c.execute('SELECT * FROM vocab_enroll WHERE user_id=? AND entry=?',(uid,entry)).fetchone()
 materials=[]
 for row in c.execute("SELECT n.ref FROM kg_edges e JOIN kg_nodes n ON n.id=e.target WHERE e.source=? AND e.relation IN ('occurs_in','introduced_by')",(node_id(entry),)):
  p=c.execute('SELECT content FROM lab_packs WHERE id=? AND (owner IS NULL OR owner=?)',(row[0],uid)).fetchone()
  if p:
   p=json.loads(p[0]);materials.append({k:p[k] for k in ('id','title','level')})
 return {'reference':__import__('reference_service').provenance(c,uid,entry) if r['origin'] in ('reference','reference-ai') else None,'id':entry,'data':r['data'],'origin':r['origin'],'version':r['version'],'enrolled':bool(enroll),'due':enroll['due'] if enroll else None,'state':state(c,uid,node_id(entry)),'materials':materials[:12],'node':node_id(entry)}

def collect_candidates(c,pack_id):
 row=c.execute('SELECT content FROM lab_packs WHERE id=? AND owner IS NULL',(pack_id,)).fetchone()
 if not row:return
 p=json.loads(row[0])
 for w in p.get('vocabulary',[])[:5]:
  term=w.get('term','').casefold();entry=key(term)
  if c.execute('SELECT 1 FROM lexicon WHERE id=?',(entry,)).fetchone():continue
  raw={'word':term,'meaning':w.get('meaning'),'example':w.get('example'),'level':p['level'],'theme':p['theme'],'source_pack':pack_id,'source':'每日热点AI候选；待人工审核'}
  try:clean=validate(raw)
  except ValueError:continue
  save(c,clean,'draft','daily')

def sync_personal(c,uid,wordbook_id):
 row=c.execute('SELECT * FROM wordbook WHERE id=? AND user_id=?',(wordbook_id,uid)).fetchone()
 if not row:return
 matches=c.execute("SELECT id,content FROM lexicon WHERE lemma=? AND status='published' AND owner IS NULL ORDER BY rowid",(row['term'].casefold(),)).fetchall()
 shared=next((r for r in matches if json.loads(r['content'])['meaning'].strip()==row['meaning'].strip()),None)
 entry=shared[0] if shared else 'private-'+str(uid)+'-'+str(wordbook_id)
 if not shared:
  raw={'word':row['term'],'sense':'personal','meaning':row['meaning'],'example':row['example'],'source':'个人生词；未经核验'}
  try:validate(raw)
  except ValueError:return
  save(c,raw,'published','personal',owner=uid,entry=entry)
 c.execute('INSERT OR IGNORE INTO vocab_enroll VALUES(?,?,0,?,NULL,?)',(uid,entry,row['due'],row['created']))
