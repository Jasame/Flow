const fs=require('fs'),vm=require('vm'),assert=require('assert');
const store=new Map(),root={innerHTML:'',addEventListener(){},querySelector(){return null}},document={documentElement:{dataset:{},classList:{remove(){},contains(){return false},toggle(){}}},querySelector:k=>k==='#app'?root:k==='#toast'?{textContent:'',style:{}}:null};
const window={addEventListener(){},scrollTo(){},location:{hash:'',pathname:'/'},history:{replaceState(){},pushState(x,y,h){window.location.hash=h}}};
const ctx=vm.createContext({document,window,localStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)},crypto:{randomUUID:()=> 'ui-merge-00001'},setTimeout(){},clearTimeout(){},console,confirm:()=>true,URLSearchParams,URL,Date,Map,RegExp});
for(const file of ['app','tutor','advanced','studio','knowledge','adaptive','coach','growth'])vm.runInContext(fs.readFileSync(__dirname+'/../public/'+file+'.js','utf8'),ctx);
vm.runInContext("user={id:1,username:'Learner',admin:0};dashboard={wrong_count:0,total:0,topics:[]};api=async()=>dashboard;var visited='';vocabLibrary=async()=>{visited='vocab';shell('<h1>词汇检查</h1>')};startAdaptive=async()=>{visited='journey';shell('<h1>自适应检查</h1>')}",ctx);
(async()=>{
 await vm.runInContext("navigate('vocab')",ctx);assert.equal(vm.runInContext('visited',ctx),'vocab');assert(root.innerHTML.includes('词汇检查'));assert(!root.innerHTML.includes('暂时无法加载'));
 await vm.runInContext("navigate('journey')",ctx);assert.equal(vm.runInContext('visited',ctx),'journey');assert(!root.innerHTML.includes('暂时无法加载'));
 vm.runInContext("applyAppearance('dark');comfortPreferences.motion=true;applyComfort()",ctx);assert.equal(document.documentElement.dataset.theme,'dark');assert.equal(document.documentElement.dataset.motion,'reduced');assert.equal(store.get('flow-appearance'),'dark');
 vm.runInContext("coachData={private:'old'};coachDraft='old';flowWord={private:'old'};growthQuality=[{private:'old'}];clearAccountState()",ctx);assert.equal(vm.runInContext('coachData',ctx),null);assert.equal(vm.runInContext('flowWord',ctx),null);assert.equal(vm.runInContext('growthQuality',ctx),null);
 ctx.crypto={getRandomValues(a){for(let i=0;i<a.length;i++)a[i]=i}};assert(/^[a-f0-9]{8}-[a-f0-9]{4}-4[a-f0-9]{3}-[89ab][a-f0-9]{3}-[a-f0-9]{12}$/.test(vm.runInContext('flowRequestId()',ctx)));
 const s=fs.readFileSync(__dirname+'/../public/studio.js','utf8');assert(s.includes("api('lab/support',{pack:id,skill:studioSkill,action:'start'})"));assert(s.includes('coach_mission:studioPack.coach_mission'));assert(s.includes('assisted:!!s.reveal'));assert(s.includes('packKnowledgeHTML(p)'));assert(!s.includes('今日还可请求 ${d.remaining}'));
 const css=fs.readFileSync(__dirname+'/../public/design-bridge.css','utf8');for(const token of ['.mentor-conversation','.flow-network-node rect','.growth-reason','var(--surface)','var(--text)'])assert(css.includes(token));
 console.log('v2.2 merged routes, appearance preferences, account isolation, support tracking and current feature hooks: passed');
})().catch(e=>{console.error(e);process.exit(1)});
