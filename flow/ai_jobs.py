"""FIFO request coordination and renewable, fenced database attempts."""
import threading,time,secrets,sqlite3
from collections import deque
from contextlib import contextmanager
import ai_stream

TTL=120
QUEUE_SECONDS=180
CONDITION=threading.Condition()
QUEUES={}

def enter(uid,timeout=QUEUE_SECONDS,cancelled=lambda:False):
    ticket=object();deadline=time.monotonic()+timeout
    with CONDITION:
        queue=QUEUES.setdefault(uid,deque());queue.append(ticket)
        try:
            while queue[0] is not ticket:
                if cancelled():raise ConnectionAbortedError('Queued browser disconnected')
                ai_stream.emit({'type':'status','message':'已排队，前面的 AI 任务完成后会自动开始；可以继续练习。','position':list(queue).index(ticket)})
                remaining=deadline-time.monotonic()
                if remaining<=0:raise TimeoutError('AI queue timeout')
                CONDITION.wait(min(5,remaining))
            if cancelled():raise ConnectionAbortedError('Queued browser disconnected')
            ai_stream.emit({'type':'status','message':'正在结合当前学习内容组织回复。','position':0})
            return uid,ticket
        except BaseException:
            queue.remove(ticket)
            if not queue:QUEUES.pop(uid,None)
            CONDITION.notify_all();raise

def leave(handle):
    if not handle:return
    uid,ticket=handle
    with CONDITION:
        queue=QUEUES.get(uid)
        if queue and ticket in queue:queue.remove(ticket)
        if not queue:QUEUES.pop(uid,None)
        CONDITION.notify_all()

def schema(c,table):
    if table not in ('lab_jobs','chat_turns'):raise ValueError('Unknown job table')
    if 'lease' not in {r[1] for r in c.execute('PRAGMA table_info('+table+')')}:
        c.execute('ALTER TABLE '+table+" ADD COLUMN lease TEXT NOT NULL DEFAULT ''")

def reserve(c,table,uid,rid):
    lease=secrets.token_hex(16)
    c.execute('UPDATE '+table+' SET lease=? WHERE user_id=? AND request_id=?',(lease,uid,rid))
    return lease

def recover_interrupted(c):
    """Called once before the single application server accepts requests."""
    for table in ('lab_jobs','chat_turns'):
        c.execute('UPDATE '+table+" SET status='failed',lease=?,error=?,updated=? WHERE status='pending'",(secrets.token_hex(16),'服务重启中断了本次处理，草稿仍保留，请重试同一次请求。',time.time()))
    c.execute("UPDATE coach_turns SET status='failed' WHERE status='pending'")
    c.commit()

@contextmanager
def renewing(c,table,uid,rid,lease,interval=5):
    filename=c.execute('PRAGMA database_list').fetchone()[2];stop=threading.Event()
    def refresh():
        while not stop.wait(interval):
            try:
                with sqlite3.connect(filename,timeout=2) as other:
                    other.execute('UPDATE '+table+" SET updated=? WHERE user_id=? AND request_id=? AND lease=? AND status='pending'",(time.time(),uid,rid,lease))
            except sqlite3.Error:pass
    thread=threading.Thread(target=refresh,daemon=True) if filename else None
    if thread:thread.start()
    try:yield
    finally:
        stop.set()
        if thread:thread.join(timeout=3)
