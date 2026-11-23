'use strict';
/* Flow 4.2 motion layer. Watches #app renders and adds motion only when the page really changes
   (the app re-renders the whole shell on many clicks, so plain CSS entrance animations would replay).
   Never changes content or behaviour; everything is skipped when the visitor asks for less motion. */
(()=>{
  if(typeof window==='undefined'||!document.querySelector||window.FlowMotion)return;
  const root=document.documentElement,app=document.querySelector('#app');
  if(!app)return;
  const reduced=()=>root.dataset.motion==='reduced'||(typeof matchMedia==='function'&&matchMedia('(prefers-reduced-motion: reduce)').matches);
  const state={key:'',page:null,navTop:null,navLeft:null,progress:new Map(),seen:new Set()};

  const routeKey=pc=>{
    const v=typeof view!=='undefined'?view:'';
    const h=pc.querySelector('h1');
    return v+'|'+location.hash+'|'+(h?h.textContent.trim().slice(0,60):'');
  };
  const isPlaceholder=pc=>!!pc.querySelector('.loading')&&pc.children.length<=2;

  // ---- page entrance: stagger the first level of blocks (or the cards of a first-level grid)
  function enter(pc){
    const items=[];
    for(const child of pc.children){
      if(items.length>=12)break;
      const cs=getComputedStyle(child);
      const kids=[...child.children];
      if((cs.display==='grid'||cs.display==='flex')&&kids.length>=2&&kids.length<=8&&child.offsetHeight>120){items.push(...kids)}
      else items.push(child);
    }
    items.slice(0,12).forEach((el,i)=>{el.classList.add('fm-in');el.style.setProperty('--fm-i',i)});
    pc.setAttribute('data-fm-enter','');
    setTimeout(()=>{pc.removeAttribute('data-fm-enter');items.forEach(el=>{el.classList.remove('fm-in');el.style.removeProperty('--fm-i')})},1100);
  }

  // ---- numbers count up from 0 on page entrance (only large stand-alone numbers)
  const NUM=/^(\D{0,4}?)(\d{1,6})(.{0,12})$/;
  function countUp(pc){
    const els=[...pc.querySelectorAll('strong,b,span,div,p,.num')].filter(el=>{
      if(el.children.length>1||(el.children.length===1&&el.firstElementChild.tagName!=='SMALL'))return false;
      const node=el.firstChild;if(!node||node.nodeType!==3)return false;
      const t=node.textContent.trim();if(!NUM.test(t)||/\d[.:]\d/.test(t))return false;
      return parseFloat(getComputedStyle(el).fontSize)>=20&&el.getClientRects().length>0;
    }).slice(0,8);
    for(const el of els){
      const node=el.firstChild,orig=node.textContent,m=orig.trim().match(NUM),end=+m[2];
      if(end<2)continue;
      const lead=orig.slice(0,orig.indexOf(m[0])),start=performance.now(),dur=Math.min(900,420+end*6);
      const tick=now=>{
        if(!node.isConnected)return;
        const p=Math.min(1,(now-start)/dur),e=1-Math.pow(1-p,3);
        node.textContent=p<1?lead+m[1]+Math.round(end*e)+m[3]:orig;
        if(p<1)requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }
  }

  // ---- progress bars slide from their previous value (or from 0 on entrance)
  function progress(pc,entering){
    pc.querySelectorAll('progress').forEach((el,i)=>{
      const key=(el.getAttribute('aria-label')||el.className||'p')+'#'+i;
      const max=+el.max||1,val=+el.value,ratio=val/max;
      const before=state.progress.get(key);
      state.progress.set(key,ratio);
      const from=before!==undefined?before:(entering?0:null);
      if(from===null||from>=ratio)return;
      el.value=from*max;el.classList.add('fm-progress');
      requestAnimationFrame(()=>requestAnimationFrame(()=>{el.value=val}));
    });
  }

  // ---- active navigation highlight slides between items
  function navSlide(){
    const side=document.querySelector('.sidebar .nav.active');
    if(side){
      const top=side.getBoundingClientRect().top;
      if(state.navTop!==null&&Math.abs(state.navTop-top)>2&&Math.abs(state.navTop-top)<700){
        side.style.setProperty('--fm-dy',(state.navTop-top)+'px');side.classList.add('fm-slide');
        setTimeout(()=>side.classList.remove('fm-slide'),450);
      }
      state.navTop=top;
    }
    const tab=document.querySelector('.mobile-nav button[aria-current=page]');
    if(tab){
      const left=tab.getBoundingClientRect().left;
      if(state.navLeft!==null&&Math.abs(state.navLeft-left)>2){
        tab.style.setProperty('--fm-dx',(state.navLeft-left)+'px');tab.classList.add('fm-slide');
        setTimeout(()=>tab.classList.remove('fm-slide'),450);
      }
      state.navLeft=left;
    }
  }

  // ---- a small burst of confetti when an answer is right
  const COLORS=['#1f9d55','#5fd394','#a7e8c4','#f2c94c','#ffffff'];
  function burst(el){
    const r=el.getBoundingClientRect();if(!r.width)return;
    const x=r.left+Math.min(r.width/2,140),y=r.top+18,layer=document.createElement('div');
    layer.className='fm-burst';layer.setAttribute('aria-hidden','true');
    for(let i=0;i<24;i++){
      const s=document.createElement('i'),a=(Math.PI*2*i)/24+Math.random()*.4,d=60+Math.random()*90;
      s.style.left=x+'px';s.style.top=y+'px';s.style.background=COLORS[i%COLORS.length];
      if(i%3===0)s.style.borderRadius='50%';
      layer.appendChild(s);
      s.animate([
        {transform:'translate(-50%,-50%) scale(.6) rotate(0deg)',opacity:1},
        {transform:`translate(calc(-50% + ${Math.cos(a)*d}px),calc(-50% + ${Math.sin(a)*d-30}px)) scale(1) rotate(${Math.random()*360}deg)`,opacity:1,offset:.6},
        {transform:`translate(calc(-50% + ${Math.cos(a)*d*1.15}px),calc(-50% + ${Math.sin(a)*d+40}px)) scale(.8) rotate(${Math.random()*540}deg)`,opacity:0}
      ],{duration:900+Math.random()*300,easing:'cubic-bezier(.2,.7,.3,1)',fill:'forwards'});
    }
    document.body.appendChild(layer);
    setTimeout(()=>layer.remove(),1400);
  }
  const GOOD='.flow-result.is-correct,.pilot-fb.ok';
  function celebrate(scope){
    scope.querySelectorAll(GOOD).forEach(el=>{
      const sig=(typeof view!=='undefined'?view:'')+'|'+el.textContent.trim().slice(0,120);
      if(state.seen.has(sig))return;
      state.seen.add(sig);if(state.seen.size>60)state.seen.delete(state.seen.values().next().value);
      el.classList.add('fm-win');burst(el);
    });
    // quiz summary: celebrate once when most answers are right
    const res=scope.querySelectorAll('.result>.correct,.result>.wrong');
    if(res.length){
      const sig='quiz|'+location.hash+'|'+res.length+'|'+[...res].map(x=>x.className[0]).join('');
      if(!state.seen.has(sig)){
        state.seen.add(sig);
        const good=scope.querySelectorAll('.result>.correct').length;
        if(good/res.length>=.6)burst(res[0].closest('.result')||res[0]);
      }
    }
  }

  // ---- render hook
  let queued=false;
  function onRender(){
    queued=false;
    const pc=app.querySelector('.page-content');
    const motion=!reduced();
    if(pc&&!isPlaceholder(pc)){
      const key=routeKey(pc),entering=key!==state.key;
      if(motion){
        if(entering){enter(pc);countUp(pc)}
        progress(pc,entering);
        navSlide();
        celebrate(pc);
      }else{state.navTop=null;state.navLeft=null}
      state.key=key;state.page=pc;
    }else if(!pc&&motion){
      celebrate(app);
    }
  }
  new MutationObserver(()=>{if(!queued){queued=true;requestAnimationFrame(onRender)}}).observe(app,{childList:true,subtree:true});

  // ---- topbar gets a soft shadow once the page scrolls
  let ticking=false;
  addEventListener('scroll',()=>{
    if(ticking)return;ticking=true;
    requestAnimationFrame(()=>{ticking=false;root.toggleAttribute('data-fm-scrolled',scrollY>6)});
  },{passive:true});

  window.FlowMotion={burst,reduced};
})();
