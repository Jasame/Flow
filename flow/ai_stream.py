"""Request-local real model deltas; previews never count as validated learning evidence."""
import json, threading, time
from contextlib import contextmanager

LOCAL = threading.local()
PATHS = {'/api/ai/help', '/api/chat', '/api/coach/chat', '/api/lab/feedback', '/api/lab/audio',
         '/api/lab/generate', '/api/vocab/feedback', '/api/vocab/explain', '/api/vocab/generate', '/api/reference/generate', '/api/manage/generate'}

def events(response):
    """Bounded SSE parser, handles CRLF, multiline data, comments and Unicode."""
    lines=[]; size=0
    for raw in response:
        if len(raw)>262144: raise ValueError('Oversized stream frame')
        line=raw.decode('utf-8').rstrip('\r\n')
        if not line:
            if lines: yield '\n'.join(lines)
            lines=[];size=0
        elif line.startswith('data:'):
            value=line[5:].lstrip(' ');size+=len(value)
            if size>262144: raise ValueError('Oversized stream frame')
            lines.append(value)
    if lines: yield '\n'.join(lines)

@contextmanager
def observe(callback,structured=True):
    old=getattr(LOCAL,'callback',None); prior=getattr(LOCAL,'structured',True)
    LOCAL.callback=callback;LOCAL.structured=structured
    try: yield
    finally: LOCAL.callback=old;LOCAL.structured=prior

def active(): return bool(getattr(LOCAL,'callback',None))
def emit(event):
    callback=getattr(LOCAL,'callback',None)
    if callback: callback(event)

def preview(raw, structured=True):
    if not structured:return raw
    source=raw.strip()
    if source.startswith('```'):source=source[source.find('\n')+1:]
    output=[]
    labels={'reply':'','strength':'做得好的地方','next_question':'下一小步','meaning':'本句词义','explanation':'语境讲解','example':'例句','translation':'中文理解','title':'待审核标题','body':'待审核语料'}
    def visible(path,value):
        label=None
        if len(path)==1 and path[0] in labels:label=labels[path[0]]
        elif len(path)==3 and path[0]=='priorities' and isinstance(path[1],int) and path[2] in ('issue','evidence','suggestion'):
            label=str(path[1]+1)+'. '+{'issue':'修改重点','evidence':'原句依据','suggestion':'如何修改'}[path[2]]
        elif len(path)==3 and path[0]=='items' and isinstance(path[1],int) and path[2] in ('word','meaning','example'):
            label='待审核词条 '+str(path[1]+1)
        if label is not None and value:output.append((label+'\n' if label else '')+value)
    def string(i):
        start=i;i+=1;escaped=False
        while i<len(source):
            if not escaped and source[i]=='"':
                try:return json.loads(source[start:i+1]),i+1,True
                except ValueError:return '',i+1,False
            if not escaped and source[i]=='\\':escaped=True
            else:escaped=False
            i+=1
        token=source[start:]
        for cut in range(min(7,len(token))):
            try:return json.loads((token if cut==0 else token[:-cut])+'"'),i,False
            except ValueError:pass
        return '',i,False
    def skip(i):
        while i<len(source) and source[i].isspace():i+=1
        return i
    def value(i,path,depth=0):
        i=skip(i)
        if i>=len(source) or depth>16:return len(source)
        if source[i]=='"':
            text,end,complete=string(i);visible(path,text);return end
        if source[i]=='{':
            i=skip(i+1)
            while i<len(source) and source[i]=='"':
                key,i,complete=string(i)
                if not complete:return len(source)
                i=skip(i)
                if i>=len(source) or source[i]!=':':return len(source)
                i=skip(value(i+1,path+(key,),depth+1))
                if i<len(source) and source[i]==',':i=skip(i+1)
                else:break
            return i+1 if i<len(source) and source[i]=='}' else len(source)
        if source[i]=='[':
            i=skip(i+1);index=0
            while i<len(source) and source[i]!=']':
                i=skip(value(i,path+(index,),depth+1));index+=1
                if i<len(source) and source[i]==',':i=skip(i+1)
                else:break
            return i+1 if i<len(source) and source[i]==']' else len(source)
        while i<len(source) and source[i] not in ',}]':i+=1
        return i
    value(0,())
    return '\n\n'.join(output)

class Transport:
    def __init__(self,handler,path):
        self.handler=handler;self.path=path;self.lock=threading.Lock();self.closed=False
        self.stop=threading.Event();self.start=time.monotonic()
        handler.send_response(200);handler.headers_common('text/event-stream; charset=utf-8')
        handler.send_header('Cache-Control','no-store');handler.send_header('X-Accel-Buffering','no')
        handler.send_header('Connection','close');handler.end_headers();handler.close_connection=True
        self.write({'type':'status','message':'已收到，正在连接 AI；可以继续编辑或练习。'})
        threading.Thread(target=self.heartbeat,daemon=True).start()
    def write(self,event):
        with self.lock:
            if self.closed:return
            try:
                self.handler.wfile.write(('data: '+json.dumps(event,ensure_ascii=False)+'\n\n').encode());self.handler.wfile.flush()
            except (OSError,ValueError):self.closed=True
    def heartbeat(self):
        while not self.stop.wait(5):
            self.write({'type':'heartbeat','elapsed':round(time.monotonic()-self.start)})
    def finish(self,obj,status):
        self.stop.set();self.write({'type':'result','status':status,'data':obj})
