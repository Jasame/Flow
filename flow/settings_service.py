"""Single source of learner settings.

learner_settings is authoritative. The older tables (coach_profiles, learner_goals,
study_preferences, practice_preferences, growth_settings) are kept as mirrors so existing
readers and rollbacks keep working. Every writer goes through save(), with an optional
version check so a stale page cannot silently overwrite a newer choice.

Three different things are kept apart:
- the starting check result (measured, or unknown when there were too few answers),
- the learner's chosen target level (a challenge, never shown as a measured level),
- the per-skill practice suggestion computed from real work (practice_service.bands).
"""
import json,re,time
MINUTES=(5,10,15,20,30,45,60)
GOALS=('general','exam','travel','work')
LEVELS=('A2','B1','B2')
THEMES=('auto','campus','travel','life','work','culture','science')
SKILLS=('listening','speaking','reading','writing')
MODES=('steady','stretch','repair')
FIELDS=('goal','goal_kind','interests','minutes','daily_new','target_level','focus_skill','practice_mode','theme')

class Conflict(Exception):
 def __init__(self,current):super().__init__('设置已在其他页面更新');self.current=current

def schema(c):
 c.execute('''CREATE TABLE IF NOT EXISTS learner_settings(user_id INTEGER PRIMARY KEY REFERENCES users(id),goal TEXT NOT NULL DEFAULT '',goal_kind TEXT NOT NULL DEFAULT 'general',interests TEXT NOT NULL DEFAULT '',minutes INTEGER NOT NULL DEFAULT 15,daily_new INTEGER NOT NULL DEFAULT 3,target_level TEXT,focus_skill TEXT NOT NULL DEFAULT 'listening',practice_mode TEXT NOT NULL DEFAULT 'steady',theme TEXT NOT NULL DEFAULT 'auto',version INTEGER NOT NULL DEFAULT 1,updated REAL NOT NULL,origin TEXT NOT NULL DEFAULT '')''')
 if not c.execute("SELECT 1 FROM migrations WHERE version='3.5-settings'").fetchone():
  for (uid,) in c.execute('SELECT id FROM users').fetchall():backfill(c,uid)
  c.execute("INSERT INTO migrations VALUES('3.5-settings')")

def _one(c,sql,uid):
 try:return c.execute(sql,(uid,)).fetchone()
 except Exception:return None

def backfill(c,uid):
 """Build settings from the scattered legacy tables. Conflict rule for minutes: the value held by
 most of coach_profiles / learner_goals / study_preferences wins; on a tie, coach_profiles, then
 learner_goals, then study_preferences. The chosen source is kept in origin."""
 if c.execute('SELECT 1 FROM learner_settings WHERE user_id=?',(uid,)).fetchone():return
 coach=_one(c,'SELECT goal,interests,minutes FROM coach_profiles WHERE user_id=?',uid)
 goals=_one(c,'SELECT goal,minutes,daily_new,level FROM learner_goals WHERE user_id=?',uid)
 study=_one(c,'SELECT minutes FROM study_preferences WHERE user_id=?',uid)
 practice=_one(c,'SELECT skill,mode FROM practice_preferences WHERE user_id=?',uid)
 lab=_one(c,'SELECT focus FROM lab_profile WHERE user_id=?',uid)
 growth=_one(c,'SELECT theme FROM growth_settings WHERE user_id=?',uid)
 candidates=[(name,row['minutes']) for name,row in (('coach_profiles',coach),('learner_goals',goals),('study_preferences',study)) if row and row['minutes'] in MINUTES]
 minutes,source=15,'default'
 if candidates:
  counts={}
  for _,m in candidates:counts[m]=counts.get(m,0)+1
  best=max(counts.values());minutes,source=next((m,n) for n,m in candidates if counts[m]==best)
 conflict=len({m for _,m in candidates})>1
 data={'goal':coach['goal'] if coach else '','goal_kind':goals['goal'] if goals and goals['goal'] in GOALS else 'general','interests':coach['interests'] if coach else '','minutes':minutes,'daily_new':goals['daily_new'] if goals else 3,
  'target_level':goals['level'] if goals and goals['level'] in LEVELS else None,
  'focus_skill':practice['skill'] if practice and practice['skill'] in SKILLS else lab['focus'] if lab and lab['focus'] in SKILLS else 'listening',
  'practice_mode':practice['mode'] if practice and practice['mode'] in MODES else 'steady','theme':growth['theme'] if growth and growth['theme'] in THEMES else 'auto'}
 # Before 3.5 the studio theme was used when no coach profile existed; 'campus' is only the column default.
 lab_theme=_one(c,'SELECT theme FROM lab_profile WHERE user_id=?',uid)
 if data['theme']=='auto' and not coach and lab_theme and lab_theme['theme'] in THEMES and lab_theme['theme']!='campus':data['theme']=lab_theme['theme']
 origin='migrated:minutes='+source+(';conflict='+','.join(f'{n}={m}' for n,m in candidates) if conflict else '')
 c.execute('INSERT INTO learner_settings(user_id,'+','.join(FIELDS)+',version,updated,origin) VALUES(?,'+','.join('?'*len(FIELDS))+',1,?,?)',(uid,*[data[k] for k in FIELDS],time.time(),origin))

def get(c,uid):
 r=c.execute('SELECT * FROM learner_settings WHERE user_id=?',(uid,)).fetchone()
 if not r:
  # A lazy backfill must not leave a read call holding an open write transaction.
  outer=c.in_transaction;backfill(c,uid)
  if not outer:c.commit()
  r=c.execute('SELECT * FROM learner_settings WHERE user_id=?',(uid,)).fetchone()
 return dict(r)

def minutes(c,uid):return get(c,uid)['minutes']

def placement_status(placement):
 """Was a starting level actually observed? Older records are judged from their saved scores."""
 if not placement:return {'status':'none','measured_band':None,'label':'还没做起点检查'}
 if 'measured' in placement:measured=placement['measured']
 else:
  scores=placement.get('scores',{});measured=sum(s.get('total',0)-s.get('hinted',0) for s in scores.values())>=4
 band=placement.get('band') if measured else None
 return {'status':'measured' if measured else 'unknown','measured_band':band,'label':('起点检查建议：'+band+'（有限题量，不是认证等级）') if band else '起点待了解：有效作答太少，先练起来再逐步校准'}

def validate(data):
 out={}
 for k,v in data.items():
  if k not in FIELDS:continue
  if k in ('goal','interests'):
   if not isinstance(v,str) or len(v.strip())>300 or k=='goal' and not v.strip():raise ValueError('学习目标需为1–300字，兴趣不超过300字')
   v=v.strip()
  elif k=='minutes' and (type(v)!=int or v not in MINUTES):raise ValueError('每日时间请选择 '+'、'.join(map(str,MINUTES))+' 分钟')
  elif k=='daily_new' and (type(v)!=int or not 1<=v<=10):raise ValueError('每日新词数量为1–10')
  elif k=='goal_kind' and v not in GOALS:raise ValueError('学习方向不正确')
  elif k=='target_level' and v not in LEVELS+(None,):raise ValueError('目标难度不正确')
  elif k=='focus_skill' and v not in SKILLS:raise ValueError('训练方式不正确')
  elif k=='practice_mode' and v not in MODES:raise ValueError('难度偏好不正确')
  elif k=='theme' and v not in THEMES:raise ValueError('主题不正确')
  out[k]=v
 return out

def save(c,uid,data,origin='settings',commit=True):
 """Partial update. Pass data['version'] to reject a stale page (raises Conflict)."""
 changes=validate(data);current=get(c,uid);expected=data.get('version')
 if expected is not None:
  if type(expected)!=int:raise ValueError('设置版本不正确')
  if expected!=current['version']:raise Conflict(public(c,uid))
 if not changes:return current
 merged={**current,**changes};now=time.time()
 c.execute('UPDATE learner_settings SET '+','.join(k+'=?' for k in changes)+',version=version+1,updated=?,origin=? WHERE user_id=?',(*changes.values(),now,origin,uid))
 # Mirrors for existing readers and for rollback to the previous release.
 c.execute('INSERT OR REPLACE INTO study_preferences VALUES(?,?)',(uid,merged['minutes']))
 old=c.execute('SELECT level FROM learner_goals WHERE user_id=?',(uid,)).fetchone()
 c.execute('INSERT OR REPLACE INTO learner_goals VALUES(?,?,?,?,?)',(uid,merged['goal_kind'],merged['minutes'],merged['daily_new'],merged['target_level'] or (old[0] if old else 'B1')))
 c.execute('UPDATE coach_profiles SET goal=CASE WHEN ?<>\'\' THEN ? ELSE goal END,interests=?,minutes=?,updated=? WHERE user_id=?',(merged['goal'],merged['goal'],merged['interests'],merged['minutes'],now,uid))
 c.execute('INSERT OR REPLACE INTO practice_preferences VALUES(?,?,?)',(uid,merged['focus_skill'],merged['practice_mode']))
 hot=c.execute('SELECT hotspots FROM growth_settings WHERE user_id=?',(uid,)).fetchone()
 c.execute('INSERT OR REPLACE INTO growth_settings VALUES(?,?,?)',(uid,merged['theme'],hot[0] if hot else 0))
 if commit:c.commit()
 return get(c,uid)

def theme(c,uid):
 """(theme, source). Source is 'chosen', 'goal' or 'default' so reasons never claim an unstated interest."""
 s=get(c,uid)
 if s['theme']!='auto':return s['theme'],'chosen'
 text=(s['goal'] or '')+' '+(s['interests'] or '')
 for pattern,name in [('旅行|旅游|travel','travel'),('职场|工作|work|email|邮件','work'),('科学|科技|science','science'),('电影|文化|culture','culture'),('生活|日常|life','life'),('校园|大学|学校|考试|campus|exam','campus')]:
  if re.search(pattern,text,re.I):return name,'interests' if s['interests'] and re.search(pattern,s['interests'],re.I) else 'goal'
 if s['goal_kind'] in ('travel','work'):return s['goal_kind'],'goal'
 return 'campus','default'

def public(c,uid):
 s=get(c,uid);row=c.execute('SELECT placement FROM coach_profiles WHERE user_id=?',(uid,)).fetchone()
 placement=json.loads(row[0]) if row else None;status=placement_status(placement)
 from foundation_service import is_basic
 from practice_service import bands
 levels={k:{'level':v['level'],'calibrated':v['calibrated'],'source':v.get('starting_source')} for k,v in bands(c,uid).items()}
 name,source=theme(c,uid)
 return {**{k:s[k] for k in FIELDS},'version':s['version'],'updated':s['updated'],'minutes_options':list(MINUTES),
  'placement':status,'target_level_note':'这是你选择的挑战方向，不是测出的水平。' if s['target_level'] else '未设置目标难度，按实际练习表现推荐。',
  'learning_mode':'basic' if is_basic(c,uid) else 'standard','skill_levels':levels,'theme_effective':{'theme':name,'source':source}}

def get_route(c,uid,path):
 if path=='/api/settings':return public(c,uid),200
 return None

def post_route(c,uid,path,data):
 if path!='/api/settings':return None
 try:save(c,uid,data,'settings')
 except Conflict as e:c.rollback();return {'error':'设置已在其他页面更新，请确认后再保存。','current':e.current},409
 return public(c,uid),200
