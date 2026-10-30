"""Persistent tutor conversations, bounded context and idempotent chat requests."""
import json,os,re,secrets,time,urllib.request,urllib.error,socket
import ai_stream
import ai_jobs
from content_v05 import PRACTICES
from vertex_auth import ai_enabled,vertex_enabled,vertex_connection
PENDING_TTL=120

def schema(c):
 c.executescript('''CREATE TABLE IF NOT EXISTS chat_turns(
 id INTEGER PRIMARY KEY,user_id INTEGER NOT NULL REFERENCES users(id),topic TEXT NOT NULL REFERENCES topics(id),
 request_id TEXT NOT NULL,message TEXT NOT NULL,reply TEXT NOT NULL DEFAULT '',status TEXT NOT NULL,
 finish_reason TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',created REAL NOT NULL,updated REAL NOT NULL,
 UNIQUE(user_id,request_id));
 CREATE INDEX IF NOT EXISTS chat_user_topic ON chat_turns(user_id,topic,id);''')
 ai_jobs.schema(c,'chat_turns')

def remaining(c,uid):
 return None  # No per-learner daily ceiling. Usage is still audited.

def history(c,uid,topic):
 if not c.execute('SELECT 1 FROM topics WHERE id=?',(topic,)).fetchone():return {'error':'知识点不存在'},404
 rows=c.execute('SELECT request_id,message,reply,status,finish_reason,error,created,updated FROM chat_turns WHERE user_id=? AND topic=? ORDER BY id DESC LIMIT 20',(uid,topic)).fetchall()
 out=[dict(r) for r in reversed(rows)]
 for row in out:
  if row['status']=='pending' and row['updated']<time.time()-PENDING_TTL:
   row.update(status='failed',error='上次请求未完成，可以重试。')
 return {'items':out,'remaining':remaining(c,uid),'enabled':ai_enabled(),'reset_timezone':'UTC'},200

def context(c,uid,topic,question):
 rows=c.execute("SELECT message,reply FROM chat_turns WHERE user_id=? AND topic=? AND status='complete' ORDER BY id DESC LIMIT 4",(uid,topic['id'])).fetchall()
 pairs=[];size=0
 # Recent exchanges take priority and are kept in chronological order.
 for row in rows:
  q=row['message'];a=row['reply']
  budget=4200-size-len(q)
  if budget<150:break
  if len(a)>budget:a='[较早内容省略] '+a[-max(1,budget-20):]
  pairs.append((q,a));size+=len(q)+len(a)
 system=('你是 Flow 英语学习导师。用简洁、完整的中文讲解，适当保留英文例句，优先用短段落和列表。'
         '先回答用户的具体问题，一次讲清一到三个要点，通常控制在400字内；不确定时明确说明。'
         '支持追问，结合之前的对话；仅讨论英语学习。教学参考：'+topic['title']+'；'+topic['lesson']+'；'+topic['example'])
 task=next((t for t in PRACTICES if question.startswith('【训练任务:'+t['id']+'】')),None)
 if task:system+='。当前训练要求：'+task['prompt']+'。反馈标准：先指出具体优点，再给最多三条修改建议与一句示范；不提供考试分数或发音评价。'
 messages=[{'role':'system','content':system}]
 for q,a in reversed(pairs):messages.extend([{'role':'user','content':q},{'role':'assistant','content':a}])
 messages.append({'role':'user','content':question})
 return messages

def request_model(messages,audio=None,grounding=False):
 endpoint=os.getenv('FLOW_AI_URL','');key=os.getenv('FLOW_AI_KEY','');model=os.getenv('FLOW_AI_MODEL','')
 from vertex_auth import AIConfigurationError
 if vertex_enabled():
  try:endpoint,key=vertex_connection()
  except (ValueError,ImportError) as exc:raise AIConfigurationError('Vertex configuration incomplete') from exc
  if audio or grounding:
   from vertex_native import request_native
   return request_native(messages,model,key,audio,grounding)
 if not endpoint.startswith('https://') or not model or not key:raise AIConfigurationError('AI configuration incomplete')
 payload={'model':model,'messages':messages,'max_tokens':4096}
 if ai_stream.active():payload['stream']=True
 if grounding:payload['flow_grounding']=True
 if audio:
  from audio_validation import validate_audio
  validate_audio(audio);payload['flow_audio']=audio
 req=urllib.request.Request(endpoint,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
 with urllib.request.urlopen(req,timeout=85) as r:
  if ai_stream.active():
   if 'text/event-stream' not in r.headers.get('Content-Type',''):raise AIConfigurationError('Gateway streaming upgrade required')
   reply='';reason=None;metadata={};started=time.monotonic()
   for frame in ai_stream.events(r):
    if time.monotonic()-started>100:raise TimeoutError('AI stream deadline exceeded')
    if frame=='[DONE]':break
    chunk=json.loads(frame)
    if chunk.get('error'):
     status=chunk.get('status',502)
     raise urllib.error.HTTPError(endpoint,status if type(status)==int and status in (400,401,403,413,429,502,503,504) else 502,'Model stream failed',None,None)
    choices=chunk.get('choices',[])
    if chunk.get('flow_grounding'):metadata=chunk['flow_grounding']
    if not choices:continue
    choice=choices[0];delta=choice.get('delta',{}).get('content','')
    if delta:
     if not isinstance(delta,str):raise ValueError('Invalid model delta')
     reply+=delta
     if len(reply)>20000:raise ValueError('Model response too long')
     ai_stream.emit({'type':'preview','text':ai_stream.preview(reply,getattr(ai_stream.LOCAL,'structured',True)),'characters':len(reply)})
    if choice.get('finish_reason') is not None:
     reason=choice['finish_reason'];break
   if not reason or reason not in ('stop','length','max_tokens','content_filter') or not reply.strip():raise ValueError('Incomplete model stream')
   if reason!='stop':raise ValueError('Model stream not complete')
   return (reply,reason,metadata) if grounding else (reply,reason)
  d=json.load(r)
 choice=d['choices'][0];reply=choice['message']['content'];reason=choice.get('finish_reason','stop')
 if not isinstance(reply,str) or not reply.strip():raise ValueError('Empty model reply')
 if grounding:return reply[:20000],reason,d.get('flow_grounding',{})
 return reply[:20000],('length' if len(reply)>20000 else reason)

def result(row,quota):
 return {'reply':row['reply'],'request_id':row['request_id'],'finish_reason':row['finish_reason'],'truncated':row['finish_reason'] in ('length','max_tokens'),'remaining':quota,'mode':'ai' if row['finish_reason']!='lesson' else 'lesson'}

def chat(c,uid,data):
 question=data.get('message','');topic_id=data.get('topic','');rid=data.get('request_id') or secrets.token_hex(16)
 if not isinstance(question,str) or not 1<=len(question.strip())<=1000 or not isinstance(rid,str) or not re.fullmatch(r'[a-zA-Z0-9_-]{12,80}',rid):return {'error':'问题需为1–1000字，请求标识不正确。'},400
 question=question.strip();topic=c.execute('SELECT * FROM topics WHERE id=?',(topic_id,)).fetchone()
 if not topic:return {'error':'知识点不存在'},400
 c.execute('BEGIN IMMEDIATE')
 row=c.execute('SELECT * FROM chat_turns WHERE user_id=? AND request_id=?',(uid,rid)).fetchone()
 if row:
  if row['topic']!=topic_id or row['message']!=question:c.rollback();return {'error':'请求标识已被使用，请重新提问。'},409
  if row['status']=='complete':c.rollback();return result(row,remaining(c,uid)),200
  if row['status']=='pending' and row['updated']>time.time()-PENDING_TTL:c.rollback();return {'error':'导师还在回答，请稍候。'},409
 if c.execute("SELECT 1 FROM lab_jobs WHERE user_id=? AND status='pending' AND updated>?",(uid,time.time()-PENDING_TTL)).fetchone():
  c.rollback();return {'error':'已有训练请求正在处理，请稍候。'},409
 if c.execute("SELECT 1 FROM chat_turns WHERE user_id=? AND status='pending' AND updated>? AND request_id!=?",(uid,time.time()-PENDING_TTL,rid)).fetchone():
  c.rollback();return {'error':'已有提问正在处理，请稍候再试。'},409
 enabled=ai_enabled()
 if enabled:
  day=time.strftime('%Y-%m-%d',time.gmtime());c.execute('INSERT OR IGNORE INTO ai_usage VALUES(?,?,0)',(uid,day))
  total=c.execute('SELECT COALESCE(SUM(count),0) FROM ai_usage WHERE day=?',(day,)).fetchone()[0]
  if int(os.getenv('FLOW_AI_DAILY_LIMIT','0'))>0 and total>=int(os.getenv('FLOW_AI_DAILY_LIMIT','0')):c.rollback();return {'error':'本站今日 AI 调用额度已用完，请明天再来。'},429
  c.execute('UPDATE ai_usage SET count=count+1 WHERE user_id=? AND day=?',(uid,day))
 now=time.time()
 if row:c.execute("UPDATE chat_turns SET status='pending',error='',updated=? WHERE id=?",(now,row['id']))
 else:c.execute("INSERT INTO chat_turns(user_id,topic,request_id,message,status,created,updated) VALUES(?,?,?,?,'pending',?,?)",(uid,topic_id,rid,question,now,now))
 lease=ai_jobs.reserve(c,'chat_turns',uid,rid);c.commit()
 try:
  if enabled:
   with ai_jobs.renewing(c,'chat_turns',uid,rid,lease):reply,reason=request_model(context(c,uid,topic,question))
  else:reply='当前未接入 AI。以下是本知识点的固定学习提示：\n\n'+topic['lesson']+'\n\n**例句**\n'+topic['example']+'\n\n'+topic['explanation'];reason='lesson'
  changed=c.execute("UPDATE chat_turns SET reply=?,finish_reason=?,status='complete',error='',updated=? WHERE user_id=? AND request_id=? AND lease=?",(reply,reason,time.time(),uid,rid,lease)).rowcount;c.commit()
  if not changed:return {'error':'旧请求已被新请求接替，请刷新记录。'},409
  row=c.execute('SELECT * FROM chat_turns WHERE user_id=? AND request_id=?',(uid,rid)).fetchone()
  return result(row,remaining(c,uid)),200
 except Exception as exc:
  error='AI 暂时无法回答，请稍后重试。';status=502
  if isinstance(exc,__import__('vertex_auth').AIConfigurationError):status=503;error='AI 配置不完整或网关不支持实时输出，请管理员检查，草稿仍保留。'
  elif isinstance(exc,urllib.error.HTTPError):
   error={401:'网关认证失败，请管理员检查连接配置。',403:'访问权限受限，请管理员检查网关白名单。',429:'模型或网关配额不足，请稍后再试。',504:'模型回答超时，请重试。'}.get(exc.code,error)
  elif isinstance(exc,(TimeoutError,socket.timeout)):error='导师回答超时，你的问题已保留，可以重试。';status=504
  c.execute("UPDATE chat_turns SET status='failed',error=?,updated=? WHERE user_id=? AND request_id=? AND lease=?",(error,time.time(),uid,rid,lease));c.commit()
  return {'error':error,'request_id':rid,'remaining':remaining(c,uid)},status
