"""Structural quality checks and version-bound human review, never a semantic guarantee."""
import json,hashlib,time,re,copy

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS material_reviews(id INTEGER PRIMARY KEY,pack TEXT REFERENCES lab_packs(id),content_hash TEXT,status TEXT,checks TEXT,note TEXT,actor INTEGER REFERENCES users(id),created REAL);
 CREATE INDEX IF NOT EXISTS material_review_pack ON material_reviews(pack,id);
 CREATE TABLE IF NOT EXISTS material_versions(id INTEGER PRIMARY KEY,pack TEXT REFERENCES lab_packs(id),content TEXT,actor INTEGER REFERENCES users(id),created REAL);''')

def digest(p):return hashlib.sha256(json.dumps(p,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def checks(p):
 from lab_service import validate_pack
 errors=[];warnings=[]
 try:validate_pack(copy.deepcopy(p))
 except (ValueError,TypeError,KeyError):errors.append('材料结构、答案索引或原文证据校验失败')
 qs=p.get('questions',[]);body=p.get('body','')
 if len({q.get('prompt','').strip().casefold() for q in qs})!=len(qs):errors.append('题目重复')
 for q in qs:
  opts=q.get('options',[])
  if len({str(x).strip().casefold() for x in opts})!=len(opts):errors.append('同一道题存在重复选项')
 for w in p.get('vocabulary',[]):
  term=w.get('term','')
  if not re.search(r'(?<![a-z])'+re.escape(term)+r'(?![a-z])',body,re.I):warnings.append('目标词未以相同词形出现在正文：'+term)
  if not re.search(r'(?<![a-z])'+re.escape(term)+r'(?![a-z])',w.get('example',''),re.I):warnings.append('例句未包含目标词原形：'+term)
 count=len(re.findall(r"[A-Za-z]+(?:'[a-z]+)?",body));band=p.get('level');lo,hi={'A2':(35,180),'B1':(60,260),'B2':(80,400)}.get(band,(0,1000))
 if not lo<=count<=hi:warnings.append('篇幅偏离该教学分级的参考范围，需人工检查难度')
 if not p.get('provenance') and p.get('daily_day'):errors.append('热点材料缺少来源记录')
 return {'errors':list(dict.fromkeys(errors)),'warnings':list(dict.fromkeys(warnings)),'words':count,'note':'自动检查只能发现结构问题；语言准确性、答案唯一性、难度与事实需人工审核。'}

def info(c,row):
 p=json.loads(row['content']);h=digest(p);review=c.execute('SELECT status,note,actor,created FROM material_reviews WHERE pack=? AND content_hash=? ORDER BY id DESC LIMIT 1',(row['id'],h)).fetchone()
 status=review['status'] if review else 'original' if row['origin']=='original' else 'candidate'
 return {'status':status,'hash':h,'checks':checks(p),'review':dict(review) if review else None}

def recommendable(c,row):
 from content_v30 import SUPERSEDED
 if row['id'] in SUPERSEDED:return False
 q=info(c,row);return q['status'] in ('original','approved') and not q['checks']['errors']

def word_checks(e):
 errors=[];warnings=[]
 if not re.search(r'(?<![a-z])'+re.escape(e['word'])+r'(?![a-z])',e['example'],re.I):warnings.append('例句未包含目标词原形；请核对屈折形式和义项')
 if not e.get('definition'):warnings.append('缺少英文释义')
 if not e.get('pos'):warnings.append('词性待补充')
 if not e.get('source'):warnings.append('来源说明待补充')
 return {'errors':errors,'warnings':warnings,'note':'发布前请核对释义、搭配、例句与语法关联；自动检查不能证明内容正确。'}

def get(c,uid,admin,path,q):
 if path!='/api/growth/quality':return None
 if not admin:return {'error':'需要管理员权限'},403
 items=[]
 for r in c.execute('SELECT * FROM lab_packs WHERE owner IS NULL ORDER BY created DESC LIMIT 200'):
  p=json.loads(r['content']);quality=info(c,r)
  attempts=[json.loads(w[0]) for w in c.execute("SELECT details FROM lab_work WHERE pack=? AND skill IN ('reading','listening')",(r['id'],))]
  attempts=[w for w in attempts if w.get('kind')=='comprehension'];stats=(len(attempts),sum(w.get('assisted')==0 for w in attempts))
  reports=c.execute("SELECT COUNT(*) FROM lab_content_reports WHERE pack=? AND status='open'",(r['id'],)).fetchone()[0]
  items.append({'id':r['id'],'origin':r['origin'],'content':p,'quality':quality,'usage':{'attempts':stats[0],'unassisted_attempts':stats[1],'open_reports':reports}})
 return {'items':items},200

def post(c,uid,admin,path,data):
 if path not in ('/api/growth/quality/review','/api/growth/quality/revise'):return None
 if not admin:return {'error':'需要管理员权限'},403
 from lab_service import text,validate_pack
 row=c.execute('SELECT * FROM lab_packs WHERE id=? AND owner IS NULL',(data.get('pack'),)).fetchone()
 if not row:raise ValueError('公共材料不存在')
 p=json.loads(row['content'])
 if data.get('hash')!=digest(p):return {'error':'材料已更新，请刷新后审核'},409
 note=text(data.get('note'),minimum=5,maximum=1000)
 if path.endswith('/revise'):
  raw=data.get('content')
  if not isinstance(raw,dict):raise ValueError('材料内容格式不正确')
  clean=validate_pack(copy.deepcopy(raw));check=checks(clean)
  if check['errors']:raise ValueError('请先修复材料结构与重复选项')
  # Keep old work, questions and source attribution immutable: revision is a new pack.
  clean.update(id='rev-'+hashlib.sha256((row['id']+str(time.time_ns())).encode()).hexdigest()[:28])
  for k in ('provenance','daily_day','genre','tags'):
   if k in p:clean[k]=p[k]
  grammar=raw.get('grammar',[]);anchors=raw.get('knowledge',[])
  if not isinstance(grammar,list) or len(grammar)>8 or any(not isinstance(n,str) or not c.execute('SELECT 1 FROM subskills WHERE id=?',(n,)).fetchone() for n in grammar):raise ValueError('语法关联无效')
  if not isinstance(anchors,list) or len(anchors)>8:raise ValueError('图谱原文锚点无效')
  clean['grammar']=grammar;clean['knowledge']=[]
  for anchor in anchors:
   if not isinstance(anchor,dict) or anchor.get('node') not in grammar or not isinstance(anchor.get('quote'),str) or not anchor['quote'] or anchor['quote'] not in clean['body']:raise ValueError('图谱锚点必须对应本版原文与语法关联')
   clean['knowledge'].append({'node':anchor['node'],'quote':anchor['quote'],'explanation':text(anchor.get('explanation'),maximum=800)})
  clean['revision_of']=row['id']
  c.execute('BEGIN IMMEDIATE');c.execute('INSERT INTO material_versions(pack,content,actor,created) VALUES(?,?,?,?)',(row['id'],row['content'],uid,time.time()))
  c.execute('INSERT INTO lab_packs VALUES(?,NULL,?,?,?)',(clean['id'],'revision',json.dumps(clean,ensure_ascii=False),time.time()))
  c.execute('INSERT INTO material_reviews(pack,content_hash,status,checks,note,actor,created) VALUES(?,?,?,?,?,?,?)',(clean['id'],digest(clean),'candidate',json.dumps(check,ensure_ascii=False),note,uid,time.time()))
  __import__('lexicon_service').sync_packs(c);c.commit();return {'ok':True,'pack':clean['id'],'note':'修订版待审核；旧版及原作答保留，可另行停用旧版。'},200
 status=data.get('status')
 if status not in ('approved','disabled','candidate'):raise ValueError('审核状态不正确')
 check=checks(p)
 if status=='approved' and check['errors']:raise ValueError('结构检查未通过，不能发布')
 required=('language','answers','difficulty','vocabulary','sources')
 if status=='approved' and (not isinstance(data.get('confirmed'),dict) or not all(data['confirmed'].get(k) is True for k in required)):raise ValueError('请逐项确认语言、答案、难度、词汇和来源')
 c.execute('INSERT INTO material_reviews(pack,content_hash,status,checks,note,actor,created) VALUES(?,?,?,?,?,?,?)',(row['id'],digest(p),status,json.dumps(check,ensure_ascii=False),note,uid,time.time()));c.commit();return {'ok':True},200
