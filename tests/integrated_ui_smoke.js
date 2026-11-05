const fs=require('fs'),vm=require('vm'),assert=require('assert');
const elements={fullLearning:{innerHTML:''}};
const context={document:{getElementById:id=>elements[id]||null},Set,Number,Object,String,RegExp};
vm.runInNewContext(fs.readFileSync('omura/docs/boat24_integrated_ui.js','utf8'),context);
const f=[{exhibition_detail:{展示順位:1},comment_detail:{伸び:1}}];
const index={factor_catalog:[{id:'x',category:'展示',label:'展示順位',group:'exhibition_detail',pattern:'展示順位'},{id:'y',category:'進入',label:'助走距離',group:'entry_detail',pattern:'',collection:'requires_verified_source_or_video'}],training:{learned_fields:['exhibition_detail|展示順位']}};
const s={input_snapshot:{features:f},feature_usage:{exhibition_detail:{used_fields:[]}},details:{boats:[{lane:1,racer:'4001',exhibition:{展示順位:1},comment:{raw:'<script>bad</script>伸びが良い',version:'v',evidence:[{aspect:'伸び',phrase:'伸びが良い',status:'current_report',value:1}]}}]}};
const html=context.Boat24Integrated.render(s,{venue:15},index);
assert(html.includes('展示・進入・足の詳細'));assert(html.includes('候補予想で検証中'));assert(html.includes('助走距離'));assert(html.includes('検証済み配信または映像計測が必要'));assert(!html.includes('<script>bad'));
context.Boat24Integrated.learning({...index,integrated_learning:{phase_reports:[]}});assert(elements.fullLearning.innerHTML.includes('予想→結果→精算→学習→検証'));
console.log('Integrated UI PASS: detailed exhibitions, evidence, missing factors, shadow status and learning in one screen');

context.Boat24Integrated.learning({...index,integrated_learning:{policy:'public-frozen-learning-1',phase_reports:[],case_audit:{excluded:{publication_proof_missing:2}}}});
assert(elements.fullLearning.innerHTML.includes('新しい学習条件での再学習待ち'));
assert(elements.fullLearning.innerHTML.includes('候補の購入100R'));
assert(elements.fullLearning.innerHTML.includes('締切前の公開を確認できない：2R'));
context.Boat24Integrated.learning({...index,training:{through:'2026-11-04',learning_policy:'public-frozen-learning-1',replay:{public_frozen:7}},integrated_learning:{policy:'public-frozen-learning-1',phase_reports:[]}});
assert(elements.fullLearning.innerHTML.includes('公開固定 7R'));

require("./study_ui.js");
