"""Repeatable import of externally prepared corpus candidates (e.g. a Gemini batch).

Everything in a bundle is treated as candidate data:
- records are joined by candidate_id (candidate text + source row + learning pack);
- counts are recomputed from the files, never copied from the bundle's own notes;
- source access, AI rewriting and permission to publish are separate review items;
- a re-run of the same bundle writes nothing new; a changed record becomes a new version;
- nothing here writes to lab_packs, attempts, bookmarks, drafts or the lexicon, so existing
  materials (e.g. campus-a2) and learner history are untouched and candidates stay invisible
  to the student catalog, direct links, the graph and recommendations until published.

CLI:  python3 corpus_import.py preflight <bundle_dir> [--json out.json] [--md out.md]
      python3 corpus_import.py apply <bundle_dir> [--actor admin_username]
"""
import csv,hashlib,json,re,sys,time
from pathlib import Path

THEME_MAP={'校园学习':'campus','日常沟通':'life','简单职场沟通':'work','职场沟通':'work','旅行生活':'travel','日常生活':'life','文化交流':'culture','科学素养':'science'}
# Flow has no exam theme. These are suggestions by subject and stay a review item until confirmed.
EXAM_THEME_HINTS=[(('拖延','情绪','记忆','认知','环保','废弃','循环','AI','人工智能'),'science'),(('实习','职场','雇主','就业'),'work')]
REQUIRED=('candidate_id','title','scenario','level','skills','learning_objective','content_type','source_title','source_url','accessed_at','usage_terms','body','vocabulary','family_id','review_status')
LEVELS=('A2','B1','B2');SKILLS=('listening','speaking','reading','writing')
MARKER=re.compile(r'\[(?:TARGET|PAUSE|STRESS|NOTE)[_A-Z0-9]*:\s*([^\]]*)\]')
POS_CLASS={'n.':'n','noun':'n','v.':'v','vt.':'v','vi.':'v','verb':'v','adj.':'adj','a.':'adj','adjective':'adj','adv.':'adv','adverb':'adv','prep.':'prep','conj.':'conj','phr.':'phr','phrase':'phr'}

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS corpus_candidates(candidate_id TEXT PRIMARY KEY,version INTEGER NOT NULL,content_hash TEXT NOT NULL,level TEXT,theme TEXT,status TEXT NOT NULL DEFAULT 'candidate',data TEXT NOT NULL,review TEXT NOT NULL,batch TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL);
 CREATE TABLE IF NOT EXISTS corpus_packs(pack_id TEXT PRIMARY KEY,candidate_id TEXT REFERENCES corpus_candidates(candidate_id),version INTEGER NOT NULL,content_hash TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'candidate',data TEXT NOT NULL,structure TEXT NOT NULL,batch TEXT NOT NULL,created REAL NOT NULL,updated REAL NOT NULL);
 CREATE TABLE IF NOT EXISTS corpus_versions(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,ref TEXT NOT NULL,version INTEGER NOT NULL,content_hash TEXT NOT NULL,data TEXT NOT NULL,batch TEXT NOT NULL,created REAL NOT NULL,UNIQUE(kind,ref,version));
 CREATE TABLE IF NOT EXISTS corpus_sense_links(candidate_id TEXT NOT NULL,word TEXT NOT NULL,pos TEXT NOT NULL,meaning TEXT NOT NULL,decision TEXT NOT NULL,lexicon TEXT,reference TEXT,status TEXT NOT NULL DEFAULT 'proposed',version INTEGER NOT NULL,PRIMARY KEY(candidate_id,word,pos,meaning));
 CREATE TABLE IF NOT EXISTS corpus_import_runs(id INTEGER PRIMARY KEY,batch TEXT NOT NULL,mode TEXT NOT NULL,summary TEXT NOT NULL,actor TEXT,created REAL NOT NULL);
 CREATE TABLE IF NOT EXISTS corpus_reviews(id INTEGER PRIMARY KEY,kind TEXT NOT NULL,ref TEXT NOT NULL,version INTEGER NOT NULL,item TEXT NOT NULL,decision TEXT NOT NULL,note TEXT NOT NULL,actor TEXT NOT NULL,created REAL NOT NULL);''')
 c.execute("INSERT OR IGNORE INTO migrations VALUES('3.9-corpus-import')")

def digest(obj):return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def clean_script(s):return re.sub(r'\s+',' ',MARKER.sub(r'\1',s or '')).strip()
def norm(s):return re.sub(r'\s+',' ',str(s or '')).strip().casefold()

# ---------- loading and joining ----------
def load(folder):
 folder=Path(folder);files={n:folder/n for n in ('sources.csv','flow_candidates.jsonl','flow_learning_packs.json','review_notes.md')}
 missing=[n for n,p in files.items() if not p.is_file()]
 if missing:raise ValueError('附件缺少文件：'+'、'.join(missing))
 raw={n:p.read_bytes() for n,p in files.items()}
 candidates=[];bad_lines=[]
 for i,line in enumerate(raw['flow_candidates.jsonl'].decode('utf-8').splitlines(),1):
  if not line.strip():continue
  try:candidates.append(json.loads(line))
  except json.JSONDecodeError:bad_lines.append(i)
 sources=list(csv.DictReader(raw['sources.csv'].decode('utf-8-sig').splitlines()))
 packs=json.loads(raw['flow_learning_packs.json'].decode('utf-8'))
 batch=hashlib.sha256(b''.join(hashlib.sha256(raw[n]).digest() for n in sorted(raw))).hexdigest()[:16]
 return {'batch':batch,'candidates':candidates,'sources':sources,'packs':packs if isinstance(packs,list) else [],'notes':raw['review_notes.md'].decode('utf-8'),'bad_lines':bad_lines,'files':{n:{'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()} for n,b in raw.items()}}

def flow_theme(label,title):
 if label in THEME_MAP:return THEME_MAP[label],'mapped'
 if label=='四六级常见场景':
  for words,theme in EXAM_THEME_HINTS:
   if any(w in title for w in words):return theme,'suggested'
  return None,'unmapped'
 return None,'unmapped'

def merge(bundle):
 by_source={};dup_sources=[]
 for r in bundle['sources']:
  cid=(r.get('candidate_id') or '').strip()
  if cid in by_source:dup_sources.append(cid)
  by_source[cid]=r
 merged=[];seen=set();dups=[]
 for cand in bundle['candidates']:
  cid=cand.get('candidate_id')
  if cid in seen:dups.append(cid);continue
  seen.add(cid);src=by_source.get(cid,{})
  theme_label=cand.get('theme') or src.get('theme') or ''
  theme,basis=flow_theme(theme_label,cand.get('title',''))
  rec={'candidate':cand,'source':src,'theme_label':theme_label,'theme_from':'candidate' if cand.get('theme') else 'sources.csv' if src.get('theme') else 'missing','flow_theme':theme,'theme_basis':basis,
   'packs':[p.get('pack_id') for p in bundle['packs'] if p.get('candidate_id')==cid]}
  merged.append(rec)
 return merged,dups,dup_sources

# ---------- review items (each one a separate human decision) ----------
def license_of(terms):
 t=terms or ''
 if '待确认' in t:return 'unconfirmed'
 if 'CC BY-NC' in t:return 'cc-by-nc'
 if 'CC BY-SA' in t:return 'cc-by-sa'
 if 'CC BY' in t:return 'cc-by'
 if 'Public Domain' in t:return 'public-domain'
 if 'Apache' in t:return 'apache-2.0-reference'
 if '版权归平台' in t or '原创' in t:return 'original-claimed'
 return 'unknown'

def review_items(rec):
 cand=rec['candidate'];src=rec['source'];items=[]
 access=src.get('access_status','')
 items.append({'item':'source_access','label':'来源可访问','evidence':access[:200] or '（sources.csv 没有该条）','auto':'ok' if access.startswith('200 OK') and not re.search('拦截|Timeout|403|人工核实',access) else 'check'})
 ai=('AI' in (cand.get('usage_terms','')+src.get('usage_terms','')+cand.get('content_type','')+src.get('notes','')))
 items.append({'item':'ai_rewrite','label':'AI 改写说明','evidence':cand.get('content_type','')+('；条款里写明 AI 生成/改写' if ai else '；没有写明是否 AI 生成'),'auto':'check'})
 lic_c=license_of(cand.get('usage_terms'));lic_s=license_of(src.get('usage_terms'))
 items.append({'item':'public_use','label':'允许公开使用','evidence':'候选：'+lic_c+'；来源表：'+lic_s,'auto':'blocked' if 'unconfirmed' in (lic_c,lic_s) else 'check'})
 if norm(cand.get('usage_terms'))!=norm(src.get('usage_terms')):
  items.append({'item':'usage_terms_mismatch','label':'两份文件的用途条款文字不同','evidence':{'flow_candidates.jsonl':cand.get('usage_terms',''),'sources.csv':src.get('usage_terms','')},'auto':'check'})
 if cand.get('source_url')!=src.get('source_url'):items.append({'item':'source_url_mismatch','label':'两份文件的来源链接不同','evidence':{'candidate':cand.get('source_url'),'sources':src.get('source_url')},'auto':'check'})
 if rec['theme_basis']!='mapped':items.append({'item':'theme_mapping','label':'主题映射','evidence':rec['theme_label']+' → '+str(rec['flow_theme'])+'（'+rec['theme_basis']+'）','auto':'check'})
 if '四六级' in rec['theme_label'] or '四六级' in cand.get('notes',''):items.append({'item':'exam_label','label':'“四六级原创模拟练习”标注','evidence':cand.get('notes','')[:120],'auto':'check'})
 items.append({'item':'language_level','label':'语言、难度与答案','evidence':cand.get('level','')+'：'+cand.get('level_rationale','')[:160],'auto':'check'})
 if 'listening' in cand.get('skills',[]):items.append({'item':'audio','label':'音频','evidence':'包内只有脚本；未录音','auto':'check'})
 return items

# ---------- question checks by role ----------
def keys(q):return [o.get('key') for o in q.get('options',[]) if isinstance(o,dict)]
def option_text(q,key):return next((o.get('text','') for o in q.get('options',[]) if o.get('key')==key),'')

def check_question(q,role,ctx):
 """Ordinary materials keep their own 2 x four-choice validation (lab_service.validate_pack).
 Diagnostic checks, remediation practice and verification each have their own rules here."""
 errs=[];warns=[];qid=q.get('question_id') or q.get('sub_id') or q.get('practice_id')
 if not qid or not re.fullmatch(r'[A-Z0-9][A-Z0-9_-]{2,60}',str(qid)):errs.append('缺少稳定题目 ID')
 ks=keys(q);n=len(ks);want={'initial':(4,4),'check':(2,3),'practice':(2,4),'verification':(4,4)}[role]
 if not want[0]<=n<=want[1]:errs.append(f'{role} 题需要 {want[0]}–{want[1]} 个选项，实际 {n} 个')
 if len(set(ks))!=n:errs.append('选项 key 重复')
 texts=[norm(o.get('text')) for o in q.get('options',[])]
 if len(set(texts))!=len(texts):errs.append('选项文字重复')
 if q.get('correct_key') not in ks:errs.append('正确答案不在选项里')
 if not (q.get('prompt') or '').strip():errs.append('缺少题干')
 right=norm(option_text(q,q.get('correct_key')))
 prompt=norm(q.get('prompt'))
 clip=norm(q.get('audio_clip_text'))
 if clip and clip in prompt:errs.append('题干直接写出了要听的音频内容')
 if role=='initial':
  ev=norm(q.get('answer_evidence'))
  if not ev:errs.append('缺少原文依据')
  elif ev not in ctx['body'] and ev not in ctx['script']:errs.append('原文依据不是正文或音频脚本的逐字片段')
 if role=='check':
  if q.get('focus_hypothesis') not in ctx['hypotheses']:errs.append('补查题没有对应的错误原因')
  if ctx['listening'] and re.match(r'\s*read\b',q.get('prompt',''),re.I):warns.append('听力包的补查题要求“读原文”，测的不是听力')
  if right and right in prompt:errs.append('题干里出现了正确选项')
 if role=='practice':
  if q.get('targeted_hypothesis') not in ctx['hypotheses']:errs.append('补练没有对应的错误原因')
  if not (q.get('explanation') or '').strip():warns.append('补练缺少解析')
 if role=='verification':
  ev=norm(q.get('answer_evidence'));context=norm(q.get('context_text'))
  if not context:errs.append('验证题缺少新语境材料')
  if not ev:errs.append('验证题缺少依据')
  elif ev not in context:errs.append('验证题依据不是新材料的逐字片段')
  missing=[k for k in ks if k!=q.get('correct_key') and k not in (q.get('distractor_explanations') or {})]
  if missing:warns.append('干扰项缺少解释：'+','.join(missing))
  if context and ctx['body'] and (context==ctx['body'] or any(s and s in context for s in re.split(r'(?<=[.!?])\s+',ctx['body']) if len(s)>40)):errs.append('验证材料与原材料有相同句子，不是新语境')
  if q.get('correct_key')==ctx.get('initial_key'):warns.append('验证题与起始题正确答案位置相同，可能被记忆猜中')
 return {'id':qid,'role':role,'errors':errs,'warnings':warns}

def check_pack(p,cand):
 body=norm(cand.get('body') if cand else '');script=norm(clean_script(p.get('audio_script')))
 hyp={h.get('hypothesis_id') for h in p.get('error_hypotheses',[])}
 ctx={'body':body,'script':script,'hypotheses':hyp,'listening':'listening' in p.get('skills',[]),'initial_key':(p.get('initial_question') or {}).get('correct_key')}
 out=[]
 if p.get('initial_question'):out.append(check_question(p['initial_question'],'initial',ctx))
 for s in (p.get('diagnostic_check') or {}).get('sub_questions',[]):out.append(check_question(s,'check',ctx))
 for b in p.get('remediation_branches',[]):
  if b.get('targeted_practice'):out.append(check_question({**b['targeted_practice'],'targeted_hypothesis':b.get('targeted_hypothesis')},'practice',ctx))
 if p.get('verification_question'):out.append(check_question(p['verification_question'],'verification',ctx))
 structure=[]
 for k in ('initial_question','error_hypotheses','diagnostic_check','remediation_branches','verification_question'):
  if not p.get(k):structure.append('缺少 '+k)
 if len(hyp)<2:structure.append('错误原因少于两条，无法分流')
 branches={b.get('targeted_hypothesis') for b in p.get('remediation_branches',[])}
 if hyp and branches!=hyp:structure.append('补练分支和错误原因没有一一对应')
 checks={s.get('focus_hypothesis') for s in (p.get('diagnostic_check') or {}).get('sub_questions',[])}
 if hyp and checks!=hyp:structure.append('补查题和错误原因没有一一对应')
 if MARKER.search(p.get('audio_script','')):structure.append('音频脚本含制作标记（播放前必须去掉）')
 if ctx['listening'] and 'audio' not in (p.get('audio_status') or '').lower() and '待制作' in (p.get('audio_status') or ''):structure.append('音频待制作')
 return {'questions':out,'structure':structure,'errors':sum(len(q['errors']) for q in out),'warnings':sum(len(q['warnings']) for q in out)}

# ---------- vocabulary: form + part of speech + sense in context ----------
def pos_class(p):
 p=(p or '').strip().casefold()
 return POS_CLASS.get(p,p.rstrip('.') or '')

def sense_tokens(meaning):
 meaning=re.sub(r'[（(][^）)]*[）)]','',meaning or '')
 return {t.strip() for t in re.split(r'[，,；;、/\s]+',meaning) if len(t.strip())>=2}

def reference_senses(variant_meaning):
 """'n. 草稿；汇票；vt. 起草' -> {'n':{'草稿','汇票'},'v':{'起草'}}"""
 out={};cur=''
 for part in re.split(r'(\b(?:n|v|vt|vi|adj|a|adv|prep|conj)\.)',variant_meaning or ''):
  if re.fullmatch(r'(?:n|v|vt|vi|adj|a|adv|prep|conj)\.',part):cur=pos_class(part);continue
  out.setdefault(cur,set()).update(sense_tokens(re.sub(r'\[[^\]]*\]','',part)))
 return out

def overlap(a,b):return any(x in y or y in x for x in a for y in b)

def match_word(c,w):
 word=(w.get('word') or '').strip().casefold();pc=pos_class(w.get('pos'));toks=sense_tokens(w.get('meaning'))
 res={'word':word,'pos':w.get('pos',''),'meaning':w.get('meaning',''),'lexicon':None,'reference':None,'decision':'new','note':''}
 rows=c.execute("SELECT id,sense,status,content FROM lexicon WHERE lemma=? AND owner IS NULL",(word,)).fetchall() if word else []
 for r in rows:
  e=json.loads(r['content']);lp=pos_class(e.get('pos'))
  if (not lp or not pc or lp==pc) and overlap(toks,sense_tokens(e.get('meaning'))):
   res.update(lexicon=r['id'],decision='reuse',note='已有教学词条同一义项（'+e.get('meaning','')+'）：复用它，补充新例句与材料关联'+('；该词条词性未填，需人工确认' if not lp else ''),published=r['status']=='published');break
 else:
  if rows:res.update(decision='new_sense',note='已有同形词条，但义项不同：保留为独立义项',lexicon_same_form=[r['id'] for r in rows])
 ref=c.execute('SELECT id,content FROM reference_terms WHERE norm=?',(word,)).fetchone() if word else None
 if ref:
  t=json.loads(ref['content']);hit=None
  for v in t.get('variants',[]):
   senses=reference_senses(v.get('meaning'))
   pool=senses.get(pc,set()) if pc else set().union(*senses.values()) if senses else set()
   if overlap(toks,pool):hit=v.get('row');break
  res['reference']={'id':ref['id'],'row':hit,'sense_found':hit is not None,'meaning':(t.get('variants') or [{}])[0].get('meaning','')[:120]}
  if res['decision']=='new' and hit is None:res['note']='yl-reference 有这个词，但没找到同词性同义项，需人工核对'
  elif res['decision']=='new':res['note']='教学词库没有；yl-reference 有同义项，可作为新教学词条的来源'
 elif res['decision']=='new':res['note']='教学词库和 yl-reference 都没有'
 return res

# ---------- preflight ----------
def preflight(c,bundle):
 merged,dup_ids,dup_sources=merge(bundle)
 report={'batch':bundle['batch'],'files':bundle['files'],'generated':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'counts':{},'new':[],'existing':[],'changed':[],'duplicates':[],'missing_fields':[],'evidence_mismatch':[],'review':[],'packs':[],'vocabulary':[],'notes_vs_data':[]}
 levels={};themes={};skills={}
 for rec in merged:
  cand=rec['candidate'];cid=cand.get('candidate_id')
  levels[cand.get('level')]=levels.get(cand.get('level'),0)+1;themes[rec['theme_label'] or '（缺）']=themes.get(rec['theme_label'] or '（缺）',0)+1
  for s in cand.get('skills',[]):skills[s]=skills.get(s,0)+1
  miss=[k for k in REQUIRED if not cand.get(k)]
  if not rec['source']:miss.append('sources.csv 中没有该 candidate_id')
  if rec['theme_from']=='missing':miss.append('theme')
  if cand.get('level') not in LEVELS:miss.append('level 不在 A2/B1/B2')
  if miss:report['missing_fields'].append({'id':cid,'fields':miss})
  h=digest(record(rec));old=c.execute('SELECT version,content_hash FROM corpus_candidates WHERE candidate_id=?',(cid,)).fetchone()
  (report['existing'] if old and old['content_hash']==h else report['changed'] if old else report['new']).append({'id':cid,'version':(old['version'] if old else 0)})
  report['review'].append({'id':cid,'title':cand.get('title'),'level':cand.get('level'),'theme':rec['flow_theme'],'theme_label':rec['theme_label'],'theme_from':rec['theme_from'],'items':review_items(rec)})
  for w in cand.get('vocabulary',[]):
   m=match_word(c,w);m['candidate']=cid
   if m['word'] and not re.search(r'(?<![a-z])'+re.escape(m['word'])+r'(?![a-z])',cand.get('body',''),re.I):m['note']+='；正文里没有这个词形'
   report['vocabulary'].append(m)
 bodies={}
 for rec in merged:
  b=norm(rec['candidate'].get('body'))
  if b in bodies:report['duplicates'].append({'kind':'same body','ids':[bodies[b],rec['candidate'].get('candidate_id')]})
  bodies[b]=rec['candidate'].get('candidate_id')
 for cid in dup_ids:report['duplicates'].append({'kind':'candidate_id repeated in flow_candidates.jsonl','ids':[cid]})
 for cid in dup_sources:report['duplicates'].append({'kind':'candidate_id repeated in sources.csv','ids':[cid]})
 families={}
 for rec in merged:families.setdefault(rec['candidate'].get('family_id'),[]).append(rec['candidate'].get('candidate_id'))
 for f,ids in families.items():
  if len(ids)>1:report['duplicates'].append({'kind':'same family_id','ids':ids,'family':f})
 urls={}
 for rec in merged:urls.setdefault(rec['candidate'].get('source_url'),[]).append(rec['candidate'].get('candidate_id'))
 for u,ids in urls.items():
  if len(ids)>1:report['duplicates'].append({'kind':'same source_url (check that each source really supports its text)','ids':ids,'url':u})
 cands={r['candidate'].get('candidate_id'):r['candidate'] for r in merged};pack_ids=set()
 for p in bundle['packs']:
  pid=p.get('pack_id')
  if pid in pack_ids:report['duplicates'].append({'kind':'pack_id repeated','ids':[pid]})
  pack_ids.add(pid);cand=cands.get(p.get('candidate_id'))
  chk=check_pack(p,cand);h=digest(p);old=c.execute('SELECT version,content_hash,status FROM corpus_packs WHERE pack_id=?',(pid,)).fetchone()
  state='existing' if old and old['content_hash']==h else 'changed' if old else 'new'
  if not cand:chk['structure'].append('找不到对应的候选材料 '+str(p.get('candidate_id')))
  elif cand.get('level')!=p.get('level'):chk['structure'].append('练习包等级与候选材料不同')
  for q in chk['questions']:
   for e in q['errors']:
    if '依据' in e:report['evidence_mismatch'].append({'pack':pid,'question':q['id'],'issue':e})
  report['packs'].append({'id':pid,'candidate':p.get('candidate_id'),'title':p.get('title'),'level':p.get('level'),'state':state,**chk})
 report['counts']={'candidates':len(merged),'levels':dict(sorted(levels.items())),'themes':themes,'skills':skills,'packs':len(bundle['packs']),'theme_from_sources':sum(r['theme_from']=='sources.csv' for r in merged),'theme_in_candidates':sum(r['theme_from']=='candidate' for r in merged),
  'vocabulary':len(report['vocabulary']),'vocab_reuse':sum(v['decision']=='reuse' for v in report['vocabulary']),'vocab_new_sense':sum(v['decision']=='new_sense' for v in report['vocabulary']),'vocab_new':sum(v['decision']=='new' for v in report['vocabulary']),
  'teaching_lexicon_published':c.execute("SELECT COUNT(*) FROM lexicon WHERE owner IS NULL AND status='published'").fetchone()[0],'bad_jsonl_lines':bundle['bad_lines']}
 claimed=re.search(r'\*\*A2\*\*：(\d+)篇.*?\*\*B1\*\*：(\d+)篇.*?\*\*B2\*\*：(\d+)篇',bundle['notes'],re.S)
 if claimed:
  said={'A2':int(claimed.group(1)),'B1':int(claimed.group(2)),'B2':int(claimed.group(3))}
  if said!={k:levels.get(k,0) for k in said}:report['notes_vs_data'].append({'item':'等级分布','review_notes':said,'data':{k:levels.get(k,0) for k in said}})
 said_skills={k:int(n) for k,n in re.findall(r'\((Listening|Reading|Writing|Speaking)\)：(\d+)篇',bundle['notes'])}
 if said_skills:
  data_skills={k:skills.get(k.lower(),0) for k in said_skills}
  if said_skills!=data_skills:report['notes_vs_data'].append({'item':'技能分布','review_notes':said_skills,'data':data_skills})
 types={}
 for rec in merged:types[rec['candidate'].get('content_type')]=types.get(rec['candidate'].get('content_type'),0)+1
 report['counts']['content_types']=types
 said_types={k:int(n) for k,n in re.findall(r'(根据来源改写|根据来源事实原创|完全原创情境练习)：(\d+)篇',bundle['notes'])}
 if said_types:
  alias={'根据来源改写':'根据来源改写的教学材料','根据来源事实原创':'根据来源事实原创编写的教学材料','完全原创情境练习':'完全原创的情境练习'}
  data_types={k:types.get(alias[k],0) for k in said_types}
  if said_types!=data_types:report['notes_vs_data'].append({'item':'内容类型','review_notes':said_types,'data':data_types})
 for rec in merged:
  title=(rec['source'].get('source_title') or '');url=(rec['source'].get('source_url') or '')
  for org,domain in (('Bureau of Labor Statistics','bls.gov'),('TSA','tsa.gov'),('EPA','epa.gov'),('NHS','nhs.uk'),('MIT','mit.edu'),('W3C','w3.org'),('OpenStax','openstax.org'),('Purdue','purdue.edu'),('Apache','apache.org'),('Wikipedia','wikipedia.org'),('Leeds','leeds.ac.uk'),('British Council','britishcouncil.org')):
   if org in title and domain not in url and not any(d in url for o,d in (('USA.gov','usa.gov'),) if o in title):
    report['duplicates'].append({'kind':'source title and link point to different organisations','ids':[rec['candidate'].get('candidate_id')],'url':url+' ← '+title[:60]})
 if bundle['notes'].count('100%正交去重') and any(d['kind'].startswith('same source_url') for d in report['duplicates']):report['notes_vs_data'].append({'item':'去重说明','review_notes':'声称 20 篇 100% 正交去重','data':'有候选共用同一个来源链接，需核对来源是否真的支撑各自正文'})
 return report

def record(rec):
 cand=rec['candidate']
 return {'candidate':cand,'source':rec['source'],'theme_label':rec['theme_label'],'theme_from':rec['theme_from'],'flow_theme':rec['flow_theme'],'theme_basis':rec['theme_basis'],'packs':rec['packs']}

# ---------- apply (idempotent) ----------
def apply(c,bundle,actor='cli'):
 report=preflight(c,bundle);merged,_,_=merge(bundle);now=time.time();written={'candidates':0,'packs':0,'versions':0,'sense_links':0}
 c.execute('BEGIN IMMEDIATE')
 try:
  for rec in merged:
   cid=rec['candidate'].get('candidate_id');data=record(rec);h=digest(data);review=review_items(rec)
   old=c.execute('SELECT version,content_hash FROM corpus_candidates WHERE candidate_id=?',(cid,)).fetchone()
   if old and old['content_hash']==h:continue
   v=(old['version']+1) if old else 1
   if old:c.execute("UPDATE corpus_candidates SET version=?,content_hash=?,level=?,theme=?,status='candidate',data=?,review=?,batch=?,updated=? WHERE candidate_id=?",(v,h,rec['candidate'].get('level'),rec['flow_theme'],json.dumps(data,ensure_ascii=False),json.dumps(review,ensure_ascii=False),bundle['batch'],now,cid))
   else:c.execute('INSERT INTO corpus_candidates VALUES(?,?,?,?,?,?,?,?,?,?,?)',(cid,v,h,rec['candidate'].get('level'),rec['flow_theme'],'candidate',json.dumps(data,ensure_ascii=False),json.dumps(review,ensure_ascii=False),bundle['batch'],now,now))
   c.execute('INSERT INTO corpus_versions(kind,ref,version,content_hash,data,batch,created) VALUES(?,?,?,?,?,?,?)',('candidate',cid,v,h,json.dumps(data,ensure_ascii=False),bundle['batch'],now));written['candidates']+=1;written['versions']+=1
   for w in rec['candidate'].get('vocabulary',[]):
    m=match_word(c,w)
    c.execute('INSERT INTO corpus_sense_links VALUES(?,?,?,?,?,?,?,?,?) ON CONFLICT(candidate_id,word,pos,meaning) DO UPDATE SET decision=excluded.decision,lexicon=excluded.lexicon,reference=excluded.reference,version=excluded.version',(cid,m['word'],m['pos'],m['meaning'],m['decision'],m['lexicon'],(m['reference'] or {}).get('id'),'proposed',v));written['sense_links']+=1
  cands={r['candidate'].get('candidate_id'):r['candidate'] for r in merged}
  for p in bundle['packs']:
   pid=p.get('pack_id');h=digest(p);chk=check_pack(p,cands.get(p.get('candidate_id')))
   old=c.execute('SELECT version,content_hash FROM corpus_packs WHERE pack_id=?',(pid,)).fetchone()
   if old and old['content_hash']==h:continue
   v=(old['version']+1) if old else 1
   # A changed pack goes back to 'candidate': a pilot or approval applies to one version only.
   if old:c.execute("UPDATE corpus_packs SET version=?,content_hash=?,status='candidate',data=?,structure=?,batch=?,updated=? WHERE pack_id=?",(v,h,json.dumps(p,ensure_ascii=False),json.dumps(chk,ensure_ascii=False),bundle['batch'],now,pid))
   else:c.execute('INSERT INTO corpus_packs VALUES(?,?,?,?,?,?,?,?,?,?)',(pid,p.get('candidate_id'),v,h,'candidate',json.dumps(p,ensure_ascii=False),json.dumps(chk,ensure_ascii=False),bundle['batch'],now,now))
   c.execute('INSERT INTO corpus_versions(kind,ref,version,content_hash,data,batch,created) VALUES(?,?,?,?,?,?,?)',('pack',pid,v,h,json.dumps(p,ensure_ascii=False),bundle['batch'],now));written['packs']+=1;written['versions']+=1
  c.execute('INSERT INTO corpus_import_runs(batch,mode,summary,actor,created) VALUES(?,?,?,?,?)',(bundle['batch'],'apply',json.dumps({'written':written,'counts':report['counts']},ensure_ascii=False),actor,now))
  c.commit()
 except Exception:
  c.rollback();raise
 return {'written':written,'report':report}

# ---------- review status ----------
STATUSES=('candidate','pilot','approved','rejected')
def set_pack_status(c,pack_id,status,actor,note):
 if status not in STATUSES:raise ValueError('状态不正确')
 if not isinstance(note,str) or len(note.strip())<5:raise ValueError('请写明原因（至少 5 个字）')
 row=c.execute('SELECT version FROM corpus_packs WHERE pack_id=?',(pack_id,)).fetchone()
 if not row:raise ValueError('练习包不存在')
 if status=='approved':raise ValueError('公开发布需要教师逐项审核来源、使用条件、语言与答案；本版本只支持候选与试点')
 c.execute('UPDATE corpus_packs SET status=?,updated=? WHERE pack_id=?',(status,time.time(),pack_id))
 c.execute('INSERT INTO corpus_reviews(kind,ref,version,item,decision,note,actor,created) VALUES(?,?,?,?,?,?,?,?)',('pack',pack_id,row['version'],'status',status,note.strip(),actor,time.time()));c.commit()

# ---------- report rendering ----------
def markdown(report,written=None):
 r=report;L=[];a=L.append;cnt=r['counts']
 a('# 语料预检报告');a('');a(f"- 批次：`{r['batch']}`（四个文件内容的 sha256 合成）；生成时间：{r['generated']}")
 for n,f in r['files'].items():a(f"- `{n}`：{f['bytes']} 字节，sha256 `{f['sha256'][:16]}…`")
 if written:a(f"- 本次写入：候选 {written['candidates']} 条，练习包 {written['packs']} 个，版本记录 {written['versions']} 条，义项关联 {written['sense_links']} 条")
 a('');a('## 数量（按数据文件重算）');a('')
 a(f"- 候选材料 {cnt['candidates']} 篇：" + '，'.join(f'{k} {v} 篇' for k,v in cnt['levels'].items()))
 a(f"- 主题：候选文件自带 {cnt['theme_in_candidates']} 条，从 sources.csv 补齐 {cnt['theme_from_sources']} 条；" + '，'.join(f'{k} {v}' for k,v in cnt['themes'].items()))
 a('- 技能：'+'，'.join(f'{k} {v}' for k,v in cnt['skills'].items()))
 a(f"- 练习包 {cnt['packs']} 个；词条 {cnt['vocabulary']} 个（复用已有义项 {cnt['vocab_reuse']}，同形异义 {cnt['vocab_new_sense']}，新词 {cnt['vocab_new']}）")
 a(f"- 教学词库覆盖只计正式发布词条：当前 {cnt['teaching_lexicon_published']} 个；本批词条都是待审核提议，不计入")
 for d in r['notes_vs_data']:a(f"- **与备忘录不一致**：{d['item']}：备忘录 {d['review_notes']}，数据 {d['data']}")
 a('');a('## 新增 / 已存在 / 有变化');a('')
 a(f"- 新增 {len(r['new'])}：" + ('、'.join(x['id'] for x in r['new']) or '无'))
 a(f"- 已存在且相同 {len(r['existing'])}：" + ('、'.join(x['id'] for x in r['existing']) or '无'))
 a(f"- 已存在但内容变化（将生成新版本）{len(r['changed'])}：" + ('、'.join(x['id'] for x in r['changed']) or '无'))
 a('');a('## 重复');a('')
 for d in r['duplicates'] or [{'kind':'无','ids':[]}]:a(f"- {d['kind']}：{'、'.join(d['ids'])}"+(f"（{d.get('url') or d.get('family')}）" if d.get('url') or d.get('family') else ''))
 a('');a('## 缺字段');a('')
 for m in r['missing_fields'] or [{'id':'无','fields':[]}]:a(f"- {m['id']}：{'、'.join(m['fields'])}")
 a('');a('## 依据不匹配');a('')
 for e in r['evidence_mismatch'] or [{'pack':'无','question':'','issue':''}]:a(f"- {e['pack']} {e['question']}：{e['issue']}")
 a('');a('## 练习包结构检查');a('')
 a('| 练习包 | 候选 | 等级 | 状态 | 结构问题 | 题目错误 | 题目提醒 |');a('|---|---|---|---|---|---|---|')
 for p in r['packs']:a(f"| {p['id']} | {p['candidate']} | {p['level']} | {p['state']} | {'；'.join(p['structure']) or '—'} | {p['errors']} | {p['warnings']} |")
 for p in r['packs']:
  a('');a(f"### {p['id']} 逐题");a('')
  for q in p['questions']:a(f"- `{q['id']}`（{q['role']}）："+('；'.join(['错误：'+e for e in q['errors']]+['提醒：'+w for w in q['warnings']]) or '通过'))
 a('');a('## 待人工审核（每条候选）');a('');a('来源可访问、AI 已改写、允许公开使用是三个独立的审核项。公开发布前由审核人员逐项确认。');a('')
 a('| 候选 | 等级 | Flow 主题 | 来源可访问 | 允许公开使用 | 条款文字不同 | 其他 |');a('|---|---|---|---|---|---|---|')
 for x in r['review']:
  it={i['item']:i for i in x['items']}
  a(f"| {x['id']} | {x['level']} | {x['theme']}（{x['theme_from']}） | {it['source_access']['auto']} | {it['public_use']['auto']}：{it['public_use']['evidence']} | {'是' if 'usage_terms_mismatch' in it else '否'} | {'、'.join(i['label'] for i in x['items'] if i['item'] not in ('source_access','public_use','usage_terms_mismatch'))} |")
 a('');a('## 词条：词形 + 词性 + 语境义项');a('')
 a('| 候选 | 词 | 词性 | 语境义项 | 判断 | 说明 |');a('|---|---|---|---|---|---|')
 for v in r['vocabulary']:a(f"| {v['candidate']} | {v['word']} | {v['pos']} | {v['meaning']} | {v['decision']} | {v['note']} |")
 return '\n'.join(L)+'\n'

def main(argv):
 import argparse,os
 ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('preflight','apply'));ap.add_argument('folder');ap.add_argument('--json');ap.add_argument('--md');ap.add_argument('--actor',default='cli')
 a=ap.parse_args(argv)
 import app
 app.init()
 with app.db() as c:
  bundle=load(a.folder)
  if a.mode=='preflight':rep=preflight(c,bundle);written=None
  else:out=apply(c,bundle,a.actor);rep=out['report'];written=out['written']
 if a.json:Path(a.json).write_text(json.dumps({'report':rep,'written':written},ensure_ascii=False,indent=1),encoding='utf-8')
 if a.md:Path(a.md).write_text(markdown(rep,written),encoding='utf-8')
 print(json.dumps({'batch':rep['batch'],'counts':rep['counts'],'new':len(rep['new']),'existing':len(rep['existing']),'changed':len(rep['changed']),'written':written},ensure_ascii=False))

if __name__=='__main__':main(sys.argv[1:])
