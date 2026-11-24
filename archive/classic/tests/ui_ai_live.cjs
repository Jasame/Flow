const fs=require('fs'),vm=require('vm'),assert=require('assert');
const root={innerHTML:'',addEventListener(){}},doc={querySelector:s=>s==='#app'?root:s==='#toast'?{textContent:'',style:{}}:null,addEventListener(){}};
const ctx=vm.createContext({toast:()=>{},document:doc,window:{addEventListener(){}},AbortController,TextDecoder,TextEncoder,setTimeout,clearTimeout,console,Map,Set,Date,RegExp});
vm.runInContext(fs.readFileSync(__dirname+'/../public/app.js','utf8'),ctx);
vm.runInContext(fs.readFileSync(__dirname+'/../public/ai-live.js','utf8'),ctx);
ctx.updates=[];vm.runInContext("user={id:1,csrf:'csrf'};view='home';flowLiveRender=s=>updates.push({text:s.text,busy:s.busy,error:s.error});",ctx);
const encoder=new TextEncoder();
function body(chunks){let i=0;return {getReader:()=>({read:async()=>i<chunks.length?{value:chunks[i++],done:false}:{done:true},releaseLock(){}})}}
const frame=e=>'data: '+JSON.stringify(e)+'\n\n';
(async()=>{
 const source=encoder.encode(': ping\n\n'+frame({type:'preview',text:'你好 🌍'})+frame({type:'heartbeat',elapsed:5}));
 const pieces=Array.from(source,x=>new Uint8Array([x]));ctx.body=body(pieces);ctx.events=[];await vm.runInContext('consumeFlowEvents(body,e=>events.push(e))',ctx);assert.equal(ctx.events[0].text,'你好 🌍');assert.equal(ctx.events.length,2);
 let release,reads=0,calls=0;ctx.fetch=async()=>{calls++;return {headers:{get:()=> 'text/event-stream'},body:{getReader:()=>({async read(){if(reads++===0)return {value:encoder.encode(frame({type:'preview',text:'先练一句'})),done:false};if(reads===2){await new Promise(r=>release=r);return {value:encoder.encode(frame({type:'result',status:200,data:{reply:'先练一句 Hello.'}})),done:false}}return {done:true}},releaseLock(){}})}}};
 const pending=vm.runInContext("api('coach/chat',{request_id:'same-request-001',message:'Help'})",ctx);
 await new Promise(r=>setImmediate(r));assert(ctx.updates.some(s=>s.busy&&s.text==='先练一句'));assert.equal(calls,1);release();assert.equal((await pending).reply,'先练一句 Hello.');assert.equal(ctx.updates.at(-1).busy,false);
 ctx.fetch=async()=>({headers:{get:()=> 'text/event-stream'},body:body([encoder.encode(frame({type:'preview',text:'未确认的回复'}))])});await assert.rejects(()=>vm.runInContext("api('lab/feedback',{request_id:'same-request-002'})",ctx),/中断/);assert.equal(ctx.updates.at(-1).text,'未确认的回复');
 ctx.fetch=async()=>({headers:{get:()=> 'text/event-stream'},body:body([encoder.encode(frame({type:'result',status:429,data:{error:'配额暂时不足'}}))])});await assert.rejects(()=>vm.runInContext("api('vocab/feedback',{request_id:'same-request-003'})",ctx),e=>e.status===429&&e.message==='配额暂时不足');

 // A terminal result is sufficient: the network need not send EOF.
 ctx.fetch=async()=>({headers:{get:()=> 'text/event-stream'},body:{getReader:()=>({read:async()=>({value:encoder.encode(frame({type:'result',status:200,data:{reply:'无需等待关闭'}})),done:false}),releaseLock(){},cancel:async()=>{}})}});
 assert.equal((await vm.runInContext("api('ai/help',{request_id:'terminal-no-eof-01'})",ctx)).reply,'无需等待关闭');
 // Two requests retain distinct task states; an active task keeps its panel selection.
 let resolveFirst,firstReads=0;ctx.fetch=async(url)=>url.endsWith('coach/chat')?{headers:{get:()=> 'text/event-stream'},body:{getReader:()=>({async read(){if(firstReads++===0)return {value:encoder.encode(frame({type:'preview',text:'第一项独立片段'})),done:false};await new Promise(r=>resolveFirst=r);return {value:encoder.encode(frame({type:'result',status:200,data:{reply:'第一项完成'}})),done:false}},releaseLock(){},cancel:async()=>{}})}}:{headers:{get:()=> 'text/event-stream'},body:body([encoder.encode(frame({type:'result',status:200,data:{result:{reply:'第二项完成'}}}))])};
 const first=vm.runInContext("api('coach/chat',{request_id:'parallel-first-01',message:'first'})",ctx);await new Promise(r=>setImmediate(r));
 const second=await vm.runInContext("api('ai/help',{request_id:'parallel-second-01'})",ctx);assert.equal(second.result.reply,'第二项完成');assert.equal(vm.runInContext('flowLive.data.request_id',ctx),'parallel-first-01');resolveFirst();await first;
 assert.equal(vm.runInContext("flowAITasks.get('parallel-second-01').text",ctx),'第二项完成');
 const ai=fs.readFileSync(__dirname+'/../public/ai-live.js','utf8');assert(ai.includes('node.textContent=s.text'));assert(!ai.includes('node.innerHTML=s.text'));assert(ai.includes('user?.id!==s.owner'));assert(ai.includes('s.originView===view'));
 console.log('AI live: fragmented UTF-8, genuine incremental arrival before final, shared API routing, no duplicate calls, EOF rejection, preview invalidation, quota errors and safe text rendering: passed');
})().catch(e=>{console.error(e);process.exit(1)});
