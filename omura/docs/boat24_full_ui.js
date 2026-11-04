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
let index=null,data=null,selected=null,loading=0,liveRef='main',refChecked=0,renderedRef='',busy=false,raceVisible=24;
async function resolveLiveRef(force=false){
 if(!force&&Date.now()-refChecked<60000)return;refChecked=Date.now();
 try{const r=await fetch('https://api.github.com/repos/tadasuketakahashi1234-design/-marugame-motor/git/ref/heads/main?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok){liveRef='main';return}const d=await r.json();const sha=d.object?.sha||d.sha;if(/^[a-f0-9]{40}$/.test(sha||''))liveRef=sha}catch(e){liveRef='main'}
}
const contextOrder=(a,b)=>Date.parse(b.context_snapshot_at||b.created_at)-Date.parse(a.context_snapshot_at||a.created_at)||b.created_at.localeCompare(a.created_at)||b.id.localeCompare(a.id);
const latest=r=>Object.values(r.revisions||{}).filter(s=>s.evaluation_eligible&&Date.parse(s.created_at)<Date.parse(s.cutoff)).sort(contextOrder)[0];
async function getJSON(path){
 const root='https://raw.githubusercontent.com/tadasuketakahashi1234-design/-marugame-motor/'+liveRef+'/omura/docs/';
 const urls=[root+path,'./'+path];
 let error;
 for(const u of urls){try{const r=await fetch(u+'?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok)throw Error('HTTP '+r.status);if(path.endsWith('.gz')){if(typeof DecompressionStream==='undefined')throw Error('このブラウザでは圧縮履歴を開けません');return await new Response(r.body.pipeThrough(new DecompressionStream('gzip'))).json()}return await r.json()}catch(e){error=e}}
 throw Error('最新データの再取得に失敗：'+(error?.message||'通信エラー'));
}
const purchasePolicy='balanced-no-gami-v2';
function purchaseSnapshot(r,fallback){
 const found=Object.values(r?.revisions||{}).filter(x=>x.purchase_plan?.policy===purchasePolicy&&x.evaluation_eligible&&Date.parse(x.created_at)<Date.parse(x.cutoff)).sort((a,b)=>Date.parse(b.context_snapshot_at||b.created_at)-Date.parse(a.context_snapshot_at||a.created_at)||b.created_at.localeCompare(a.created_at)||b.id.localeCompare(a.id));
 return found[0]||fallback;
}
function purchaseView(s){
 const p=s.purchase_plan||{},closed=Date.now()>=Date.parse(s.cutoff);
 const age=Date.now()-Date.parse(p.odds_observed_at),fresh=Number.isFinite(age)&&age>=0&&age<=300000;
 const tickets=p.tickets||[],total=tickets.reduce((v,t)=>v+t.stake,0);
 const current=p.policy===purchasePolicy;
 const valid=current&&p.status==='ready'&&tickets.length>0&&new Set(tickets.map(t=>t.combo)).size===tickets.length&&total===p.budget&&total<=p.budget_cap&&p.estimated_roi>1&&tickets.every(t=>Number.isInteger(t.stake)&&t.stake>=100&&t.stake%100===0&&Number.isFinite(t.odds)&&Math.floor((t.odds+1e-9)*10)*10*(t.stake/100)>total&&t.expected_return>total);
 const reasons={odds_stale:'オッズが古い・取得時刻不明',odds_incomplete:'オッズ未取得・不足',probabilities_invalid:'確率データの整合性未確認',no_positive_value:'モデル推定の期待回収率100％超の案なし',no_feasible_plan:'ガミなし条件の配分なし'};
 if(['odds_stale','odds_incomplete'].includes(p.status))return {pending:true,html:'<strong>判定保留（購入候補なし）</strong><br>'+(!p.odds_observed_at?'オッズ未取得':p.status==='odds_incomplete'?'オッズ120通りが揃っていません':'オッズ更新遅延')+'<br>価格が低いことによる見送りではありません',metrics:'オッズ更新 '+esc(p.odds_observed_at||'未取得')};
 if(!valid)return {html:'<strong>見送り</strong><br>'+(!current?'点数可変の新条件の保存待ち（旧予想は詳細に保持）':reasons[p.status]||'配分の整合性未確認'),metrics:'購入候補なし'};
 if(!closed&&Date.now()>=Date.parse(s.cutoff)-120000)return {html:'<strong>見送り：締切2分前</strong>',metrics:'新規の購入候補表示を停止'};
 if(!closed&&!fresh)return {html:'<strong>判定保留：オッズ更新遅延</strong>',metrics:'オッズが古い・取得時刻不明'};
 const minimum=Math.min(...tickets.map(t=>t.expected_return));
 return {valid:true,ready:!closed,html:(closed?'<b>締切済み・保存時の参考</b><br>':'')+'<b>'+tickets.length+'点・計'+total+'円</b><br>'+tickets.map(t=>esc(t.combo)+'：'+t.stake+'円').join('<br>'),metrics:'取得時の最低想定払戻 '+minimum+'円<br>最低想定利益 ＋'+(minimum-total)+'円<br>モデル内試算回収率 '+pct(p.estimated_roi)+'（未校正・実績ではありません）<br>合成 '+num(p.synthetic_odds)+'倍<br>オッズ時刻 '+esc(p.odds_observed_at)+'<br>候補計算 '+esc(s.created_at)+'<br>点数・配分の近似比較／的中確率とのバランス優先'};
}
function renderNarrative(c){
 if(!c)return '<section class="race-analysis"><h4>予想見解</h4><p>この保存版の見解を準備中です。補足データで確認できる範囲を表示します。</p></section>';
 return '<section class="race-analysis"><h4>'+esc(c.headline)+'</h4>'+((c.forecast_lines||[]).length?'<p><b>展開予想の本線</b> '+c.forecast_lines.map(esc).join(' ／ ')+'<br><span class="small muted">購入対象・金額は上の購入判定で確認してください。</span></p>':'')+[['本線の評価',c.axis],['相手の評価',c.opponents],['想定展開',c.deployment],['当日の水面をどう読むか',c.water],['買い目との関係',c.price]].map(([h,t])=>'<div><b>'+h+'</b><p>'+esc(t)+'</p></div>').join('')+'<div><b>本線が崩れる条件・注意点</b><p>'+c.risks.map(esc).join('<br>')+'</p></div><details><summary>6艇を比較する</summary><div class="boat-comparison">'+c.boats.map(b=>'<div><b>'+esc(b.mark)+' '+b.lane+'号艇 '+esc(b.name||'')+'</b><p>'+b.evidence.map(esc).join(' ／ ')+'</p></div>').join('')+'</div></details><p class="small muted">'+esc(c.notice)+'</p></section>';
}
async function openDetail(){
 const r=data.records?.[selected],snap=r&&latest(r);if(!snap)return;
 if($('fullSupplement')){$('fullSupplement').open=true;$('fullSupplement').scrollIntoView?.({behavior:'smooth',block:'start'})}
 if(!snap._details_compacted){renderDetail();return}
 const code=selected;$('fullDetail').innerHTML='<p>このRの補足データと保存入力を読込中…</p>';
 try{const full=await readRaceArchive(code);if(code!==selected)return;full.race_commentary=r.race_commentary;data.records[code]=full;renderDetail()}catch(e){$('fullDetail').innerHTML='<p>'+esc(e.message)+'</p>'}
}
async function readRaceArchive(code){
 const archived=await getJSON(index.days?.[$('fullDate').value]?.archive_path||'full_history/'+$('fullDate').value+'.json');
 const path=archived.history_storage?.record_paths?.[code];
 const record=path?await getJSON('full_history/'+path):archived.records?.[code];
 if(!record)throw Error('このRの補足データを取得できません');return record;
}
function records(){const venue=Number($('venue').value);return Object.values(data?.records||{}).filter(r=>!venue||Number(r.venue)===venue).sort((a,b)=>b.race_code.localeCompare(a.race_code))}
function catalogRows(){const v=Number($('venue').value);return Object.values(data?.catalog||index?.catalogs?.[$('fullDate').value]||{}).filter(r=>!v||r.venue===v).sort((a,b)=>a.race_code.localeCompare(b.race_code))}
function render(){
 if(!index||!data)return;
 const list=records(),venue=String(Number($('venue').value)),day=$('fullDate').value;
 const phaseCounts={initial:0,preview:0,partial:0,missed:0,old:0};for(const r of list){const snap=latest(r),stage=snap?.phase;if(stage==='initial'&&Date.now()>=Date.parse(snap.cutoff))phaseCounts.missed++;else if(stage in phaseCounts)phaseCounts[stage]++;else phaseCounts.old++}
 const group=index.days?.[day],stats=venue==='0'?group?.summary:group?.venues?.[venue];
 const h=data.health||index.health||{},age=(Date.now()-Date.parse(h.attempt_at||data.updated_at))/60000,today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo'}).format(new Date())===day,stale=today&&age>(h.stale_after_minutes||5);
 $('fullStatus').textContent=(stale?'【更新遅延 '+Math.floor(age)+'分】 ':h.state==='degraded'?'【一部の直前情報が未取得】 ':'')+'総合予想更新：'+(data.updated_at||index.updated_at)+' ／ '+(index.model||'')+(h.collection_mode==='live_watch'?' ／ ライブ更新を監視中':' ／ 取得できた情報で再計算')+(h.missing_forecasts?.length?' ／ 保存待ち '+h.missing_forecasts.length+'R':'');
 $('fullHealth').textContent=(stale?'自動更新が遅れています。最新の買い目として扱う前に更新時刻を確認してください。 ':'')+'取得失敗 '+Object.keys(h.source_errors||{}).length+'件 ／ '+Object.entries(h.source_counts||{}).map(([k,v])=>k+':'+v).join('・')+'。自動実行には遅延・欠落が起こる場合があります。';
 if(data.quote_health)$('fullStatus').textContent+=' ／ 直前オッズ確認 '+esc(data.quote_health.attempt_at?.slice(11,19))+'（'+data.quote_health.confirmed+'/'+data.quote_health.targets+'R）';
 if(data.settlement_updated_at)$('fullStatus').textContent+=' ／ 精算更新 '+data.settlement_updated_at;
 $('fullStatus').textContent+=' ／ 表示中：展示後 '+phaseCounts.preview+'件・直前情報一部 '+phaseCounts.partial+'件・展示前 '+phaseCounts.initial+'件'+(phaseCounts.missed?'・展示更新なし（締切済み） '+phaseCounts.missed+'件':'')+(phaseCounts.old?'・旧版 '+phaseCounts.old+'件':'');
 let tiles=[`<div class="metric">研究予想の保存履歴（購入条件とは別）<strong>${list.length}</strong>予定 ${catalogRows().length}R ／ 予想未保存 ${catalogRows().filter(x=>!data.records?.[x.race_code]).length}R<br>必須情報使用 ${stats?.complete_inputs??0}件<br>結果確定 ${stats?.settled??0}件 ／ 待ち ${stats?.pending??0}件</div>`];
 for(const n of [12,18]){const s=stats?.[n]||{};tiles.push(`<div class="metric">研究${n}点的中率<strong>${pct(s.hit_rate)}</strong>${s.hits??0}/${s.races??0}レース</div><div class="metric">研究${n}点回収率<strong>${pct(s.roi)}</strong>仮想収支 ${s.profit??0}円</div>`)}
 const ng=(index.purchase_policy===purchasePolicy?stats?.no_gami:null)||{};tiles.unshift(`<div class="metric">点数可変・ガミなし想定の仮想成績<strong>${pct(ng.roi)}</strong>${ng.races??0}R ／ 的中 ${ng.hits??0}R<br>収支 ${ng.profit??0}円<br>各Rの最初の有効候補1件・保存後の仮想検証<br>返還未照合 ${ng.refund_unverified??0}R／モデル別成績は下に表示</div>`);$('fullMetrics').innerHTML=tiles.join('');
 const catalog=catalogRows(),known=new Set(catalog.map(r=>r.race_code));
 const cutoffOf=item=>Date.parse(item.cutoff||latest(data.records?.[item.race_code]||{})?.cutoff||'');
 const rows=[...catalog,...list.filter(r=>!known.has(r.race_code))].sort((a,b)=>{const ac=cutoffOf(a),bc=cutoffOf(b),af=Date.now()<ac,bf=Date.now()<bc;return Number(bf)-Number(af)||(af&&bf?ac-bc:0)||a.race_code.localeCompare(b.race_code)});
 const next=rows.find(item=>Date.now()<cutoffOf(item));
 if($('fullPurchaseSummary')){
  const r=next&&data.records?.[next.race_code],s=r&&latest(r),view=s&&purchaseView(purchaseSnapshot(r,s));
  $('fullPurchaseSummary').innerHTML=next?'<b>次のレース：'+esc(names[next.venue])+' '+esc(next.race)+'R</b><br>'+(view?view.html:'<strong>判定保留：購入候補の保存待ち</strong>')+(s?'<p class="small">オッズ時刻 '+esc(purchaseSnapshot(r,s).purchase_plan?.odds_observed_at?.slice(11,19)||'未取得')+' ／ 候補計算 '+esc(purchaseSnapshot(r,s).created_at.slice(11,19))+'</p>':''):'締切前のレースはありません。各Rの保存時の判定は下に表示します。';
 }

 const visible=venue==='0'?rows.slice(0,raceVisible):rows;
 if($('fullRaceNav'))$('fullRaceNav').innerHTML=visible.map(x=>'<a href="#race-'+esc(x.race_code)+'">'+(venue==='0'?esc(names[x.venue])+' ':'')+x.race+'R</a>').join('');
 $('fullRecords').innerHTML=visible.map(item=>{
  const r=data.records?.[item.race_code],snap=r&&latest(r);
  if(!snap)return '<article class="race-card" id="race-'+esc(item.race_code)+'"><h3>'+esc(names[item.venue])+' '+item.race+'R</h3><p>'+esc(raceStates[item.state]||'予想作成待ち')+'</p><p>締切 '+esc(item.cutoff?.slice(11,16)||'未確認')+'</p></article>';
  const ps=purchaseSnapshot(r,snap),v=purchaseView(ps),c=r.race_commentary,closed=Date.now()>=Date.parse(snap.cutoff),bet=r.result?.paper?.balanced;
  return '<article class="race-card" id="race-'+esc(r.race_code)+'" data-full-code="'+esc(r.race_code)+'"><header class="race-card-heading"><h3>'+esc(names[r.venue])+' '+r.race+'R</h3><span>締切 '+esc(snap.cutoff.slice(11,16))+(closed?'／締切済み':'／あと'+Math.max(0,Math.ceil((Date.parse(snap.cutoff)-Date.now())/60000))+'分')+'</span></header><div class="purchase-main">'+v.html+(v.valid?'<p class="small">取得時の最低想定払戻 '+Math.min(...ps.purchase_plan.tickets.map(t=>t.expected_return))+'円</p>':'')+'</div><p class="quote-clock">予想 '+esc(snap.created_at.slice(11,19))+' ／ オッズ '+esc(snap.purchase_plan?.odds_observed_at?.slice(11,19)||'未取得')+'<br>確率は校正検証中／情報段階：'+esc(({initial:'展示前の暫定評価',partial:'直前情報は一部取得',preview:'展示後'})[snap.phase]||snap.phase)+(snap.context_snapshot_at?'／オッズ以外の入力 '+esc(snap.context_snapshot_at.slice(11,19)):'')+'</p>'+renderNarrative(c)+'<details class="purchase-evidence"><summary>オッズ・配分と購入条件の根拠</summary><p>'+v.metrics+'</p><p>点数可変・上限1,200円。全買い目の取得時払戻が総購入額を超える配分に限定。オッズ変動後のガミや利益を保証する条件ではありません。</p></details>'+(r.result?'<div class="race-result">結果 '+esc(r.result.combo)+'／100円払戻 '+r.result.payout_100yen+'円'+(bet?'<br>保存候補：'+bet.stake+'円→'+bet.return+'円（返還 '+bet.refund+'円含む）':'')+'</div>':'')+'<button type="button" data-full-detail="'+esc(r.race_code)+'">使った情報を見る</button></article>';
 }).join('')+(venue==='0'&&rows.length>visible.length?'<button type="button" id="fullMoreRaces">さらに24Rの予想・見解を見る</button>':'');
 $('fullRecords').querySelectorAll('[data-full-detail]').forEach(b=>b.addEventListener('click',()=>{selected=b.dataset.fullDetail;openDetail()}));
 $('fullMoreRaces')?.addEventListener('click',()=>{raceVisible+=24;render()});
 if(!rows.length)$('fullRecords').innerHTML='<p>この日の総合予想はまだ保存されていません。旧モデルの保存履歴は下に残しています。</p>';
 if(selected&&data.records[selected]&&!latest(data.records[selected])?._details_compacted)renderDetail();
 renderReport();
 renderVenueCoverage();
 const check=index.training?.validation||{},loss=check.test_mean_logloss||{};
 if(globalThis.Boat24Integrated)Boat24Integrated.learning(index);
 $('fullTraining').textContent=(index.training?.frozen_for_forward_evaluation?'採用済みモデルを固定して前向き検証中（自動再学習による切替停止）。 ':'')+'場別水面モデル／参照データ：'+(index.training?.through||'―')+'まで ／ '+(index.training?.samples??0)+'艇標本（朝・展示別） ／ コース集計 '+(index.training?.course_window_days??'―')+'日 ／ 過去情報の取得失敗 '+Object.keys(index.training?.source_errors||{}).length+'件。総合モデル開始後の成績を、旧モデルと分けて集計しています。男女構成・開催条件・相手関係を追加。調整用と最終評価用の期間を分離しています。未学習の潮汐・コメント等の仮補正は停止しました。映像AI解析は未実装です。調整 '+(check.tuning_races??'―')+'R／別期間の校正 '+(check.calibration_races??'―')+'R／さらに別期間の最終評価 '+(check.test_races??'―')+'R。市場単独への改善：'+(loss.selected!=null&&loss.market!=null&&loss.selected<loss.market?'短期評価では確認・長期未証明':'未確認')+'。要素を外した比較 '+(check.ablations?.races??0)+'R：'+Object.entries(check.ablations?.mean_logloss||{}).map(([k,v])=>({none:'全要素',behavior:'ST・進入なし',motor_history:'モーター履歴なし',course:'コース実績なし',race_conditions:'開催条件なし',wind:'場別の風なし',tide:'場別の潮汐なし'}[k]||k)+' '+Number(v).toFixed(3)).join('／')+'（対数損失：低いほど良い。短期比較です）';
}
function renderReport(){
 const choice=$('fullReportGroup')?.value||'all',group=choice==='venue'?(Number($('venue').value)?'venue:'+Number($('venue').value):'all'):choice;
 const rows=(index.forward_report?.rows||[]).filter(r=>r.group===group);
 const el=$('fullForward');if(!el)return;
 const labels={new:'新モデル12点均等',old:'旧モデル12点均等',market:'同時刻市場12点均等',allocated_paper:'オッズ選択・配分（仮想）'};
 el.innerHTML='<h3>保存後の比較検証</h3><p class="small">新旧・市場の3者比較は同じレースだけで集計します。旧版と新版の保存時刻は異なります。朝にオッズがなければ市場比較から除外。性別・開催場・予想段階別も集計しています。</p>'+(rows.length?'<table><tr><th>比較</th><th>対象</th><th>的中</th><th>回収率</th><th>的中率95%区間</th></tr>'+rows.map(r=>`<tr><td>${esc(labels[r.model]||r.model)}</td><td>${r.cohort==='same_races'?'3者共通':'取得分'} ${r.races}R</td><td>${r.hits}/${r.races}</td><td>${pct(r.roi)}</td><td>${r.hit_rate_interval95.map(pct).join('〜')}</td></tr>`).join('')+'</table>':'<p>新しい比較条件での結果確定を待っています。</p>');
 const cohorts=index.purchase_forward_report?.rows||[],protocol=index.purchase_forward_report?.protocol;
 el.innerHTML+='<h3>点数可変候補：全保存期間・全場のモデル別成績</h3><p>各Rの最初の有効候補を1件だけ集計します。保存時刻に基づく仮想検証で、公開時刻・実購入の検証ではありません。旧12点・18点の成績とは別集計です。固定条件 '+esc(protocol?.id||'未設定')+'。少数標本で収益性を証明できません。</p>'+(cohorts.length?'<table><tr><th>保存条件／モデル／段階</th><th>対象・的中</th><th>購入想定／払戻</th><th>回収率</th></tr>'+cohorts.map(g=>'<tr><td>'+esc(g.protocol_id==='historical-reconstructed'?'過去保存から復元':g.protocol_id)+'<br>'+esc(g.model)+'<br>'+esc(g.model_id)+'<br>'+esc(g.phase)+'</td><td>'+g.races+'R／'+g.hits+'R<br>全額返還 '+g.fully_refunded+'R<br>返還未照合 '+g.refund_unverified+'R</td><td>'+g.stake+'円／'+g.return+'円<br>返還 '+g.refund+'円含む</td><td>'+pct(g.roi)+'</td></tr>').join('')+'</table>':'<p>条件を満たす候補の結果確定を待っています。</p>');
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
   record.race_commentary=data.records[code]?.race_commentary;data.records[code]=record;renderDetail();
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
  r.revision_count=Math.max(r.revision_count||0,old.revision_count||0,Object.keys(r.revisions).length);
 }
 if(Date.parse(previous.quote_health?.attempt_at)>Date.parse(next.quote_health?.attempt_at||0))next.quote_health=previous.quote_health;
 return next;
}
async function loadDay(){
 const ticket=++loading;try{const day=$('fullDate').value;if(!day)return;const next=await getJSON(index.days?.[day]?.view_path||'full_history/'+day+'.json');if(ticket!==loading)return;if(next.history_storage&&!next.records)throw Error('表示用データの更新待ちです。更新ボタンで再取得してください');const keep=selected&&next.records?.[selected];data=retainNewerView(next,data);if(!keep)selected=null;if(!keep)$('fullDetail').innerHTML='<span class="muted">レースの「使った情報を見る」で入力の使用状況と更新履歴を確認できます。</span>';render()}catch(e){$('fullStatus').textContent=e.message;throw e;}
}
async function load(force=false){
 if(busy)return;busy=true;
 const buttons=[$('fullReload'),$('reload')].filter(Boolean);buttons.forEach(b=>{b.disabled=true;b.textContent='最新データを取得中…'});
 const oldRef=liveRef,oldUpdated=index?.updated_at,feedback=$('fullRefreshStatus');if(feedback)feedback.textContent='更新確認中…';
 try{if(force===true||!index)await resolveLiveRef(force===true);else liveRef='main';let nextIndex=await getJSON('boat24_full_index.json');if(force!==true&&index&&Date.parse(nextIndex.updated_at)<=Date.parse(index.updated_at)&&Date.now()-Date.parse(index.updated_at)>60000&&Date.now()-refChecked>=60000){await resolveLiveRef(false);nextIndex=await getJSON('boat24_full_index.json');}if(index&&Date.parse(nextIndex.updated_at)<Date.parse(index.updated_at)){liveRef='main';const direct=await getJSON('boat24_full_index.json');if(Date.parse(direct.updated_at)>=Date.parse(index.updated_at))nextIndex=direct;else{render();if(feedback)feedback.textContent='確認完了 '+new Date().toLocaleTimeString('ja-JP')+'／新しい保存版は確認できませんでした。表示中の新しい版を保持しています。';return}}if(force!==true&&data&&index?.updated_at===nextIndex.updated_at){index=nextIndex;render();if(feedback)feedback.textContent='表示確認 '+new Date().toLocaleTimeString('ja-JP')+'／新しい保存版はまだありません';return}index=nextIndex;if(!$('fullDate').value){const linkedDay=typeof location==='undefined'?null:new URLSearchParams(location.search).get('day');$('fullDate').value=index.days?.[linkedDay]?linkedDay:index.latest_day||'';}await loadDay();renderedRef=liveRef;if(feedback)feedback.textContent='再取得完了 '+new Date().toLocaleTimeString('ja-JP')+(oldUpdated===index.updated_at?'／新しい保存版はまだありません':'／最新の保存版を反映しました')+'。このボタンは保存済みデータを再取得します。';}
 catch(e){$('fullStatus').textContent=e.message;if(feedback)feedback.textContent='再取得に失敗しました。表示中データの時刻を確認してください。';}
 finally{busy=false;buttons.forEach(b=>{b.disabled=false;b.textContent='最新の予想・オッズを再取得'})}
}
setInterval(()=>{if(!document.hidden)load(false)},20000);
$('fullReportGroup')?.addEventListener('change',renderReport);
$('fullDate').addEventListener('change',()=>loadDay().catch(()=>{}));$('venue').addEventListener('change',()=>{raceVisible=24;render()});$('fullReload').addEventListener('click',()=>load(true));$('reload')?.addEventListener('click',()=>load(true));load();
})();
