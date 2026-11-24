// 3.9.0 · Listening pilot (FLOW-PACK-001). Only shown to admins and enrolled pilot members.
// The server owns every step and never sends an answer before the item is submitted.
viewTitles.pilot='听力试点';
let pilotView=null,pilotEpoch=0,pilotSlow=false,pilotAudio=null,pilotHints={},pilotFeedback={},pilotNext=null;
const PILOT_SUPPORT={none:'独立作答',hint:'用了提示',answer_seen:'看过答案',guided:'引导练习'};
const PILOT_STEPS=[['initial','起始题'],['intro','找原因'],['check','短检查'],['teach','讲解与补练'],['verify','新通知验证'],['done','完成']];
function pilotCurrent(owner,epoch){return user?.id===owner&&epoch===pilotEpoch&&view==='pilot'}
function pilotPlayer(url,item){if(!url)return '';return `<div class="pilot-audio"><button class="btn secondary" data-pilot-play="${esc(url)}" data-pilot-item="${esc(item)}">▶ 播放</button><button class="text-button" data-pilot-slow="1" aria-pressed="${pilotSlow}">${pilotSlow?'正常速度':'慢一点（0.8 倍）'}</button><span class="small muted">合成语音</span></div>`}
function pilotOptions(q,fb){return `<div class="pilot-options" role="group" aria-label="选项">${q.options.map(o=>{const picked=fb&&fb.selected===o.key,right=fb&&fb.correct_key===o.key;return `<button class="pilot-option ${picked?'picked':''} ${fb?(right?'right':picked?'wrong':''):''}" data-pilot-answer="${esc(q.id)}" data-key="${esc(o.key)}" ${fb?'disabled':''}><b>${esc(o.key)}</b><span lang="en">${esc(o.text)}</span></button>`}).join('')}</div>`}
function pilotFeedbackHTML(fb){if(!fb)return '';if(fb.skipped)return '<p class="pilot-fb muted">已跳过。</p>';
 const label=fb.correct?'✓ 答对了':'○ 没答对';const sup=fb.support&&fb.support!=='none'?` · ${PILOT_SUPPORT[fb.support]||fb.support}`:'';
 return `<div class="pilot-fb ${fb.correct?'ok':'no'}"><strong>${label}${sup}</strong>${fb.correct_text&&!fb.correct?`<p>正确答案：<span lang="en">${esc(fb.correct_key)}. ${esc(fb.correct_text)}</span></p>`:''}${fb.distractor?`<p>${esc(fb.distractor.text)}</p>`:''}${fb.explanation?`<p>${esc(fb.explanation)}</p>`:''}${fb.transcript?`<details><summary>看原文</summary><p lang="en" class="pilot-script">${esc(fb.transcript)}</p></details>`:''}${fb.correct_slots?`<p>${Object.entries(fb.correct_slots).map(([a,t])=>`<span lang="en">${esc(a)}</span>：${esc(t)}`).join('；')}</p>`:''}</div>`}
function pilotHintHTML(q){const got=pilotHints[q.id]||[];return `${got.map((t,i)=>`<p class="pilot-hint">提示 ${i+1}：${esc(t)}</p>`).join('')}${q.hint_levels&&got.length<q.hint_levels&&!pilotFeedback[q.id]?`<button class="text-button" data-pilot-hint="${esc(q.id)}">${got.length?'再给一点提示':'给我一点提示'}</button>`:''}`}
function pilotItem(q,{skip=false}={}){const fb=pilotFeedback[q.id]||pilotView.answered?.[q.id];return `<article class="pilot-item" id="pilot-${esc(q.id)}"><p class="pilot-q">${esc(q.prompt_zh)}</p>${q.prompt?`<p class="small muted" lang="en">${esc(q.prompt)}</p>`:''}${pilotPlayer(q.audio,q.id)}${q.role==='card'?pilotCard(q,fb):pilotOptions(q,fb)}<div class="pilot-tools">${pilotHintHTML(q)}${skip&&!fb?`<button class="text-button" data-pilot-skip="${esc(q.id)}">跳过这题</button>`:''}</div>${pilotFeedbackHTML(fb)}</article>`}
function pilotCard(q,fb){const chosen=fb?JSON.parse(fb.selected||'{}'):{};return `<div class="pilot-card">${q.slots.map(a=>`<label><span lang="en">${esc(a)}</span><select data-pilot-slot="${esc(a)}" ${fb?'disabled':''}><option value="">选择时间</option>${q.choices.map(t=>`<option ${chosen[a]===t?'selected':''}>${esc(t)}</option>`).join('')}</select></label>`).join('')}${fb?'':`<button class="btn" data-pilot-card="${esc(q.id)}">填好了</button>`}</div>`}
function pilotSteps(step){const order=PILOT_STEPS.map(s=>s[0]);const at=step==='uncertain'?2:step==='practice'?3:order.indexOf(step);return `<ol class="pilot-steps">${PILOT_STEPS.map(([k,t],i)=>`<li class="${i<at?'done':i===at?'now':''}">${t}</li>`).join('')}</ol>`}
function pilotBody(v){const s=v.step;
 if(s==='initial')return pilotItem(v.item);
 if(s==='intro'){const i=v.intro;return `<section class="pilot-panel"><h2>先看这道题在考什么</h2><p>${esc(i.tests)}</p>${i.choice_note?`<p class="pilot-choice">${esc(i.choice_note)}</p>`:''}<h3>可能是这两个原因之一</h3><ul class="pilot-reasons">${i.reasons.map(r=>`<li><strong>${esc(r.label)}</strong><span>${esc(r.text)}</span></li>`).join('')}</ul><p class="small muted">${esc(i.why_check)} ${esc(i.cause_note)}</p><div class="actions"><button class="btn" data-pilot-action="check">做两道短检查 →</button><button class="btn secondary" data-pilot-action="explain">直接看讲解</button></div></section>`}
 if(s==='check')return `<section class="pilot-panel"><h2>短检查 · 第 ${v.set} 组</h2><p class="small muted">每题只查一件事。不确定可以跳过；用了提示或跳过，就先不下结论。</p>${v.items.map(q=>pilotItem(q,{skip:true})).join('')}</section>`;
 if(s==='uncertain')return `<section class="pilot-panel"><h2>暂时无法确定原因</h2><p>${esc(v.decision.text)}</p><div class="actions">${v.can_retry?'<button class="btn" data-pilot-action="retry">再试一次（换两道新短题）</button>':''}<button class="btn ${v.can_retry?'secondary':''}" data-pilot-action="explain">直接看讲解</button></div></section>`;
 if(s==='teach'||s==='practice'){const b=v.branch;const head=`<section class="pilot-panel pilot-branch"><span class="tag">${esc(b.name)}</span><h2>为什么推荐这项</h2><p>${esc(v.decision?.text||b.why)}</p><h3>${esc(b.action)}</h3><ul>${b.points.map(p=>`<li>${esc(p)}</li>`).join('')}</ul></section>`;
  if(s==='practice')return head+`<section class="pilot-panel"><h2>再练一题</h2>${pilotItem(v.item)}</section>`;
  if(v.drill)return head+`<section class="pilot-panel"><h2>跟着听：重音在哪里</h2>${v.drill.map(q=>pilotItem(q)).join('')}</section>`;
  if(v.card)return head+`<section class="pilot-panel"><h2>一项活动一张卡片</h2>${pilotItem(v.card)}</section>`;
  return head+`<div class="actions"><button class="btn" data-pilot-action="continue">去做新通知验证 →</button></div>`}
 if(s==='verify')return `<section class="pilot-panel"><h2>新通知验证</h2><p class="small muted">${esc(v.note)}${v.seen_before?' 你以前做过这道验证题，这次记为“看过答案”。':''}</p>${pilotItem(v.item)}</section>`;
 if(s==='done'){const m=v.summary||{};return `<section class="pilot-panel pilot-done"><h2>${m.correct?'新通知也听对了':'这次新通知还没听对'}</h2><p>${esc(m.label||'')}</p><p class="small muted">${esc(m.purpose||'')}</p><div class="actions">${v.status==='complete'?'<button class="btn" data-view="home">回到今日学习</button><button class="btn secondary" data-view="report">在学习档案查看</button>':'<button class="btn" data-pilot-finish="1">完成本次听力 ✓</button>'}</div></section>`}
 return ''}
function pilotRender(v){pilotView=v;const continueBtn=pilotNext?`<div class="pilot-next"><button class="btn" data-pilot-continue="1">继续 →</button></div>`:'';shell(pagehead(esc(v.title),`${esc(v.level)} · 听力 · 试点材料`)+`<div class="pilot">${pilotSteps(v.step)}${pilotBody(v)}${continueBtn}<p class="small muted pilot-note">${esc(v.status_note)} ${esc(v.audio_note)}</p></div>`)}
async function flowPilot(){view='pilot';const owner=user.id,epoch=++pilotEpoch;pilotNext=null;pilotFeedback={};const l=await api('pilot/list');if(!pilotCurrent(owner,epoch))return;
 const p=l.pilots[0];if(!p)return shell(pagehead('听力试点','')+'<section class="card empty"><h2>这个试点没有对你开放</h2><p>试点材料还在审核，只对管理员和试点成员开放。</p><button class="btn secondary" data-view="studio">回到语料库</button></section>');
 if(p.active_run){const v=await api('pilot/run?id='+p.active_run);if(pilotCurrent(owner,epoch))pilotRender(v);return}
 shell(pagehead('听力试点','')+`<section class="card pilot-start"><span class="tag">试点 · ${esc(p.level)} · 听力</span><h2>${esc(p.title)}</h2><p>先听一则校园通知答一道题。答错了，会先帮你找原因，再针对原因练一小段，最后用一则新通知检查。${esc(p.minutes)}。</p><p class="small muted">${esc(p.status_note)} ${esc(p.audio_note)}</p><button class="btn" data-pilot-start="${esc(p.id)}">开始 →</button></section>`)}
function pilotHeard(){try{pilotAudio?.pause()}catch{}}
async function pilotPost(path,data){const r=await api('pilot/'+path,data);return r}
app.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b||b.disabled||!user)return;const d=b.dataset;
 if(!('pilotStart' in d||'pilotPlay' in d||'pilotSlow' in d||'pilotAnswer' in d||'pilotHint' in d||'pilotSkip' in d||'pilotAction' in d||'pilotCard' in d||'pilotFinish' in d||'pilotContinue' in d||'pilotOpen' in d))return;
 try{
  if(d.pilotOpen!==undefined)return navigate('pilot');
  if(d.pilotStart){b.disabled=true;pilotHints={};pilotFeedback={};return pilotRender(await pilotPost('start',{pilot:d.pilotStart}))}
  if(d.pilotSlow){pilotSlow=!pilotSlow;if(pilotAudio)pilotAudio.playbackRate=pilotSlow?.8:1;document.querySelectorAll('[data-pilot-slow]').forEach(x=>{x.setAttribute('aria-pressed',String(pilotSlow));x.textContent=pilotSlow?'正常速度':'慢一点（0.8 倍）'});return}
  if(d.pilotPlay){pilotHeard();pilotAudio=new Audio(d.pilotPlay);pilotAudio.preservesPitch=true;pilotAudio.playbackRate=pilotSlow?.8:1;b.textContent='▶ 正在播放';pilotAudio.onended=()=>{b.textContent='▶ 再听一遍'};pilotAudio.onerror=()=>{b.textContent='▶ 播放';toast('音频加载失败，请重试')};await pilotAudio.play().catch(()=>{});pilotPost('play',{run:pilotView.run,item:d.pilotItem,rate:pilotSlow?.8:1}).catch(()=>{});return}
  if(d.pilotHint){b.disabled=true;const r=await pilotPost('hint',{run:pilotView.run,item:d.pilotHint});(pilotHints[d.pilotHint]=pilotHints[d.pilotHint]||[])[r.level-1]=r.text;toast(r.note);return pilotRender(pilotView)}
  if(d.pilotAnswer||d.pilotSkip||d.pilotCard){const item=d.pilotAnswer||d.pilotSkip||d.pilotCard;let body={run:pilotView.run,item};
   if(d.pilotAnswer)body.choice=d.key;else if(d.pilotSkip)body.skip=true;else{const choice={};for(const s of document.querySelectorAll(`#pilot-${CSS.escape(item)} [data-pilot-slot]`)){if(!s.value)return toast('请为每项活动选一个时间');choice[s.dataset.pilotSlot]=s.value}body.choice=choice}
   document.querySelectorAll(`#pilot-${CSS.escape(item)} button`).forEach(x=>x.disabled=true);pilotHeard();
   const r=await pilotPost('answer',body);pilotFeedback[item]=r.feedback;
   // Stay on this screen to read the feedback when the step changed; otherwise keep answering here.
   if(r.view.step!==pilotView.step){pilotNext=r.view;pilotView.answered={...(pilotView.answered||{}),[item]:r.feedback};pilotRender(pilotView)}else pilotRender(r.view);
   document.getElementById('pilot-'+item)?.scrollIntoView({block:'nearest'});return}
  if(d.pilotContinue){const v=pilotNext;pilotNext=null;pilotRender(v);window.scrollTo(0,0);return}
  if(d.pilotAction){b.disabled=true;pilotNext=null;pilotRender(await pilotPost('action',{run:pilotView.run,action:d.pilotAction}));window.scrollTo(0,0);return}
  if(d.pilotFinish){b.disabled=true;await pilotPost('finish',{run:pilotView.run});toast('已完成本次听力，记录已保存到学习档案');pilotRender(await api('pilot/run?id='+pilotView.run));return}
 }catch(err){b.disabled=false;toast(err.message)}});
function pilotTraceHTML(t){const yes=x=>x==null?'—':x.skipped?'跳过':x.correct?'对':'错';const sup=x=>x&&x.support&&x.support!=='none'?'（'+(PILOT_SUPPORT[x.support]||x.support)+(x.hint_level?' · 提示 '+x.hint_level+' 级':'')+'）':'';
 return `<article class="pilot-trace"><header><strong>${esc(t.title)}</strong><span class="small muted">${new Date(t.started*1000).toLocaleString('zh-CN',{dateStyle:'short',timeStyle:'short'})} · ${t.status==='complete'?'已完成':'进行中'} · 来源 ${esc(t.source_pack)}</span></header><ol>
 ${t.initial?`<li><b>起始题</b> ${esc(t.initial.item)}（原题 ${esc(t.initial.origin)}）：选 ${esc(t.initial.selected)}，${yes(t.initial)}${t.initial.cause?'；所选干扰项对应“'+({time:'时间没听清',binding:'时间配错活动',deadline:'把截止时间当活动时间'}[t.initial.cause]||t.initial.cause)+'”':''}</li>`:''}
 ${t.checks.map(c=>`<li><b>短检查第 ${c.set} 组</b>：${c.items.map(x=>`${esc(x.item)} ${yes(x)}${sup(x)}`).join('，')} → ${c.branch?'推荐 '+esc({time:'时间听辨',binding:'活动与时间对应'}[c.branch]):'暂时无法确定'}：${esc(c.text)}</li>`).join('')}
 ${t.branch?`<li><b>补练</b>：${esc(t.branch.name)}${t.checks.some(c=>c.branch)?'':'（'+esc(t.branch.why||'')+'）'}</li>`:''}
 ${t.teaching.filter(Boolean).length?`<li><b>引导练习</b>：${t.teaching.filter(Boolean).map(x=>`${esc(x.item)} ${yes(x)}`).join('，')}</li>`:''}
 ${t.practice?`<li><b>补练题</b> ${esc(t.practice.item)}：${yes(t.practice)}</li>`:''}
 ${t.verification?`<li><b>新通知验证</b> ${esc(t.verification.item)}（${esc(t.verification.context)}）：${yes(t.verification)}${sup(t.verification)} · ${esc(t.summary?.label||'')}</li>`:'<li><b>新通知验证</b>：还没做</li>'}
 ${t.hints.length?`<li><b>提示</b>：${t.hints.map(h=>esc(h.item)+' 第 '+h.level+' 级').join('，')}</li>`:''}</ol></article>`}
const pilotBaseReport=learningReport;
learningReport=async function(){await pilotBaseReport();if(view!=='report'||!user)return;const owner=user.id;let h;try{h=await api('pilot/history')}catch{return}if(user?.id!==owner||view!=='report'||!h.runs.length)return;
 const main=document.querySelector('#main-content')||document.querySelector('main');if(!main||main.querySelector('.pilot-history'))return;
 main.insertAdjacentHTML('beforeend',`<section class="card pilot-history"><h2>听力试点记录</h2><p class="small muted">${esc(h.note)}</p>${h.runs.map(pilotTraceHTML).join('')}</section>`)};
const pilotBaseStudio=studio;
studio=async function(){await pilotBaseStudio();if(view!=='studio'||!user)return;const owner=user.id;let l;try{l=await api('pilot/list')}catch{return}if(user?.id!==owner||view!=='studio'||!l.pilots.length)return;
 const head=document.querySelector('.library-heading')||document.querySelector('.pagehead');if(!head||document.querySelector('.pilot-entry'))return;const p=l.pilots[0];
 head.insertAdjacentHTML('afterend',`<section class="card pilot-entry"><div><span class="tag">试点 · ${esc(p.level)} · 听力</span><h2>${esc(p.title)}</h2><p class="small muted">${esc(p.status_note)}</p></div><button class="btn" data-pilot-open="1">${p.active_run?'继续':'开始'} →</button></section>`)};

// ---- listnav (source: listnav.js) ----
'use strict';
// Flow 3.9.1 · list position, shareable list addresses and the Back button for the corpus library.
// Loads after every other script and wraps a few globals (navigate, studio, openStudioPack, updateCorpus, renderStudioCatalog).
(()=>{
 if(typeof navigate!=='function'||typeof openStudioPack!=='function')return;

 // Land on a list after paging: the heading sits just under the sticky top bar, and the "page N / M" status gets focus.
 window.flowListLanded=function(target,status){
  const el=typeof target==='string'?document.querySelector(target):target;if(!el)return;
  const bar=document.querySelector('.topbar');const off=(bar&&getComputedStyle(bar).position!=='static'?bar.getBoundingClientRect().height:0)+12;
  const root=document.documentElement,prev=root.style.scrollBehavior;root.style.scrollBehavior='auto';
  window.scrollTo(0,Math.max(0,el.getBoundingClientRect().top+window.scrollY-off));root.style.scrollBehavior=prev;
  const s=status&&document.querySelector(status);if(s){s.setAttribute('tabindex','-1');s.focus({preventScroll:true})}
 };

 // #studio?q=&level=&theme=&genre=&scope=&sort=&page= mirrors the corpus filters (replaceState, so no extra history entries).
 const KEYS=['query','level','theme','genre','scope','sort','page'],SHORT={query:'q'};
 const DEF={query:'',level:'',theme:'',genre:'',scope:'all',sort:'recommended',page:1};
 const OK={level:v=>['A2','B1','B2'].includes(v),theme:v=>typeof themeLabels==='object'&&v in themeLabels,genre:v=>typeof genreLabels==='object'&&v in genreLabels,scope:v=>['all','daily','saved','unfinished'].includes(v),sort:v=>['recommended','short','recent'].includes(v),query:v=>v.length<=100,page:()=>true};
 const hashBase=()=>location.hash.slice(1).split(/[?\/]/)[0];
 const packInHash=()=>{const m=location.hash.match(/^#studio\/(.+)$/);return m?decodeURIComponent(m[1]):null};
 function corpusHash(){const p=new URLSearchParams();for(const k of KEYS){const v=corpusFilters[k];if(v!==undefined&&String(v)!==String(DEF[k]))p.set(SHORT[k]||k,v)}const q=p.toString();return '#studio'+(q?'?'+q:'')}
 function readCorpusHash(){const h=location.hash.slice(1);if(!/^studio(\?|$)/.test(h))return false;const p=new URLSearchParams(h.split('?')[1]||'');const f={...DEF};for(const k of KEYS){const v=p.get(SHORT[k]||k);if(v===null)continue;if(k==='page')f.page=Math.max(1,parseInt(v,10)||1);else if(OK[k](v))f[k]=v}corpusFilters=f;return true}
 function inCatalog(){return view==='studio'&&!studioPack&&studioSection==='catalog'&&!!document.querySelector('#corpus-results')}
 function syncCorpusURL(){if(!inCatalog())return;const h=corpusHash();if(location.hash!==h)history.replaceState({view:'studio'},'',h)}

 const baseUpdate=updateCorpus;updateCorpus=function(){baseUpdate.apply(this,arguments);syncCorpusURL()};
 const baseRender=renderStudioCatalog;renderStudioCatalog=function(){baseRender.apply(this,arguments);syncCorpusURL()};
 const baseStudio=studio;studio=function(){readCorpusHash();return baseStudio.apply(this,arguments)};

 // Opening a pack from the list remembers where you were; the pack gets its own address (#studio/<id>).
 let mark=null,firstNav=true;
 const baseOpen=openStudioPack;
 openStudioPack=async function(id){
  const fromList=inCatalog();
  if(fromList)mark={y:window.scrollY,id,hash:location.hash};
  await baseOpen.apply(this,arguments);
  if(view!=='studio'||studioPack?.id!==id)return;
  const h='#studio/'+encodeURIComponent(id);if(location.hash===h)return;
  if(hashBase()==='studio'&&packInHash()&&!fromList)history.replaceState({view:'studio',pack:id},'',h);
  else{history.pushState({view:'studio',pack:id},'',h);if(mark)mark.pushed=fromList}
 };
 function restoreList(){if(!mark)return;const card=document.querySelector(`[data-studio-pack="${CSS.escape(mark.id)}"]`)?.closest('.corpus-card');
  const root=document.documentElement,prev=root.style.scrollBehavior;root.style.scrollBehavior='auto';
  if(card){const r=card.getBoundingClientRect();if(Math.abs(window.scrollY+r.top-mark.y)>innerHeight*0.6)window.scrollTo(0,Math.max(0,window.scrollY+r.top-innerHeight/3));else window.scrollTo(0,mark.y)}else window.scrollTo(0,mark.y);
  root.style.scrollBehavior=prev;card?.querySelector('[data-studio-pack]')?.focus({preventScroll:true})}

 const baseNavigate=navigate;
 navigate=async function(v){
  const wasPack=view==='studio'&&!!studioPack,deep=firstNav?packInHash():null;firstNav=false;
  await baseNavigate.apply(this,arguments);
  if(v!=='studio'||view!=='studio'||studioPack)return;
  if(deep){await openStudioPack(deep);return}
  syncCorpusURL();
  if(wasPack)restoreList();
 };

 // The word reference opened from the library gets its own history step, so Back returns to the same list.
 if(typeof referenceLoad==='function'){const baseRef=referenceLoad;referenceLoad=async function(){await baseRef.apply(this,arguments);if(view==='vocab'&&hashBase()!=='vocab')history.pushState({view:'vocab'},'','#vocab')}}

 // "← 语料库" goes back one history step when the pack was opened from the list, so Back/forward never loop.
 document.addEventListener('click',e=>{const b=e.target.closest?.('.back-link[data-view="studio"]');if(!b||!studioPack)return;
  if(mark?.pushed&&history.state?.pack===studioPack.id){e.preventDefault();e.stopImmediatePropagation();history.back()}},true);

 // Browser Back / forward: follow the address instead of leaving Flow.
 window.addEventListener('popstate',async()=>{
  if(!user)return;const base=hashBase()||'home';
  if(base==='studio'){const id=packInHash();
   if(id){if(studioPack?.id!==id)await baseOpen(id);return}
   if(view==='studio'&&studioPack){const id0=studioPack.id;await navigate('studio');if(studioPack?.id===id0)history.pushState({view:'studio',pack:id0},'','#studio/'+encodeURIComponent(id0));return}
   if(view==='studio'&&inCatalog()){if(readCorpusHash())baseRender();return}
   return navigate('studio')}
  if(typeof viewTitles==='object'&&viewTitles[base]&&base!==view)return navigate(base);
 });
})();
