#!/usr/bin/env python3
"""Live deployment probe. No database writes; never prints keys or upstream bodies."""
import argparse,base64,json,os,time,urllib.error
from pathlib import Path
import ai_stream
from chat_service import request_model

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',default='/etc/flow.env')
    parser.add_argument('--grounding',action='store_true')
    parser.add_argument('--audio',help='Optional short English recording (wav, webm, mp3, ogg, m4a)')
    parser.add_argument('--output',help='Optional JSON report path (no credentials)')
    parser.add_argument('--configuration-only',action='store_true')
    args=parser.parse_args()
    from studio_setup import read_env
    if Path(args.env_file).is_file():
        for key,value in read_env(Path(args.env_file).read_text()).items():
            if key.startswith(('FLOW_','GOOGLE_')):os.environ[key]=value
    report={'configuration':{key:bool(os.getenv(key)) for key in ('FLOW_AI_URL','FLOW_AI_KEY','FLOW_AI_MODEL','GOOGLE_CLOUD_PROJECT')},'checks':[]}
    def run(name,operation):
        print('正在实测：'+name,flush=True);start=time.monotonic()
        try:
            details=operation();item={'name':name,'ok':True,'seconds':round(time.monotonic()-start,3),**details}
        except Exception as exc:
            item={'name':name,'ok':False,'seconds':round(time.monotonic()-start,3),'error_type':type(exc).__name__}
            if isinstance(exc,urllib.error.HTTPError):item['http_status']=exc.code
        report['checks'].append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    def text_check():
        text,reason=request_model([{'role':'user','content':'Give one short English greeting for a beginner.'}])
        if reason!='stop' or not text.strip():raise ValueError('Incomplete answer')
        return {'characters':len(text)}
    def stream_check():
        times=[]
        def delta(event):
            if event.get('type')=='preview' and event.get('text'):times.append(time.monotonic())
        start=time.monotonic()
        with ai_stream.observe(delta,structured=False):
            text,reason=request_model([{'role':'user','content':'Explain in five short sentences how to practice English every day.'}])
        if reason!='stop' or not times:raise ValueError('No visible stream')
        return {'first_text_seconds':round(times[0]-start,3),'visible_events':len(times),'characters':len(text),'stream_span_seconds':round(times[-1]-times[0],3)}
    def structured_check():
        from lab_service import parse,validate_feedback
        raw,reason=request_model([{'role':'user','content':'As an English tutor, give feedback on "I like apples.". Return only JSON with strength (Chinese), priorities (empty array if correct), revision (English), next_question (English).'}])
        if reason!='stop':raise ValueError('Truncated JSON')
        validate_feedback(parse(raw));return {'validated':True}
    if not args.configuration_only:
        run('普通文字调用',text_check);run('真实流式输出',stream_check);run('学习反馈结构校验',structured_check)
        if args.grounding:
            def grounding():
                text,reason,metadata=request_model([{'role':'user','content':'Find a recent English-language science news story for learners, and state its date and source.'}],grounding=True)
                if reason!='stop' or not metadata.get('groundingChunks'):raise ValueError('No grounded sources')
                return {'source_count':len(metadata['groundingChunks'])}
            run('联网热点检索',grounding)
        if args.audio:
            def audio():
                path=Path(args.audio);mimes={'.wav':'audio/wav','.webm':'audio/webm','.mp3':'audio/mpeg','.ogg':'audio/ogg','.m4a':'audio/mp4'}
                if path.stat().st_size>1500000:raise ValueError('Recording too large')
                payload={'mime_type':mimes[path.suffix.lower()],'data':base64.b64encode(path.read_bytes()).decode()}
                raw,reason=request_model([{'role':'user','content':'Transcribe only the English you hear. Mark unclear audio explicitly. Do not invent speech.'}],audio=payload)
                if reason!='stop' or not raw.strip():raise ValueError('No audio response')
                return {'characters':len(raw),'requires_manual_transcript_check':True}
            run('录音分析传输',audio)
    report['ok']=bool(report['checks']) and all(x['ok'] for x in report['checks'])
    report['not_tested']=[name for name,enabled in [('联网检索',args.grounding),('真实录音',args.audio)] if not enabled]
    if args.output:Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return 0 if report['ok'] or args.configuration_only else 1
if __name__=='__main__':raise SystemExit(main())
