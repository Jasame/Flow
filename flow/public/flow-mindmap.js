'use strict';
// Flow 4.4 · knowledge graph as a mind map.
// Only draws edges the server has saved (flowGraph.edges); it never infers links and never writes anything.
(function(){
  if(typeof renderFlowGraph!=='function')return;
  const app=document.querySelector('#app');
  const HIDDEN=new Set(['trains','occurs_in']);
  const ORDER=['prerequisite','has_sense','has_pattern','uses_grammar','introduced_by','practised_in','trains','occurs_in'];
  const RANK={repair:0,transfer:1,delayed:2,independent:3,observed:4,unknown:5};
  const STAT={unknown:'待了解',observed:'已有接触',repair:'需要巩固',independent:'独立通过',delayed:'延迟记得',transfer:'迁移有证据'};
  const KIND={lesson:'基础句框',word:'单词',sense:'义项',pattern:'搭配',grammar:'语法',material:'语料',skill:'技能'};
  const SHAPE={
    word:'M-5 0a5 5 0 1 0 10 0a5 5 0 1 0-10 0Z',
    sense:'M0-6 6 0 0 6-6 0Z',
    pattern:'M0-6 6 5H-6Z',
    grammar:'M-5-5h10v10h-10Z',
    material:'M-6-4h12v8h-12Z',
    skill:'M-6 0l3-5h6l3 5-3 5h-6Z',
    lesson:'M-1.6-6h3.2v4.4h4.4v3.2h-4.4V6h-3.2V1.6H-6v-3.2h4.4Z'
  };
  const MM={owner:null,center:null,open:new Map(),more:new Set(),all:false,view:null,fit:true,drawn:new Set(),visible:new Set(),drawer:true,lastSel:null,pos:new Map(),graph:null,adj:null,byid:null,tree:null,dragged:false};
  const original=renderFlowGraph;
  const reduced=()=>window.FlowMotion&&typeof window.FlowMotion.reduced==='function'?window.FlowMotion.reduced():matchMedia('(prefers-reduced-motion: reduce)').matches;
  const label=r=>(typeof RELATION_LABELS!=='undefined'&&RELATION_LABELS[r])||flowGraph?.relations?.[r]||r;
  const name=n=>typeof flowNodeName==='function'?flowNodeName({title:n.title,node:n.id}):n.title;
  const cut=(s,m)=>s.length>m?s.slice(0,m-1)+'…':s;
  const textWidth=s=>{let w=0;for(const ch of s)w+=/[⺀-鿿＀-￯　-〿]/.test(ch)?13.2:7.4;return w};

  function adjacency(){
    if(MM.graph===flowGraph&&MM.adj)return MM.adj;
    const adj=new Map();
    for(const e of flowGraph.edges){
      for(const [a,b,dir] of [[e.source,e.target,1],[e.target,e.source,-1]]){
        if(!adj.has(a))adj.set(a,[]);
        adj.get(a).push({id:b,rel:e.relation,dir});
      }
    }
    MM.graph=flowGraph;MM.adj=adj;MM.byid=new Map(flowGraph.nodes.map(n=>[n.id,n]));
    return adj;
  }
  function neighbours(id,seen){
    const out=[],ids=new Set();
    for(const x of MM.adj.get(id)||[]){
      if((!MM.all&&HIDDEN.has(x.rel))||!MM.byid.has(x.id)||ids.has(x.id)||(seen&&seen.has(x.id)))continue;
      ids.add(x.id);out.push(x);
    }
    return out.sort((a,b)=>ORDER.indexOf(a.rel)-ORDER.indexOf(b.rel)||(RANK[MM.byid.get(a.id).status]??6)-(RANK[MM.byid.get(b.id).status]??6)||MM.byid.get(a.id).title.localeCompare(MM.byid.get(b.id).title));
  }
  function build(){
    adjacency();
    const root={id:MM.center,node:MM.byid.get(MM.center),depth:0,children:[],parent:null};
    const seen=new Set([root.id]),list=[root],queue=[root];
    while(queue.length){
      const t=queue.shift(),all=neighbours(t.id,seen),state=MM.open.get(t.id);
      let cap;
      if(state==='closed')cap=0;
      else if(state==='open'||t.depth===0)cap=MM.more.has(t.id)?40:8;
      else cap=t.depth===1&&list.length<24?2:0;
      for(const x of all.slice(0,cap)){
        seen.add(x.id);
        const c={id:x.id,node:MM.byid.get(x.id),depth:t.depth+1,children:[],parent:t,rel:x.rel,dir:x.dir};
        t.children.push(c);list.push(c);queue.push(c);
      }
      t.extra=all.length-t.children.length;
    }
    // real edges between visible nodes that the tree does not already draw
    const ids=new Map(list.map(t=>[t.id,t])),tree=new Set(list.filter(t=>t.parent).map(t=>t.parent.id+'|'+t.id)),cross=[];
    for(const e of flowGraph.edges){
      if(cross.length>=40)break;
      if((!MM.all&&HIDDEN.has(e.relation))||!ids.has(e.source)||!ids.has(e.target)||e.source===e.target)continue;
      if(tree.has(e.source+'|'+e.target)||tree.has(e.target+'|'+e.source))continue;
      if(cross.some(c=>c.a===e.source&&c.b===e.target||c.a===e.target&&c.b===e.source))continue;
      cross.push({a:e.source,b:e.target,rel:e.relation});
    }
    return {root,list,ids,cross};
  }
  function layout(tree){
    for(const t of tree.list){
      const title=cut(name(t.node),t.depth?14:20);
      t.label=title;t.h=t.depth?30:42;t.w=Math.round(textWidth(title)+(t.depth?40:52));
    }
    const leaves=t=>t.leaves=t.children.length?t.children.reduce((s,c)=>s+leaves(c),0):1;
    leaves(tree.root);
    const root=tree.root,sides=[[],[]],load=[0,0];
    root.children.forEach(c=>{const k=load[0]<=load[1]?0:1;sides[k].push(c);load[k]+=c.leaves});
    root.x=0;root.y=0;root.side=0;
    const ROW=40,GAP=48;
    for(const [k,list] of sides.entries()){
      const side=k===0?1:-1;let row=0;
      const place=(t,parent)=>{
        t.side=side;t.x=parent.x+side*(parent.w/2+GAP+t.w/2);
        if(!t.children.length){t.y=row*ROW;row++;return}
        for(const c of t.children)place(c,t);
        t.y=(t.children[0].y+t.children[t.children.length-1].y)/2;
      };
      for(const c of list)place(c,root);
      const shift=(row-1)*ROW/2,move=t=>{t.y-=shift;t.children.forEach(move)};
      list.forEach(move);
    }
  }
  function bbox(list){
    let x0=Infinity,y0=Infinity,x1=-Infinity,y1=-Infinity;
    for(const t of list){x0=Math.min(x0,t.x-t.w/2-14);x1=Math.max(x1,t.x+t.w/2+14);y0=Math.min(y0,t.y-t.h/2);y1=Math.max(y1,t.y+t.h/2)}
    return {x0,y0,x1,y1};
  }
  function linkPath(t){
    const p=t.parent,side=t.side,sx=p.x+side*p.w/2,sy=p.y,ex=t.x-side*t.w/2,ey=t.y,dx=Math.max(18,Math.abs(ex-sx)*.55)*side;
    return {d:`M${sx.toFixed(1)} ${sy.toFixed(1)}C${(sx+dx).toFixed(1)} ${sy.toFixed(1)} ${(ex-dx).toFixed(1)} ${ey.toFixed(1)} ${ex.toFixed(1)} ${ey.toFixed(1)}`,mx:(sx+ex)/2,my:(sy+ey)/2};
  }
  function nodeSVG(t,sel,isNew,index){
    const n=t.node,status=n.kind==='material'?'material':(n.status||'unknown'),p=t.parent;
    const was=!isNew&&MM.pos.get(t.id),move=was&&Math.hypot(was[0]-t.x,was[1]-t.y)>1;
    const dx=move?Math.round(was[0]-t.x):isNew&&p?Math.round(p.x-t.x):0,dy=move?Math.round(was[1]-t.y):isNew&&p?Math.round(p.y-t.y):0,delay=move?0:Math.min(520,t.depth*110+index*14);
    const side=t.side||1,tog=t.extra>0||t.children.length&&t.depth;
    const togX=t.depth?side*(t.w/2+12):t.w/2+12;
    const togText=t.extra>0?'+'+(t.extra>99?'99':t.extra):'−';
    const aria=`${name(n)}，${KIND[n.kind]||'节点'}，${n.kind==='material'?'教学语料':STAT[n.status]||'待了解'}${t.rel?'，'+label(t.rel):''}`;
    return `<g class="mm-node k-${esc(n.kind)} s-${esc(status)}${t.depth?'':' is-center'}${n.id===sel?' is-sel':''}${isNew?' is-new':''}${move?' is-move':''}" transform="translate(${t.x.toFixed(1)} ${t.y.toFixed(1)})" data-mm-id="${esc(n.id)}">`+
      `<g class="mm-pop" data-dx="${dx}" data-dy="${dy}" data-delay="${delay}">`+
      `<g class="mm-hit" data-flow-node="${esc(n.id)}" role="button" tabindex="0" aria-label="${esc(aria)}">`+
      (n.id===sel?`<rect class="mm-ring" x="${-t.w/2-5}" y="${-t.h/2-5}" width="${t.w+10}" height="${t.h+10}" rx="${t.h/2+5}"/>`:'')+
      `<rect class="mm-pill" x="${-t.w/2}" y="${-t.h/2}" width="${t.w}" height="${t.h}" rx="${t.h/2}"/>`+
      `<path class="mm-shape" transform="translate(${-t.w/2+(t.depth?17:22)} 0)${t.depth?'':' scale(1.2)'}" d="${SHAPE[n.kind]||SHAPE.word}"/>`+
      `<text x="${-t.w/2+(t.depth?29:36)}" y="${t.depth?4.5:5.5}">${esc(t.label)}</text>`+
      `<title>${esc(aria)}</title></g>`+
      (tog?`<g class="mm-tog" transform="translate(${togX.toFixed(1)} 0)" data-mm-toggle="${esc(n.id)}" role="button" tabindex="0" aria-label="${t.extra>0?'展开另外 '+t.extra+' 个连接':'收起这一支'}"><circle r="10"/><text y="3.8">${togText}</text></g>`:'')+
      `</g></g>`;
  }
  const arc=(a,b)=>{const mx=(a.x+b.x)/2,my=(a.y+b.y)/2,cy=my-Math.min(80,Math.abs(a.x-b.x)*.18+24);return `M${a.x.toFixed(1)} ${a.y.toFixed(1)}Q${mx.toFixed(1)} ${cy.toFixed(1)} ${b.x.toFixed(1)} ${b.y.toFixed(1)}`};
  function canvasSVG(tree,sel){
    const links=tree.list.filter(t=>t.parent).map((t,i)=>{
      const {d,mx,my}=linkPath(t),src=t.dir===1?t.parent.node:t.node,dst=t.dir===1?t.node:t.parent.node,isNew=!MM.drawn.has(t.id),moved=!isNew&&MM.pos.size&&MM.moved;
      return `<g class="mm-link r-${esc(t.rel)}${isNew?' is-new':''}${moved?' is-move':''}" data-a="${esc(t.parent.id)}" data-b="${esc(t.id)}"><path class="mm-wire" d="${d}" pathLength="1" data-delay="${Math.min(480,t.depth*110+i*10)}" ${t.dir===1?'marker-end':'marker-start'}="url(#mm-arrow)"/><path class="mm-wire-hit" d="${d}"/><text class="mm-elabel" x="${mx.toFixed(1)}" y="${(my+4).toFixed(1)}" text-anchor="middle">${esc(label(t.rel))}</text><title>${esc(name(src))} → ${esc(label(t.rel))} → ${esc(name(dst))}</title></g>`;
    }).join('');
    const cross=tree.cross.map(c=>{
      const a=tree.ids.get(c.a),b=tree.ids.get(c.b);
      return `<g class="mm-link mm-cross" data-a="${esc(c.a)}" data-b="${esc(c.b)}"><path class="mm-wire" d="${arc(a,b)}"/><path class="mm-wire-hit" d="${arc(a,b)}"/><text class="mm-elabel" x="${((a.x+b.x)/2).toFixed(1)}" y="${((a.y+b.y)/2-Math.min(40,Math.abs(a.x-b.x)*.09+12)+4).toFixed(1)}" text-anchor="middle">${esc(label(c.rel))}</text><title>${esc(name(a.node))} → ${esc(label(c.rel))} → ${esc(name(b.node))}</title></g>`;
    }).join('');
    const order=[...tree.list].sort((a,b)=>b.depth-a.depth);
    const nodes=order.map((t,i)=>nodeSVG(t,sel,!MM.drawn.has(t.id),tree.list.indexOf(t))).join('');
    return `<svg class="mm-svg" viewBox="-600 -300 1200 600" role="group" aria-label="知识思维导图：以 ${esc(name(tree.root.node))} 为中心，只画已保存的连接"><defs><marker id="mm-arrow" viewBox="0 0 8 8" markerWidth="7" markerHeight="7" refX="7" refY="4" orient="auto-start-reverse"><path d="M0 0 8 4 0 8Z"/></marker></defs><g class="mm-world">${cross}${links}${nodes}</g></svg>`;
  }
  function treeHTML(t,sel){
    const n=t.node,status=n.kind==='material'?'material':(n.status||'unknown'),open=t.children.length>0;
    const toggle=t.extra>0||t.children.length&&t.depth?`<button class="mm-ttog" data-mm-toggle="${esc(n.id)}" aria-expanded="${open&&!t.extra}" aria-label="${t.extra>0?'展开另外 '+t.extra+' 个连接':'收起这一支'}">${t.extra>0?'+'+t.extra:'−'}</button>`:'<span class="mm-ttog-pad"></span>';
    return `<li class="s-${esc(status)}"><div class="mm-trow">${toggle}<button class="mm-tnode${n.id===sel?' is-sel':''}${t.depth?'':' is-center'}" data-flow-node="${esc(n.id)}" aria-current="${n.id===sel}"><svg class="mm-tshape k-${esc(n.kind)}" viewBox="-7 -7 14 14" aria-hidden="true"><path d="${SHAPE[n.kind]||SHAPE.word}"/></svg><span>${t.rel?`<small>${esc(label(t.rel))}</small>`:''}<strong>${esc(name(n))}</strong></span></button></div>${open?`<ul>${t.children.map(c=>treeHTML(c,sel)).join('')}</ul>`:''}</li>`;
  }
  function primaryAction(d){
    const n=d.node;
    if(d.entry)return `<button class="btn" data-flow-word="${esc(d.entry.id)}">进入词卡 →</button>`;
    if(n.kind==='grammar')return `<button class="btn" data-flow-start="grammar" data-flow-grammar="${esc(n.id)}">验证这个知识点 →</button>`;
    if(n.kind==='material')return `<button class="btn" data-studio-pack="${esc(n.ref)}">进入听说读写 →</button>`;
    if(n.kind==='lesson')return `<button class="btn" data-foundation-lesson="${esc(n.ref)}">练习这个句框 →</button>`;
    if(n.kind==='skill')return '<button class="btn" data-view="studio">选择语料训练 →</button>';
    return '';
  }
  function drawerHTML(d){
    const n=d.node,s=d.state||{},rels=neighbours(n.id).slice(0,6),status=n.kind==='material'?'material':(n.status||'unknown');
    const open=MM.tree&&MM.tree.ids.get(n.id),hasKids=open&&open.children.length>0;
    return `<aside class="mm-drawer${MM.drawer?' is-open':''}" aria-label="节点详情" ${MM.drawer?'':'hidden'}><button class="mm-close" data-mm-drawer="0" aria-label="收起详情">×</button><p class="eyebrow"><i class="mm-dot s-${esc(status)}"></i>${esc(KIND[n.kind]||'节点')} · ${esc(n.kind==='material'?'教学语料':s.state||STAT[n.status]||'待了解')}</p><h3>${esc(name(n))}</h3>${n.kind==='material'?'':`<dl class="mm-evi"><div><dt>独立通过</dt><dd>${s.independent||0}</dd></div><div><dt>延迟记得</dt><dd>${s.delayed||0}</dd></div><div><dt>迁移</dt><dd>${s.transfer||0}</dd></div></dl>`}<div class="mm-actions">${primaryAction(d)}<div class="mm-actions-row">${n.id!==MM.center?`<button class="quiet-button" data-mm-center="${esc(n.id)}">以它为中心</button>`:''}${open&&(open.extra>0||hasKids&&open.depth)?`<button class="quiet-button" data-mm-toggle="${esc(n.id)}">${open.extra>0?'展开分支':'收起分支'}</button>`:''}<button class="text-button" data-mm-detail="1">完整证据 ↓</button></div></div>${rels.length?`<p class="mm-rels-title small muted">相连的节点</p><div class="mm-rels">${rels.map(x=>`<button data-flow-node="${esc(x.id)}"><small>${esc(label(x.rel))} ${x.dir===1?'→':'←'}</small>${esc(cut(name(MM.byid.get(x.id)),18))}</button>`).join('')}</div>`:'<p class="small muted">还没有保存的连接。</p>'}</aside>`;
  }
  function legendHTML(){
    return `<div class="mm-legend" aria-label="图例"><span class="mm-legend-group">${['repair','unknown','observed','independent','delayed','transfer'].map(k=>`<span><i class="mm-dot s-${k}"></i>${STAT[k]}</span>`).join('')}</span><span class="mm-legend-group">${['word','sense','pattern','grammar','material','skill','lesson'].map(k=>`<span><svg viewBox="-7 -7 14 14" aria-hidden="true"><path d="${SHAPE[k]}"/></svg>${KIND[k]}</span>`).join('')}</span></div>`;
  }
  function sectionHTML(tree,d){
    const sel=d.node.id,hiddenCount=MM.all?0:(MM.adj.get(MM.center)||[]).filter(x=>HIDDEN.has(x.rel)).length;
    return `<section class="card mm-card" aria-label="知识思维导图"><div class="mm-head"><div><p class="eyebrow">思维导图</p><h2>从「${esc(cut(name(tree.root.node),20))}」出发</h2><p class="small muted">点节点看详情，点 + 展开。显示 ${tree.list.length} 个节点，图谱共 ${flowGraph.nodes.length} 个。</p></div><div class="mm-tools"><button class="quiet-button" data-mm-all="1" aria-pressed="${MM.all}">${MM.all?'隐藏':'显示'}训练与原文匹配连线${!MM.all&&hiddenCount?` · ${hiddenCount}`:''}</button><span class="mm-zoom" role="group" aria-label="缩放"><button class="quiet-button" data-mm-zoom="out" aria-label="缩小">−</button><button class="quiet-button" data-mm-zoom="in" aria-label="放大">+</button><button class="quiet-button" data-mm-zoom="fit">回到中心</button></span></div></div><div class="mm-body"><div class="mm-stage">${canvasSVG(tree,sel)}<p class="mm-hint small muted">拖动画布移动，按住 ⌘ 或 Ctrl 滚动缩放</p></div><div class="mm-tree-wrap"><ul class="mm-tree">${treeHTML(tree.root,sel)}</ul></div>${drawerHTML(d)}</div>${legendHTML()}<details class="mm-notes"><summary>说明</summary><p>只画系统里已保存的连线，不让 AI 猜测新的连接。颜色是你在这个节点上的记录，形状是节点类型；位置不表示学习顺序。“训练方式”和“原文词形匹配”两类连线很多，默认隐藏，可以用上面的按钮打开。相邻节点不会因为连在一起就自动算通过。</p></details></section>`;
  }
  function foldNotes(section){
    const box=section.querySelector('.mm-notes');
    const picks=[...app.querySelectorAll('.flow-graph-canvas>p.small.muted,.atlas-focus>p.small.muted:last-child,.atlas-summary+p.small.muted,p.section-note')];
    for(const p of picks){p.classList.add('mm-folded');box.appendChild(p)}
    app.querySelectorAll('.flow-graph-canvas details.atlas-explore').forEach(x=>x.remove());
    const canvas=app.querySelector('.flow-graph-canvas');
    if(canvas){const eb=canvas.querySelector(':scope>.eyebrow');if(eb)eb.textContent=(KIND[flowGraphDetail.node.kind]||'节点')+' · 完整详情'}
  }

  // ---------- pan & zoom ----------
  function fitView(stage,tree){
    const w=stage.clientWidth||900,h=stage.clientHeight||520,b=bbox(tree.list),bw=b.x1-b.x0,bh=b.y1-b.y0;
    const drawer=MM.drawer&&stage.parentElement.querySelector('.mm-drawer.is-open')&&w>760?292:0;
    const k=Math.max(w<700?.62:.78,Math.min(1.05,(w-drawer-40)/bw,(h-40)/bh));
    const x=Math.max(-w/2+120,Math.min(w/2-drawer-120,-((b.x0+b.x1)/2)*k-drawer/2)),y=Math.max(-h/2+60,Math.min(h/2-60,-((b.y0+b.y1)/2)*k));
    return {k,x,y};
  }
  function applyView(svg){
    const w=svg.clientWidth||900,h=svg.clientHeight||520;
    svg.setAttribute('viewBox',`${-w/2} ${-h/2} ${w} ${h}`);
    const v=MM.view;svg.querySelector('.mm-world').setAttribute('transform',`translate(${v.x.toFixed(1)} ${v.y.toFixed(1)}) scale(${v.k.toFixed(3)})`);
  }
  function zoomAt(svg,factor,cx=0,cy=0){
    const v=MM.view,k=Math.max(.3,Math.min(2.4,v.k*factor)),f=k/v.k;
    v.x=cx-(cx-v.x)*f;v.y=cy-(cy-v.y)*f;v.k=k;applyView(svg);
  }
  function wire(section){
    const stage=section.querySelector('.mm-stage'),svg=section.querySelector('.mm-svg');
    if(!svg)return;
    const prev=MM.view;
    if(MM.fit||!MM.view){MM.view=fitView(stage,MM.tree);MM.fit=false}
    if(MM.ease&&prev&&!reduced()){const target=MM.view;MM.view=prev;applyView(svg);svg.getBoundingClientRect();svg.classList.add('is-easing');MM.view=target;requestAnimationFrame(()=>{applyView(svg);setTimeout(()=>svg.classList.remove('is-easing'),450)})}
    else applyView(svg);
    MM.ease=false;
    const pointers=new Map();let start=null,pinch=null;
    const local=e=>{const r=svg.getBoundingClientRect();return [e.clientX-r.left-r.width/2,e.clientY-r.top-r.height/2]};
    svg.addEventListener('pointerdown',e=>{
      if(e.button!==0&&e.pointerType==='mouse')return;
      pointers.set(e.pointerId,local(e));
      if(pointers.size===1){start={p:local(e),x:MM.view.x,y:MM.view.y,moved:false};MM.dragged=false}
      if(pointers.size===2){const [a,b]=[...pointers.values()];pinch={dist:Math.hypot(a[0]-b[0],a[1]-b[1]),k:MM.view.k}}
    });
    svg.addEventListener('pointermove',e=>{
      if(!pointers.has(e.pointerId))return;
      pointers.set(e.pointerId,local(e));
      if(pinch&&pointers.size===2){const [a,b]=[...pointers.values()],dist=Math.hypot(a[0]-b[0],a[1]-b[1]);zoomAt(svg,pinch.k*dist/pinch.dist/MM.view.k,(a[0]+b[0])/2,(a[1]+b[1])/2);MM.dragged=true;return}
      if(!start)return;
      const [x,y]=local(e),dx=x-start.p[0],dy=y-start.p[1];
      if(!start.moved&&Math.hypot(dx,dy)<5)return;
      if(!start.moved){start.moved=true;MM.dragged=true;svg.setPointerCapture?.(e.pointerId);svg.classList.add('is-dragging')}
      MM.view.x=start.x+dx;MM.view.y=start.y+dy;applyView(svg);
    });
    const end=e=>{pointers.delete(e.pointerId);if(pointers.size<2)pinch=null;if(!pointers.size){start=null;svg.classList.remove('is-dragging');setTimeout(()=>{MM.dragged=false},0)}};
    svg.addEventListener('pointerup',end);svg.addEventListener('pointercancel',end);
    svg.addEventListener('wheel',e=>{if(!e.ctrlKey&&!e.metaKey)return;e.preventDefault();const [x,y]=local(e);zoomAt(svg,Math.exp(-e.deltaY*.0025),x,y)},{passive:false});
    svg.addEventListener('pointerover',e=>{const g=e.target.closest?.('.mm-node');if(!g)return;const id=g.dataset.mmId;svg.querySelectorAll('.mm-link').forEach(l=>l.classList.toggle('is-hot',l.dataset.a===id||l.dataset.b===id))});
    svg.addEventListener('pointerleave',()=>svg.querySelectorAll('.mm-link.is-hot').forEach(l=>l.classList.remove('is-hot')));
    if(typeof ResizeObserver==='function'){const ro=new ResizeObserver(()=>{if(!svg.isConnected){ro.disconnect();return}applyView(svg)});ro.observe(svg)}
    if(reduced())section.classList.add('mm-still');
  }

  function decorate(){
    if(!flowGraph||!flowGraphDetail||!app)return;
    const head=app.querySelector('.flow-library-head');if(!head)return;
    if(MM.owner!==user?.id){MM.owner=user?.id;MM.center=null;MM.open.clear();MM.more.clear();MM.drawn=new Set();MM.view=null}
    adjacency();
    const sel=flowGraphDetail.node.id;
    if(!MM.center||!MM.byid.has(MM.center)){
      const a=flowGraph.focus?.anchors?.[0];MM.center=MM.byid.has(a)?a:sel;MM.fit=true;
    }
    if(sel!==MM.lastSel){
      if(MM.byid.has(sel)&&!MM.visible.has(sel)&&sel!==MM.center){MM.center=sel;MM.open.clear();MM.more.clear();MM.fit=true}
      MM.drawer=true;
    }
    MM.lastSel=sel;
    const tree=build();layout(tree);MM.tree=tree;
    MM.moved=tree.list.some(t=>{const w=MM.pos.get(t.id);return w&&Math.hypot(w[0]-t.x,w[1]-t.y)>1});
    const wrap=document.createElement('div');wrap.innerHTML=sectionHTML(tree,flowGraphDetail);
    const section=wrap.firstElementChild;head.after(section);
    foldNotes(section);
    section.querySelectorAll('[data-delay]').forEach(el=>{const st=el.style;if(el.dataset.dx!=null){st.setProperty('--dx',el.dataset.dx+'px');st.setProperty('--dy',el.dataset.dy+'px')}st.animationDelay=el.dataset.delay+'ms'});
    wire(section);
    if(MM.reveal){MM.reveal=false;section.querySelector('.mm-drawer')?.scrollIntoView({block:'nearest',behavior:reduced()?'auto':'smooth'})}
    MM.drawn=new Set(tree.list.map(t=>t.id));MM.visible=MM.drawn;MM.pos=new Map(tree.list.map(t=>[t.id,[t.x,t.y]]));MM.moved=false;
  }
  function redraw(){renderFlowGraph()}

  renderFlowGraph=function(){original.apply(this,arguments);try{decorate()}catch(err){console.error('mindmap',err)}};

  // drag should never turn into a click
  app?.addEventListener('click',e=>{if(e.target.closest?.('.mm-card [data-flow-node]')){MM.drawer=true;MM.reveal=!!e.target.closest('.mm-tree')}},true);
  app?.addEventListener('click',e=>{if(MM.dragged&&e.target.closest?.('.mm-svg')){e.preventDefault();e.stopImmediatePropagation();MM.dragged=false}},true);
  app?.addEventListener('click',e=>{
    const t=e.target.closest?.('[data-mm-toggle],[data-mm-center],[data-mm-all],[data-mm-zoom],[data-mm-drawer],[data-mm-detail]');
    if(!t||!app.querySelector('.mm-card'))return;
    const svg=app.querySelector('.mm-svg');
    if(t.dataset.mmToggle){
      const id=t.dataset.mmToggle,node=MM.tree?.ids.get(id);if(!node)return;
      if(node.extra>0){if(node.children.length&&(MM.open.get(id)==='open'||node.depth===0))MM.more.add(id);MM.open.set(id,'open')}
      else{MM.open.set(id,'closed');MM.more.delete(id)}
      MM.fit=true;MM.ease=true;redraw();return;
    }
    if(t.dataset.mmCenter){
      const id=t.dataset.mmCenter;MM.center=id;MM.open.clear();MM.more.clear();MM.fit=true;MM.drawn=new Set();MM.visible=new Set([id]);redraw();return;
    }
    if(t.dataset.mmAll){MM.all=!MM.all;MM.fit=true;redraw();return}
    if(t.dataset.mmZoom&&svg){
      if(t.dataset.mmZoom==='fit'){MM.view=fitView(app.querySelector('.mm-stage'),MM.tree);applyView(svg);svg.classList.add('is-easing');setTimeout(()=>svg.classList.remove('is-easing'),400)}
      else zoomAt(svg,t.dataset.mmZoom==='in'?1.25:.8);
      return;
    }
    if(t.dataset.mmDrawer){MM.drawer=false;const d=app.querySelector('.mm-drawer');if(d){d.classList.remove('is-open');d.hidden=true}return}
    if(t.dataset.mmDetail){app.querySelector('.flow-graph-layout')?.scrollIntoView({behavior:reduced()?'auto':'smooth',block:'start'})}
  });
  app?.addEventListener('keydown',e=>{
    if((e.key==='Enter'||e.key===' ')&&e.target.matches?.('g[data-mm-toggle]')){e.preventDefault();e.target.dispatchEvent(new MouseEvent('click',{bubbles:true}))}
    if(e.key==='Escape'&&app.querySelector('.mm-drawer.is-open')){MM.drawer=false;const d=app.querySelector('.mm-drawer');d.classList.remove('is-open');d.hidden=true}
  });
  window.FlowMindmap={state:MM};
})();
