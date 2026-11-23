'use strict';
/* Flow 3.5 learning layer. Loaded last; wraps existing globals instead of rewriting them.
   - subskill page renders that subskill's own content (P0-1)
   - quiz: server-recorded layered hints, familiar items, idempotent submit retry, support labels, disputes (P0-2, P1-6)
   - one next step with its reason and a way back (P1-6, P2-1)
   - review takes due items only; new learning has its own entry (P1-3)
   - settings writes carry a version; a stale page is told instead of overwriting (P1-1)
   - starting check: transcript support recorded by the server; learning mode is a choice (P1-5)
   - dictation shows a word-level diff and is not listening comprehension (P1-4)
   - knowledge graph uses the shared state labels and folds long material lists (P2-4) */
let flow35Settings=null,flow35Purpose=null,flow35Hints={},flow35QuizHints={},flow35Disputed={};
const flow35SettingPaths=new Set(['settings','study/preferences','adaptive/goal','coach/profile','practice/preferences','growth/settings']);
const flow35SupportLabels={none:'独立作答',hint:'看过提示',familiar:'熟悉题（24小时内做过）'};
const flow35HintNames={1:'线索',2:'对比',3:'部分支架',4:'完整答案'};

async function flow35LoadSettings(){try{flow35Settings=await flow35Api('settings')}catch{flow35Settings=null}return flow35Settings}
const flow35Api=api;
api=async function(path,data){
 if(data&&flow35SettingPaths.has(path)){
  if(!flow35Settings)await flow35LoadSettings();
  if(flow35Settings&&data.version===undefined)data={...data,version:flow35Settings.version};
  try{const out=await flow35Api(path,data);flow35LoadSettings();return out}
  catch(e){if(e.status===409){flow35Settings=e.payload?.current||null;throw Error('设置已在其他页面更新（当前每日 '+(flow35Settings?.minutes??'?')+' 分钟）。请确认后再保存一次。')}throw e}
 }
 if(path==='adaptive/next'&&data&&flow35Purpose&&!data.purpose){data={...data,purpose:flow35Purpose};flow35Purpose=null}
 if(path==='coach/placement/submit'&&data){const f=document.querySelector('#coach-placement-form');const choice=f?.querySelector('input[name="flow35-support"]:checked')?.value;if(choice)data={...data,support:choice}}
 if(path==='submit'&&data){
  data={...data,return_to:data.return_to||location.hash||view};
  // An identical replay returns the stored result, so a dropped connection can safely be retried once.
  try{return await flow35Api(path,data)}catch(e){if(e.status)throw e;return await flow35Api(path,data)}
 }
 const out=await flow35Api(path,data);
 if(path==='adaptive/hint'&&out?.hint&&data?.token){
  const list=flow35Hints[data.token]=(flow35Hints[data.token]||[]).filter(h=>h.level!==out.hint.level).concat([out.hint]);
  out.raw=out.hint;out.hint=Object.fromEntries(list.map(h=>['l'+h.level,'第'+h.level+'层 · '+h.kind+'：'+h.text]));
 }
 return out};

/* ---------- next step ---------- */
function flow35StepHTML(step,fallback){
 if(!step)return fallback?`<section class="card flow35-next"><span class="eyebrow">下一步</span><h2>回到今天的计划</h2><p class="muted">没有需要先处理的补练，按计划继续。</p><div class="actions"><button class="btn" data-view="home">回到今日学习 →</button></div></section>`:'';
 const back=step.return_to?.route?`<button class="text-button" data-flow35-route="${esc(step.return_to.route)}">${esc(step.return_to.label)}</button>`:`<button class="text-button" data-view="home">${esc(step.return_to?.label||'回到今天的计划')}</button>`;
 return `<section class="card flow35-next" aria-label="下一步"><span class="eyebrow">下一步 · 约 ${esc(step.minutes||3)} 分钟</span><h2>${esc(step.title)}</h2><p>${esc(step.reason)}</p>${step.then?`<p class="small muted">${esc(step.then)}</p>`:''}<div class="actions"><button class="btn" data-flow35-step="1">开始 →</button>${back}</div><details class="help-details"><summary>依据</summary><p class="small muted">${step.basis?.length?'依据记录编号：'+esc(step.basis.join('、')):'按教学顺序安排，还没有相关作答记录。'} · 规则版本 ${esc(step.policy||'')}</p></details></section>`}
let flow35Step=null;
async function flow35RunStep(step){
 if(!step)return;
 if(step.type==='recheck'||step.type==='grammar')return startNode(step.node);
 if(step.type==='foundation')return openFoundation(step.lesson,!!step.review);
 if(step.type==='repair')return startAdaptive(step.kind,step.kind==='vocab'?step.target:null,step.kind==='grammar'?step.target:null,true);
 if(step.type==='material_repair'||step.type==='dictation_repair')return openStudioPack(step.pack,step.skill||'listening');
}

/* ---------- subskill page (P0-1) ---------- */
function flow35Pair(list,cls){return `<ul class="flow35-pairs ${cls}">${list.map(x=>`<li><span lang="en">${esc(x[0])}</span>${x.length===3?` → <span lang="en">${esc(x[1])}</span><small>${esc(x[2])}</small>`:`<small>${esc(x[1])}</small>`}</li>`).join('')}</ul>`}
async function flow35OpenSubskill(id){
 const owner=user?.id,serial=navigationSerial;await loadStudy();if(user?.id!==owner||serial!==navigationSerial)return;
 const n=nodeById(id);if(!n)throw Error('知识细项不存在');
 if(quiz&&!confirm('离开将丢失当前未提交的答案，确定离开吗？'))return;
 quiz=null;stopRecording();view='learn';activeTopic=null;
 const p=n.content||{status:'pending'},prior=nodeById(n.prereq),topic=dashboard?.topics?.find(t=>t.id===n.topic);
 const g=p.guided;
 const fresh=p.status==='ready'&&!n.independent&&!n.history?.attempts;
 const body=p.status==='ready'?`<section class="card flow35-section" id="flow35-lesson-start" tabindex="-1"><h2>这一项学什么</h2><p>${esc(p.goal)}</p><ol>${p.steps.map(s=>`<li>${esc(s)}</li>`).join('')}</ol></section>
<section class="card flow35-section"><h2>对比着看</h2>${flow35Pair(p.contrast,'contrast')}</section>
<section class="card flow35-section"><h2>常见错误</h2>${flow35Pair(p.pitfalls,'pitfalls')}</section>
<section class="card flow35-section flow35-guided" data-flow35-guided="${esc(n.id)}"><h2>带着提示试一题</h2><p class="small muted">这一题是学习用的，不记入验证。</p><p class="question" lang="en">${esc(g.prompt)}</p><div class="flow35-options">${g.options.map((o,i)=>`<button class="option" lang="en" data-flow35-guided-answer="${i}">${'ABCD'[i]}. ${esc(o)}</button>`).join('')}</div><details class="help-details flow35-scaffold"><summary>需要提示？</summary><p class="small muted">${esc(g.scaffold)}</p></details><p class="flow35-guided-feedback" role="status"></p><div class="flow35-after-guided" hidden><p class="small muted">换一道没见过的题，不看提示做对，才算这一项的独立记录。</p><button class="btn" data-node-quiz="${esc(n.id)}" ${n.available?'':'disabled'}>换一道题验证 →</button></div></section>
${p.extension?`<section class="card flow35-section flow35-extension"><span class="tag">拓展 · 不在本项验证题内</span><p>${esc(p.extension.replace(/^拓展 · /,''))}</p></section>`:''}
<details class="help-details flow-review-note"><summary>这份讲解还在等英语老师审核</summary><p class="small muted">内容是原创教学稿，可以先学；老师审核后可能会调整措辞或例句。讲解版本 ${esc(p.version)}${p.review?' · 审核状态 '+esc(p.review==='draft-needs-language-review'?'待语言审核':p.review):''}</p></details>`
 :`<section class="card flow35-section"><span class="tag">完整讲解编写中</span><p>${esc(n.lesson)}</p><div class="example" lang="en">${esc(n.example)}</div><p class="small muted">${esc(p.note||'')}</p></section>`;
 shell(`<div class="flow35-subskill"><div class="flow-workhead"><button class="back-link" data-view="learn">← 语法学习</button>${topic?`<button class="text-button" data-topic="${esc(topic.id)}">所属主题：${esc(topic.title)}</button>`:''}</div>
<header class="pagehead"><span class="eyebrow">语法细项</span><h1>${esc(n.title)}</h1><p class="muted">${esc(n.label)} · 下一步：${esc(n.purpose_label)}</p></header>
<section class="card flow35-state"><div><strong>${esc(n.label)}</strong><p class="small muted">独立做对 ${n.independent} 次（${n.independent_items} 道不同题）· 隔天做对 ${n.delayed} 次 · 换情境做对 ${n.transfer} 次</p><details class="help-details"><summary>这些说法是什么意思？</summary><p class="small muted">“独立”是没看提示、也不是24小时内刚做过的题。首次作答正确率 ${n.history.first_accuracy==null?'—':n.history.first_accuracy+'%'} 只是历史统计，不决定当前状态。${n.basis?.length?' 依据记录：'+esc(n.basis.join('、')):''}</p></details></div><div class="actions">${fresh?`<button class="btn" data-flow35-start-lesson="1">开始讲解 ↓</button><button class="quiet-button" data-node-quiz="${esc(n.id)}" ${n.available?'':'disabled'}>我学过，直接验证</button>`:`<button class="btn" data-node-quiz="${esc(n.id)}" ${n.available?'':'disabled'}>做验证题 →</button>`}${prior?`<button class="btn secondary" data-node="${esc(prior.id)}">先看前一项：${esc(prior.title)}</button>`:''}</div></section>
${body}</div>`)}
openNode=async function(...args){if(typeof flowGuardLeave==='function'&&!flowGuardLeave())return;if(typeof flowPushReturn==='function')flowPushReturn();return flow35OpenSubskill(...args)};

/* ---------- quiz: hints, familiar items (P0-2, P1-6) ---------- */
const flow35QuizPage=quizPage;
quizPage=function(){flow35QuizPage();const q=quiz?.questions?.[index];if(!q)return;const card=app.querySelector('.quiz article.card');if(!card)return;
 const shown=flow35QuizHints[quiz.token+':'+q.id]||[],next=(shown.at(-1)?.level||0)+1;
 card.insertAdjacentHTML('afterbegin',q.familiar?'<span class="tag flow35-familiar">熟悉题 · 24小时内做过，做对记为有支持的练习</span>':'');
 card.querySelector('.actions')?.insertAdjacentHTML('beforebegin',`<div class="flow35-hints" aria-live="polite">${shown.map(h=>`<p class="flow-hint"><strong>第${h.level}层 · ${esc(h.kind)}</strong> ${esc(h.text)}</p>`).join('')}${next<=4?`<button class="text-button" data-flow35-qhint="${next}">${shown.length?'再给一点提示':'需要提示'}（${flow35HintNames[next]}）</button>`:''}${shown.length?'<p class="small muted">看过提示的题记为“有支持的练习”，不计独立通过。</p>':''}</div>`)};

/* ---------- results: support labels, disputes, next step ---------- */
results=function(r){
 const wrong=r.results.filter(q=>!q.correct).length;
 shell(pagehead('测评结果',`共 ${r.results.length} 题，答对 ${r.results.length-wrong} 题；其中独立答对 ${r.independent??'—'} 题。`)+flow35StepHTML(r.next_step,true)+`<div class="card" data-flow35-results="1">${r.results.map(q=>`<article class="result"><span class="${q.correct?'correct':'wrong'}">${q.correct?'✓ 回答正确':'○ 需要巩固'}</span>${q.support?` <span class="tag">${esc(flow35SupportLabels[q.support]||q.support)}</span>`:''}<h3 lang="en">${esc(q.prompt)}</h3><p class="small muted">你的答案：${esc(q.options[q.selected])} · 正确答案：${esc(q.options[q.answer])}</p><p>${esc(q.explanation)}</p>${!q.correct&&q.attempt?(flow35Disputed[q.attempt]?`<p class="small muted">已记下你的反馈：${esc(flow35Disputed[q.attempt])}</p>`:`<details class="help-details"><summary>这题记错了？</summary><div class="actions"><button class="text-button" data-flow35-dispute="${q.attempt}" data-reason="misclick">我点错了</button><button class="text-button" data-flow35-dispute="${q.attempt}" data-reason="misread">我对题意理解不同</button><button class="text-button" data-flow35-dispute="${q.attempt}" data-reason="explanation">解析可能有误</button></div><p class="small muted">原记录会保留；下一步会先换一道新题确认。</p></details>`):''}${q.topic?`<button class="btn secondary" data-explain-wrong="${esc(JSON.stringify(q))}">${q.correct?'请 AI 延伸讲解':'请 AI 分析错因'}</button>`:''}</article>`).join('')}<div class="actions"><button class="btn secondary" data-view="wrongs">查看待巩固错题</button>${r.topic?`<button class="btn secondary" data-topic="${esc(r.topic)}">返回本课</button>`:''}</div></div>`);
 flow35Step=r.next_step;flow35LastResult=r};
let flow35LastResult=null;

/* ---------- review hub: due only, separate new learning (P1-3) ---------- */
reviewHub=async function(){view='review';const owner=user.id,epoch=++flowEpoch;
 const s=await api('review/status');if(!flowCurrent(owner,epoch)||view!=='review')return;
 const when=s.next_due?new Date(s.next_due*1000).toLocaleString('zh-CN',{month:'numeric',day:'numeric',hour:'2-digit',minute:'2-digit'}):'';
 if(dashboard)dashboard.due_review=s.due_grammar+s.due_words;
 shell(pagehead('复习','这里只放到期的内容。想学新的，用“学新内容”。')+`<div class="review-hub"><section class="card"><span class="eyebrow">到期复习</span><h2>${esc(s.message)}</h2>${s.status==='due'?`<p>语法 ${s.due_grammar} 项 · 单词 ${s.due_words} 个</p><ul class="flow35-due">${s.items.map(x=>`<li>${esc(x.title)}<small>${esc(x.reason)}</small></li>`).join('')}</ul><button class="btn" data-flow35-review="1">开始复习 →</button>`:`<p class="muted">${s.status==='no_records'?'先学一点新内容，之后会自动安排复习。':s.status==='done_today'?'今天到期的都做完了。':'到期的会在这里出现。'}${when?' 下一次到期：'+esc(when)+'。':''}</p>`}</section><section class="card"><span class="eyebrow">学新内容</span><h2>学一个新词或新细项</h2><p>和复习分开记录；每天的新词数量按你的设置。</p><button class="btn secondary" data-flow35-new="1">学新内容 →</button></section></div><section class="card fine-skills"><h2>其他</h2><div class="actions"><button class="text-button" data-studio-history="1">作品与修订 →</button><button class="text-button" data-flow-old-review="1">旧词汇本、错题与其他复习 →</button></div><p class="small muted">${esc(s.note)}</p></section>`)};

async function flow35Review(purpose){
 if(purpose==='new'){flow35Purpose='new';return startAdaptive()}
 view='journey';const owner=user.id,epoch=++flowEpoch;flowBusy=false;flowTask=null;flowTaskResult=null;flowTaskHint=null;
 const d=await api('adaptive/next',{purpose:'review'});if(!flowCurrent(owner,epoch))return;
 if(d.empty){view='review';shell(pagehead('复习',esc(d.message))+`<section class="card"><p class="muted">复习不会自动加入新内容。</p><div class="actions"><button class="btn secondary" data-flow35-new="1">学新内容 →</button><button class="text-button" data-view="home">回到今日学习</button></div></section>`);return}
 if(d.foundation){await openFoundation(d.foundation);return}
 flowTask=d.task;renderAdaptiveTask()}

/* ---------- adaptive task: layered hint labels ---------- */
const flow35Render=renderAdaptiveTask;
renderAdaptiveTask=function(){flow35Render();if(!flowTask)return;const list=flow35Hints[flowTask.token]||[],level=list.at(-1)?.level||0,b=app.querySelector('[data-flow-hint]');
 if(b){if(level>=4)b.remove();else b.textContent=(level?'下一层提示：':'需要提示：')+flow35HintNames[level+1]}
 const h=app.querySelector('.flow-hint strong');if(h&&level)h.textContent='学习提示（已看到第 '+level+' 层）· 本题记为有支持的练习';
 // 3.6.3: one next step at a time. After a right answer, keep going; after a miss, the short detour leads
 // and "继续下一小步" steps back to a secondary button.
 if(flowTaskResult?.next_step&&!flowTaskResult.correct&&!app.querySelector('.flow35-next')){const box=app.querySelector('.flow-result'),acts=box?.querySelector(':scope > .actions');(acts||box)?.insertAdjacentHTML(acts?'beforebegin':'beforeend',flow35StepHTML(flowTaskResult.next_step));box?.querySelector('.flow35-next .actions > .text-button')?.remove();box?.querySelector('[data-flow-next]')?.classList.add('secondary')}
 if(flowTaskResult?.next_step)flow35Step=flowTaskResult.next_step;
 if(flowTaskResult&&!flowTaskResult.correct&&flowTaskResult.attempt&&!app.querySelector('[data-flow35-dispute]'))app.querySelector('.flow-result')?.insertAdjacentHTML('beforeend',`<details class="help-details"><summary>这题记错了？</summary><div class="actions"><button class="text-button" data-flow35-dispute="${flowTaskResult.attempt}" data-reason="misclick">我点错了</button><button class="text-button" data-flow35-dispute="${flowTaskResult.attempt}" data-reason="misread">我对题意理解不同</button></div></details>`)};

/* ---------- dictation diff (P1-4) ---------- */
const flow35Result=resultHTML;
resultHTML=function(s){const html=flow35Result(s),d=s?.result;if(d?.kind!=='dictation'||!d.diff)return html;
 const part=(title,list,fn)=>list.length?`<div><strong>${title} · ${list.length}</strong><ul>${list.slice(0,12).map(fn).join('')}</ul></div>`:'';
 const diff=`<div class="flow35-diff">${part('漏写',d.diff.missing,x=>`<li lang="en">${esc(x.expected)}</li>`)}${part('写成了别的词',d.diff.replaced,x=>`<li lang="en">${esc(x.expected)} → <s>${esc(x.written)}</s></li>`)}${part('多写',d.diff.extra,x=>`<li lang="en"><s>${esc(x.written)}</s></li>`)}${!d.diff.missing.length&&!d.diff.replaced.length&&!d.diff.extra.length?'<p>逐词完全一致。</p>':''}<p class="small muted">听写只看逐词回忆和拼写，单独记录，不算听力理解的通过或不通过。</p></div>`;
 return html.replace(/<\/section>$/,diff+'</section>')};

/* ---------- knowledge graph: shared labels, folded detail (P2-4) ---------- */
const flow35Knowledge=renderKnowledge;
renderKnowledge=function(){flow35Knowledge();const d=knowledgeData;if(!d)return;
 const legend=app.querySelector('.kg-legend');if(legend)legend.innerHTML='<span>○ 还没开始 / 待独立检查</span><span class="wrong">● 最近没做对或借助提示</span><span class="correct">● 有独立做对的记录</span><small>状态只看真实作答：是否独立、是否隔天、是否换了情境</small>';
 for(const b of app.querySelectorAll('.kg-node[data-kg-select]')){const n=d.nodes.find(x=>x.id===b.dataset.kgSelect);if(!n)continue;b.classList.toggle('stable',!!n.stable);b.classList.toggle('weak',n.state==='需要巩固'||n.state==='提示后完成');const small=b.querySelector('small');if(small)small.textContent=n.label+' · '+n.material_count+' 篇语料'}
 const detail=app.querySelector('.kg-detail');if(detail){const sel=d.nodes.find(x=>x.id===knowledgeSelected)||d.nodes[0];for(const p of detail.querySelectorAll('p.small.muted'))if(p.textContent.startsWith(sel.state+' ·'))p.textContent=sel.label+' · 下一步：'+sel.purpose_label;
  const stats=detail.querySelectorAll('.kg-evidence small');if(stats[1])stats[1].textContent='首次正确率（历史统计）';
  const mats=[...detail.querySelectorAll('.kg-material')];if(mats.length>2){const box=document.createElement('details');box.className='help-details';box.innerHTML=`<summary>还有 ${mats.length-2} 篇关联语料</summary>`;mats[2].before(box);mats.slice(2).forEach(m=>box.append(m))}}};

/* ---------- starting check: support recorded by the server; mode is a choice (P1-5) ---------- */
function flow35Enhance(){
 const f=document.querySelector('#coach-placement-form');
 if(f&&!f.querySelector('.flow35-support')){const at=f.querySelector('button:last-of-type')||f.lastElementChild;at?.insertAdjacentHTML('beforebegin',`<fieldset class="flow35-support field"><legend>学习方式（可以随时改）</legend><label><input type="radio" name="flow35-support" value="" checked> 按检查结果建议</label><label><input type="radio" name="flow35-support" value="basic"> 基础起步：先看例句，再练短句</label><label><input type="radio" name="flow35-support" value="standard"> 标准练习</label><p class="small muted">有效作答少于 4 题时不判断起点；基础起步是一种支持方式，不是水平判断。</p></fieldset>`)}}
new MutationObserver(()=>flow35Enhance()).observe(app,{childList:true,subtree:true});

/* ---------- clicks ---------- */
app.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b||!user||b.disabled)return;try{
 if(b.dataset.coachTranscript&&typeof coachPlacement!=='undefined'&&coachPlacement?.token)api('coach/placement/support',{token:coachPlacement.token,item:b.dataset.coachTranscript}).catch(()=>{});
 if(b.dataset.flow35Qhint){const q=quiz.questions[index],key=quiz.token+':'+q.id,level=Number(b.dataset.flow35Qhint);b.disabled=true;const d=await api('attempt/hint',{token:quiz.token,question:q.id,level});(flow35QuizHints[key]=flow35QuizHints[key]||[]).push(d.hint);quizPage()}
 if(b.dataset.flow35Dispute){const attempt=Number(b.dataset.flow35Dispute),reason=b.dataset.reason;const note=reason==='explanation'?(prompt('哪里可能有误？（可选，400 字以内）')||'').slice(0,400):'';b.disabled=true;const d=await api('attempt/dispute',{attempt,reason,note});flow35Disputed[attempt]={misclick:'我点错了',misread:'我对题意理解不同',explanation:'解析可能有误'}[reason];toast(d.message);
  if(app.querySelector('[data-flow35-results]')&&flow35LastResult){const s=await api('study');flow35LastResult.next_step=s.next_step;results(flow35LastResult)}else if(flowTaskResult){flowTaskResult.next_step=(await api('study')).next_step;app.querySelector('.flow35-next')?.remove();renderAdaptiveTask()}}
 if(b.dataset.flow35Step)await flow35RunStep(flow35Step);
 if(b.dataset.flow35Route){location.hash=b.dataset.flow35Route}
 if(b.dataset.flow35Review)await flow35Review('review');
 if(b.dataset.flow35New)await flow35Review('new');
 if(b.dataset.flow35GuidedAnswer!==undefined){const box=b.closest('[data-flow35-guided]'),n=nodeById(box.dataset.flow35Guided),g=n?.content?.guided;if(!g)return;const i=Number(b.dataset.flow35GuidedAnswer);box.querySelectorAll('[data-flow35-guided-answer]').forEach(x=>x.classList.toggle('selected',x===b));const tries=Number(box.dataset.tries||0)+1;box.dataset.tries=tries;const fb=box.querySelector('.flow35-guided-feedback');if(i!==g.answer&&tries===1){b.disabled=true;b.classList.add('wrong');const hint=box.querySelector('.flow35-scaffold');if(hint)hint.open=true;fb.textContent='还不对。先看上面的提示，再选一次。';return}box.querySelectorAll('[data-flow35-guided-answer]').forEach(x=>{x.disabled=true;x.classList.toggle('correct',Number(x.dataset.flow35GuidedAnswer)===g.answer)});fb.textContent=(i===g.answer?(tries===1?'对。':'这次对了。'):'正确答案是 '+'ABCD'[g.answer]+'。')+g.explanation;const after=box.querySelector('.flow35-after-guided');if(after)after.hidden=false}
  if(b.dataset.flow35StartLesson){const start=document.querySelector('#flow35-lesson-start');start?.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth',block:'start'});start?.focus({preventScroll:true})}
}catch(err){toast(err.message)}});

/* The home "next step" button also understands the 3.5 step types. */
app.addEventListener('click',async e=>{const b=e.target.closest('button');if(!b?.dataset.learningNext||!user)return;const a=coachData?.learning_loop?.next_action;if(!a||!['recheck','dictation_repair','grammar'].includes(a.type))return;try{await flow35RunStep(a)}catch(err){toast(err.message)}});
