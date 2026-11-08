/* All-input forecasts and the exact input evidence used by each immutable revision. */
(function(){
'use strict';
const $=id=>document.getElementById(id),esc=x=>String(x??'―').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names=['全24場','桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑','津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島','宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'];
const linkedVenue=typeof location==='undefined'?null:new URLSearchParams(location.search).get('venue');
if(linkedVenue!==null&&/^(?:[0-9]|1[0-9]|2[0-4])$/.test(linkedVenue))$('venue').value=String(Number(linkedVenue));
const raceStates={waiting_initial:'展示前予想の保存待ち',program_unconfirmed:'番組未確認',cancelled:'中止・順延',cutoff_unknown:'締切時刻未確認',closed_no_forecast:'締切済み・新モデル予想なし',result_pending:'結果・払戻金待ち',saved:'予想保存済み',settled:'結果確定'};
const statuses={shadow:'候補予想で検証中',not_applicable:'対象外',not_implemented:'取得処理が未実装',partial_used:'一部を計算に使用',not_contributing_market_only:'検証で市場のみ採用・文脈は未採用',used:'計算に使用',missing:'未取得',partial:'一部のみ取得',historical_sample_insufficient:'参照できる過去標本が不足'};
const pct=x=>x==null?'未集計':(100*x).toFixed(1)+'%',num=x=>x==null?'未取得':Number(x).toFixed(2);
let index=null,data=null,loadedDay='',selected=null,loading=0,liveRef='main',refChecked=0,renderedRef='',busy=false,raceVisible=24;
async function resolveLiveRef(force=false){
 if(!force&&Date.now()-refChecked<60000)return;refChecked=Date.now();
 try{const r=await fetch('https://api.github.com/repos/tadasuketakahashi1234-design/-marugame-motor/git/ref/heads/main?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok){liveRef='main';return}const d=await r.json();const sha=d.object?.sha||d.sha;if(/^[a-f0-9]{40}$/.test(sha||''))liveRef=sha}catch(e){liveRef='main'}
}
const stage=s=>s.phase==='preview'?2:0;
const contextOrder=(a,b)=>stage(b)-stage(a)||Date.parse(b.context_snapshot_at||b.created_at)-Date.parse(a.context_snapshot_at||a.created_at)||b.created_at.localeCompare(a.created_at)||b.id.localeCompare(a.id);
const latest=r=>Object.values(r.revisions||{}).filter(s=>s.evaluation_eligible&&Date.parse(s.created_at)<Date.parse(s.cutoff)).sort(contextOrder)[0];
async function getJSON(path){
 const root='https://raw.githubusercontent.com/tadasuketakahashi1234-design/-marugame-motor/'+liveRef+'/omura/docs/';
 const urls=[root+path,'./'+path];
 let error;
 for(const u of urls){try{const r=await fetch(u+'?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error('HTTP '+r.status);if(path.endsWith('.gz')){if(typeof DecompressionStream==='undefined')throw Error('このブラウザでは圧縮履歴を開けません');return await new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).json()}return await r.json()}catch(e){error=e}}
 throw Error('最新データの再取得に失敗：'+(error?.message||'通信エラー'));
}
const purchasePolicy='balanced-no-gami-v2',riskPolicy='probability-price-stress-1';
function purchaseSnapshot(r,fallback){
 const found=Object.values(r?.revisions||{}).filter(x=>x.purchase_plan?.policy===purchasePolicy&&x.evaluation_eligible&&Date.parse(x.created_at)<Date.parse(x.cutoff)).sort((a,b)=>(b.phase==='preview'?2:0)-(a.phase==='preview'?2:0)||Date.parse(b.context_snapshot_at||b.created_at)-Date.parse(a.context_snapshot_at||a.created_at)||b.created_at.localeCompare(a.created_at)||b.id.localeCompare(a.id));
 return found[0]||fallback;
}
function purchaseView(s){
 const p=s.purchase_plan||{},closed=Date.now()>=Date.parse(s.cutoff);
 const age=Date.now()-Date.parse(p.odds_observed_at),fresh=Number.isFinite(age)&&age>=0&&age<=300000;
 const tickets=p.tickets||[],total=tickets.reduce((v,t)=>v+t.stake,0);
 const current=p.policy===purchasePolicy;
 const valid=current&&p.status==='ready'&&tickets.length>0&&new Set(tickets.map(t=>t.combo)).size===tickets.length&&total===p.budget&&total<=p.budget_cap&&p.estimated_roi>1&&tickets.every(t=>Number.isInteger(t.stake)&&t.stake>=100&&t.stake%100===0&&Number.isFinite(t.odds)&&Math.floor((t.odds+1e-9)*10)*10*(t.stake/100)>total&&t.expected_return>total);
 const reasons={preview_pending:'全6艇の展示・進入・展示STの確認待ち',risk_no_positive_value:'確率・払戻の下振れ条件で期待回収率100％を超えない',risk_no_feasible_plan:'下振れ時のガミ回避と1点の集中上限を両立する配分なし',odds_stale:'オッズが古い・取得時刻不明',odds_incomplete:'オッズ未取得・不足',probabilities_invalid:'確率データの整合性未確認',no_positive_value:'モデル推定の期待回収率100％超の案なし',no_feasible_plan:'ガミなし条件の配分なし'};
 if(!closed&&p.risk_policy!==riskPolicy)return {pending:true,html:'<strong>判定保留：配分の新条件を計算中</strong>',metrics:'以前の配分は保存履歴に保持しています'};
 if(p.status==='preview_pending')return {pending:true,html:'<strong>判定保留：展示・進入の確認待ち</strong><br>'+esc(p.reason||reasons[p.status]),metrics:'オッズが低いことによる見送りではありません'};
 if(p.risk_policy===riskPolicy&&p.status==='ready'){
  const r=p.risk_controls||{},ph=r.probability_haircut,qh=r.price_haircut,cap=r.maximum_ticket_share;
  const stressReturn=t=>Math.floor((Math.floor((t.odds*(1-qh)+1e-9)*10)/10+1e-9)*10)*10*(t.stake/100);
  const stressROI=tickets.reduce((v,t)=>v+t.estimated_probability*(1-ph)*stressReturn(t),0)/total;
  const nominalMass=tickets.reduce((v,t)=>v+t.estimated_probability,0);
  if(!Number.isFinite(ph)||ph<(p.probability_verified ? .10 : .20)||ph>=1||!Number.isFinite(qh)||qh<.10||qh>=1||!Number.isFinite(cap)||cap>(p.probability_verified ? .35 : .25)||cap<=0||!Number.isFinite(stressROI)||stressROI<=1||nominalMass>1+1e-6||!tickets.every(t=>Number.isFinite(t.estimated_probability)&&t.estimated_probability>=0&&t.stake<=total*cap+1e-9&&stressReturn(t)>total)||Math.abs(stressROI-p.stress_expected_roi)>1e-6)return {html:'<strong>見送り：下振れ・集中条件の整合性未確認</strong>',metrics:'購入候補なし'};
 }
 if(['odds_stale','odds_incomplete'].includes(p.status))return {pending:true,html:'<strong>判定保留（購入候補なし）</strong><br>'+(!p.odds_observed_at?'オッズ未取得':p.status==='odds_incomplete'?'オッズ120通りが揃っていません':'オッズ更新遅延')+'<br>価格が低いことによる見送りではありません',metrics:'オッズ更新 '+esc(p.odds_observed_at||'未取得')};
 if(!valid)return {html:'<strong>見送り</strong><br>'+(!current?'点数可変の新条件の保存待ち（旧予想は詳細に保持）':reasons[p.status]||'配分の整合性未確認'),metrics:'購入候補なし'};
 if(!closed&&Date.now()>=Date.parse(s.cutoff)-120000)return {html:'<strong>見送り：締切2分前</strong>',metrics:'新規の購入候補表示を停止'};
 if(!closed&&!fresh)return {html:'<strong>判定保留：オッズ更新遅延</strong>',metrics:'オッズが古い・取得時刻不明'};
 const minimum=Math.min(...tickets.map(t=>t.expected_return));
 return {valid:true,ready:!closed,html:(closed?'<b>締切済み・保存時の参考</b><br>':'')+'<b>'+tickets.length+'点・計'+total+'円</b><br>'+tickets.map(t=>esc(t.combo)+'：'+t.stake+'円').join('<br>'),metrics:'取得時の最低想定払戻 '+minimum+'円<br>最低想定利益 ＋'+(minimum-total)+'円<br>モデル内試算回収率 '+pct(p.estimated_roi)+'（未校正・実績ではありません）<br>合成 '+num(p.synthetic_odds)+'倍<br>オッズ時刻 '+esc(p.odds_observed_at)+'<br>候補計算 '+esc(s.created_at)+'<br>点数・配分の近似比較／的中確率とのバランス優先'+(p.risk_policy===riskPolicy?'<br>感度条件：確率 '+pct(p.risk_controls.probability_haircut)+'減・払戻 '+pct(p.risk_controls.price_haircut)+'減／1点上限 '+pct(p.risk_controls.maximum_ticket_share)+'<br>下振れ条件の試算回収率 '+pct(p.stress_expected_roi)+'<br>感度条件は統計的な信頼区間ではありません':'')};
}
function renderBoatComparison(x,code){
 const boats=Array.from({length:6},(_,i)=>x?.boats?.find(b=>b.lane===i+1)||{lane:i+1}),val=(v,unit='',digits=2)=>v==null?'未取得':Number(v).toFixed(digits)+unit;
 const row=(label,fn)=>'<tr><th scope="row">'+label+'</th>'+boats.map(b=>'<td>'+fn(b)+'</td>').join('')+'</tr>';
 const html='<div class="six-boat-scroll" role="region" aria-label="1〜6号艇のデータ比較" tabindex="0"><table class="six-boat-table"><thead><tr><th scope="col">項目</th>'+boats.map(b=>'<th scope="col" class="boat-color-'+b.lane+'"><b>'+b.lane+'号艇</b><span>'+esc(b.name||'選手未取得')+'</span></th>').join('')+'</tr></thead><tbody>'+row('モーター',b=>esc(b.motor==null?'未取得':b.motor+'号機'))+row('2連対率',b=>val(b.motor_two,'%',1))+row('3連対率',b=>val(b.motor_three,'%',1))+row('全国平均ST',b=>val(b.average_st))+row('今節平均ST<br>当日確認分',b=>val(b.series_st)+(b.series_normal_count?'<small>'+b.series_normal_count+'走</small>':''))+row('今節の本番ST<br>当日確認分',b=>(b.series_starts||[]).map(r=>r.race+'R '+(r.f?'F':'')+Math.abs(r.st).toFixed(2)).join('<br>')||'未取得')+row('展示進入',b=>b.course==null?'未確認':esc(b.course)+'コース')+row('展示タイム',b=>val(b.exhibition_time,'',2))+row('展示ST',b=>val(b.exhibition_st,'',2))+row('コース平均ST',b=>val(b.course_average_st))+row('コース勝率<br>補正得点',b=>val(b.course_points))+row('コース1着率<br>実績',b=>b.course_win_rate==null?'未取得':val(b.course_win_rate*100,'%',1)+'<small>'+esc(b.course_races)+'走</small>')+['逃げ','差し','まくり','まくり差し'].map(m=>row(m+'<br>補正率',b=>b.methods?.[m]==null?'未取得':val(b.methods[m]*100,'%',1))).join('')+'</tbody></table></div>';
 return '<details class="six-boat-comparison" data-six-code="'+esc(code)+'"'+(activeRace===code?' open':'')+'><summary>1〜6号艇を比較</summary>'+html+'<details class="six-boat-notes"><summary>集計期間・項目の見方</summary><p class="small">'+esc(x?.series_scope||'この保存版の比較データは更新待ちです。')+'<br>'+esc(x?.course_scope||'')+'<br>コース実績の基準日 '+esc(x?.through||'未確認')+'。決まり手率の分母はコース出走数で、勝った時の内訳ではありません。</p></details></details>';
}
function renderWaterAnalysis(c){
 const w=c.water_analysis;
 if(!w)return '<section class="water-summary"><h4>水面と艇への影響</h4><p>'+esc((c.water||'観測なし').split('。')[0])+'。</p><p class="small">この保存版は艇別の水面比較を未収録。</p><details><summary>保存時の観測説明</summary><p>'+esc(c.water||'')+'</p></details></section>';
 const cell=x=>esc(x.label)+(x.n?' <small>'+x.n+'例</small>':'');
 return '<section class="water-summary"><h4>水面と艇への影響</h4><p>'+esc(w.conditions)+' ／ '+esc(w.tide)+'</p>'+(!w.fresh?'<p class="small warning">風の観測が古い・未確認のため、風の有利不利は評価保留。</p>':'')+'<div class="scroll"><table class="reasoning-table"><tr><th>艇／展示コース</th><th>似た風条件</th><th>似た潮条件</th></tr>'+w.rows.map(r=>'<tr><td>'+r.lane+'艇／'+esc(r.course??'未確認')+'</td><td>'+cell(r.wind)+'</td><td>'+cell(r.tide)+'</td></tr>').join('')+'</table></div><p class="small">同場・同コースの過去傾向。選手個人の適性ではありません。</p><details><summary>水面比較の根拠・不足</summary><p>'+esc(w.scope)+'<br>'+esc(w.missing)+'<br>'+esc(w.prediction_use)+'<br>観測 '+esc(w.observed_at||'未確認')+' ／ 学習基準日 '+esc(w.through||'未確認')+'</p><p>'+w.rows.map(r=>r.lane+'艇：'+['wind','tide'].map(k=>(k==='wind'?'風':'潮')+' '+(r[k].delta==null?'未評価':(r[k].delta>=0?'+':'')+r[k].delta.toFixed(2)+'着分')+'／'+r[k].n+'例').join('・')).join('<br>')+'</p><p class="small">正の差は平均着順の良化、負は悪化。20例未満は評価保留。統計的に確定した効果ではありません。</p></details></section>';
}
function renderNarrative(c){
 if(!c)return '<section class="race-analysis"><h4>予想見解</h4><p>見解を準備中です。</p></section>';
 const lead=t=>(t||'').split('。').filter(Boolean).slice(0,2).join('。')+'。';
 const branches=c.reasoning?.branches||[],axis=c.reasoning?.axis;
 const observed=i=>(c.boats||[]).find(b=>b.lane===i)?.evidence?.filter(x=>!x.startsWith('モデル内')).slice(0,3).join('・');
 const axisSummary=axis&&observed(axis)?axis+'号艇：'+observed(axis)+'。'+(c.reasoning.components?.market_weight===1?'順位は市場評価による。':''):lead(c.axis);
 const opponents=(c.reasoning?.axis_opponents||[]).slice(0,2);
 const opponentSummary=opponents.length&&opponents.every(r=>observed(r.lane))?opponents.map(r=>r.lane+'号艇：'+observed(r.lane)).join(' ／ '):lead(c.opponents);
 const deployment=branches.length?branches.slice(0,2).map(b=>b.winner+'号艇：'+(b.conditions||[]).slice(0,1).join('')).join(' ／ '):lead(c.deployment);
 return '<section class="race-analysis"><h4>'+esc(c.headline)+'</h4><div><b>軸の理由</b><p>'+esc(axisSummary)+'</p></div><div><b>相手の理由</b><p>'+esc(opponentSummary)+'</p></div><div><b>想定展開</b><p>'+esc(deployment)+'</p></div>'+renderWaterAnalysis(c)+'<details class="analysis-details"><summary>予想の詳しい根拠・反証</summary>'+renderReasoning(c.reasoning)+'<details><summary>観測値と軸・相手の比較</summary><p>'+esc(c.axis)+'</p><p>'+esc(c.opponents)+'</p></details><details><summary>注意点・未確認情報</summary><p>'+(c.risks||[]).map(esc).join('<br>')+'</p><p>'+esc(c.notice||'')+'</p></details><details><summary>6艇を比較する</summary><div class="boat-comparison">'+(c.boats||[]).map(b=>'<div><b>'+esc(b.mark)+' '+b.lane+'号艇 '+esc(b.name||'')+'</b><p>'+b.evidence.map(esc).join(' ／ ')+'</p></div>').join('')+'</div></details></details></section>';
}
function renderReasoning(r){
 if(!r)return '';
 const fmt=x=>Number.isFinite(x)?(100*x).toFixed(1)+'％':'未確認';
 const axis=r.axis,rival=r.first_candidates?.find(i=>i!==axis),comp=r.components||{};
 let html='<div class="reasoning-proof"><b>軸の順位が決まった過程</b><p>1着軸 '+esc(axis)+'号艇／連軸 '+esc(r.place_axis)+'号艇。数値はモデル内の比較値です。</p>';
 if(rival)html+='<table class="reasoning-table"><tr><th>段階</th><th>'+axis+'号艇</th><th>'+rival+'号艇</th></tr>'+[['独自データ部分',comp.context],['市場由来',comp.market],['混合・補正後',comp.final]].map(([name,rows])=>'<tr><td>'+name+'</td><td>'+fmt(rows?.[axis-1]?.first)+'</td><td>'+fmt(rows?.[rival-1]?.first)+'</td></tr>').join('')+'</table><p class="small">混合前の重み：市場 '+fmt(comp.market_weight)+'・独自 '+fmt(1-comp.market_weight)+'。'+esc(comp.notice||'')+'</p>';
 if(r.sensitivity?.rows?.length)html+='<details><summary>何の要素で軸評価が変わったか</summary><table class="reasoning-table"><tr><th>外して再計算した要素</th><th>'+axis+'号艇への差</th></tr>'+r.sensitivity.rows.map(x=>'<tr><td>'+esc(x.label)+'</td><td>'+esc((100*x.first_delta[axis-1]).toFixed(1))+'ポイント</td></tr>').join('')+'</table><p class="small">'+esc(r.sensitivity.notice)+'</p></details>';
 html+='</div><div class="race-branches"><b>頭候補ごとの展開条件と相手</b><p class="small">'+esc(r.numerical_notice||'')+'</p>';
 for(const b of r.branches||[]){
  html+='<section class="race-branch"><h5>'+b.winner+'号艇が勝つ場合'+(b.course?'／展示'+b.course+'コース':'／進入未確認')+'</h5><p><b>成立に必要な条件</b><br>'+b.conditions.map(esc).join('<br>')+'</p>';
  if(b.counter_evidence?.length)html+='<p><b>反証・評価を下げる材料</b><br>'+b.counter_evidence.map(esc).join('<br>')+'</p>';
  if(b.start_comparison?.status==='uncalibrated_normal_reference')html+='<p class="small">内隣より早いSTとなる正規近似 '+fmt(b.start_comparison.earlier_probability)+'。'+esc(b.start_comparison.notice)+'</p>';
  const mr=b.method_reference;
  if(mr?.status==='historical_reference')html+='<details><summary>決まり手別の2・3着連動実績（'+mr.known+'例）</summary><p class="small">'+esc(mr.notice)+'</p>'+mr.methods.map(m=>'<p>'+esc(m.method)+' '+m.races+'例／コース勝利時の内訳 '+fmt(m.share_among_course_wins)+'<br>'+m.pairs.map(p=>esc(p.combo)+' '+p.count+'例（'+fmt(p.rate)+'）').join('／')+'</p>').join('')+'</details>';
  else html+='<p class="small">決まり手別の連動実績：'+(mr?.known??0)+'例確認／全ラベル確認・20例以上の条件待ち。今回の攻め方の確率は未推定です。</p>';
  html+='<table class="reasoning-table"><tr><th>相手</th><th>条件付き2着</th><th>条件付き3着</th></tr>'+(b.opponents||[]).slice(0,3).map(x=>'<tr><td>'+x.lane+'号艇</td><td>'+fmt(x.second)+'</td><td>'+fmt(x.third)+'</td></tr>').join('')+'</table><p>条件付き上位着順 '+(b.combos||[]).map(x=>esc(x.combo)).join('／')+'。購入採否は価格・配分条件で別に判定します。</p><p class="small"><b>未確認</b> '+(b.unknown||[]).map(esc).join(' ')+'</p></section>';
 }
 html+='</div>';
 if(r.price_audit?.length)html+='<details class="purchase-evidence"><summary>買い目を採った・外した価格根拠</summary><p class="small">1口100円あたりのモデル内期待回収率です。単独の期待値と配分全体の採否を区別します。</p>'+r.price_audit.map(x=>'<p><b>'+esc(x.combo)+(x.selected?' 採用':' 非採用')+'</b>／取得 '+esc(x.odds)+'倍<br>通常 '+fmt(x.unit_expected_roi)+'／下振れ条件 '+fmt(x.stress_unit_expected_roi)+'<br>'+esc(x.reason)+'</p>').join('')+'</details>';
 return html;
}
async function openDetail(){
 const r=data.records?.[selected],snap=r&&latest(r);if(!snap)return;
 if($('fullSupplement')){$('fullSupplement').open=true;$('fullSupplement').scrollIntoView?.({behavior:'smooth',block:'start'})}
 if(!snap._details_compacted){renderDetail();return}
 const code=selected;$('fullDetail').innerHTML='<p>このRの補足データと保存入力を読込中…</p>';
 try{const full=await readRaceArchive(code);if(code!==selected)return;full.race_commentary=r.race_commentary;full.boat_comparison=r.boat_comparison;data.records[code]=full;renderDetail()}catch(e){$('fullDetail').innerHTML='<p>'+esc(e.message)+'</p>'}
}
async function readRaceArchive(code){
 const archived=await getJSON(index.days?.[$('fullDate').value]?.archive_path||'full_history/'+$('fullDate').value+'.json');
 const path=archived.history_storage?.record_paths?.[code];
 const record=path?await getJSON('full_history/'+path):archived.records?.[code];
 if(!record)throw Error('このRの補足データを取得できません');return record;
}
function renderResultPanel(record,snapshot,cutoff,health={}){
 const result=record?.result;
 if(!result){
  const minutes=(Date.now()-Date.parse(cutoff))/60000,waiting=minutes>=0;
  return '<div class="result-panel"><h4>結果</h4><strong>'+(minutes>=10?'結果更新が遅れています':waiting?'結果確認中':'レース前')+'</strong><p>'+(waiting?'公式の着順・払戻を確認中':'締切後に公式結果と照合')+'</p>'+(waiting?'<p class="small">最終確認 '+esc(health.attempt_at?.slice(11,19)||'未取得')+'</p>':'')+'</div>';
 }
 const bet=result.offer_settlements?.[snapshot?.id];
 const summary=b=>'<b>'+(b.hit?(b.profit<0?'的中・ガミ':'的中'):b.refund===b.stake?'全額返還':'不的中')+'</b><br>購入想定 '+esc(b.stake)+'円<br>払戻 '+esc(b.return)+'円（返還 '+esc(b.refund??0)+'円含む）<br>収支 '+esc(b.profit??b.return-b.stake)+'円';
 const first=result.offer_settlements?.[result.purchase_snapshot_id];
 const source=result.result_source?.official_result_source;
 return '<div class="result-panel"><h4>結果</h4><strong>'+esc(result.combo)+'</strong><p>100円払戻 '+esc(result.payout_100yen)+'円</p><p class="small">'+(result.refund_verified?'返還艇：'+esc(result.refund_boats?.join('・')||'なし（公式確認）'):'返還は照合待ち')+'</p><div class="paper-result">この表示予想の仮想照合<br>'+(bet?summary(bet):'購入候補の保存なし')+'</div>'+(first&&result.purchase_snapshot_id!==snapshot?.id?'<details><summary>最初の候補の仮想照合</summary>'+summary(first)+'</details>':'')+(/^https:\/\/www\.boatrace\.jp\/owpc\/pc\/race\/raceresult\?/.test(source||'')?'<p><a href="'+esc(source)+'" target="_blank" rel="noopener noreferrer">公式結果</a></p>':'')+'</div>';
}
function renderComparison(items){
 return '<h3>予想と結果をまとめて確認</h3><table class="race-comparison"><thead><tr><th scope="col">R</th><th scope="col">予想・購入判定</th><th scope="col">結果・払戻</th></tr></thead><tbody>'+[...items].sort((a,b)=>a.race_code.localeCompare(b.race_code)).map(item=>{
 const r=data.records?.[item.race_code],s=r&&latest(r),ps=s&&purchaseSnapshot(r,s),p=ps?.purchase_plan,result=r?.result;
 const reason={odds_stale:'保存時：オッズ更新遅延',odds_incomplete:'保存時：オッズ不足',preview_pending:'保存時：展示未確認',no_feasible_plan:'保存時：条件を満たす買い目なし',no_value:'保存時：期待値条件未達',no_bet:'保存時：見送り'};
 const ready=p?.status==='ready'&&Array.isArray(p.tickets)&&p.tickets.length>0;
 const prediction=ready?p.tickets.map(t=>esc(t.combo)).join('／')+'<br>'+p.tickets.length+'点・'+esc(p.budget)+'円（保存時）':s?'購入候補なし<br>'+esc(reason[p?.status]||('保存時：'+(p?.status||'判定情報なし'))):'予想保存待ち';
 return '<tr><th scope="row"><a href="#race-'+esc(item.race_code)+'">'+(Number($('venue').value)?'':esc(names[item.venue])+' ')+esc(item.race)+'R</a></th><td>'+prediction+'</td><td>'+ (result?'<b>'+esc(result.combo)+'</b><br>'+esc(result.payout_100yen)+'円 / 100円':Date.now()>=Date.parse(item.cutoff||s?.cutoff)?'結果確認中':'レース前')+'</td></tr>';
 }).join('')+'</tbody></table>';
}
function records(){const venue=Number($('venue').value);return Object.values(data?.records||{}).filter(r=>!venue||Number(r.venue)===venue).sort((a,b)=>b.race_code.localeCompare(a.race_code))}
function catalogRows(){const v=Number($('venue').value);return Object.values(data?.catalog||index?.catalogs?.[$('fullDate').value]||{}).filter(r=>!v||Number(r.venue)===v).sort((a,b)=>a.race_code.localeCompare(b.race_code))}
let quickRows=[],activeRace=null,quickScope='',raceObserver=null,manualRaceUntil=0;
function syncQuickSelection(){
 const pos=quickRows.findIndex(x=>x.race_code===activeRace);
 if($('fullQuickRace')){$('fullQuickRace').value=pos<0?'':activeRace;$('fullQuickRace').disabled=pos<0;}
 if($('fullQuickPrev'))$('fullQuickPrev').disabled=pos<=0;
 if($('fullQuickNext'))$('fullQuickNext').disabled=pos<0||pos>=quickRows.length-1;
 if($('fullQuickStatus'))$('fullQuickStatus').textContent=pos<0?'この日の選択中の場にはレースがありません':'選択中：'+names[quickRows[pos].venue]+' '+quickRows[pos].race+'R ／ 前R・次Rでも切り替えられます';
 $('fullRecords')?.querySelectorAll('[data-six-code]').forEach(el=>{el.open=el.dataset.sixCode===activeRace;});
 $('fullRaceNav')?.querySelectorAll('a').forEach(a=>a.setAttribute?.('aria-current',a.getAttribute('href')==='#race-'+activeRace?'true':'false'));
}
function renderQuickNav(rows,scope){
 const changed=quickScope!==scope;quickScope=scope;
 quickRows=rows.slice().sort((a,b)=>a.race_code.localeCompare(b.race_code));
 if(changed||!quickRows.some(x=>x.race_code===activeRace))activeRace=rows[0]?.race_code||null;
 const picker=$('fullQuickRace');
 if(picker){const html=quickRows.length?quickRows.map(x=>'<option value="'+esc(x.race_code)+'">'+esc(names[x.venue])+' '+x.race+'R'+(x.cutoff?' · '+esc(x.cutoff.slice(11,16)):'')+'</option>').join(''):'<option value="">レースなし</option>';if(picker.innerHTML!==html)picker.innerHTML=html;}
 if($('fullQuickVenue'))$('fullQuickVenue').value=$('venue').value;
 syncQuickSelection();
}
function jumpToRace(code){
 const row=quickRows.find(x=>x.race_code===code);if(!row)return;
 activeRace=code;manualRaceUntil=Date.now()+1500;
 // The national list initially renders 24 races; make an off-screen selection available too.
 if(!$('race-'+code)&&String(Number($('venue').value))==='0'){raceVisible=Math.max(raceVisible,quickRows.length);render();}
 syncQuickSelection();const target=$('race-'+code);
 target?.scrollIntoView?.({block:'start',behavior:'auto'});target?.focus?.({preventScroll:true});
}
function observeReadingRace(){
 if(typeof IntersectionObserver==='undefined')return;
 raceObserver?.disconnect();raceObserver=new IntersectionObserver(entries=>{
  if(Date.now()<manualRaceUntil)return;
  const hit=entries.filter(x=>x.isIntersecting).sort((a,b)=>a.boundingClientRect.top-b.boundingClientRect.top)[0];
  if(hit){activeRace=hit.target.id.slice(5);syncQuickSelection();}
 },{rootMargin:'-8% 0px -65% 0px',threshold:0});
 $('fullRecords').querySelectorAll('.race-card').forEach(card=>raceObserver.observe(card));
}
function render(){
 if(!index||!data)return;
 const list=records(),venue=String(Number($('venue').value)),day=$('fullDate').value;
 const phaseCounts={initial:0,preview:0,partial:0,missed:0,old:0};for(const r of list){const snap=latest(r),stage=snap?.phase;if(stage==='initial'&&Date.now()>=Date.parse(snap.cutoff))phaseCounts.missed++;else if(stage in phaseCounts)phaseCounts[stage]++;else phaseCounts.old++}
 const group=index.days?.[day],stats=venue==='0'?group?.summary:group?.venues?.[venue];
 const h=data.health||index.health||{},age=(Date.now()-Date.parse(h.attempt_at||data.updated_at))/60000,today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo'}).format(new Date())===day,stale=today&&age>(h.stale_after_minutes||5);
 $('fullStatus').textContent=(stale?'【更新遅延 '+Math.floor(age)+'分】 ':h.state==='degraded'?'【一部の直前情報が未取得】 ':'')+'総合予想更新：'+(data.updated_at||index.updated_at)+' ／ '+(index.model||'')+(h.collection_mode==='live_watch'?' ／ ライブ更新を監視中':' ／ 取得できた情報で再計算')+(h.missing_forecasts?.length?' ／ 保存待ち '+h.missing_forecasts.length+'R':'');
 $('fullHealth').textContent=(stale?'自動更新が遅れています。最新の買い目として扱う前に更新時刻を確認してください。 ':'')+'取得失敗 '+Object.keys(h.source_errors||{}).length+'件 ／ '+Object.entries(h.source_counts||{}).map(([k,v])=>k+':'+v).join('・')+'。自動実行には遅延・欠落が起こる場合があります。';
 if(data.quote_health)$('fullStatus').textContent+=' ／ 直前オッズ確認 '+esc(data.quote_health.attempt_at?.slice(11,19))+'（'+data.quote_health.confirmed+'/'+data.quote_health.targets+'R）';
 if(data.quote_health?.context_errors&&Object.keys(data.quote_health.context_errors).length){const keys=Object.keys(data.quote_health.context_errors);$('fullStatus').textContent+=' ／ 直前情報の取得待ち：'+[keys.some(k=>k.startsWith('before_'))?'公式展示':null,keys.some(k=>k.startsWith('water_'))?'水面観測':null,keys.some(k=>k.startsWith('original_'))?'足別タイム':null].filter(Boolean).join('・')+'（確認済みの情報を保持）';}
 if(data.settlement_updated_at)$('fullStatus').textContent+=' ／ 精算更新 '+data.settlement_updated_at;
 $('fullStatus').textContent+=' ／ 表示中：展示後 '+phaseCounts.preview+'件・直前情報一部 '+phaseCounts.partial+'件・展示前 '+phaseCounts.initial+'件'+(phaseCounts.missed?'・展示更新なし（締切済み） '+phaseCounts.missed+'件':'')+(phaseCounts.old?'・旧版 '+phaseCounts.old+'件':'');
 let tiles=[`<div class="metric">研究予想の保存履歴（購入条件とは別）<strong>${list.length}</strong>予定 ${catalogRows().length}R ／ 予想未保存 ${catalogRows().filter(x=>!data.records?.[x.race_code]).length}R<br>必須情報使用 ${stats?.complete_inputs??0}件<br>結果確定 ${stats?.settled??0}件 ／ 待ち ${stats?.pending??0}件</div>`];
 for(const n of [12,18]){const s=stats?.[n]||{};tiles.push(`<div class="metric">研究${n}点的中率<strong>${pct(s.hit_rate)}</strong>${s.hits??0}/${s.races??0}レース</div><div class="metric">研究${n}点回収率<strong>${pct(s.roi)}</strong>仮想収支 ${s.profit??0}円</div>`)}
 const ng=(index.purchase_policy===purchasePolicy?stats?.no_gami:null)||{};tiles.unshift(`<div class="metric">旧集計：各R最初の購入候補の仮想成績<strong>${pct(ng.roi)}</strong>${ng.races??0}R ／ 的中 ${ng.hits??0}R<br>収支 ${ng.profit??0}円<br>各Rの最初の有効候補1件・保存後の仮想検証<br>返還未照合 ${ng.refund_unverified??0}R／モデル別成績は下に表示</div>`);const fixed=(index.decision_report?.decisions||[]).filter(x=>x.freeze_at?.startsWith(day)&&(venue==='0'||Number(x.venue)===Number(venue)));if(fixed.length){const bets=fixed.filter(x=>x.paper),stake=bets.reduce((v,x)=>v+x.paper.stake,0),returned=bets.reduce((v,x)=>v+x.paper.return,0);tiles.unshift('<div class="metric">締切2分前・公開確認による固定評価<strong>'+pct(stake?returned/stake:null)+'</strong>結果照合 '+bets.length+'R／仮想収支 '+(returned-stake)+'円<br>見送り '+fixed.filter(x=>x.state==='skip').length+'R／情報不足 '+fixed.filter(x=>x.state==='pending').length+'R／公開確認なし '+fixed.filter(x=>x.state==='unavailable').length+'R<br>過去の最初の候補と別集計</div>')}$('fullMetrics').innerHTML=tiles.join('');
 const catalog=catalogRows(),known=new Set(catalog.map(r=>r.race_code));
 const cutoffOf=item=>Date.parse(item.cutoff||latest(data.records?.[item.race_code]||{})?.cutoff||'');
 const rows=[...catalog,...list.filter(r=>!known.has(r.race_code))].sort((a,b)=>{const ac=cutoffOf(a),bc=cutoffOf(b),af=Date.now()<ac,bf=Date.now()<bc;return Number(bf)-Number(af)||(af&&bf?ac-bc:0)||a.race_code.localeCompare(b.race_code)});
 const next=rows.find(item=>Date.now()<cutoffOf(item));
 if($('fullPurchaseSummary')){
  const r=next&&data.records?.[next.race_code],s=r&&latest(r),view=s&&purchaseView(purchaseSnapshot(r,s));
  $('fullPurchaseSummary').innerHTML=next?'<b>次のレース：'+esc(names[next.venue])+' '+esc(next.race)+'R</b><br>'+(view?view.html:'<strong>判定保留：購入候補の保存待ち</strong>')+(s?'<p class="small">オッズ時刻 '+esc(purchaseSnapshot(r,s).purchase_plan?.odds_observed_at?.slice(11,19)||'未取得')+' ／ 候補計算 '+esc(purchaseSnapshot(r,s).created_at.slice(11,19))+'</p>':''):'締切前のレースはありません。各Rの保存時の判定は下に表示します。';
 }

 renderQuickNav(rows,day+'|'+venue);
 const visible=venue==='0'?rows.slice(0,raceVisible):rows;
 if($('fullRaceComparison'))$('fullRaceComparison').innerHTML=renderComparison(visible);
 if($('fullRaceNav'))$('fullRaceNav').innerHTML=visible.map(x=>'<a href="#race-'+esc(x.race_code)+'">'+(venue==='0'?esc(names[x.venue])+' ':'')+x.race+'R</a>').join('');
 $('fullRecords').innerHTML=visible.map(item=>{
  const r=data.records?.[item.race_code],snap=r&&latest(r);
  if(!snap)return '<article class="race-card" tabindex="-1" id="race-'+esc(item.race_code)+'"><h3>'+esc(names[item.venue])+' '+item.race+'R</h3><p>'+esc(raceStates[item.state]||'予想作成待ち')+'</p><p>締切 '+esc(item.cutoff?.slice(11,16)||'未確認')+'</p>'+renderResultPanel(r,null,item.cutoff,data.result_health)+'</article>';
  const ps=purchaseSnapshot(r,snap),v=purchaseView(ps),c=r.race_commentary,closed=Date.now()>=Date.parse(snap.cutoff);
  return '<article class="race-card" tabindex="-1" id="race-'+esc(r.race_code)+'" data-full-code="'+esc(r.race_code)+'"><header class="race-card-heading"><h3>'+esc(names[r.venue])+' '+r.race+'R</h3><span>締切 '+esc(snap.cutoff.slice(11,16))+(closed?'／締切済み':'／あと'+Math.max(0,Math.ceil((Date.parse(snap.cutoff)-Date.now())/60000))+'分')+'</span></header>'+(c?'<section class="race-hypothesis"><h4>予想の仮説・想定展開</h4>'+renderNarrative(c)+'</section>':'<p class="small">予想仮説は未保存・取得待ちです。</p>')+'<div class="prediction-result-pair"><div class="purchase-main"><h4>予想・買い目</h4>'+v.html+(v.valid?'<p class="small">取得時の最低想定払戻 '+Math.min(...ps.purchase_plan.tickets.map(t=>t.expected_return))+'円</p>':'')+'</div>'+renderResultPanel(r,ps,snap.cutoff,data.result_health)+'</div><p class="quote-clock">予想 '+esc(snap.created_at.slice(11,19))+' ／ オッズ '+esc(snap.purchase_plan?.odds_observed_at?.slice(11,19)||'未取得')+'<br>確率は校正検証中／情報段階：'+esc(({initial:'展示前の暫定評価',partial:'直前情報は一部取得',preview:'展示後'})[snap.phase]||snap.phase)+(snap.context_snapshot_at?'／オッズ以外の入力 '+esc(snap.context_snapshot_at.slice(11,19)):'')+'</p><details class="purchase-evidence"><summary>オッズ・配分と購入条件の根拠</summary><p>'+v.metrics+'</p><p>点数可変・上限1,200円。全買い目の取得時払戻が総購入額を超える配分に限定。オッズ変動後のガミや利益を保証する条件ではありません。</p></details>'+(globalThis.Boat24Study?.race((index.prospective_study?.race_audit||[]).find(x=>x.race_code===r.race_code))||'')+'<details class="optional-boat-comparison"><summary>6艇の詳細比較（必要なときだけ表示）</summary>'+renderBoatComparison(r.boat_comparison,r.race_code)+'</details><button type="button" data-full-detail="'+esc(r.race_code)+'">使った情報を見る</button></article>';
 }).join('')+(venue==='0'&&rows.length>visible.length?'<button type="button" id="fullMoreRaces">さらに24Rの予想・見解を見る</button>':'');
 $('fullRecords').querySelectorAll('[data-full-detail]').forEach(b=>b.addEventListener('click',()=>{selected=b.dataset.fullDetail;openDetail()}));
 $('fullMoreRaces')?.addEventListener('click',()=>{raceVisible+=24;render()});
 if(!rows.length)$('fullRecords').innerHTML='<p>この日の総合予想はまだ保存されていません。旧モデルの保存履歴は下に残しています。</p>';
 syncQuickSelection();observeReadingRace();
 if(selected&&data.records[selected]&&!latest(data.records[selected])?._details_compacted)renderDetail();
 renderReport();
 renderVenueCoverage();
 const check=index.training?.validation||{},loss=check.test_mean_logloss||{};
 if(globalThis.Boat24Integrated)Boat24Integrated.learning(index);
 $('fullTraining').textContent=(index.training?.frozen_for_forward_evaluation?'採用済みモデルを固定して前向き検証中（自動再学習による切替停止）。 ':'')+'場別水面モデル／参照データ：'+(index.training?.through||'―')+'まで ／ '+(index.training?.samples??0)+'艇標本（朝・展示別） ／ コース集計 '+(index.training?.course_window_days??'―')+'日 ／ 過去情報の取得失敗 '+Object.keys(index.training?.source_errors||{}).length+'件。総合モデル開始後の成績を、旧モデルと分けて集計しています。男女構成・開催条件・相手関係を追加。調整用と最終評価用の期間を分離しています。未学習の潮汐・コメント等の仮補正は停止しました。映像AI解析は未実装です。調整 '+(check.tuning_races??'―')+'R／別期間の校正 '+(check.calibration_races??'―')+'R／さらに別期間の最終評価 '+(check.test_races??'―')+'R。市場単独への改善：'+(loss.selected!=null&&loss.market!=null&&loss.selected<loss.market?'短期評価では確認・長期未証明':'未確認')+'。要素を外した比較 '+(check.ablations?.races??0)+'R：'+Object.entries(check.ablations?.mean_logloss||{}).map(([k,v])=>({none:'全要素',behavior:'ST・進入なし',motor_history:'モーター履歴なし',course:'コース実績なし',race_conditions:'開催条件なし',wind:'場別の風なし',tide:'場別の潮汐なし'}[k]||k)+' '+Number(v).toFixed(3)).join('／')+'（対数損失：低いほど良い。短期比較です）';
}
function renderPipelineHealth(h){
 if(!h)return '';
 const c=h.collector||{},p=h.publication||{},o=h.public_observation||{},sum=x=>Object.values(x||{}).reduce((n,r)=>n+(Number(r.seconds)||0),0),sec=x=>Number.isFinite(Number(x))?Number(x).toFixed(1)+'秒':'未計測';
 const labels={saved:'計算・保存済み（公開前）',unchanged_saved_snapshot:'同じ入力の保存版を保持',odds_unconfirmed:'オッズ未確認',compute_failed:'計算失敗',not_saved_by_timing_or_model_gate:'保存条件未達'};
 let html='<details class="purchase-evidence"><summary>データ取得から公開までの実測状況</summary><p>公式情報の更新時刻と、サイト側の処理時刻を区別します。最後の公開取得確認：'+esc(h.last_observed_at||'未確認')+'</p><p>入力取得 '+sec(c.stages?.acquire?.seconds)+'／予想計算（合計） '+sec(Object.values(c.races||{}).reduce((n,r)=>n+(Number(r.compute_seconds)||0),0))+'／公開待ち '+sec(p.lock_wait_seconds)+'／公開処理 '+sec(sum(p.stages))+'／公開取得確認 '+sec(sum(o.stages))+'</p>';
 const rejected=Object.values(p.rejected_context_updates||{}).reduce((n,ids)=>n+ids.length,0);
 if(rejected)html+='<p>新しい文脈との整合性確認で公開対象外になった更新：'+rejected+'件。元の入力が古い更新は、そのまま最新予想には採用しません。</p>';
 const rows=Object.entries(c.races||{}).filter(([code])=>!Number($('venue').value)||Number(code.slice(8,10))===Number($('venue').value));
 if(rows.length)html+='<div class="scroll"><table><tr><th>R</th><th>取得・計算</th><th>公式オッズ更新</th><th>展示の取得確認</th></tr>'+rows.map(([code,r])=>{const b=r.source_checks?.before;return '<tr><td>'+esc(names[Number(code.slice(8,10))])+' '+Number(code.slice(10))+'R</td><td>'+esc(labels[r.state]||'処理確認待ち')+'／'+sec(r.compute_seconds)+'</td><td>'+esc(r.official_quote_at?.slice(11,19)||'未確認')+'</td><td>'+esc(!b?'計測なし':b.state==='parsed'?'対象R・艇番・展示を照合済み':b.state==='verified_page_preview_incomplete'?'対象R照合済み・展示数値未確認（未公表／解析問題は未判定）':'取得・照合未確認')+'</td></tr>'}).join('')+'</table></div>';
 return html+'</details>';
}
function renderFixedDecisions(d){
 if(!d)return '<p>締切2分前の固定評価：公開データの取得確認を開始する前です。</p>';
 const c=d.counts||{},labels={buy:'購入候補',skip:'見送り',pending:'情報不足・保留',unavailable:'公開確認なし',historical_unverified:'過去・公開時刻未確認',awaiting_freeze:'固定時刻前',cutoff_unknown:'締切時刻未確認',cancelled:'中止確認'};
 const reasons={risk_no_positive_value:'下振れ条件で期待回収率が基準未達',risk_no_feasible_plan:'下振れ時のガミ回避・集中上限を両立する配分なし',no_positive_value:'期待回収率が基準未達',no_feasible_plan:'条件に合う配分なし',odds_stale:'オッズ更新待ち',odds_incomplete:'オッズ不足',preview_pending:'展示・進入の確認待ち',probabilities_invalid:'確率の整合性を確認できない',quote_expired_at_freeze:'固定時刻でオッズが古い',unsupported_plan_policy:'旧条件のため対象外',invalid_saved_allocation:'保存配分の整合性を確認できない',computed_after_freeze:'固定時刻までに計算が未完了',no_public_payload_observed_before_freeze:'固定時刻までに公開データの取得確認なし',public_cancellation_observed:'公開データで中止を確認'};
 let html='<h3>締切2分前に固定した予想の検証</h3><p>開始 '+esc(d.protocol?.started_at||'公開取得確認待ち')+'。締切2分前までに公開データを取得確認できた最新版を固定します。実購入ではなく仮想照合です。遅延・見送りも数え、後から当たった版へ差し替えません。</p><p>'+Object.entries(c).map(([k,n])=>esc(labels[k]||k)+' '+esc(n)+'R').join('／')+'</p>';
 const groups=d.model_rows||[];
 if((d.last_public_observed_at||d.updated_at)&&Date.now()-Date.parse(d.last_public_observed_at||d.updated_at)>300000)html+='<p class="warning">公開取得確認・固定処理の更新が5分以上前です。固定結果の反映待ちがある可能性があります。</p>';
 html+=groups.length?'<p>全保存期間・全場のモデル別成績</p><div class="scroll"><table><tr><th>モデル・段階</th><th>購入候補・的中</th><th>回収率・収支</th><th>的中時のガミ／最大損失幅／連続損失</th></tr>'+groups.map(g=>'<tr><td>'+esc(g.model_id?.slice(0,12))+'／'+esc(g.phase)+'</td><td>'+g.races+'R／'+g.hits+'R</td><td>'+pct(g.roi)+'／'+g.profit+'円</td><td>'+g.gami+'R／'+esc(g.max_drawdown??0)+'円／'+esc(g.max_loss_streak??0)+'R</td></tr>').join('')+'</table></div>':'<p>この固定条件での結果確定を待っています。過去の最初の候補の成績は下段に区別して表示します。</p>';
 const rows=(d.decisions||[]).filter(r=>r.state!=='historical_unverified'&&r.state!=='awaiting_freeze'&&(!Number($('venue').value)||Number(r.venue)===Number($('venue').value)));
 if(rows.length)html+='<div class="scroll"><table><tr><th>レース</th><th>固定した判定・買い目</th><th>結果</th><th>仮想収支</th></tr>'+rows.map(r=>'<tr><td>'+esc(names[r.venue])+' '+r.race+'R<br>'+esc(r.freeze_at?.slice(0,10))+' '+esc(r.freeze_at?.slice(11,19))+'</td><td>'+esc(labels[r.state]||r.state)+'<br>'+(r.state==='buy'?(r.plan?.tickets||[]).map(t=>esc(t.combo)+'：'+t.stake+'円').join('<br>'):esc(reasons[r.reason]||'判定条件の確認待ち'))+'<br>公開取得確認 '+esc(r.observed_at?.slice(11,19)||'なし')+'</td><td>'+esc(r.result||'結果待ち')+'</td><td>'+(r.paper?r.paper.profit+'円（払戻 '+r.paper.return+'円）':'購入候補なし・照合待ち')+'</td></tr>').join('')+'</table></div>';
 const bins=Object.entries(d.purchase_probability_bins||{});
 if(bins.length)html+='<h4>購入候補として選んだ組み合わせ全体の確率点検</h4><p>確率帯ごとの推定的中数と実際の的中数を比較します。返還・同着のあるRは確率点検から除外。少数標本では確率の妥当性を判断できません。</p><div class="scroll"><table><tr><th>推定的中確率帯</th><th>R数</th><th>推定的中数</th><th>実際の的中数</th></tr>'+bins.map(([k,b])=>'<tr><td>'+Number(k)*10+'％台</td><td>'+b.races+'</td><td>'+b.expected_hits.toFixed(2)+'</td><td>'+b.hits+'</td></tr>').join('')+'</table></div>';
 const pairs=Object.entries(d.paired_rows||{});
 if(pairs.length)html+='<h4>同じ公開保存版・同じ配分条件の候補比較</h4><p>両案が事前保存された同じRだけを比較。双方とも未検証確率の下振れ20％・価格10％・1点25％上限で計算。実際の表示候補とは別の研究比較です。</p><div class="scroll"><table><tr><th>案</th><th>共通R／購入／見送り／保留</th><th>的中／回収率／収支</th></tr>'+pairs.map(([name,g])=>'<tr><td>'+esc(name==='baseline'?'現行モデル':'追加要素の候補モデル')+'</td><td>'+g.comparable_races+'／'+g.buys+'／'+g.skips+'／'+g.pending+'</td><td>'+g.hits+'／'+pct(g.roi)+'／'+g.profit+'円</td></tr>').join('')+'</table></div>';
 return html;
}
function renderReport(){
 const choice=$('fullReportGroup')?.value||'all',group=choice==='venue'?(Number($('venue').value)?'venue:'+Number($('venue').value):'all'):choice;
 const rows=(index.forward_report?.rows||[]).filter(r=>r.group===group);
 const el=$('fullForward');if(!el)return;
 const labels={new:'新モデル12点均等',old:'旧モデル12点均等',market:'同時刻市場12点均等',allocated_paper:'オッズ選択・配分（仮想）'};
 el.innerHTML=renderPipelineHealth(index.pipeline_health)+renderFixedDecisions(index.decision_report)+'<h3>過去の保存予想の比較検証</h3><p class="small">新旧・市場の3者比較は同じレースだけで集計します。旧版と新版の保存時刻は異なります。朝にオッズがなければ市場比較から除外。性別・開催場・予想段階別も集計しています。</p>'+(rows.length?'<table><tr><th>比較</th><th>対象</th><th>的中</th><th>回収率</th><th>的中率95%区間</th></tr>'+rows.map(r=>`<tr><td>${esc(labels[r.model]||r.model)}</td><td>${r.cohort==='same_races'?'3者共通':'取得分'} ${r.races}R</td><td>${r.hits}/${r.races}</td><td>${pct(r.roi)}</td><td>${r.hit_rate_interval95.map(pct).join('〜')}</td></tr>`).join('')+'</table>':'<p>新しい比較条件での結果確定を待っています。</p>');
 const audit=index.forward_report?.input_audit;
 if(audit)el.innerHTML+='<p class="small">全保存期間の比較入力点検：'+esc(audit.evaluated_races)+'R／保存済みの同時刻オッズから市場比較を再構成 '+esc(audit.market_rebuilt)+'R／元オッズ不足で比較除外 '+esc(audit.market_excluded)+'R／時点不整合・未確認の研究配分を除外 '+esc(audit.allocation_excluded)+'R。購入候補の仮想精算とは別です。</p>';
 if(index.integrated_learning?.policy==='public-frozen-learning-1')el.innerHTML+='<p>学習・採用の比較は、締切前に公開確認して固定した可変点数・金額配分を使用します。旧12点均等の研究比較は採用判定から分離しています。取得不足・結果未確認などの除外理由も記録します。</p>';
 const cohorts=index.purchase_forward_report?.protocol_comparison_rows||index.purchase_forward_report?.rows||[],protocol=index.purchase_forward_report?.protocol;
 el.innerHTML+='<h3>旧集計：最初の購入候補のモデル別成績</h3><p>条件ごとに各Rの最初の有効候補を1件だけ集計します。条件間の件数は合算しません。保存時刻に基づく仮想検証で、公開時刻・実購入の検証ではありません。旧12点・18点の成績とは別集計です。固定条件 '+esc(protocol?.id||'未設定')+'。少数標本で収益性を証明できません。</p>'+(cohorts.length?'<table><tr><th>保存条件／モデル／段階</th><th>対象・的中</th><th>購入想定／払戻</th><th>回収率</th></tr>'+cohorts.map(g=>'<tr><td>'+esc(g.protocol_id==='historical-reconstructed'?'過去保存から復元':g.protocol_id)+'<br>'+esc(g.model)+'<br>'+esc(g.model_id)+'<br>'+esc(g.phase)+'</td><td>'+g.races+'R／'+g.hits+'R<br>全額返還 '+g.fully_refunded+'R<br>返還未照合 '+g.refund_unverified+'R</td><td>'+g.stake+'円／'+g.return+'円<br>返還 '+g.refund+'円含む</td><td>'+pct(g.roi)+'</td></tr>').join('')+'</table>':'<p>条件を満たす候補の結果確定を待っています。</p>');
}
function renderOfferHistory(r){
 const offers=Object.values(r.offers||{}).sort((a,b)=>a.created_at.localeCompare(b.created_at)||a.snapshot_id.localeCompare(b.snapshot_id));
 const res=r.result||{};
 const research=[12,18].filter(n=>res.paper?.[String(n)]).map(n=>{const b=res.paper[String(n)];return '<tr><td>研究'+n+'点</td><td>'+b.stake+'円</td><td>'+b.return+'円（返還 '+(b.refund??0)+'円含む）</td><td>'+(b.return-b.stake)+'円</td></tr>'}).join('');
 const proof=res.result_source?.official_result_source;
 const researchHTML=(research?'<h3>研究予想の仮想精算（購入候補とは別）</h3><div class="scroll"><table><tr><th>条件</th><th>購入想定</th><th>払戻合計</th><th>収支</th></tr>'+research+'</table></div>':'')+(res.refund_verified&&/^https:\/\/www\.boatrace\.jp\/owpc\/pc\/race\/raceresult\?/.test(proof||'')?'<p><a href="'+esc(proof)+'" target="_blank" rel="noopener noreferrer">公式結果・返還の確認元</a></p>':'');
 return '<h3>提示候補の保存履歴と精算</h3><p>後の見送りでも保存済み候補は消しません。主集計は各Rの最初の有効候補1件です。購入実績ではなく、締切前に保存された候補の仮想精算です。</p>'+(offers.length?'<div class="scroll"><table><tr><th>保存時刻・条件</th><th>買い目と配分</th><th>精算</th></tr>'+offers.map(o=>{const b=res.offer_settlements?.[o.snapshot_id];return '<tr><td>'+esc(o.created_at)+(o.snapshot_id===res.purchase_snapshot_id?'<br>主集計対象':'<br>更新版・主集計に重複加算しない')+'<br>'+esc(o.protocol_id||'過去保存から復元')+'</td><td>'+o.tickets.map(t=>esc(t.combo)+'：'+t.stake+'円').join('<br>')+'</td><td>'+(b?'購入想定 '+b.stake+'円<br>払戻 '+b.return+'円（返還 '+b.refund+'円含む）<br>収支 '+b.profit+'円':'結果待ち')+'</td></tr>'}).join('')+'</table></div>':'<p>有効な購入候補の保存はありません。</p>')+'<p>返還艇：'+(res.refund_verified?esc((res.refund_boats||[]).join('・')||'なし（公式確認）'):'公式照合待ち・精算は暫定')+'</p>'+researchHTML;
}
function displayAudit(s,r){
 const out=Object.fromEntries(Object.entries(s.feature_usage||{}).map(([k,v])=>[k,{...v}])),p=s.water_context?.profile||index.training?.venue_profiles?.[String(r.venue)];
 if(out.tide){out.tide.label=(names[r.venue]||'当該場')+'の潮汐推算';if(p?.tidal_range==='なし')Object.assign(out.tide,{status:'not_applicable',reason:'公式場データで干満差なし'});else if(!s.water_context)Object.assign(out.tide,{status:'not_implemented',reason:'この保存版には場別潮汐モデルが未実装'})}
 if(out.wind){out.wind.label=(names[r.venue]||'当該場')+'の風とコース別実績';if(!s.water_context&&r.venue!==15)Object.assign(out.wind,{status:'not_implemented',reason:'この保存版には場別の風モデルが未実装'})}
 if(out.comments&&!s.details&&r.venue!==15&&!out.comments.available_fields?.length)Object.assign(out.comments,{status:'not_implemented',reason:'この場の選手コメント自動取得は未実装'});
 for(const f of Object.values(out))if(f.status==='used'&&(f.unused_fields?.length||f.used_lanes<f.available_lanes))f.status='partial_used';
 return out;
}
function renderVenueCoverage(){
 const el=$('fullVenueCoverage');if(!el)return;const profiles=index.training?.venue_profiles||{},coverage=index.training?.venue_coverage||{};
 el.innerHTML='<h3>24場の水面条件・学習状況</h3>'+(!Object.keys(profiles).length?'<p>場別モデルの作成待ちです。旧版を場別対応済みとして表示しません。</p>':'<table><tr><th>場</th><th>水質／干満差</th><th>潮汐の参照地点</th><th>風・潮汐の学習対象</th></tr>'+Object.entries(profiles).map(([v,p])=>{const c=coverage[v]||{};return `<tr><td>${esc(p.name)}</td><td>${esc(p.water_type)}／${esc(p.tidal_range)}</td><td>${p.tide_source?esc(p.tide_source.name)+'<br><span class="small">'+esc(p.tide_source.scope)+'</span>':'対象外（干満差なし）'}</td><td>風 ${c.wind_races??0}R／潮汐 ${c.tide_races??0}R<br>${c.days??0}日・${esc(c.latest_day||'標本なし')}</td></tr>`}).join('')+'</table><p class="small">潮位の変化量は流速ではありません。近隣港の推算を使う場では、水面への伝播差・流速を実測したとは扱いません。</p>');
}
function renderWater(s){
 const w=s.water_context;if(!w)return '<p class="warning">この保存版には新しい場別の水面モデルがありません。過去予想は書き換えません。</p>';
 const p=w.profile,t=w.tide||{},wind=w.latest_official_wind||{};
 return `<h3>${esc(p.name)}の水面・風・潮汐</h3><p>水質：${esc(p.water_type)} ／ 公式の干満差：${esc(p.tidal_range)}<br>潮汐：${t.status==='not_applicable'?'対象外（公式に干満差なし）':t.status==='available'?esc(t.station)+'の天文潮汐推算を参照':'対象日の推算が未取得'}<br>${esc(t.scope||t.reason||'')}<br>公式の風：${esc(wind.wind_direction_literal||'未取得')} ${esc(wind.wind_quality_literal||'')} ／ 計測 ${esc(wind.measured_at||'未取得')}<br>${esc(w.wind_method)}<br>実測の流速・競走水面の実潮位は未取得です。</p><p>${(w.condition_evidence_by_boat||[]).map((e,i)=>`${i+1}艇：同場・同進入・同風条件 ${e.wind?.same_venue_course_condition_samples??0}例／同潮汐条件 ${e.tide?.same_venue_course_condition_samples??0}例`).join('<br>')}</p>`;
}
function renderDetail(){
 const r=data?.records?.[selected],s=r&&latest(r);if(!s)return;
 const history=s.input_snapshot?.motor_history||{},previews=s.input_snapshot?.previews||{},official=s.input_snapshot?.official||{},tide=s.input_snapshot?.tide_schedule;
 const allocation=s.allocation||{},behavior=s.behavior_forecast||{};
 const times=s.input_snapshot?.source_times||{},ctx=s.input_snapshot?.race_context||{};
 $('fullDetail').innerHTML=`<h3>${esc(names[r.venue])} ${esc(r.race)}R｜実際に使った情報</h3><p>計算 ${esc(s.created_at)} ／ 締切 ${esc(s.cutoff)}<br>購入判定はレースカードに表示／確率は校正検証中</p>${renderOfferHistory(r)}${renderWater(s)}${globalThis.Boat24Integrated?Boat24Integrated.render(s,r,index):''}<div class="scroll"><table class="feature-audit"><tr><th>情報</th><th>状態</th><th>使用した項目</th></tr>${Object.entries(displayAudit(s,r)).map(([key,f])=>`<tr><td>${esc(f.label)}</td><td>${esc(statuses[f.status]||f.status)}${['not_applicable','not_implemented'].includes(f.status)?'':key==='odds'?'':`（使用 ${f.used_lanes||0}/6艇・取得 ${f.available_lanes||0}/6艇）`}${f.reason?'<br>'+esc(f.reason):''}</td><td>${esc((f.used_fields||[]).map(k=>k+'（'+(f.field_coverage?.[k]??0)+'/6艇）').join('・')||(key==='odds'?`${f.valid_combinations||0}/120組、確率への市場情報比率 ${pct(f.market_blend)}`:'―'))}${f.unused_fields?.length?'<br>取得済み・計算未使用：'+esc(f.unused_fields.join('・')):''}</td></tr>`).join('')}</table></div><h3>ガミなし想定の購入候補</h3><p>${purchaseView(purchaseSnapshot(r,s)).html}<br>${purchaseView(purchaseSnapshot(r,s)).metrics}</p><p>1レース1,200円を上限に点数と100円単位の配分を比較。全買い目の想定払戻が購入総額を超え、モデル推定回収率が100％を超える案から、的中確率×（推定回収率−100％）で比較します。近似探索であり、全候補での最大値や実際の利益は未証明です。合成7倍の条件はありません。オッズ変動によるガミまでは保証できません。</p><details><summary>旧条件の研究用配分・購入候補ではありません</summary><h3>オッズ選択と100円単位の仮想配分</h3><p>仮想予算 ${allocation.budget??'―'}円 ／ 目標 ${allocation.target??7}倍 ／ ${allocation.status==='odds_incomplete'?'オッズ不足・配分待ち':allocation.rounded_target_met?'100円単位でも目標到達':allocation.status?'100円単位の最低払戻倍率は目標未達':'旧版・配分記録なし'}<br>最低払戻 ${num(allocation.minimum_hit_return)}円〜最高 ${num(allocation.maximum_hit_return)}円 ／ 最低払戻倍率 ${num(allocation.rounded_minimum_return_multiple)}倍<br>予算は比較用の仮想2,400円です。近似探索による候補で、最大利益や的中を保証するものではありません。</p><p>${(allocation.tickets||[]).map(t=>esc(t.combo)+'：'+t.stake+'円（'+num(t.odds)+'倍）').join('<br>')}</p></details><h3>研究予想（購入候補ではありません）</h3><p>${esc((s.selection?.['12']||[]).join(', '))}</p><h3>展示STと本番ST・進入の予測</h3><p>過去データ：${esc(behavior.trained_through||'未集計')}まで。展示Fと正常STを分け、6艇でコースが重複しない進入候補を計算します。<br>${(behavior.st_estimates||[]).map((v,i)=>`${i+1}艇 本番ST推定 ${num(v)}`).join(' ／ ')}<br>${(behavior.scenarios||[]).map(x=>'艇番1〜6の進入：'+x.courses_by_boat.join('-')+'（'+pct(x.probability)+'）').join('<br>')}</p><h3>レース条件・当地の確認範囲</h3><p>6艇構成：${esc(({mixed:'男女混合',women_only:'女子のみ',men_only:'男子のみ',unknown:'性別未確認あり'})[ctx.field_type]||'旧版・未取得')} ／ 女子 ${ctx.female_count??'―'}艇・男子 ${ctx.male_count??'―'}艇・未確認 ${ctx.unknown_sex_count??'―'}艇<br>開催区分：${esc(ctx.meeting_type||'未取得')} ／ グレード ${esc(ctx.grade||'未取得')} ／ ${esc(ctx.stage||'未取得')}<br>当地の確認走数は保存された過去期間内の数です。公式3年分の総出走数ではありません。0.00・0％・0％の組合せを苦手の根拠には使いません。</p><h3>気象・展示の取得日時</h3><p>${Object.entries(times).map(([k,v])=>esc(({ex:'展示タイム',st:'展示ST・進入',weather:'気象',odds:'オッズ',original:'独自展示'})[k]||k)+': '+esc(v)+' ／ '+esc(previews[k]?.情報源||'配信CSV')).join('<br>')||'まだ取得できていません'}</p><h3>モーター過去3節・選手補正・今節</h3><div class="scroll"><table><tr><th>艇</th><th>期開始日・確認元</th><th>過去節</th><th>使用選手補正</th><th>今節走数</th><th>履歴</th></tr>${Object.entries(history).map(([lane,h])=>`<tr><td>${esc(lane)}</td><td>${esc(h.period)}<br>${h.period_source&&h.period_source!=='daily_motor_csv'?'公式の場共通期を照合':''}<br>${h.individual_totals_available===false?'個別の期成績は未取得':''}</td><td>${h.uses?.length||0}/3節</td><td>${h.matched_riders||0}/${h.total_riders||0}名</td><td>${h.current_series_runs||0}</td><td>${(h.uses||[]).map(u=>`${esc(u.start)}〜${esc(u.end)} ${esc(u.racer)}：${esc(u.finishes)}（全国勝率 ${num(u.racer_win_rate)}）`).join('<br>')||esc(h.status)}</td></tr>`).join('')}</table></div><p class="small warning">選手補正と確率は研究用です。風向は同じ場の過去条件として参照し、未確認の向かい風・追い風換算は行っていません。</p><h3>追加情報の根拠</h3><p>潮汐：${s.water_context?(s.water_context.tide.status==='not_applicable'?'対象外（この場は干満差なし）':esc(s.water_context.tide.station||s.water_context.tide.reason||'未取得')):tide?esc(`旧版の丸亀表：満潮 ${tide.high}／干潮 ${tide.low}`):'この旧版では未対応'}<br>根拠のない固定補正は停止しました。過去標本で学習できていない情報は記録・表示にとどめ、計算未使用を明記します。</p><p>${Object.entries(official.comments||{}).map(([lane,c])=>esc(lane)+'艇：'+esc(c.comment)).join('<br>')}</p><p>${Object.entries(official.before||{}).map(([lane,c])=>esc(lane)+'艇：プロペラ '+esc(c.propeller||'変更表示なし')+'／部品交換 '+esc(c.parts||'表示なし')).join('<br>')}</p><p>公式取得：${esc(official.observed_at||'未取得')}</p><h3>更新履歴</h3><p>${(r.revision_history||Object.values(r.revisions||{})).slice().sort((a,b)=>a.created_at.localeCompare(b.created_at)).map(x=>`${esc(x.created_at)} ${x.complete_inputs?'全入力':'暫定'}：${esc((x.selection?.['12']||[]).join(', '))}`).join('<br>')}</p><p><button type="button" id="loadAllRaceHistory">このレースの全履歴を見る</button></p>`;
 $('loadAllRaceHistory')?.addEventListener('click',async()=>{
  const code=selected;try{
   const archived=await getJSON(index.days?.[$('fullDate').value]?.archive_path||'full_history/'+$('fullDate').value+'.json');
   const path=archived.history_storage?.record_paths?.[code];
   const record=path?await getJSON('full_history/'+path):archived.records?.[code];
   if(selected!==code)return;if(!record)throw Error('このレースの履歴を取得できません');
   record.race_commentary=data.records[code]?.race_commentary;record.boat_comparison=data.records[code]?.boat_comparison;data.records[code]=record;renderDetail();
  }catch(e){$('fullDetail').insertAdjacentHTML('beforeend','<p class="warning">'+esc(e.message)+'</p>')}
 });
}
function retainNewerView(next,previous){
 if(!previous||next.date!==previous.date)return next;
 for(const [code,old] of Object.entries(previous.records||{})){
  const r=next.records?.[code];if(!r)continue;
  r.revisions={...old.revisions,...r.revisions};
  if(Date.parse(old.result?.settled_at)>Date.parse(r.result?.settled_at||0))r.result=old.result;
  r.offers={...old.offers,...r.offers};
  const chosen=latest(r);
  if(chosen&&r.race_commentary?.snapshot_id!==chosen.id&&old.race_commentary?.snapshot_id===chosen.id)r.race_commentary=old.race_commentary;
  if(chosen&&r.boat_comparison?.snapshot_id!==chosen.id&&old.boat_comparison?.snapshot_id===chosen.id)r.boat_comparison=old.boat_comparison;
  r.revision_count=Math.max(r.revision_count||0,old.revision_count||0,Object.keys(r.revisions).length);
 }
 if(Date.parse(previous.quote_health?.attempt_at)>Date.parse(next.quote_health?.attempt_at||0))next.quote_health=previous.quote_health;
 return next;
}
async function loadDay(){
 const ticket=++loading;try{const day=$('fullDate').value;if(!day){$('fullStatus').textContent='表示する日付が選択されていません';return;}const candidate=index.days?.[day]?.view_path;const primary=typeof candidate==='string'&&/^day_views\/[0-9]{4}-[0-9]{2}-[0-9]{2}(?:-[a-f0-9]{16})?\.json$/.test(candidate)?candidate:'day_views/'+day+'.json';let next;try{next=await getJSON(primary)}catch(primaryError){const fallback='day_views/'+day+'.json';if(primary===fallback)throw primaryError;try{next=await getJSON(fallback)}catch(fallbackError){throw Error('公開予想JSONの取得失敗（指定版：'+primaryError.message+'／通常版：'+fallbackError.message+'）')}}if(ticket!==loading||day!==$('fullDate').value)return;if(!next||next.date&&next.date!==day||!next.records||typeof next.records!=='object'||Array.isArray(next.records)||next.history_storage&&!next.records)throw Error('公開予想JSONの内容が不完全です。保存・公開処理を確認してください');const keep=selected&&next.records?.[selected];data=retainNewerView(next,loadedDay===day?data:null);loadedDay=day;if(!keep)selected=null;if(!keep)$('fullDetail').innerHTML='<span class="muted">レースの「使った情報を見る」で入力の使用状況と更新履歴を確認できます。</span>';render()}catch(e){if(ticket===loading&&day===$('fullDate').value){if(loadedDay!==day){data=null;selected=null;$('fullRecords').innerHTML='<p class="warning">選択した日付の予想データを取得できません。別の日付の予想は表示していません。</p>';$('fullPurchaseSummary').textContent='予想データを確認できないため、購入判定は表示できません。';$('fullRaceNav').replaceChildren();$('fullRaceComparison').replaceChildren();$('fullDetail').replaceChildren();}$('fullStatus').textContent='予想データ取得失敗：'+e.message;throw e;}}
}
async function load(force=false){
 if(busy)return;busy=true;
 const buttons=[$('fullReload'),$('reload')].filter(Boolean);buttons.forEach(b=>{b.disabled=true;b.textContent='最新データを取得中…'});
 const oldRef=liveRef,oldIndex=index,oldUpdated=index?.updated_at,feedback=$('fullRefreshStatus');if(feedback)feedback.textContent='更新確認中…';
 try{if(force===true||!index||Date.now()-refChecked>=60000)await resolveLiveRef(force===true);let nextIndex=await getJSON('boat24_full_index.json');if(force!==true&&index&&Date.parse(nextIndex.updated_at)<=Date.parse(index.updated_at)&&Date.now()-Date.parse(index.updated_at)>60000&&Date.now()-refChecked>=60000){await resolveLiveRef(false);nextIndex=await getJSON('boat24_full_index.json');}if(index&&Date.parse(nextIndex.updated_at)<Date.parse(index.updated_at)){liveRef='main';const direct=await getJSON('boat24_full_index.json');if(Date.parse(direct.updated_at)>=Date.parse(index.updated_at))nextIndex=direct;else{render();if(feedback)feedback.textContent='確認完了 '+new Date().toLocaleTimeString('ja-JP')+'／新しい保存版は確認できませんでした。表示中の新しい版を保持しています。';return}}if(force!==true&&data&&index?.updated_at===nextIndex.updated_at&&renderedRef===liveRef&&loadedDay===$('fullDate').value){index=nextIndex;render();if(feedback)feedback.textContent='表示確認 '+new Date().toLocaleTimeString('ja-JP')+'／新しい保存版はまだありません';return}index=nextIndex;if(!index.days?.[$('fullDate').value]){$('fullDate').value='';const linkedDay=typeof location==='undefined'?null:new URLSearchParams(location.search).get('day');$('fullDate').value=index.days?.[linkedDay]?linkedDay:index.latest_day||'';}await loadDay();renderedRef=liveRef;if(feedback)feedback.textContent='再取得完了 '+new Date().toLocaleTimeString('ja-JP')+(oldUpdated===index.updated_at?'／新しい保存版はまだありません':'／最新の保存版を反映しました')+'。このボタンは保存済みデータを再取得します。';}
 catch(e){index=oldIndex;$('fullStatus').textContent='予想データの更新に失敗：'+e.message+'。直前に読み込めたデータを保持しています。';if(feedback)feedback.textContent='再取得に失敗しました。表示中データの時刻を確認してください。';}
 finally{busy=false;buttons.forEach(b=>{b.disabled=false;b.textContent='最新の予想・オッズを再取得'})}
}
setInterval(()=>{if(!document.hidden&&!busy)load(false)},20000);
$('fullQuickVenue')&&($('fullQuickVenue').innerHTML=names.map((n,i)=>'<option value="'+i+'">'+n+'</option>').join(''));
$('fullQuickVenue')?.addEventListener('change',()=>{$('venue').value=$('fullQuickVenue').value;$('venue').dispatchEvent(new Event('change',{bubbles:true}));if(activeRace)jumpToRace(activeRace)});
$('fullQuickRace')?.addEventListener('change',()=>jumpToRace($('fullQuickRace').value));
$('fullQuickPrev')?.addEventListener('click',()=>{const i=quickRows.findIndex(x=>x.race_code===activeRace);if(i>0)jumpToRace(quickRows[i-1].race_code)});
$('fullQuickNext')?.addEventListener('click',()=>{const i=quickRows.findIndex(x=>x.race_code===activeRace);if(i>=0&&i<quickRows.length-1)jumpToRace(quickRows[i+1].race_code)});
$('fullRaceNav')?.addEventListener('click',e=>{const a=e.target.closest?.('a[href^="#race-"]');if(a){e.preventDefault();jumpToRace(a.getAttribute('href').slice(6))}});
$('fullReportGroup')?.addEventListener('change',renderReport);
$('fullDate').addEventListener('change',()=>loadDay().catch(()=>{}));$('venue').addEventListener('change',()=>{raceVisible=24;render()});$('fullReload').addEventListener('click',()=>load(true));$('reload')?.addEventListener('click',()=>load(true));load();
})();
