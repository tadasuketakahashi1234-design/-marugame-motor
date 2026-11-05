const fs=require('fs'),vm=require('vm'),assert=require('assert');
const elements={},requests=[];let version=0,apiCalls=0,stale=false,staleView=false;
function el(id){return elements[id]||=( {value:id==='venue'?'10':'',innerHTML:'',textContent:'',events:{},addEventListener(t,fn){this.events[t]=fn},querySelectorAll(){return []}})}
const now=new Date(),code='202611041002',cutoff=new Date(Date.now()+600000).toISOString();
const c={snapshot_id:'s',headline:'◎1号艇を中心',axis:'一周は上位、展示タイムは下位',opponents:'2・3号艇を比較',deployment:'進入が変われば相手順も変わる',water:'風速6m・波高8cm。観測が古いため留保',price:'配分は取得時オッズで判定',reasoning:{axis:1,place_axis:4,first_candidates:[1,4],components:{market_weight:.75,context:[{first:.3},{},{},{first:.4}],market:[{first:.4},{},{},{first:.3}],final:[{first:.41},{},{},{first:.39}]},branches:[{winner:4,course:3,conditions:['内隣の壁を確認'],counter_evidence:['展示F'],unknown:['助走距離は未計測'],opponents:[{lane:1,second:.5,third:.2}],combos:[{combo:'4-1-2'}]}]},risks:['展示Fを正常ST最速と扱わない'],boats:[],notice:'数値からの条件付き想定'};
const snap=()=>({id:staleView?'old':'s',phase:'preview',created_at:new Date(now.getTime()-(staleView?60000:0)).toISOString(),cutoff,evaluation_eligible:true,_details_compacted:true,purchase_plan:version&&!staleView?{policy:'balanced-no-gami-v2',status:'ready',risk_policy:'probability-price-stress-1',probability_verified:false,risk_controls:{probability_haircut:.2,price_haircut:.1,maximum_ticket_share:.25},stress_expected_roi:1.8,budget:400,budget_cap:1200,estimated_roi:2.5,odds_observed_at:now.toISOString(),tickets:['1-2-3','1-2-4','4-1-2','4-1-5'].map(combo=>({combo,stake:100,odds:10,expected_return:1000,estimated_probability:.25}))}:{policy:'balanced-no-gami-v2',status:'odds_stale',tickets:[]}});
const index=()=>({latest_day:'2026-11-04',updated_at:new Date(now.getTime()+(stale?-10000:version*1000)).toISOString(),days:{'2026-11-04':{summary:{},venues:{10:{}}}},training:{},forward_report:{rows:[]}});
const data=()=>({updated_at:now.toISOString(),catalog:{[code]:{race_code:code,venue:10,race:2,cutoff}},records:{[code]:{race_code:code,venue:10,race:2,revisions:{[staleView?'old':'s']:snap()},race_commentary:c}}});
const context={document:{getElementById:el,hidden:false},fetch:async u=>{requests.push(u);if(u.includes('api.github.com')){apiCalls++;return{ok:true,json:async()=>({object:{sha:(version?'b':'a').repeat(40)}})}}if(u.startsWith('./'))return new Promise(()=>{});return{ok:true,json:async()=>u.includes('boat24_full_index')?index():data()}},AbortSignal:{timeout(){}},Date,Intl,Number,String,Object,Set,Promise,Error,setInterval(){}};
vm.runInNewContext(fs.readFileSync('omura/docs/boat24_full_ui.js','utf8'),context);
(async()=>{
 await new Promise(r=>setTimeout(r,50));
 assert(el('fullRecords').innerHTML.includes('判定保留'));assert(el('fullRecords').innerHTML.includes('風速6m'));assert(el('fullRaceNav').innerHTML.includes('#race-'+code));assert(el('fullRecords').innerHTML.includes('想定展開'));assert(el('fullRecords').innerHTML.includes('軸の順位が決まった過程'));assert(el('fullRecords').innerHTML.includes('条件付き2着'));assert(el('fullRecords').innerHTML.includes('助走距離は未計測'));
 assert(!requests.some(u=>u.startsWith('./')),'A successful primary read must not wait for a slow fallback');
 version=1;const done=el('fullReload').events.click();assert(el('fullReload').disabled);assert(el('fullReload').textContent.includes('取得中'));
 await done;assert.equal(apiCalls,2,'Manual refresh must bypass the previous 45-second ref cache');
 assert(!el('fullReload').disabled);assert(el('fullRecords').innerHTML.includes('4点・計400円'));assert(el('fullRefreshStatus').textContent.includes('再取得完了'));
 staleView=true;version=2;await el('fullReload').events.click();assert(el('fullRecords').innerHTML.includes('4点・計400円'),'A delayed day view must not erase a fresher quote');staleView=false;
 stale=true;await el('fullReload').events.click();assert(el('fullRefreshStatus').textContent.includes('表示中の新しい版を保持'));assert(!el('fullRefreshStatus').textContent.includes('失敗'));assert(el('fullRecords').innerHTML.includes('4点・計400円'));
 console.log('Forecast UI PASS: race reasoning, pending versus price skip, immediate feedback, forced latest ref, fast primary read');
})().catch(e=>{console.error(e);process.exitCode=1});

require('./race_navigation_ui.js');
