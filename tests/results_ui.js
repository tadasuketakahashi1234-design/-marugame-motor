const fs=require('fs'),vm=require('vm'),assert=require('assert');
const script=fs.readFileSync('omura/docs/boat24_full_ui.js','utf8');
const section=script.slice(script.indexOf('function renderResultPanel('),script.indexOf('function renderComparison('));
const ctx={Date,esc:x=>String(x??'―')};vm.createContext(ctx);vm.runInContext(section,ctx);
const record={result:{combo:'1-3-5',payout_100yen:1140,refund_verified:true,refund_boats:[],purchase_snapshot_id:'first',offer_settlements:{first:{stake:1200,return:0,refund:0,profit:-1200,hit:false},latest:{stake:1200,return:1140,refund:0,profit:-60,hit:true}}}};
let html=ctx.renderResultPanel(record,{id:'latest'});
assert(html.includes('1-3-5'));assert(html.includes('的中・ガミ'));assert(html.indexOf('収支 -60円')<html.indexOf('最初の候補'));assert(html.indexOf('最初の候補')<html.indexOf('収支 -1200円'));
html=ctx.renderResultPanel(record,{id:'skipped'});assert(html.includes('購入候補の保存なし'));assert(!html.split('最初の候補')[0].includes('収支 -1200円'));
html=ctx.renderResultPanel({},null,new Date(Date.now()-20*60000).toISOString(),{attempt_at:'2026-11-04T19:45:24+09:00'});assert(html.includes('結果更新が遅れています'));assert(html.includes('19:45:24'));
// The hypothesis is intentionally above the purchase/result pair; retain result visibility.
assert(script.includes('renderNarrative(c)'));
assert(script.indexOf('renderNarrative(c)')<script.indexOf('renderResultPanel(r,ps,snap.cutoff'));
assert(script.includes('renderResultPanel(r,ps,snap.cutoff'));
const page=fs.readFileSync('omura/docs/boat24_results.html','utf8');assert(page.indexOf('id="fullRaceComparison"')<page.indexOf('id="fullRecords"'));assert(page.includes('grid-template-columns:minmax(0,1fr) minmax(0,1fr)'));
console.log('Results UI PASS: displayed-version settlement, hit loss, pending delay, top comparison and two columns');
