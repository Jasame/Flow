"""Indexed source dictionary and explicit, private learning adoption. No bulk AI calls."""
import json,re,time,hashlib
from pathlib import Path
from functools import lru_cache
import lexicon_service as lex
DATA=Path(__file__).resolve().parent/'corpus_data'/'yl-reference.json'
@lru_cache(maxsize=1)
def dataset():return json.loads(DATA.read_text(encoding='utf-8'))

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS reference_terms(id TEXT PRIMARY KEY,norm TEXT NOT NULL,word TEXT NOT NULL,rank INTEGER NOT NULL,meaning TEXT NOT NULL,has_examples INTEGER NOT NULL,content TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS reference_term_norm ON reference_terms(norm);
 CREATE INDEX IF NOT EXISTS reference_term_rank ON reference_terms(rank,id);
 CREATE TABLE IF NOT EXISTS reference_meta(id TEXT PRIMARY KEY,source TEXT NOT NULL,stats TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS reference_adoptions(user_id INTEGER REFERENCES users(id),reference TEXT REFERENCES reference_terms(id),source_row INTEGER,entry TEXT REFERENCES lexicon(id),pack TEXT REFERENCES lab_packs(id),source_hash TEXT,created REAL,PRIMARY KEY(user_id,reference));''')
 data=dataset();stamp=data['source']['sha256'];old=c.execute("SELECT id FROM reference_meta WHERE id=?",(stamp,)).fetchone()
 if not old:
  c.executemany('INSERT INTO reference_terms VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET norm=excluded.norm,word=excluded.word,rank=excluded.rank,meaning=excluded.meaning,has_examples=excluded.has_examples,content=excluded.content',[(t['id'],t['norm'],t['word'],t['rank'],' '.join(dict.fromkeys(v['meaning'] for v in t['variants'])),int(any(v['examples'] for v in t['variants'])),json.dumps(t,ensure_ascii=False)) for t in data['terms']])
  c.execute('INSERT INTO reference_meta VALUES(?,?,?)',(stamp,json.dumps(data['source'],ensure_ascii=False),json.dumps(data['stats'],ensure_ascii=False)))
 c.execute("INSERT OR IGNORE INTO migrations VALUES('2.4-reference')")

def summary(c):
 r=c.execute('SELECT source,stats FROM reference_meta ORDER BY rowid DESC LIMIT 1').fetchone()
 return {'source':json.loads(r['source']),'stats':json.loads(r['stats'])} if r else {}

def examples(raw):
 result=[]
 for line in raw.replace('\\n','\n').splitlines():
  line=re.sub(r'^\s*\d+[.)、]\s*','',line).strip()
  match=re.search(r'[\u3400-\u9fff]',line)
  english=(line[:match.start()] if match else line).strip();translation=line[match.start():].strip() if match else ''
  if english and re.search('[A-Za-z]',english):result.append({'english':english,'translation':translation})
 return result

def entry(c,uid,id):
 if not isinstance(id,str) or not re.fullmatch(r'yl-[a-f0-9]{20}',id):raise ValueError('词条标识不正确')
 row=c.execute('SELECT content FROM reference_terms WHERE id=?',(id,)).fetchone()
 if not row:raise ValueError('来源词条不存在')
 t=json.loads(row[0]);t['source']=summary(c)['source'];t['ai_enabled']=__import__('vertex_auth').ai_enabled();t['learnable']=bool(re.fullmatch(r"[a-zA-Z][a-zA-Z '\-]{0,79}",t['norm']))
 for v in t['variants']:v['parsed_examples']=examples(v['examples'])
 adopted=c.execute('SELECT entry,pack,source_row FROM reference_adoptions WHERE user_id=? AND reference=?',(uid,id)).fetchone();t['adopted']=dict(adopted) if adopted else None
 return t

def variant(c,uid,data):
 t=entry(c,uid,data.get('reference'));row=data.get('row')
 if type(row)!=int:raise ValueError('请选择来源行')
 v=next((v for v in t['variants'] if v['row']==row),None)
 if not v:raise ValueError('来源行与词条不匹配')
 if not t['learnable']:raise ValueError('该词形需要人工拆分，暂不能直接生成或加入学习')
 return t,v

def target(c,uid,data):
 t,v=variant(c,uid,{'reference':data.get('reference'),'row':data.get('source_row')})
 return {'id':t['id'],'word':t['norm'],'row':v['row'],'meaning':v['meaning'],'hash':t['source']['sha256']}

def source_word_present(word,text):
 # A narrow form check for imported examples, not a sense-equivalence assertion.
 forms={word,word+'s',word+'es',word+'ed',word+'ing'}
 if word.endswith('e'):forms.update((word+'d',word[:-1]+'ing'))
 if word.endswith('y'):forms.update((word[:-1]+'ies',word[:-1]+'ied'))
 forms.update({'be':('am','is','are','was','were','been','being'),'have':('has','had','having'),'do':('does','did','done','doing'),'go':('goes','went','gone','going')}.get(word,()))
 return any(re.search(r'(?<![a-z])'+re.escape(form)+r'(?![a-z])',text,re.I) for form in forms)

def get(c,uid,path,q):
 if path=='/api/reference/entry':return entry(c,uid,q.get('id',[''])[0]),200
 if path!='/api/reference':return None
 query=q.get('q',[''])[0].strip()
 if len(query)>100:raise ValueError('搜索最多100字')
 try:page=max(1,min(1000,int(q.get('page',['1'])[0])))
 except (ValueError,TypeError):raise ValueError('页码不正确')
 scope=q.get('scope',['all'])[0]
 if scope not in ('all','examples','missing'):raise ValueError('词库筛选不正确')
 where=[];args=[]
 if query:
  escaped=query.casefold().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
  if re.search('[\u3400-\u9fff]',query):where.append("r.meaning LIKE ? ESCAPE '\\'");args.append('%'+escaped+'%')
  else:where.append("r.norm LIKE ? ESCAPE '\\'");args.append(escaped+'%')
 if scope!='all':where.append('r.has_examples=?');args.append(int(scope=='examples'))
 condition=' WHERE '+' AND '.join(where) if where else ''
 total=c.execute('SELECT COUNT(*) FROM reference_terms r'+condition,args).fetchone()[0];page=min(page,max(1,(total+29)//30))
 rows=c.execute('SELECT r.id,r.word,r.rank,r.has_examples,r.content,a.entry adopted FROM reference_terms r LEFT JOIN reference_adoptions a ON a.reference=r.id AND a.user_id=?'+condition+' ORDER BY r.rank,r.id LIMIT 30 OFFSET ?',[uid,*args,(page-1)*30]).fetchall()
 items=[]
 for r in rows:
  t=json.loads(r['content']);v=min(t['variants'],key=lambda v:(not bool(v['examples']),v['rank']))
  items.append({'id':r['id'],'word':r['word'],'rank':r['rank'],'meaning':v['meaning'],'phonetic':v['phonetic'],'variants':len(t['variants']),'has_examples':bool(r['has_examples']),'flags':t['flags'],'adopted':r['adopted']})
 return {**summary(c),'items':items,'page':page,'pages':max(1,(total+29)//30),'total':total},200

def adopt(c,uid,t,v,example,level,theme,pack=None,generated=False):
 import adaptive_service as adaptive
 old=c.execute('SELECT entry,pack FROM reference_adoptions WHERE user_id=? AND reference=?',(uid,t['id'])).fetchone()
 if old:return {'entry':old['entry'],'pack':old['pack'],'cached':True}
 if level not in ('A2','B1','B2') or theme not in ('campus','travel','life','work','culture','science'):raise ValueError('请选择练习难度和主题；词频不代表等级')
 item={'word':t['norm'],'sense':'reference','meaning':example.get('meaning',v['meaning']),'example':example['english'],'translation':example.get('translation',''),'pos':'','level':level,'theme':theme,'source':('Gemini基于用户词库生成；待校对；' if generated else '用户词库原文；未经全面校对；')+'yl.xlsx / Sheet1 / 行'+str(v['row'])}
 if pack:item['source_pack']=pack
 # Reject before opening a write transaction; keep both word and enrollment atomic.
 lex.validate(item);id='ref-'+str(uid)+'-'+t['id'][3:]
 c.execute('BEGIN IMMEDIATE')
 try:
  # Serialize concurrent adoption across different generation requests.
  old=c.execute('SELECT entry,pack FROM reference_adoptions WHERE user_id=? AND reference=?',(uid,t['id'])).fetchone()
  if old:c.rollback();return {'entry':old['entry'],'pack':old['pack'],'cached':True}
  lex.save(c,item,'published','reference-ai' if generated else 'reference',owner=uid,entry=id,actor=uid);adaptive.enroll(c,uid,id)
  c.execute('INSERT INTO reference_adoptions VALUES(?,?,?,?,?,?,?)',(uid,t['id'],v['row'],id,pack,t['source']['sha256'],time.time()))
  # Literal links to accessible materials are owner-filtered and never claim sense equivalence.
  for r in c.execute('SELECT id,content FROM lab_packs WHERE owner IS NULL OR owner=?',(uid,)):
   p=json.loads(r['content'])
   if re.search(r'(?<![a-z])'+re.escape(t['norm'])+r'(?![a-z])',p['body'],re.I):c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',(lex.node_id(id),'material:'+r['id'],'occurs_in','literal-match'))
  c.commit()
 except Exception:c.rollback();raise
 return {'entry':id,'pack':pack,'cached':False}

def provenance(c,uid,id):
 row=c.execute('SELECT a.reference,a.source_row,a.source_hash,r.content FROM reference_adoptions a JOIN reference_terms r ON r.id=a.reference WHERE a.user_id=? AND a.entry=?',(uid,id)).fetchone()
 if not row:return None
 t=json.loads(row['content']);v=next((v for v in t['variants'] if v['row']==row['source_row']),None)
 return {'id':row['reference'],'row':row['source_row'],'sha256':row['source_hash'],'variant':v,'flags':t['flags'],'note':'音标、词形与同义线索来自原表，尚未全面校对；同义线索不表示可在任何语境互换。'}

def post(c,uid,path,data):
 if path not in ('/api/reference/adopt','/api/reference/generate'):return None
 t,v=variant(c,uid,data)
 if t['adopted'] and path.endswith('/adopt'):return {'ok':True,**t['adopted'],'cached':True},200
 level=data.get('level');theme=data.get('theme')
 if path.endswith('/adopt'):
  index=data.get('example')
  if type(index)!=int or not 0<=index<len(v['parsed_examples']):raise ValueError('请选择一条例句；没有例句时请先生成')
  ex=v['parsed_examples'][index]
  if not source_word_present(t['norm'],ex['english']):raise ValueError('暂未匹配到目标词或常见屈折形式，请选择其他例句或生成语境')
  return {'ok':True,**adopt(c,uid,t,v,ex,level,theme)},200
 import lab_service as lab
 out,status=lab.post(c,uid,'/api/lab/generate',{'request_id':data.get('request_id'),'level':level,'theme':theme,'reference':t['id'],'source_row':v['row']})
 if status!=200:return out,status
 p=out['result'];w=next(w for w in p['vocabulary'] if w['term'].casefold()==t['norm'])
 if t['adopted']:
  id=t['adopted']['entry']
  c.execute('INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)',(lex.node_id(id),'material:'+p['id'],'introduced_by','personal-generation'))
  c.execute('UPDATE reference_adoptions SET pack=? WHERE user_id=? AND reference=?',(p['id'],uid,t['id']));c.commit()
  result={'entry':id,'pack':p['id'],'cached':out.get('cached',False)}
 else:result=adopt(c,uid,t,v,{'english':w['example'],'meaning':w['meaning']},level,theme,p['id'],True)
 return {'ok':True,**result,'note':'已生成个人学习材料并加入学习；AI语料待校对，未发布到公共词库。'},200
