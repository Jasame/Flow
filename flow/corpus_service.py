"""Search metadata, owned bookmarks and precise resume/feedback restoration."""
import json,time,hashlib
from content_v07 import metadata
THEME_NAMES={'campus':'校园学习','travel':'旅行生活','life':'日常生活','work':'职场沟通','culture':'文化交流','science':'科学素养'}

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS lab_bookmarks(user_id INTEGER REFERENCES users(id),pack TEXT REFERENCES lab_packs(id),created REAL,PRIMARY KEY(user_id,pack));
 CREATE TABLE IF NOT EXISTS lab_notes(user_id INTEGER REFERENCES users(id),pack TEXT REFERENCES lab_packs(id),note TEXT,updated REAL,PRIMARY KEY(user_id,pack));
 CREATE TABLE IF NOT EXISTS lab_content_reports(id INTEGER PRIMARY KEY,user_id INTEGER REFERENCES users(id),pack TEXT REFERENCES lab_packs(id),category TEXT,note TEXT,status TEXT DEFAULT 'open',created REAL);
 CREATE INDEX IF NOT EXISTS lab_drafts_user_updated ON lab_drafts(user_id,updated);''')
 c.execute("INSERT OR IGNORE INTO migrations VALUES('0.7')")

def catalog(c,uid):
 saved={r[0] for r in c.execute('SELECT pack FROM lab_bookmarks WHERE user_id=?',(uid,))}
 progress={}
 for r in c.execute('SELECT pack,skill,MAX(created) recent FROM lab_work WHERE user_id=? GROUP BY pack,skill',(uid,)):
  progress.setdefault(r['pack'],[]).append(r['skill'])
 drafts={r[0] for r in c.execute("SELECT DISTINCT pack FROM lab_drafts WHERE user_id=? AND trim(answer)!=''",(uid,))}
 lastskills={}
 for r in c.execute("SELECT pack,skill,stamp FROM (SELECT pack,skill,updated stamp FROM lab_drafts WHERE user_id=? AND trim(answer)!='' UNION ALL SELECT pack,skill,created stamp FROM lab_work WHERE user_id=?) ORDER BY stamp DESC",(uid,uid)):
  lastskills.setdefault(r['pack'],r['skill'])
 out=[]
 for row in c.execute("""SELECT * FROM lab_packs WHERE (owner IS NULL AND (origin!='daily' OR created>?)) OR owner=? OR id IN (SELECT pack FROM lab_bookmarks WHERE user_id=?) ORDER BY CASE WHEN origin='daily' THEN 0 WHEN owner IS NULL THEN 1 ELSE 2 END,created DESC LIMIT 500""",(time.time()-90*86400,uid,uid)):
  quality=__import__('quality_service').info(c,row)
  if quality['status']=='disabled':continue
  p=json.loads(row['content'])
  from content_v30 import SUPERSEDED
  if p['id'] in SUPERSEDED and p['id'] not in saved and p['id'] not in drafts:continue
  m=metadata(p);words=len(p['body'].split())
  out.append({k:p[k] for k in ('id','title','level','theme')}|m|{'quality':{'status':quality['status'],'warnings':quality['checks']['warnings']},'origin':row['origin'],'daily_day':p.get('daily_day'),'words':words,'minutes':__import__('practice_service').metadata(p)['minutes'],'preview':p['body'][:160],
    'grading':__import__('practice_service').metadata(p),'search_text':' '.join([p['title'],p['body'],THEME_NAMES.get(p['theme'],''),*m['tags'],*(w['term'] for w in p['vocabulary'])]),'saved':p['id'] in saved,'recorded_skills':progress.get(p['id'],[]),'has_draft':p['id'] in drafts,'resume_skill':lastskills.get(p['id'])})
 ranked,_=__import__('practice_service').rank(c,uid,c.execute('SELECT * FROM lab_packs WHERE owner IS NULL OR owner=?',(uid,)).fetchall())
 order={r['pack']['id']:i for i,r in enumerate(ranked)}
 out.sort(key=lambda p:(order.get(p['id'],100000),p['id']))
 return out

def resume(c,uid):
 row=c.execute("""SELECT pack,skill,stamp FROM (SELECT pack,skill,updated stamp FROM lab_drafts WHERE user_id=? AND trim(answer)!=''
 UNION ALL SELECT pack,skill,created stamp FROM lab_work WHERE user_id=?) ORDER BY stamp DESC LIMIT 1""",(uid,uid)).fetchone()
 if not row:return None
 return dict(row)

def detail(c,uid,pack,drafts):
 p=dict(pack);p.update(metadata(p));feedback={}
 byskill={d['skill']:d['answer'].strip() for d in drafts}
 seen=set()
 for r in c.execute("SELECT * FROM lab_jobs WHERE user_id=? AND pack=? AND kind IN ('feedback','audio') AND status='complete' ORDER BY id DESC LIMIT 40",(uid,p['id'])):
  skill=r['skill'];answer=byskill.get(skill)
  if skill in seen or not answer:continue
  result=json.loads(r['result'])
  spec={'pack':p['id'],'skill':skill,'answer':answer}
  expected=hashlib.sha256(json.dumps(spec,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
  if (r['kind']=='feedback' and r['fingerprint']==expected) or (r['kind']=='audio' and result.get('transcript')==answer):
   feedback[skill]={'result':result,'request_id':r['request_id']};seen.add(skill)
 note=c.execute('SELECT note FROM lab_notes WHERE user_id=? AND pack=?',(uid,p['id'])).fetchone()
 return {'metadata':metadata(p),'feedback':feedback,'bookmark':bool(c.execute('SELECT 1 FROM lab_bookmarks WHERE user_id=? AND pack=?',(uid,p['id'])).fetchone()),'note':note[0] if note else '',
   'recorded_skills':[r[0] for r in c.execute('SELECT DISTINCT skill FROM lab_work WHERE user_id=? AND pack=?',(uid,p['id']))]}

def post(c,uid,path,data,pack_for):
 if path not in ('/api/lab/bookmark','/api/lab/note','/api/lab/report','/api/lab/report/resolve'):return None
 if path.endswith('/resolve'):
  if not c.execute('SELECT 1 FROM users WHERE id=? AND admin=1',(uid,)).fetchone():return {'error':'需要管理员权限'},403
  if type(data.get('id'))!=int:raise ValueError('反馈标识不正确')
  c.execute("UPDATE lab_content_reports SET status='resolved' WHERE id=?",(data['id'],));c.commit();return {'ok':True},200
 p=pack_for(c,uid,data.get('pack'))
 if path=='/api/lab/report':
  category=data.get('category');note=data.get('note','')
  if category not in ('answer','expression','difficulty','other') or not isinstance(note,str) or not 5<=len(note.strip())<=800:raise ValueError('请写 5–800 字的问题描述')
  if c.execute('SELECT COUNT(*) FROM lab_content_reports WHERE user_id=? AND created>?',(uid,time.time()-86400)).fetchone()[0]>=5:return {'error':'每天最多提交 5 条语料反馈'},429
  c.execute('INSERT INTO lab_content_reports(user_id,pack,category,note,created) VALUES(?,?,?,?,?)',(uid,p['id'],category,note.strip(),time.time()));c.commit();return {'ok':True},200
 if path.endswith('/bookmark'):
  if type(data.get('saved'))!=bool:raise ValueError('收藏状态不正确')
  if data['saved']:c.execute('INSERT OR IGNORE INTO lab_bookmarks VALUES(?,?,?)',(uid,p['id'],time.time()))
  else:c.execute('DELETE FROM lab_bookmarks WHERE user_id=? AND pack=?',(uid,p['id']))
 else:
  note=data.get('note','')
  if not isinstance(note,str) or len(note)>1200:raise ValueError('笔记不正确')
  c.execute('INSERT OR REPLACE INTO lab_notes VALUES(?,?,?,?)',(uid,p['id'],note,time.time()))
 c.commit();return {'ok':True},200

def reports(c):
 items=[]
 for r in c.execute("SELECT r.id,r.pack,r.category,r.note,r.created,p.content FROM lab_content_reports r JOIN lab_packs p ON p.id=r.pack WHERE r.status='open' ORDER BY r.id DESC LIMIT 20"):
  item=dict(r);p=json.loads(item.pop('content'));item['material']={k:p[k] for k in ('title','body','questions')};items.append(item)
 return items
