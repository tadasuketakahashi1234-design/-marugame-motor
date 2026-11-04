const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync('omura/docs/boat24_full_ui.js','utf8');
const context={Date,Number,Math,Set,Object,esc:String,num:String,pct:x=>(100*x).toFixed(1)+'%'};
vm.createContext(context);
vm.runInContext(src.slice(src.indexOf('const purchasePolicy='),src.indexOf('function records()')),context);
const tickets=[{combo:'1-2-3',stake:200,odds:5,expected_return:1000},{combo:'1-2-4',stake:100,odds:4,expected_return:400}];
const s={id:'new',evaluation_eligible:true,created_at:new Date().toISOString(),cutoff:new Date(Date.now()+600000).toISOString(),purchase_plan:{policy:'balanced-no-gami-v2',status:'ready',budget:300,budget_cap:1200,estimated_roi:1.4,tickets,odds_observed_at:new Date().toISOString()}};
assert(context.purchaseView(s).html.includes('2点・計300円'));
assert(context.purchaseView(s).html.includes('1-2-3：200円'));
assert(context.purchaseView(s).metrics.includes('＋100円'));
s.purchase_plan.odds_observed_at=new Date(Date.now()-301000).toISOString();
assert(context.purchaseView(s).html.includes('判定保留'));
assert(!context.purchaseView(s).html.includes('低い'));
s.purchase_plan.odds_observed_at=new Date().toISOString();tickets[0].odds=1.4;
assert(context.purchaseView(s).html.includes('見送り'));
assert(context.purchaseView({cutoff:s.cutoff}).html.includes('保存待ち'));
assert.equal(context.purchaseSnapshot({revisions:{new:s,old:{...s,id:'old',purchase_plan:{}}}},null).id,'new');
console.log('PASS: variable counts/stakes, stale odds, losing payout, legacy snapshots');
vm.runInContext(src.slice(src.indexOf('function renderOfferHistory('),src.indexOf('function displayAudit(')),context);
const offered={snapshot_id:'issued',created_at:'2026-11-03T21:20:08+09:00',tickets:[{combo:'1-3-4',stake:700}],budget:1200};
const history=context.renderOfferHistory({offers:{issued:offered},result:{purchase_snapshot_id:'issued',refund_verified:true,refund_boats:[],offer_settlements:{issued:{stake:1200,return:5950,refund:0,profit:4750}}}});
assert(history.includes('5950円'));assert(history.includes('4750円'));assert(history.includes('主集計対象'));
assert(history.includes('公式確認'));assert(context.renderOfferHistory({}).includes('公式照合待ち'));
console.log('PASS: saved offer history and first-offer settlement remain visible after skip');

const research=context.renderOfferHistory({result:{refund_verified:true,refund_boats:['2'],paper:{'12':{stake:1200,return:1380,refund:600}},result_source:{official_result_source:'https://www.boatrace.jp/owpc/pc/race/raceresult?hd=20261103&jcd=09&rno=12'}}});
assert(research.includes('1380円（返還 600円含む）'));assert(research.includes('公式結果・返還の確認元'));

// A newer quote clock must not restore pre-exhibition context.
vm.runInContext(src.slice(src.indexOf('const contextOrder='),src.indexOf('async function getJSON('))+'globalThis.selectLatest=latest;',context);
const freshContext={...s,id:'fresh-context',phase:'preview',created_at:'2026-11-04T17:36:52+09:00',cutoff:'2026-11-04T17:41:00+09:00'};
const staleContext={...s,id:'late-quote',phase:'partial',created_at:'2026-11-04T17:37:48+09:00',cutoff:freshContext.cutoff,context_snapshot_at:'2026-11-04T17:12:33+09:00'};
const race={revisions:{fresh:freshContext,old:staleContext},result:{selection_snapshot_id:staleContext.id}};
assert.equal(context.selectLatest(race).id,freshContext.id);
assert.equal(context.purchaseSnapshot(race,null).id,freshContext.id);
assert.equal(race.result.selection_snapshot_id,staleContext.id);
console.log('PASS: latest commentary and tickets share the newest context; historical evaluation pointer is preserved');
