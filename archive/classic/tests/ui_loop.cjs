const fs=require('fs'),vm=require('vm'),assert=require('assert');
const ctx=vm.createContext({coachLoad(){},home:null,app:{addEventListener(){}},document:{querySelector:()=>({addEventListener(){}})},console,Date,Map,window:{}});
vm.runInContext('function esc(s){return String(s).replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;").replaceAll(\'"\',"&quot;")}',ctx);
vm.runInContext(fs.readFileSync(__dirname+'/../public/growth.js','utf8'),ctx);
ctx.d={day:'2026-10-21',unit:{chapter:1,session:2,remaining_minutes:8,tasks:[{id:'resume-1',title:'<img src=x>',minutes:4}]},today:{activities:2,independent_checks:1},note:'Evidence',changes:[{id:7,node:'sense:suggest',title:'suggest',before:'待验证',after:'待验证',changed:false,evaluator:'ai',assisted:null,created:1}],words:[{node:'sense:suggest',title:'suggest',modes:[{label:'拼写',status:'待练习',evidence_ids:[]}]}]};
const h=vm.runInContext('loopHomeHTML(d)',ctx);assert(h.includes('data-coach-mission="resume-1"'));assert(!h.includes('<img'));assert(h.includes('剩余约 8 分钟'));
const e=vm.runInContext('loopEvidenceHTML(d)',ctx);assert(e.includes('AI意见 · 待验证'));assert(e.includes('状态保持'));assert(e.includes('data-flow-node="sense:suggest"'));assert(e.includes('拼写'));assert(e.includes('尚缺独立证据'));assert.equal(vm.runInContext('loopHomeHTML(null)',ctx),'');
console.log('Learning continuity rendering, evidence labels, resume links and escaping: passed');
