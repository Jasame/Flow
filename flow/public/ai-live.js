'use strict';
// Genuine server deltas. No typewriter timers, automatic retries or extra model calls.
const flowAIPaths=new Set(['ai/help','chat','coach/chat','lab/feedback','lab/audio','lab/generate','vocab/feedback','vocab/explain','vocab/generate','reference/generate','manage/generate']);
let flowLive=null;
const flowAITasks=new Map();
function flowAIReset(){for(const s of flowAITasks.values())s.controller?.abort();flowAITasks.clear();flowLive=null;document.querySelector('#flow-ai-live')?.remove()}
function flowLiveRender(s){
 if(user?.id!==s.owner)return;
 s=flowLive;if(!s||user?.id!==s.owner)return;
 let panel=document.querySelector('#flow-ai-live');
 if(!panel){panel=document.createElement('aside');panel.id='flow-ai-live';panel.className='ai-live';panel.setAttribute('aria-label','随堂 AI 回复');panel.innerHTML='<div class="ai-live-bar"><strong>随堂 AI</strong><span class="ai-live-status" role="status" aria-live="polite"></span><button type="button" data-ai-collapse aria-expanded="true">收起</button><button type="button" data-ai-close aria-label="关闭回复面板">×</button></div><div class="ai-live-body"><label>AI 任务<select class="ai-task-select" aria-label="切换 AI 任务"></select></label><p class="ai-live-note"></p><div class="ai-live-text" tabindex="0" aria-label="AI 回复内容"></div><button type="button" data-ai-retry hidden>重试本次请求</button><button type="button" data-ai-status>查看连接状态</button></div>';document.body.appendChild(panel)}
 panel.classList.toggle('is-collapsed',!!s.collapsed);
 const toggle=panel.querySelector('[data-ai-collapse]');toggle.textContent=s.collapsed?'展开':'收起';toggle.setAttribute('aria-expanded',String(!s.collapsed));
 panel.querySelector('[data-ai-close]').hidden=s.busy;
 const chooser=panel.querySelector('.ai-task-select');
 if(chooser&&document.activeElement!==chooser){chooser.replaceChildren();for(const [key,t] of flowAITasks){const option=document.createElement('option');option.value=key;option.textContent=(t.label||'')+' · '+(t.path==='coach/chat'?'私教':t.path==='ai/help'?'随堂提示':t.path.includes('generate')?'内容生成':'学习反馈')+' · '+(t.queued?'排队中':t.busy?'处理中':t.error?'未完成':'已完成');option.selected=t===s;chooser.appendChild(option)}}
 const status=s.busy?(s.queued?'排队中':s.text?'正在回复':'正在连接'):s.error?'未完成':'已完成';
 if(panel.querySelector('.ai-live-status').textContent!==status)panel.querySelector('.ai-live-status').textContent=status;
 panel.querySelector('.ai-live-note').textContent=s.error?(s.error+' 已生成片段尚未完成校验，不计入学习成果。'):s.note;
 const node=panel.querySelector('.ai-live-text'),nearEnd=node.scrollHeight-node.scrollTop-node.clientHeight<45;
 node.textContent=s.text|| (s.busy?'回复会逐步出现在这里。可收起面板继续练习。':'');
 if(nearEnd)node.scrollTop=node.scrollHeight;
 panel.querySelector('[data-ai-retry]').hidden=!s.error;panel.querySelector('.ai-live-bar strong').textContent='随堂 AI · '+flowAITasks.size+'项';
 // Update the current conversation in place without rerendering the input/draft.
 if(s.busy&&s.originView===view&&s.text&&((s.path==='coach/chat'&&typeof coachRetry!=='undefined'&&coachRetry===s.data.request_id)||(s.path==='chat'&&typeof activeTopic!=='undefined'&&activeTopic===s.data.topic))){
  const inline=s.path==='coach/chat'?document.querySelector('.mentor-live-preview'):s.path==='chat'?document.querySelector('.chat-assistant.pending .thinking'):null;
  if(inline){inline.textContent='AI 正在回复（尚未校验）\n'+s.text;inline.classList.add('preserve-lines')}
 }
}
async function consumeFlowEvents(body,onEvent){
 if(!body?.getReader)throw Error('浏览器不支持实时回复，请更新浏览器。');
 const reader=body.getReader(),decoder=new TextDecoder();let buffer='';
 const drain=()=>{let at;while((at=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,at);buffer=buffer.slice(at+2);const data=frame.split('\n').filter(x=>x.startsWith('data:')).map(x=>x.slice(5).trimStart()).join('\n');if(data&&onEvent(JSON.parse(data))===true)return true}};
 try{while(true){const {value,done}=await reader.read();buffer+=done?decoder.decode():decoder.decode(value,{stream:true});buffer=buffer.replace(/\r\n/g,'\n');if(buffer.length>262144)throw Error('实时回复数据过大');if(drain()){Promise.resolve(reader.cancel?.()).catch(()=>{});return}if(done)break}if(buffer.trim())throw Error('实时连接意外中断')}finally{reader.releaseLock()}
}
async function flowAIRequest(path,data){
 const s={owner:user.id,path,data,originView:view,label:String(data.message||(typeof studioPack!=='undefined'&&studioPack?.id===(data.pack||data.target)?studioPack.title:'')||(typeof flowWord!=='undefined'&&flowWord?.id===(data.entry||data.target)?flowWord.word:'')||'学习任务').slice(0,18),busy:true,text:'',note:'连接后逐步显示。临时回复经校验后才会保存。',controller:new AbortController(),queued:false,collapsed:['chat','coach/chat'].includes(path),error:''};const taskKey=data.request_id||flowRequestId();if(flowAITasks.get(taskKey)?.busy)throw Error('同一请求正在处理中，请查看任务状态。');flowAITasks.set(taskKey,s);if(!flowLive?.busy)flowLive=s;for(const [key,t] of flowAITasks){if(flowAITasks.size<=10)break;if(!t.busy&&t!==flowLive)flowAITasks.delete(key)}flowLiveRender(s);
 let idle;const reset=()=>{clearTimeout(idle);idle=setTimeout(()=>s.controller.abort(),35000)};reset();const total=setTimeout(()=>s.controller.abort(),390000);
 let final=null;
 try{
  const r=await fetch('/api/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':user.csrf,Accept:'text/event-stream'},body:JSON.stringify(data),signal:s.controller.signal});reset();
  if(r.headers.get('Content-Type')?.includes('text/event-stream'))await consumeFlowEvents(r.body,e=>{reset();if(e.type==='result'){if(final)throw Error('重复的完成事件');final=e;return true}else if(!final&&e.type==='status'){s.queued=!!e.position;s.note=e.message||s.note;flowLiveRender(s)}else if(!final&&e.type==='preview'){s.queued=false;s.text=e.text||'';s.note=s.text?'正在生成，尚未校验。英文示范会在完成后按需展开。':`已接收 ${e.characters||0} 个字符，正在核对结构。`;flowLiveRender(s)}else if(!final&&e.type==='heartbeat'){s.note=s.queued?`仍在排队，可继续练习。已等待 ${e.elapsed} 秒。`:`已等待 ${e.elapsed} 秒。可收起面板继续练习，完成后在这里查看。`;flowLiveRender(s)}});
  else final={status:r.status,data:await r.json()};
  if(user?.id!==s.owner)throw Error('账号已切换，本次回复不会显示在当前账号。');
  if(!final)throw Error('回复连接中断，尚未确认完成。请重试同一次请求。');
  if(final.status>=400){const error=Error(final.data?.error||'AI 暂时无法回复');error.status=final.status;error.payload=final.data;if(final.status===401){if(typeof flowStash==='function')flowStash();clearAccountState();user=null;auth()}throw error}
  const result=final.data.result||final.data;
  s.text=result.reply||[result.strength,...(result.priorities||[]).map((p,i)=>(i+1)+'. '+p.issue+'\n原句：'+p.evidence+'\n建议：'+p.suggestion),result.explanation,result.meaning,result.next_question].filter(Boolean).join('\n\n')||s.text||'任务已完成，请在原页面或任务记录查看。';s.note=result.mode==='lesson'?'当前为内置讲解，未调用AI模型。':path.includes('generate')?'生成内容格式已校验，语义与难度仍需核对。':'回复结构已校验；教学判断仍需结合原意核对，不等于已掌握。';
  return final.data;
 }catch(e){s.note='未完成片段，仅供核对，不计入学习成果。';s.error=e.name==='AbortError'?'连接超时，草稿仍保留。可重试同一次请求，或先继续内置练习。':e.message;throw Object.assign(Error(s.error),{status:e.status,payload:e.payload})}
 finally{clearTimeout(idle);clearTimeout(total);s.busy=false;s.queued=false;flowLiveRender(s);if(flowLive!==s&&user?.id===s.owner)toast(s.error?'有一项 AI 任务未完成，可展开任务面板重试。':'有一项 AI 任务已完成，可在任务列表切换查看。')}
}
function flowContextHelp(){
 const main=document.querySelector('.page-content');if(!main||!user)return;
 let target=null;
 if(view==='studio'&&typeof studioPack!=='undefined'&&studioPack)target={kind:'material',target:studioPack.id,skill:studioSkill};
 else if(view==='vocab'&&typeof flowWord!=='undefined'&&flowWord)target={kind:'word',target:flowWord.id};
 if(!target)return;
 const box=document.createElement('section');box.className='ai-context-help';box.setAttribute('aria-label','随堂 AI 帮助');
 const label=document.createElement('span');label.textContent='卡住了？';box.appendChild(label);
 const question=document.createElement('input');question.type='text';question.maxLength=500;question.placeholder='具体哪里不懂？也可先选中原文片段';question.setAttribute('aria-label','想问随堂 AI 的具体问题');const ask=document.createElement('details');const askTitle=document.createElement('summary');askTitle.textContent='补充具体问题或选中片段';ask.append(askTitle,question);box.appendChild(ask);
 for(const [mode,title] of [['hint','给一点提示'],['explain','解释一个难点'],['example','换个例句']]){const b=document.createElement('button');b.type='button';b.className='text-button';b.textContent=title;b.addEventListener('click',()=>{const answer=target.kind==='material'?studioState(target.target,studioSkill).answer:draftFor(target.target).answer;let selected=window.getSelection?.()?.toString().trim().slice(0,600)||'';if(target.kind==='material'&&!studioPack.body.includes(selected))selected='';api('ai/help',{...target,mode,question:question.value,answer,selected,request_id:flowRequestId()}).catch(e=>toast(e.message))});box.appendChild(b)}
 if(target.kind==='material'){
  const levelBox=document.createElement('details');const note=document.createElement('summary');note.textContent='这篇难度合适吗？';levelBox.appendChild(note);const info=document.createElement('small');info.textContent=studioPack.calibration?.status||'教学建议分级，真实样本持续积累中';levelBox.appendChild(info);box.appendChild(levelBox);
  for(const [rating,title] of [['easy','偏简单'],['right','难度合适'],['hard','偏难']]){const vote=document.createElement('button');vote.type='button';vote.className='text-button';vote.textContent=title;vote.addEventListener('click',()=>api('lab/difficulty',{pack:target.target,rating}).then(d=>toast(d.message)).catch(e=>toast(e.message)));levelBox.appendChild(vote)}
 }
 main.prepend(box);
}
document.addEventListener('click',e=>{
 if(!flowLive)return;
 if(e.target.closest('[data-ai-status]'))api('ai/status').then(d=>toast(d.message)).catch(err=>toast(err.message));
 if(e.target.closest('[data-ai-collapse]')){flowLive.collapsed=!flowLive.collapsed;flowLiveRender(flowLive)}
 if(e.target.closest('[data-ai-close]')&&!flowLive.busy){document.querySelector('#flow-ai-live')?.remove();flowLive=null}
 if(e.target.closest('[data-ai-retry]')&&!flowLive.busy){const {path,data,owner}=flowLive;api(path,data).then(out=>{if(user?.id===owner)flowApplyAIRetry(path,data,out);toast('本次请求已完成。')}).catch(err=>toast(err.message))}
});
document.addEventListener('focusin',e=>{if(flowLive?.busy&&!e.target.closest('#flow-ai-live')&&e.target.matches('textarea,input,[contenteditable=true]')){flowLive.collapsed=true;flowLiveRender(flowLive)}});

document.addEventListener('change',e=>{if(e.target.matches('.ai-task-select')){const s=flowAITasks.get(e.target.value);if(s&&s.owner===user?.id){flowLive=s;flowLiveRender(s)}}});
function flowApplyAIRetry(path,data,out){
 if(path==='coach/chat'&&view==='home'&&typeof coachLoad==='function'){coachLoad();return}
 if(path==='chat'&&typeof loadChat==='function'){loadChat(data.topic);return}
 if(['lab/feedback','lab/audio'].includes(path)&&typeof studioState==='function'){
  const state=studioState(data.pack,data.skill);
  if(!data.audio&&state.answer.trim()!==data.answer)return;
  if(data.audio&&state.answer!==out.result?.transcript)return;
  state.feedback=out.result;state.feedbackRequest=out.request_id;state.error='';
  if(view==='studio'&&studioPack?.id===data.pack&&studioSkill===data.skill)renderStudioPack();
 }
 if(path==='vocab/feedback'&&typeof flowWord!=='undefined'&&flowWord?.id===data.entry&&draftFor(data.entry).answer.trim()===data.answer){flowWord.feedback=out.result;renderFlowWord()}
 if(path==='vocab/explain'&&typeof flowWord!=='undefined'&&flowWord?.id===data.entry){flowWord.contextExplanation=out.result;renderFlowWord()}
}
