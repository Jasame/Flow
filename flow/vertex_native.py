"""Vertex ADC native multimodal transport for the same validated audio contract."""
import json,os,urllib.request,time
import ai_stream
from audio_validation import validate_audio

def request_native(messages,model,token,audio=None,grounding=False):
    project=os.environ['GOOGLE_CLOUD_PROJECT'];location=os.getenv('GOOGLE_CLOUD_LOCATION','global')
    host='aiplatform.googleapis.com' if location=='global' else location+'-aiplatform.googleapis.com'
    method='streamGenerateContent?alt=sse' if ai_stream.active() else 'generateContent'
    url=f'https://{host}/v1/projects/{project}/locations/{location}/publishers/google/models/{model.removeprefix("google/")}:{method}'
    system=[];contents=[]
    for message in messages:
        if message['role']=='system':system.append({'text':message['content']})
        else:contents.append({'role':'model' if message['role']=='assistant' else 'user','parts':[{'text':message['content']}]})
    payload={'contents':contents,'generationConfig':{'maxOutputTokens':4096}}
    if system:payload['systemInstruction']={'parts':system}
    if audio:
        validate_audio(audio)
        next(m for m in reversed(contents) if m['role']=='user')['parts'].append({'inlineData':{'mimeType':audio['mime_type'],'data':audio['data']}})
    if grounding:payload['tools']=[{'googleSearch':{}}]
    req=urllib.request.Request(url,data=json.dumps(payload,ensure_ascii=False).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    reply='';finish=None;metadata={};start=time.monotonic()
    with urllib.request.urlopen(req,timeout=85) as response:
        if ai_stream.active() and 'text/event-stream' not in response.headers.get('Content-Type',''):
            from vertex_auth import AIConfigurationError
            raise AIConfigurationError('Vertex did not return SSE')
        chunks=(json.loads(frame) for frame in ai_stream.events(response)) if ai_stream.active() else [json.load(response)]
        for chunk in chunks:
            if time.monotonic()-start>100:raise TimeoutError('Vertex deadline')
            candidate=(chunk.get('candidates') or [{}])[0]
            reply+=''.join(p['text'] for p in candidate.get('content',{}).get('parts',[]) if p.get('text') and not p.get('thought'))
            finish=candidate.get('finishReason',finish);metadata=candidate.get('groundingMetadata',metadata)
            if len(reply)>20000:raise ValueError('Vertex output too long')
            ai_stream.emit({'type':'preview','text':ai_stream.preview(reply,getattr(ai_stream.LOCAL,'structured',True)),'characters':len(reply)})
            if finish:break
    if finish!='STOP' or not reply.strip():raise ValueError('Incomplete Vertex output')
    return (reply,'stop',metadata) if grounding else (reply,'stop')
