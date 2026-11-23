// DOM-free behavior checks. Real browser layout QA is still required after deployment.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const listeners={};const root={innerHTML:'',addEventListener:(event,fn)=>{(listeners[event]??=[]).push(fn)}};
const nodes={'#app':root,'#toast':{textContent:'',style:{}}};
const context=vm.createContext({document:{querySelector:selector=>nodes[selector]||null},window:{addEventListener(){},scrollTo(){}},crypto:{randomUUID:()=> 'ui-request-00000001'},setTimeout(){},clearTimeout(){},console,confirm:()=>true});
vm.runInContext(fs.readFileSync(__dirname+'/../public/app.js','utf8'),context);
vm.runInContext(fs.readFileSync(__dirname+'/../public/tutor.js','utf8'),context);
const topics=['tense','clause','conditional','nonfinite','agreement','subjunctive'].map((id,i)=>({id,title:'Topic '+i,summary:'Summary',lesson:'Lesson',example:'Example',explanation:'Explanation',mastery:null,attempts:0,completed:false,details:[['Step','Details']],prereqs:i===5?['conditional']:[]}));
context.fixture={topics,recommended:topics[0],reason:'Start here',total:0,correct:0,wrong_count:0,completed:0,days:[]};
async function main(){
vm.runInContext("user={id:1,username:'<img onerror=evil>',admin:1};dashboard=fixture;shell('<p>Legacy widgets</p>')",context);
assert(root.innerHTML.includes('&lt;img onerror=evil&gt;'));assert(!root.innerHTML.includes('<img onerror'));
assert(root.innerHTML.includes('data-view="review"'));assert(root.innerHTML.includes('data-view="settings"'));
vm.runInContext('graph()',context);assert.equal((root.innerHTML.match(/class="graph-node/g)||[]).length,6);
vm.runInContext("tutorState('tense').loaded=true;lesson('tense')",context);
assert(root.innerHTML.includes('Details'));assert(root.innerHTML.includes('data-complete="tense"'));
assert(root.innerHTML.includes('data-panel="tutor"'));assert(root.innerHTML.includes('data-prompt="举两个例子"'));assert(root.innerHTML.includes('data-timeline="past"'));
let html=vm.runInContext('renderMarkdown("## 标题\\n\\n**重点**\\n\\n- 一\\n- 二\\n\\n<script>alert(1)</script>\\n\\n| A | B |\\n| --- | --- |\\n| 1 | 2 |")',context);
assert(html.includes('<strong>重点</strong>'));assert(html.includes('<ul>'));assert(html.includes('<table>'));assert(!html.includes('<script>'));assert(html.includes('&lt;script&gt;'));
html=vm.runInContext('renderMarkdown("```html\\n<img src=x onerror=alert(1)>\\n```\\n**<svg onload=alert(1)>**")',context);
assert(html.includes('<pre><code>'));assert(!html.includes('<img'));assert(!html.includes('<svg'));
vm.runInContext("view='home';api=async()=>({reply:'**清楚的回答**',finish_reason:'length',remaining:19})",context);
await vm.runInContext("sendChat('tense','解释一下')",context);
assert.equal(vm.runInContext("tutorState('tense').items[0].status",context),'complete');
html=vm.runInContext("chatMessages('tense')",context);assert(html.includes('data-continue'));assert(html.includes('<strong>清楚的回答</strong>'));assert(!vm.runInContext("tutorState('tense').busy",context));
vm.runInContext("api=async()=>{throw Error('network failed')}",context);
await vm.runInContext("sendChat('clause','再试一次')",context);
assert.equal(vm.runInContext("tutorState('clause').items[0].status",context),'failed');assert(vm.runInContext("chatMessages('clause')",context).includes('data-retry'));
vm.runInContext('settings()',context);assert(root.innerHTML.includes('new_password'));assert(!root.innerHTML.includes('undefined'));
context.q={token:'test',questions:[{id:1,prompt:'Choose <safe>',options:['A','B','C','D']}]};vm.runInContext("quiz=q;answers={};index=0;quizPage()",context);assert(root.innerHTML.includes('Choose &lt;safe&gt;'));assert.equal((root.innerHTML.match(/data-answer=/g)||[]).length,4);
console.log('UI render, tutor, retry, truncation and Markdown escaping checks: passed');
}
main().catch(e=>{console.error(e);process.exitCode=1});
