const fs=require('fs'),vm=require('vm'),assert=require('assert');
const root={innerHTML:'',addEventListener(){},querySelector(){return null}};
const window={addEventListener(){},location:{hash:'',pathname:'/'},history:{replaceState(){}}};
const ctx=vm.createContext({document:{querySelector:s=>s==='#app'?root:{textContent:'',style:{}}},window,crypto:{randomUUID:()=> 'request-advanced-001'},setTimeout(){},clearTimeout(){},console,confirm:()=>true,URLSearchParams});
for(const name of ['app','tutor','advanced'])vm.runInContext(fs.readFileSync(__dirname+'/../public/'+name+'.js','utf8'),ctx);
ctx.fixture={topics:['tense','clause','conditional','subjunctive','nonfinite','agreement'].map(id=>({id,title:'Title',prereqs:[],mastery:null,attempts:0,summary:'S',lesson:'L',example:'E',explanation:'X'})),days:[]};
ctx.study={nodes:[{id:'tense-perfect',topic:'tense',title:'Safe <node>',available:3,distinct:0,state:'证据不足',first_accuracy:null,total:0,lesson:'Node lesson',example:'Example'}],tasks:[{kind:'verify',title:'Verify',node:'tense-perfect',minutes:5,reason:'Unseen first'}],due:[],minutes:15,plan_minutes:5,coverage:0,first:{total:0,correct:0},repeat:{total:0,correct:0},days:[],skill_count:0,limitations:'Limit'};
ctx.practiceFixture={tasks:[{id:'speaking-1',kind:'speaking',title:'Speak',topic:'tense',prompt:'Say hello',reference:'Example'}],history:[]};
vm.runInContext("skillLabels={listening:'听力',speaking:'口语',reading:'阅读',writing:'写作'};user={id:1,username:'Student',admin:1};dashboard=fixture;window.aiEnabled=true;api=async path=>path==='study'?study:path==='practices'?practiceFixture:path==='lab/history'?{items:[],jobs:[],report:{skills:[],words:0,revisions:0}}:path.startsWith('manage/questions')?{items:[],total:0,page:1}:path==='manage/monitor'?{used:0,drafts:0,turns_24h:[],errors:[],pending_stale:0}:{}",ctx);
(async()=>{
 await vm.runInContext("view='plan';plan()",ctx);assert(root.innerHTML.includes('到期语法复习'));assert(root.innerHTML.includes('data-node-quiz'));
 await vm.runInContext("view='report';learningReport()",ctx);assert(root.innerHTML.includes('首次作答正确率'));assert(root.innerHTML.includes('Safe &lt;node&gt;'));assert(!root.innerHTML.includes('undefined'));
 await vm.runInContext("view='practice';practices()",ctx);assert(root.innerHTML.includes('data-task'));
 vm.runInContext("taskPage('speaking-1')",ctx);assert(root.innerHTML.includes('不会上传'));assert(root.innerHTML.includes('data-record'));assert(root.innerHTML.includes('practice-form'));
 await vm.runInContext("view='admin';contentAdmin()",ctx);assert(root.innerHTML.includes('AI 生成一题草稿'));assert(root.innerHTML.includes('待审核'));
 vm.runInContext('editQuestion(null)',ctx);assert(root.innerHTML.includes('advanced-question-form'));assert(!root.innerHTML.includes('undefined'));
 vm.runInContext("window.location.hash='#reset=private-token';boot()",ctx);assert(root.innerHTML.includes('recovery-reset-form'));assert(!root.innerHTML.includes('private-token'));
 console.log('v0.5 plan/report/practice/admin/recovery rendering and escaping: passed');
})().catch(e=>{console.error(e);process.exitCode=1});
