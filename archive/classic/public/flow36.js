'use strict';
// Flow 3.6: email-verified sign-up, code or password login, and focus layout hooks for phone and iPad.
// Loads last; it replaces auth() and only adds classes for layout, so every learning view keeps its logic.
let auth36Method='password',auth36Values={},auth36Timer=0,auth36Waits={register:0,login:0},auth36Mail=false;
// Email codes only appear once the server can send mail; until then sign-up and login are username + password.
fetch('/api/health',{credentials:'same-origin'}).then(r=>r.json()).then(d=>{auth36Mail=d.mail===true;if(auth36Mail&&document.querySelector('.auth36')){auth36Remember();auth()}}).catch(()=>{});
function auth36Field(id,label,attrs,hint=''){return `<div class="field"><label for="${id}">${label}</label><input id="${id}" name="${id.replace('a36-','')}" ${attrs} value="${esc(auth36Values[id]||'')}">${hint?`<span class="field-hint">${hint}</span>`:''}</div>`}
function auth36Code(purpose){return `<div class="field"><label for="a36-code">邮箱验证码</label><div class="code-control"><input id="a36-code" name="code" inputmode="numeric" autocomplete="one-time-code" pattern="[0-9]{6}" maxlength="6" required placeholder="6 位数字" value="${esc(auth36Values['a36-code']||'')}"><button type="button" class="btn secondary code-send" data-auth36-send="${purpose}" ${auth36Waits[purpose]>0?'disabled':''}>${auth36Waits[purpose]>0?auth36Waits[purpose]+' 秒后重发':'获取验证码'}</button></div><span class="field-hint" id="a36-note" role="status">验证码会发到上面的邮箱，10 分钟内有效。</span></div>`}
function auth36Password(login){return `<div class="field"><label for="a36-password">密码</label><div class="password-control"><input id="a36-password" name="password" type="password" autocomplete="${login?'current-password':'new-password'}" minlength="${login?1:10}" maxlength="200" required placeholder="${login?'输入密码':'至少 10 个字符'}"><button type="button" class="password-toggle" data-show-password="a36-password" aria-label="显示密码" aria-pressed="false">${flowIcon('eye')}</button></div></div>`}
auth=function(){
 const login=authMode==='login',mail=auth36Mail,code=mail&&login&&auth36Method==='code';
 const savedTrial=typeof meetingAuthContext==='function'?meetingAuthContext():null;
 document.title=(savedTrial?'保存练习':login?'登录':'注册')+' · 语流 Flow';
 document.documentElement.classList.add('flow-auth');
 const fields=login?(code?auth36Field('a36-email','邮箱','type="email" autocomplete="email" maxlength="254" required placeholder="you@example.com"')+auth36Code('login'):auth36Field('a36-username','用户名或邮箱','autocomplete="username" maxlength="254" required placeholder="输入用户名或邮箱"')+auth36Password(true))
  :auth36Field('a36-username','用户名','autocomplete="username" minlength="3" maxlength="40" required placeholder="3–40 个字符"','登录和学习档案里显示的名字')+(mail?auth36Field('a36-email','邮箱','type="email" autocomplete="email" maxlength="254" required placeholder="you@example.com"','用于验证、找回密码和验证码登录')+auth36Code('register'):'')+auth36Password(false);
 app.innerHTML=`<main class="auth-scene auth36"><section class="auth-window"><div class="auth-story">${brand}<div class="auth-editorial"><span class="auth-kicker">语料 · 词汇 · 语法 · 私教</span><h1>你的长期<br>AI 英语私教</h1><p>从了解你的起点开始，用长期私教对话、真实练习和知识图谱，安排你的下一步。</p></div><span class="auth-caption">测试中，欢迎试用</span></div><div class="auth-form"><div class="auth-panel"><div class="auth-mobile-brand">${brand}</div>${savedTrial?`<a class="meeting-guest-link" href="${meetingTrialHref(savedTrial.day)}">← 返回我的答案</a>`:'<a class="meeting-guest-link" href="/?trial=1#try-meeting/1">直接做一道练习</a>'}<div class="auth-form-heading"><h2>${savedTrial?'保存这次练习':login?'继续你的学习':'建立学习档案'}</h2><p class="muted">${savedTrial?'你的答案已暂存在此标签页。登录或注册后，可以确认保存到学习档案。':login?'登录后，接着上次的进度。':mail?'先验证邮箱，再设置密码。':'设置用户名和密码，马上开始。'}</p><p class="small muted">测试期间，所有内容和功能均免费。</p></div><div class="auth-segments" role="group" aria-label="账号入口"><button data-auth36-mode="login" type="button" aria-pressed="${login}">登录</button><button data-auth36-mode="register" type="button" aria-pressed="${!login}">注册</button></div>${login&&mail?`<div class="auth-methods" role="group" aria-label="登录方式"><button type="button" data-auth36-method="password" aria-pressed="${!code}">密码登录</button><button type="button" data-auth36-method="code" aria-pressed="${code}">邮箱验证码</button></div>`:''}<form method="post" id="auth36-form" novalidate>${fields}<p id="auth-error" class="error" role="alert"></p><button class="btn auth-submit" type="submit">${login?'登录 Flow':mail?'验证并创建账号':'创建账号'} ${flowIcon('arrow')}</button></form>${login&&mail?'<p class="switch"><button type="button" data-forgot="1">忘记密码？用绑定邮箱找回</button></p>':''}<p class="auth-privacy">${login&&mail?'老账号还没绑定邮箱时，请用用户名和密码登录，再到“设置”里绑定邮箱。':'账号与学习记录保存在服务器。使用 AI 功能时，相关学习内容会发送给配置的模型服务。'}</p></div></div></section></main>`;
 document.querySelector('#auth36-form input')?.focus({preventScroll:true});
};
function auth36Remember(){document.querySelectorAll('#auth36-form input[id^="a36-"]:not([type=password])').forEach(i=>auth36Values[i.id]=i.value)}
function auth36Error(message,field){const box=document.querySelector('#auth-error');if(box)box.textContent=message||'';if(field){const input=document.querySelector('#a36-'+field);input?.setAttribute('aria-invalid','true');input?.focus()}}
// Each purpose has its own resend wait, matching the server's per-purpose limit.
function auth36Tick(){clearInterval(auth36Timer);auth36Timer=setInterval(()=>{for(const k in auth36Waits)auth36Waits[k]=Math.max(0,auth36Waits[k]-1);const b=document.querySelector('[data-auth36-send]');if(b){const w=auth36Waits[b.dataset.auth36Send];b.textContent=w>0?w+' 秒后重发':'重新获取';b.disabled=w>0}if(!Object.values(auth36Waits).some(Boolean))clearInterval(auth36Timer)},1000)}
app.addEventListener('click',async e=>{
 const b=e.target.closest('button');if(!b||!document.querySelector('.auth36'))return;
 if(b.dataset.auth36Mode){auth36Remember();authMode=b.dataset.auth36Mode;auth();return}
 if(b.dataset.auth36Method){auth36Remember();auth36Method=b.dataset.auth36Method;auth();return}
 if(b.dataset.auth36Send){
  e.preventDefault();const purpose=b.dataset.auth36Send;if(auth36Waits[purpose]>0||b.disabled)return;const email=document.querySelector('#a36-email');auth36Error('');
  if(!email?.value.trim()||!email.checkValidity()){auth36Error('请先填写有效的邮箱地址','email');return}
  b.disabled=true;const note=document.querySelector('#a36-note');
  try{const r=await api('auth/code',{email:email.value.trim(),purpose});if(note)note.textContent=r.message;auth36Waits[purpose]=r.resend_after||60;b.textContent=auth36Waits[purpose]+' 秒后重发';auth36Tick();document.querySelector('#a36-code')?.focus()}
  catch(err){b.disabled=false;auth36Error(err.message,err.payload?.code==='email_taken'||err.payload?.code==='email_unknown'?'email':null);if(err.payload?.code==='email_taken'&&note)note.textContent='可以切换到“登录 → 邮箱验证码”。'}
 }
},true);
app.addEventListener('submit',async e=>{
 const f=e.target;if(f.id!=='auth36-form')return;e.preventDefault();e.stopImmediatePropagation();
 const b=f.querySelector('.auth-submit');if(b.disabled)return;
 f.querySelectorAll('[aria-invalid]').forEach(i=>i.removeAttribute('aria-invalid'));
 const bad=[...f.querySelectorAll('input')].find(i=>!i.checkValidity());
 if(bad){const label=f.querySelector(`label[for="${bad.id}"]`)?.textContent||'这一项';auth36Error(bad.validity.valueMissing?'请填写'+label:label+'格式不正确',bad.id.replace('a36-',''));return}
 const data=Object.fromEntries(new FormData(f));if(authMode==='login'&&auth36Method==='code')data.method='code';
 b.disabled=true;f.setAttribute('aria-busy','true');auth36Error('');
 try{auth36Remember();await api(authMode,data);auth36Values={};document.documentElement.classList.remove('flow-auth');await boot()}
 catch(err){auth36Error(err.message,err.payload?.field||null)}
 finally{if(b.isConnected)b.disabled=false;f.removeAttribute('aria-busy')}
},true);

// Layout hooks: the learning view in front decides whether chrome steps back.
function flow36Layout(){
 const root=document.documentElement,a=document.querySelector('#app');if(!a)return;
 const authOpen=!!a.querySelector('.auth-scene');root.classList.toggle('flow-auth',authOpen);
 const focus=!authOpen&&!!a.querySelector('.quiz .option,.foundation-lesson,.adaptive-task,.flow-task,.practice-work,.mentor-placement,.recovery-wrap');
 root.classList.toggle('flow-focus',focus);
 root.classList.toggle('flow-home',!!a.querySelector('.mentor-head'));
 flow36Help();
}
// Phone (3.6.2): the "stuck?" AI help becomes a bottom sheet behind one small button, so the word or text stays on top.
const flow36Phone=window.matchMedia?.('(max-width:640px)');
function flow36Help(){
 const root=document.documentElement,box=document.querySelector('.ai-context-help');let fab=document.querySelector('.help-fab');
 if(!box||!flow36Phone?.matches){fab?.remove();root.classList.remove('help-open');return}
 if(!box.querySelector('.help-close')){root.classList.remove('help-open');const close=document.createElement('button');close.type='button';close.className='help-close';close.setAttribute('aria-label','关闭帮助');close.textContent='×';box.prepend(close)}
 box.id='flow-help-sheet';
 if(!fab){fab=document.createElement('button');fab.type='button';fab.className='help-fab';fab.textContent='卡住了？';fab.setAttribute('aria-controls','flow-help-sheet');document.body.appendChild(fab)}
 fab.setAttribute('aria-expanded',String(root.classList.contains('help-open')));
}
function flow36HelpOpen(open){document.documentElement.classList.toggle('help-open',open);document.querySelector('.help-fab')?.setAttribute('aria-expanded',String(open));if(open)document.querySelector('.ai-context-help button:not(.help-close)')?.focus({preventScroll:true})}
document.addEventListener('click',e=>{
 if(e.target.closest('.help-fab')){flow36HelpOpen(!document.documentElement.classList.contains('help-open'));return}
 if(e.target.closest('.help-close'))return flow36HelpOpen(false);
 if(document.documentElement.classList.contains('help-open')&&!e.target.closest('.ai-context-help'))return flow36HelpOpen(false);
 // A help request shows its answer in the floating AI panel, so the sheet steps aside.
 if(document.documentElement.classList.contains('help-open')&&e.target.closest('.ai-context-help > .text-button'))flow36HelpOpen(false);
});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&document.documentElement.classList.contains('help-open'))flow36HelpOpen(false)});
flow36Phone?.addEventListener?.('change',flow36Help);
// The keyboard flag (mobile.js) only listened inside #app; search lives in a dialog outside it,
// so closing search with the keyboard up left the bottom navigation hidden. Re-check on any focus change.
for(const ev of ['focusin','focusout'])document.addEventListener(ev,()=>setTimeout(()=>{if(typeof mobileViewport==='function')mobileViewport()},60),true);
new MutationObserver(()=>{flow36Layout();setTimeout(flow36Help,0)}).observe(document.querySelector('#app'),{childList:true});
flow36Layout();

// Quiz pause / resume (3.6.3). Answers used to live only in memory, the bottom navigation is hidden while
// answering, and there was no way out. Now every answer is kept on this device for the quiz's lifetime
// (the server accepts a quiz for 1 hour), "暂停" leaves safely, and the quiz page offers to continue.
const flow36QuizTTL=55*60*1000;
function flow36QuizKey(){return user?'flow-quiz:'+user.id:null}
function flow36QuizSaved(){const k=flow36QuizKey();if(!k)return null;try{const s=JSON.parse(localStorage.getItem(k)||'null');if(s&&s.quiz?.token&&Array.isArray(s.quiz.questions)&&Date.now()-s.saved<flow36QuizTTL)return s;localStorage.removeItem(k)}catch{}return null}
function flow36QuizForget(){const k=flow36QuizKey();try{if(k)localStorage.removeItem(k)}catch{}}
function flow36QuizKeep(){const k=flow36QuizKey();if(!k||!quiz?.token)return;try{const old=flow36QuizSaved();localStorage.setItem(k,JSON.stringify({quiz,index,answers,saved:old?.quiz?.token===quiz.token?old.saved:Date.now()}))}catch{}}
const flow36QuizPage=quizPage;
quizPage=function(){flow36QuizPage();if(!quiz)return;flow36QuizKeep();
 const note=app.querySelector('.quiz > p.small.muted');if(note)note.textContent='答案会自动保存在这台设备上，1 小时内回来可以接着做。';
 const card=app.querySelector('.quiz article.card');if(card&&!card.querySelector('[data-quiz-pause]'))card.insertAdjacentHTML('afterend','<p class="quiz-pause"><button type="button" class="text-button" data-quiz-pause="1">暂停，稍后继续</button></p>')};
const flow36QuizIntro=quizIntro;
quizIntro=function(){flow36QuizIntro();const s=flow36QuizSaved();if(!s)return;const done=Object.keys(s.answers||{}).length,total=s.quiz.questions.length;
 const head=app.querySelector('.pagehead');const html=`<section class="card quiz-resume" aria-label="没做完的测评"><span class="eyebrow">没做完的测评</span><h2>已答 ${done} / ${total} 题</h2><p class="muted">接着上次的位置做，答过的题都还在。</p><div class="actions"><button class="btn" data-quiz-resume="1">接着做 →</button><button class="text-button" data-quiz-discard="1">放弃这次，重新开始</button></div></section>`;
 if(head)head.insertAdjacentHTML('afterend',html);else app.querySelector('.card')?.insertAdjacentHTML('beforebegin',html);
 app.querySelector('[data-action=start]')?.classList.add('secondary')};
const flow36Results=results;
results=function(...args){flow36QuizForget();return flow36Results(...args)};
const flow36ClearAccount=clearAccountState;
clearAccountState=function(...args){flow36QuizForget();return flow36ClearAccount(...args)};
app.addEventListener('click',e=>{
 const b=e.target.closest('button');if(!b)return;
 if(b.dataset.quizPause){e.stopImmediatePropagation();flow36QuizKeep();quiz=null;navigate('home');toast('已暂停。到“诊断测评”可以接着做。');return}
 if(b.dataset.quizResume){e.stopImmediatePropagation();const s=flow36QuizSaved();if(!s){toast('这次测评已过期，请重新开始');quizIntro();return}quiz=s.quiz;index=Math.min(s.index||0,s.quiz.questions.length-1);answers=s.answers||{};view='quiz';quizPage();return}
 if(b.dataset.quizDiscard){e.stopImmediatePropagation();flow36QuizForget();quizIntro();return}
},true);

// Review badge (3.6.3): the count of items due now, the same number the review page shows.
// The dashboard only loads at start, so refresh it when the view changes (at most every 20 seconds).
let flow36DueAt=0;
function flow36Due(){if(typeof user==='undefined'||!user||!dashboard||document.hidden||Date.now()-flow36DueAt<20000)return;flow36DueAt=Date.now();
 api('review/status').then(s=>{const n=(s.due_grammar||0)+(s.due_words||0);dashboard.due_review=n;
  document.querySelectorAll('.nav[data-view=review]').forEach(b=>{let c=b.querySelector('.nav-count');if(!n){c?.remove();return}if(!c){c=document.createElement('span');c.className='nav-count';c.title='到期复习';b.append(c)}c.textContent=n})}).catch(()=>{})}
new MutationObserver(()=>setTimeout(flow36Due,400)).observe(document.querySelector('#app'),{childList:true});

// Graph node list on phones (3.6.4): show 8, then "显示全部" instead of a small inner scroll box.
function flow36NodeMore(){if(!flow36Phone?.matches)return;document.querySelectorAll('.flow-node-list>div').forEach(list=>{const n=list.querySelectorAll(':scope>button').length;const next=list.nextElementSibling;if(n<=8||next?.classList.contains('node-more')||list.classList.contains('show-all'))return;list.insertAdjacentHTML('afterend',`<button type="button" class="btn secondary node-more">显示全部 ${n} 个</button>`)})}
document.addEventListener('click',e=>{const b=e.target.closest('.node-more');if(!b)return;b.previousElementSibling?.classList.add('show-all');b.remove()});
new MutationObserver(()=>setTimeout(flow36NodeMore,0)).observe(document.querySelector('#app'),{childList:true,subtree:true});
// 3.6.5: on phones the "卡住了？" button steps aside while you scroll down through a text, and comes back when you scroll up or reach the end.
(()=>{const last=new WeakMap();
 document.addEventListener('scroll',e=>{if(!flow36Phone?.matches||!document.querySelector('.help-fab'))return;const t=e.target===document?document.scrollingElement:e.target;if(!t||t.scrollHeight<=t.clientHeight)return;
  const y=t.scrollTop,root=document.documentElement;
  if(y<80||y+t.clientHeight>=t.scrollHeight-48){last.set(t,y);root.classList.remove('help-away');return}
  const prev=last.get(t)??y;if(Math.abs(y-prev)<8)return;last.set(t,y);root.classList.toggle('help-away',y>prev);
 },{capture:true,passive:true});
 document.addEventListener('focusin',e=>{if(e.target.closest?.('.help-fab'))document.documentElement.classList.remove('help-away')});
})();
document.addEventListener('click',e=>{if(e.target.closest?.('[data-view]'))document.documentElement.classList.remove('help-away')});
window.addEventListener('hashchange',()=>document.documentElement.classList.remove('help-away'));

/* 3.7.0: an unfinished quiz shows up on home, not only inside 诊断测评. */
function flow36HomeQuizResume(){if(view!=='home'||app.querySelector('.quiz-resume'))return;const s=flow36QuizSaved();if(!s)return;const done=Object.keys(s.answers||{}).length,total=s.quiz.questions.length;const box=app.querySelector('.page-content');if(!box)return;
 box.insertAdjacentHTML('afterbegin',`<section class="card quiz-resume home-quiz-resume" aria-label="没做完的测评"><div><span class="eyebrow">没做完的测评</span><p>已答 ${done} / ${total} 题，答过的题都还在。</p></div><button class="btn" data-quiz-resume="1">接着做 →</button></section>`)}
if(typeof renderCoach==='function'){const flow36RenderCoach=renderCoach;renderCoach=function(...args){const out=flow36RenderCoach(...args);flow36HomeQuizResume();return out}}
if(typeof renderCoachWelcome==='function'){const flow36Welcome=renderCoachWelcome;renderCoachWelcome=function(...args){const out=flow36Welcome(...args);flow36HomeQuizResume();return out}}
