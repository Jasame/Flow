'use strict';
// Progressive mobile enhancements; desktop navigation and learning state stay shared.
let mobileViewportBaseline=0,mobileViewportWidth=0;
function mobileNavHTML(active){const selected=['journey','meeting'].includes(active)?'home':active;return `<nav class="mobile-nav" aria-label="手机快捷导航">${[['home','home','今日'],['review','review','复习'],['studio','library','语料'],['vocab','book','词汇']].map(([id,icon,label])=>`<button data-view="${id}" ${selected===id?'aria-current="page"':''}>${flowIcon(icon)}<span>${label}</span></button>`).join('')}<button data-mobile-menu="1" aria-controls="app-sidebar" aria-expanded="false" aria-label="更多学习功能">${flowIcon('grid')}<span>更多</span></button></nav>`}
function mobileGraphHTML(d,compact=false){const nodes=new Map(d.network.nodes.map(n=>[n.id,n])),limit=compact?3:8;let edges=d.network.edges.filter(e=>e.source===d.node.id||e.target===d.node.id);if(!edges.length)edges=d.network.edges;const status=d.node.state||'教学语料';return `<section class="mobile-graph" aria-label="手机知识连接"><div class="mobile-graph-selected"><span class="small muted">${esc(kindLabels[d.node.kind]||'知识节点')} · 当前焦点</span><button data-flow-node="${esc(d.node.id)}"><i class="atlas-dot atlas-${esc(d.node.status||'unknown')}"></i><strong>${esc(d.node.title)}</strong><span>${esc(status)}</span></button></div>${compact?'<details class="mobile-home-connections"><summary>展开知识连接</summary>':''}${edges.slice(0,limit).map(e=>{const source=nodes.get(e.source),target=nodes.get(e.target);if(!source||!target)return '';return `<div class="mobile-graph-relation"><button data-flow-node="${esc(source.id)}">${esc(source.title)}</button><span>${esc(RELATION_LABELS[e.relation]||e.relation)} →</span><button data-flow-node="${esc(target.id)}">${esc(target.title)}</button></div>`}).join('')||'<p class="small muted">暂未记录邻接关系，先从本节点的词卡或练习开始。</p>'}<p class="small muted">点击节点查看证据与练习；只展示已记录的连接。</p>${compact?'</details>':''}</section>`}
function mobileEnhance(){const nav=document.querySelector('.mobile-nav'),open=!!document.documentElement?.classList.contains('sidebar-open');if(nav){nav.inert=open;nav.querySelector('[data-mobile-menu]')?.setAttribute('aria-expanded',String(open))}const root=document.documentElement;if(root?.dataset&&typeof view!=='undefined')root.dataset.view=view;mobileViewport();mobileChat()}
// 3.8: on phones the tutor is a chat screen: one-line input that grows, newest message in view.
let mobileChatObserver=null,mobileChatPinned=true;
function mobilePhone(){return !!window.matchMedia?.('(max-width: 640px)').matches}
function mobileChatGrow(t){if(!t)return;t.style.height='auto';t.style.height=Math.min(t.scrollHeight,Math.round((window.visualViewport?.height||window.innerHeight||600)*.4))+'px'}
function mobileChatBottom(){const h=document.querySelector('.mentor-history');if(!h)return;const last=h.lastElementChild;const composer=document.querySelector('.mentor-composer');const y=(last?last.getBoundingClientRect().bottom:0)+window.scrollY-(window.innerHeight-(composer?.offsetHeight||0)-90);if(y>window.scrollY)window.scrollTo({top:y,behavior:'auto'})}
function mobileChat(){mobileChatObserver?.disconnect();mobileChatObserver=null;const h=document.querySelector('.mentor-history'),t=document.querySelector('#coach-message');if(!h||!mobilePhone())return;if(t){t.rows=1;t.placeholder='发消息给私教…';mobileChatGrow(t)}mobileChatPinned=true;requestAnimationFrame(mobileChatBottom);if(typeof MutationObserver==='function'){mobileChatObserver=new MutationObserver(()=>{if(mobileChatPinned)mobileChatBottom()});mobileChatObserver.observe(h,{childList:true,subtree:true,characterData:true})}}
window.addEventListener('scroll',()=>{if(!mobilePhone()||!document.querySelector('.mentor-history'))return;const doc=document.documentElement;mobileChatPinned=window.innerHeight+window.scrollY>=doc.scrollHeight-160},{passive:true});
function mobileViewport(){const root=document.documentElement;if(!root)return;const viewport=window.visualViewport,small=!!window.matchMedia?.('(max-width: 760px)').matches,focused=document.activeElement,editing=!!focused?.matches?.('textarea,input:not([type=checkbox]):not([type=radio]),select');const height=viewport?.height||window.innerHeight||0,width=window.innerWidth||0;if(!small||!editing||Math.abs(width-mobileViewportWidth)>120)mobileViewportBaseline=height;else mobileViewportBaseline=Math.max(mobileViewportBaseline,window.innerHeight||height);mobileViewportWidth=width;root.style?.setProperty('--flow-visible-height',height+'px');const keyboard=small&&editing&&!!viewport&&(Math.max(window.innerHeight||0,mobileViewportBaseline)-height)>140;root.classList.toggle('mobile-keyboard',keyboard);if(keyboard&&focused?.getBoundingClientRect){const rect=focused.getBoundingClientRect();if(rect.bottom>height+(viewport.offsetTop||0)-12)focused.scrollIntoView?.({block:'nearest',behavior:'auto'})}}
const mobileRoot=document.querySelector('#app');
mobileRoot.addEventListener('click',e=>{const b=e.target.closest('button');if(b?.dataset.mobileMenu)setSidebarOpen(!document.documentElement.classList.contains('sidebar-open'),b)});
window.addEventListener('resize',mobileEnhance);
window.visualViewport?.addEventListener('resize',mobileViewport);
mobileRoot.addEventListener('focusin',mobileViewport);
mobileRoot.addEventListener('input',e=>{if(e.target?.id==='coach-message'&&mobilePhone())mobileChatGrow(e.target)});
mobileRoot.addEventListener('focusout',()=>{document.documentElement?.classList.remove('mobile-keyboard')});
/* Jasa Studio bridge: shared display preferences from jasa.hk and a way back to the main site. */
(()=>{
 try{
  const m=document.cookie.match(/(?:^|; )jasa_prefs=([^;]*)/);const p=m&&JSON.parse(decodeURIComponent(m[1]));
  let seen=0;try{seen=+localStorage.getItem('flow-prefs-t')||0}catch{}
  if(p&&p.t>seen){
   if(p.th==='light'||p.th==='dark')applyAppearance(p.th);else if(p.th==='auto')applyAppearance('system');
   if(p.m==='off'||p.m==='on'){comfortPreferences.motion=p.m==='off';try{localStorage.setItem('flow-reduce-motion',String(comfortPreferences.motion))}catch{}applyComfort()}
   try{localStorage.setItem('flow-prefs-t',String(p.t))}catch{}
  }
 }catch{}
 const link=()=>{const a=document.createElement('a');a.className='jasa-back';a.href='https://jasa.hk/';a.setAttribute('aria-label','返回 Jasa Studio');a.innerHTML='<span aria-hidden="true">←</span><span class="jb-long">Jasa Studio</span><span class="jb-short">Studio</span>';return a};
 const place=()=>{
  const bar=document.querySelector('#app .toolbar-trailing');
  if(bar){if(!bar.querySelector('.jasa-back'))bar.prepend(link());return}
  const auth=document.querySelector('#app .auth-scene');
  if(auth&&!auth.querySelector('.jasa-back'))auth.prepend(Object.assign(link(),{className:'jasa-back jb-float'}));
 };
 const root=document.querySelector('#app');
 if(root){new MutationObserver(place).observe(root,{childList:true});place()}
})();
