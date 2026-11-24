const fs=require('fs'),vm=require('vm'),assert=require('assert');
const root={innerHTML:'',addEventListener(){},querySelector(){return null}},window={addEventListener(){},scrollTo(){},location:{hash:'',pathname:'/'},history:{replaceState(){}}};
const ctx=vm.createContext({document:{querySelector:k=>k==='#app'?root:k==='#toast'?{textContent:'',style:{}}:null},window,crypto:{randomUUID:()=> 'coach-request-001'},setTimeout(){},clearTimeout(){},console,confirm:()=>true,URLSearchParams,URL,Date,Map,RegExp});
for(const file of ['app','tutor','advanced','studio','knowledge','adaptive','coach'])vm.runInContext(fs.readFileSync(__dirname+'/../public/'+file+'.js','utf8'),ctx);
const skills=['vocabulary','grammar','listening','speaking','reading','writing'];
ctx.fixture={profile:null,growth:{level:1,xp:0,completed:0,coverage:{}},turns:[],missions:[],memories:[],draft:'',ai_enabled:true};
vm.runInContext("user={id:1,username:'Learner',admin:0};dashboard={topics:[]};api=async p=>p==='coach'?fixture:{}",ctx);
(async()=>{
 await vm.runInContext('home()',ctx);assert(root.innerHTML.includes('建立我的学习起点'));assert(!root.innerHTML.includes('undefined'));
 ctx.fixture.profile={goal:'Travel <script>bad</script>',interests:'Culture',minutes:15,placement:{band:'B1'}};
 ctx.fixture.turns=[{id:1,request_id:'r1',message:'My <img src=x> example',reply:'Try **practising**. <script>bad</script>',status:'complete',created:Date.now()/1000}];
 ctx.fixture.memories=[{id:1,text:'Enjoys travel',evidence:'I like travel.'}];ctx.fixture.missions=skills.map((s,i)=>({id:'m'+i,chapter:1,skill:s,title:s+' task',instruction:'Practice this dimension',minutes:5,status:'active'}));
 await vm.runInContext('home()',ctx);assert(root.innerHTML.includes('私教对话'));assert(root.innerHTML.includes('coach-chat-form'));assert(root.innerHTML.includes('无个人每日调用次数上限'));assert(!root.innerHTML.includes('<script>bad'));assert(root.innerHTML.includes('<strong>practising</strong>'));assert.equal((root.innerHTML.match(/data-coach-mission=/g)||[]).length,6);assert(!root.innerHTML.includes('undefined'));
 vm.runInContext("coachPanel='journey';renderCoach()",ctx);assert(root.innerHTML.includes('旅程'));assert(root.innerHTML.includes('XP不代表英语水平'));
 vm.runInContext("coachPanel='memory';renderCoach()",ctx);assert(root.innerHTML.includes('I like travel.'));assert(root.innerHTML.includes('data-coach-forget="1"'));
 vm.runInContext("coachMission={id:'private-old',title:'Other user private task'};user={id:2,username:'Other',admin:0}",ctx);ctx.fixture.memories=[];ctx.fixture.turns=[];await vm.runInContext('home()',ctx);assert(!root.innerHTML.includes('Other user private task'));
 console.log('v2.0 coach welcome, persistent conversation, six-dimension missions, growth labels, memory controls, escaping and account transition: passed');
})().catch(e=>{console.error(e);process.exit(1)});
