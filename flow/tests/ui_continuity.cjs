const fs=require('fs'),vm=require('vm'),assert=require('assert');
const store=new Map(),handlers={},root={innerHTML:'',addEventListener(k,f){(handlers[k]??=[]).push(f)},querySelector(){return null}};
const document={addEventListener(){},documentElement:{dataset:{},classList:{remove(){},contains(){return false},toggle(){}}},querySelector:k=>k==='#app'?root:k==='#toast'?{textContent:'',style:{}}:null};
const window={addEventListener(){},scrollTo(){},location:{hash:'',pathname:'/'},history:{replaceState(){},pushState(){}}};
const ctx=vm.createContext({document,window,localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)},crypto:{randomUUID:()=> 'continuity-test-001'},setTimeout(){},clearTimeout(){},console,confirm:()=>true,URLSearchParams,URL,Date,Map,RegExp});
for(const file of ['app','tutor','advanced','studio','knowledge','adaptive','coach','growth','atlas','reference','practice','continuity','foundation'])vm.runInContext(fs.readFileSync(__dirname+'/../public/'+file+'.js','utf8'),ctx);
vm.runInContext("user={id:1,username:'One'};dashboard={topics:[]}",ctx);
(async()=>{
 vm.runInContext("flowLocalPut('foundation','food','My unsynced answer');flowPoint({type:'foundation',key:'food'})",ctx);
 assert.equal(vm.runInContext("flowLocalGet('foundation','food').answer",ctx),'My unsynced answer');
 vm.runInContext('clearAccountState();user={id:2}',ctx);assert.equal(vm.runInContext("flowLocalGet('foundation','food')",ctx),null);
 vm.runInContext("user={id:1,username:'One'}",ctx);assert.equal(vm.runInContext("flowLocalGet('foundation','food').answer",ctx),'My unsynced answer');assert(vm.runInContext('flowResumeHTML()',ctx).includes('继续上次学习'));
 vm.runInContext("flowLocalDrop('foundation','food','old answer')",ctx);assert(vm.runInContext("flowLocalGet('foundation','food')",ctx));
 vm.runInContext("api=async()=>{throw Error('503')}",ctx);await vm.runInContext("openFoundation('food')",ctx);assert(root.innerHTML.includes('在这里重试'));assert(!root.innerHTML.includes('正在打开小课程'));
 ctx.lesson={lesson:'food',title:'Food',step:2,answer:'',target:'Water',options:['Water'],example:'Water',meaning:'水',note:'supported',revision:0};
 vm.runInContext("foundationData={...lesson,step:0};view='journey';api=async()=>{const e=Error('progress');e.status=409;e.payload={current:lesson};throw e}",ctx);
 await vm.runInContext("foundationSubmit('')",ctx);assert.equal(vm.runInContext('foundationData.step',ctx),2);assert.equal(vm.runInContext('foundationBusy',ctx),false);assert(root.innerHTML.includes('My unsynced answer'));
 vm.runInContext("api=async p=>p==='lab'?{profile:{focus:'writing'},packs:[]}:p.startsWith('lab/pack')?{pack:{id:'x'},metadata:{},drafts:[],feedback:{}}:p==='lab/support'?Promise.reject(Error('telemetry')):{};renderStudioPack=()=>shell('Practice ready')",ctx);
 await vm.runInContext("openStudioPack('x','writing')",ctx);assert(root.innerHTML.includes('Practice ready'));
 vm.runInContext("view='studio';studioPack={id:'x'};studioSkill='writing';flowPushReturn();view='graph';shell('Graph')",ctx);assert(root.innerHTML.includes('回到刚才的练习'));
 vm.runInContext("view='journey';foundationData={lesson:'food',step:3};api=async()=>({ok:true});var stageReturned=false;coachLoad=async()=>{stageReturned=true}",ctx);const stageClick=handlers.click.find(fn=>fn.toString().includes('dataset.foundationStage'));await stageClick({target:{closest:()=>({dataset:{foundationStage:'1'},isConnected:true})}});assert(vm.runInContext('stageReturned',ctx));
 // The actual shared request path has abort handling and preserves response payload for conflict recovery.
 const source=fs.readFileSync(__dirname+'/../public/app.js','utf8');assert(source.includes('controller.abort()'));assert(source.includes('error.payload=out'));
 vm.runInContext("api=async()=>({pack:{id:'cached'},drafts:[],metadata:{}})",ctx);await vm.runInContext("flowCachedPack('cached')",ctx);vm.runInContext("api=async()=>{throw Error('offline')}",ctx);assert((await vm.runInContext("flowCachedPack('cached')",ctx)).offline);vm.runInContext("api=async()=>{const e=Error('denied');e.status=403;throw e}",ctx);await assert.rejects(()=>vm.runInContext("flowCachedPack('cached')",ctx));
 ctx.AbortController=AbortController;let abort;ctx.setTimeout=fn=>{abort=fn;return 1};ctx.fetch=(url,opt)=>new Promise((resolve,reject)=>opt.signal.addEventListener('abort',()=>{const e=Error('timeout');e.name='AbortError';reject(e)}));vm.runInContext(source.slice(source.indexOf('async function api('),source.indexOf('\nconst brand')),ctx);const waiting=vm.runInContext("api('lab/draft',{answer:'saved locally'})",ctx);abort();await assert.rejects(()=>waiting,/输入已保留/);
 console.log('Continuity: account-scoped local drafts, login reset recovery, guarded removal, inline retry, 409 reconciliation, nonblocking content and return path: passed');
})().catch(e=>{console.error(e);process.exit(1)});
