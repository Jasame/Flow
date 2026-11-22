"""Instructional labels, observed skill bands and explainable personalized material selection."""
import json,re,time,math
from collections import Counter
LEVELS=('A2','B1','B2');SKILLS=('listening','speaking','reading','writing');DAY=86400

def schema(c):
 c.execute("CREATE TABLE IF NOT EXISTS practice_preferences(user_id INTEGER PRIMARY KEY REFERENCES users(id),skill TEXT NOT NULL DEFAULT 'listening',mode TEXT NOT NULL DEFAULT 'steady')")
 c.execute("CREATE TABLE IF NOT EXISTS practice_calibration(user_id INTEGER REFERENCES users(id),skill TEXT,level TEXT,evidence TEXT,updated REAL,PRIMARY KEY(user_id,skill))")
 c.execute("INSERT OR IGNORE INTO migrations VALUES('2.5-practice')")
 c.execute("INSERT OR IGNORE INTO migrations VALUES('3.0-pedagogy')")

def family(p):return 'family:'+p['family'] if p.get('family') else p['id']
def metadata(p):
 parts=[s for s in re.split(r'(?<=[.!?])\s+',p['body']) if s.strip()];words=re.findall(r"[A-Za-z]+(?:'[a-z]+)?",p['body'])
 return {'band':p['level'],'family':p.get('family',p['id']),'words':len(words),'sentences':len(parts),'mean_sentence_words':round(len(words)/max(1,len(parts)),1),'max_sentence_words':max((len(re.findall(r"[A-Za-z]+(?:'[a-z]+)?",s)) for s in parts),default=0),'targets':len(p.get('vocabulary',[])),'grammar':p.get('grammar',[]),'rationale':p.get('grading_basis',{}).get('rationale','沿用教学编排的练习难度，结合实际表现继续校准。'),'label':'教学建议分级 · 非认证','source':'authored' if p.get('grading_basis') else 'existing-label','minutes':max(4,3+math.ceil(len(words)/65))}

def starting_source(c,uid):
 """(level, source). A measured starting check wins; then the learner's chosen target; then an older saved
 level; otherwise the start is unknown and practice begins at the base band, to be calibrated by real work."""
 from settings_service import placement_status,get
 p=c.execute('SELECT placement FROM coach_profiles WHERE user_id=?',(uid,)).fetchone()
 status=placement_status(json.loads(p[0]) if p else None)
 if status['measured_band'] in LEVELS:return status['measured_band'],'placement'
 target=get(c,uid)['target_level']
 if target in LEVELS:return target,'target'
 if not p:
  old=c.execute('SELECT level FROM lab_profile WHERE user_id=?',(uid,)).fetchone()
  if old and old[0] in LEVELS:return old[0],'previous'
 return 'A2','unknown'

STARTING_NOTES={'placement':'来自起点检查（有限题量，不是认证）','target':'起点待了解，暂按你选择的目标难度试练','previous':'沿用之前保存的练习难度','unknown':'起点待了解，先从基础档试练，按真实表现调整'}

def starting(c,uid):return starting_source(c,uid)[0]

def bands(c,uid):
 base,source=starting_source(c,uid);packs={r['id']:json.loads(r['content']) for r in c.execute('SELECT id,content FROM lab_packs WHERE owner IS NULL OR owner=?',(uid,))};out={}
 for skill in SKILLS:
  samples=[];seen=set()
  if skill in ('listening','reading'):
   for r in c.execute("SELECT * FROM learning_events WHERE user_id=? AND node=? AND evaluator='rule' AND assisted=0 AND correct IS NOT NULL AND created>? ORDER BY created DESC,id DESC",(uid,'skill:'+skill,time.time()-14*DAY)):
    p=packs.get(r['item']) or packs.get(r['context'])
    if not p or p['level'] not in LEVELS:continue
    key=family(p)
    if key in seen:continue
    seen.add(key);samples.append({'id':r['id'],'correct':r['correct'],'level':p['level'],'family':key})
    if len(samples)==6:break
  checkpoint=c.execute('SELECT level FROM practice_calibration WHERE user_id=? AND skill=?',(uid,skill)).fetchone()
  level=checkpoint[0] if checkpoint else base;reason='独立理解样本不足，'+STARTING_NOTES[source]+'。';direction='calibrate'
  if len(samples)==6 and len({r['level'] for r in samples})==1:
   observed=samples[0]['level'];passed=sum(r['correct'] for r in samples);index=LEVELS.index(observed)
   level=LEVELS[min(2,index+1)] if passed>=5 else LEVELS[max(0,index-1)] if passed<=2 else observed
   direction='advance' if level>observed else 'repair' if level<observed else 'steady'
   reason='近14天六个不同情境的独立理解检查，'+(('至少五次通过，继续在本库B2档换语境巩固。' if index==2 else '至少五次通过，尝试高一档。') if passed>=5 else ('通过不超过两次，继续在本库A2基础档巩固。' if index==0 else '通过不超过两次，先降低一档巩固。') if passed<=2 else '其余情况维持难度并换语境。')
  elif skill in ('speaking','writing'):reason='表达作品和AI反馈单独记录，暂不据此自动判定口语或写作等级。'
  out[skill]={'level':level,'starting_level':base,'starting_source':source,'evidence_ids':[r['id'] for r in samples],'families':len(samples),'reason':reason,'direction':direction,'calibrated':len(samples)==6 and len({r['level'] for r in samples})==1}
 return out

def update_bands(c,uid):
 for skill,d in bands(c,uid).items():
  if d['calibrated']:
   c.execute('INSERT OR REPLACE INTO practice_calibration VALUES(?,?,?,?,?)',(uid,skill,d['level'],json.dumps(d['evidence_ids']),time.time()))

def preferences(c,uid):
 st=__import__('settings_service').get(c,uid)
 return {'skill':st['focus_skill'],'mode':st['practice_mode']}

def rank(c,uid,rows,node=None,skill=None,mode=None):
 import quality_service as quality
 from growth_service import settings,review_queue
 import settings_service as store
 pref=preferences(c,uid);skill=skill or pref['skill'];mode=mode or pref['mode']
 if skill not in SKILLS or mode not in ('steady','stretch','repair'):raise ValueError('训练方式或难度偏好不正确')
 levels=bands(c,uid);observed=levels[skill]['level'];index=LEVELS.index(observed);target=LEVELS[min(2,index+1)] if mode=='stretch' else LEVELS[max(0,index-1)] if mode=='repair' else observed
 theme,theme_source=store.theme(c,uid);hot=settings(c,uid)['hotspots'];budget=store.minutes(c,uid)
 allpacks={r['id']:json.loads(r['content']) for r in c.execute('SELECT id,content FROM lab_packs WHERE owner IS NULL OR owner=?',(uid,))};used=Counter()
 for r in c.execute('SELECT pack FROM lab_work WHERE user_id=?',(uid,)):
  if r['pack'] in allpacks:used[family(allpacks[r['pack']])]+=1
 weak={r['node'] for r in review_queue(c,uid) if r['kind']=='grammar' and r['ready']}
 if node:weak.add(node)
 ratings={r['pack']:r['rating'] for r in c.execute('SELECT pack,rating FROM material_difficulty WHERE user_id=?',(uid,))}
 observed_materials=__import__('learning_insights').calibrations(c,uid)
 result=[]
 for row in rows:
  if not quality.recommendable(c,row) or row['origin']=='daily' and not hot:continue
  p=json.loads(row['content'])
  if p['level'] not in LEVELS:continue
  m=metadata(p);gap=abs(LEVELS.index(p['level'])-LEVELS.index(target));linked=bool(set(m['grammar'])&weak);seen=used[family(p)];fits=m['minutes']<=budget
  prior=ratings.get(p['id']);calibration=observed_materials.get(p['id'],{});friction=2 if prior=='hard' else 1 if calibration.get('calibrated') and calibration['pass_rate']<.35 else 0
  key=(gap,friction,not fits,seen>0,not linked,p['theme']!=theme,seen,m['minutes'],p['id'])
  # Structured reasons. 'personal' is true only when the reason comes from something the learner chose or did.
  items=[{'code':'level','text':'匹配'+target+'练习难度' if gap==0 else '相邻难度备选：'+p['level'],'personal':levels[skill]['starting_source']!='unknown' or levels[skill]['calibrated'],'default':levels[skill]['starting_source']=='unknown' and not levels[skill]['calibrated']},
   {'code':'novelty','text':'未练过的情境' if not seen else '熟悉情境复练，不作为新语境','personal':bool(seen),'default':False}]
  if prior=='hard':items.append({'code':'rated_hard','text':'你曾标记本篇偏难，同档优先换一篇','personal':True,'default':False})
  if calibration.get('calibrated'):items.append({'code':'calibrated','text':'已有真实理解检查样本；不是认证难度','personal':False,'default':False})
  if linked:items.append({'code':'grammar','text':'关联你待验证的语法细项','personal':True,'default':False})
  if p['theme']==theme:items.append({'code':'theme','text':{'chosen':'符合你选择的主题','interests':'符合你填写的兴趣','goal':'贴近你的学习目标'}.get(theme_source,'默认主题（你还没有设置兴趣）'),'personal':theme_source!='default','default':theme_source=='default'})
  items.append({'code':'time','text':'约'+str(m['minutes'])+'分钟'+('，适合你设置的每日时间' if fits else '，可拆成多个学习单元'),'personal':True,'default':False})
  reasons=[x['text'] for x in items]
  result.append((key,{'pack':p,'grading':m,'reason':'；'.join(reasons)+'。','reasons':items,'seen_family':bool(seen),'skill':skill,'target':target}))
 result.sort(key=lambda pair:pair[0])
 # Offer distinct situations first; sibling variants remain available through the level filters.
 unique=[];seenfamilies=set()
 for _,r in result:
  key=family(r['pack'])
  if key not in seenfamilies:seenfamilies.add(key);unique.append(r)
 return unique,{'skill':skill,'mode':mode,'target':target,'observed':observed,'dimensions':levels,'minutes':budget,'theme':theme,'theme_source':theme_source,'starting_source':levels[skill]['starting_source'],'starting_note':STARTING_NOTES[levels[skill]['starting_source']],'note':'难度是下一次练习建议，不是能力认证。挑战/巩固是你的练习偏好；同一情境的改写版本不算新语境。'}

def overview(c,uid,skill=None,mode=None):
 rows=c.execute('SELECT * FROM lab_packs WHERE owner IS NULL OR owner=?',(uid,)).fetchall();ranked,plan=rank(c,uid,rows,skill=skill,mode=mode)
 counts=Counter();families=set()
 import quality_service as quality
 for r in rows:
  if quality.recommendable(c,r):
   p=json.loads(r['content']);counts[p['level']]+=1;families.add(family(p))
 plan['counts']={l:counts[l] for l in LEVELS};plan['situations']=len(families);plan['total']=sum(counts.values());plan['items']=[{k:r[k] for k in ('grading','reason','reasons','seen_family','skill')}|{'id':r['pack']['id'],'title':r['pack']['title'],'level':r['pack']['level'],'theme':r['pack']['theme']} for r in ranked[:6]]
 return plan

def get(c,uid,path,q):
 if path!='/api/practice':return None
 return overview(c,uid,q.get('skill',[None])[0],q.get('mode',[None])[0]),200

def post(c,uid,path,data):
 if path!='/api/practice/preferences':return None
 skill=data.get('skill');mode=data.get('mode')
 if skill not in SKILLS or mode not in ('steady','stretch','repair'):raise ValueError('训练设置不正确')
 import settings_service as store
 try:store.save(c,uid,{'focus_skill':skill,'practice_mode':mode,**({'version':data['version']} if 'version' in data else {})},'practice')
 except store.Conflict as e:c.rollback();return {'error':'设置已在其他页面更新，请确认后再保存。','current':e.current},409
 return overview(c,uid),200
