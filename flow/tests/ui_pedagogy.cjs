const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx=vm.createContext({document:{querySelector:()=>({addEventListener(){}})},coachLoad(){},home:null,app:{addEventListener(){}},Date,Map,console,window:{},graphDiagram:null,kindLabels:{sense:'义项',pattern:'搭配'}});
vm.runInContext('function esc(s){return String(s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll(\'"\',"&quot;")}',ctx);
for(const f of ['growth','atlas'])vm.runInContext(fs.readFileSync(__dirname+'/../public/'+f+'.js','utf8'),ctx);
ctx.d={day:'2026-10-21',today:{activities:0,independent_checks:0},unit:{chapter:1,session:1,tasks:[{id:'mission',title:'Read'}]},next_action:{type:'repair',title:'先补 suggest',reason:'最近答错 <img>',minutes:3,label:'补练后继续',evidence_ids:[4]}};
let html=vm.runInContext('loopHomeHTML(d)',ctx);assert(html.includes('data-learning-next'));assert(html.includes('先继续原计划'));assert(!html.includes('<img>'));
ctx.g={node:{id:'s',kind:'sense',title:'Suggest'},network:{nodes:[{id:'s',title:'Suggest',kind:'sense'},{id:'p',title:'suggest doing',kind:'pattern'}],edges:[{source:'s',target:'p',relation:'has_pattern'}]},relationship_meanings:[{source:'s',target:'p',category:'表达扩展',meaning:'认识词义不等于会用搭配',learning_action:'独立造句',limit:'不共享通过状态',origin:'published'}]};
html=vm.runInContext('graphDiagram(g)',ctx);assert(html.includes('这些连接如何帮助我'));assert(html.includes('独立造句'));assert(html.includes('不共享通过状态'));assert(html.includes('<summary>探索完整连接图</summary>'));assert(!html.includes('<details class="atlas-explore" open'));
console.log('Repair-first action, preserved plan, semantic relation explanations, progressive graph and escaping: passed');
