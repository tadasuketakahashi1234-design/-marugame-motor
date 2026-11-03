/* All-input forecasts and the exact input evidence used by each immutable revision. */
(function(){
'use strict';
const $=id=>document.getElementById(id),esc=x=>String(x??'―').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names=['全24場','桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑','津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島','宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'];
const raceStates={waiting_initial:'朝予想の保存待ち',program_unconfirmed:'番組未確認',cancelled:'中止・順延',cutoff_unknown:'締切時刻未確認',closed_no_forecast:'締切済み・新モデル予想なし',result_pending:'結果・払戻金待ち',saved:'予想保存済み',settled:'結果確定'};
const statuses={not_applicable:'対象外',not_implemented:'取得処理が未実装',partial_used:'一部を計算に使用',not_contributing_market_only:'検証で市場のみ採用・文脈は未採用',used:'計算に使用',missing:'未取得',partial:'一部のみ取得',historical_sample_insufficient:'参照できる過去標本が不足'};
const pct=x=>x==null?'未集計':(100*x).toFixed(1)+'%',num=x=>x==null?'未取得':Number(x).toFixed(2);
let index=null,data=null,selected=null,loading=0,liveRef='main',refChecked=0;
async function resolveLiveRef(){
 if(Date.now()-refChecked<45000)return;refChecked=Date.now();
 try{const r=await fetch('https://api.github.com/repos/tadasuketakahashi1234-design/-marugame-motor/commits/main?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(8000)});if(!r.ok)return;const d=await r.json();if(/^[a-f0-9]{40}$/.test(d.sha||''))liveRef=d.sha}catch(e){/* Keep the last verified commit or the regular data sources. */}
}
const latest=r=>r.revisions?.[r.result?.selection_snapshot_id]||Object.values(r.revisions||{}).filter(s=>s.evaluation_eligible&&Date.parse(s.created_at)<Date.parse(s.cutoff)).sort((a,b)=>b.created_at.localeCompare(a.created_at)||b.id.localeCompare(a.id))[0];
async function getJSON(path){
 const root='https://raw.githubusercontent.com/tadasuketakahashi1234-design/-marugame-motor/'+liveRef+'/omura/docs/';
 const urls=[root+path,'./'+path];
 const got=await Promise.allSettled(urls.map(async u=>{const r=await fetch(u+'?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(20000)});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}));
 const valid=got.filter(r=>r.status==='fulfilled').map(r=>r.value);
 if(!valid.length)throw Error('総合予想データを読み込めません');
 return valid.sort((a,b)=>Date.parse(b.updated_at||b.generated_at||0)-Date.parse(a.updated_at||a.generated_at||0))[0];
}
function records(){const venue=Number($('venue').value);return Object.values(data?.records||{}).filter(r=>!venue||Number(r.venue)===venue).sort((a,b)=>b.race_code.localeCompare(a.race_code))}
function catalogRows(){const v=Number($('venue').value);return Object.values(data?.catalog||index?.catalogs?.[$('fullDate').value]||{}).filter(r=>!v||r.venue===v).sort((a,b)=>a.race_code.localeCompare(b.race_code))}
function render(){
 if(!index||!data)return;
 const list=records(),venue=String(Number($('venue').value)),day=$('fullDate').value;
 const group=index.days?.[day],stats=venue==='0'?group?.summary:group?.venues?.[venue];
 const h=data.health||index.health||{},age=(Date.now()-Date.parse(h.attempt_at||data.updated_at))/60000,today=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo'}).format(new Date())===day,stale=today&&age>(h.stale_after_minutes||5);
 $('fullStatus').textContent=(stale?'【更新遅延 '+Math.floor(age)+'分】 ':h.state==='degraded'?'【一部取得失敗・未保存あり】 ':'')+'総合予想更新：'+(data.updated_at||index.updated_at)+' ／ '+(index.model||'')+(h.collection_mode==='live_watch'?' ／ ライブ更新を監視中':' ／ 取得できた情報で再計算')+(h.missing_forecasts?.length?' ／ 保存待ち '+h.missing_forecasts.length+'R':'');
 $('fullHealth').textContent=(stale?'自動更新が遅れています。最新の買い目として扱う前に更新時刻を確認してください。 ':'')+'取得失敗 '+Object.keys(h.source_errors||{}).length+'件 ／ '+Object.entries(h.source_counts||{}).map(([k,v])=>k+':'+v).join('・')+'。自動実行には遅延・欠落が起こる場合があります。';
 let tiles=[`<div class="metric">当日の総合保存履歴（過去版含む）<strong>${list.length}</strong>必須情報使用 ${stats?.complete_inputs??0}件<br>結果確定 ${stats?.settled??0}件 ／ 待ち ${stats?.pending??0}件</div>`];
 for(const n of [12,18]){const s=stats?.[n]||{};tiles.push(`<div class="metric">${n}点的中率<strong>${pct(s.hit_rate)}</strong>${s.hits??0}/${s.races??0}レース</div><div class="metric">${n}点回収率<strong>${pct(s.roi)}</strong>仮想収支 ${s.profit??0}円</div>`)}
 $('fullMetrics').innerHTML=tiles.join('');
 const catalog=catalogRows(),known=new Set(catalog.map(r=>r.race_code));
 const rows=[...catalog,...list.filter(r=>!known.has(r.race_code))].sort((a,b)=>a.race_code.localeCompare(b.race_code));
 $('fullRecords').innerHTML='<p class="small">全レースの保存状態を表示。締切後に予想を作り足すことはありません。過去の旧版買い目は下の旧モデル履歴に残っています。</p><table><thead><tr><th>場・R</th><th>情報状態</th><th>最終計算／締切</th><th>12点買い目</th><th>検証状態・合成オッズ</th><th>結果</th></tr></thead><tbody>'+rows.map(item=>{const r=data.records?.[item.race_code],s=r&&latest(r);if(!s){const closed=item.cutoff&&Date.now()>=Date.parse(item.cutoff)-120000;return `<tr><td>${esc(names[item.venue])} ${item.race}R</td><td>${esc(raceStates[closed&&item.state==='waiting_initial'?'closed_no_forecast':item.state]||'未保存')}</td><td>締切 ${esc(item.cutoff?.slice(11,16)||'未確認')}</td><td colspan="3">新モデルの買い目なし</td></tr>`}const m=s.market_metrics?.['12']||{},a=s.allocation||{},status=s.phase==='initial'?'朝予想（展示前）':s.phase==='preview'?'展示後の予想':s.phase==='partial'?'直前情報は一部取得':s.complete_inputs?'必須情報を使用':'未採用・未取得の情報あり';return `<tr data-full-code="${esc(r.race_code)}"><td>${esc(names[r.venue])} ${esc(r.race)}R</td><td>${status}<br><button type="button" data-full-detail="${esc(r.race_code)}">使った情報を見る</button></td><td>${esc(s.created_at.slice(11,19))}<br>締切 ${esc(s.cutoff.slice(11,16))}<br>履歴 ${Object.keys(r.revisions||{}).length}版</td><td>${esc((s.selection?.['12']||[]).join(', '))}${a.tickets?.length?'<br><strong>オッズを考慮した12点・配分は詳細へ</strong>':''}</td><td>${s.probability_verified?'校正後 '+pct(m.estimated_hit_probability):'確率の表示保留（校正検証中）'}<br>合成 ${num(m.synthetic_odds)}倍<br><span class="muted">仮想検証・収益性未証明</span></td><td>${esc(r.result?.combo||r.result_pending_reason||(Date.now()<Date.parse(s.cutoff)?'締切前': '結果・払戻金待ち'))}<br>${r.result?esc(r.result.payout_100yen)+'円':''}</td></tr>`}).join('')+'</tbody></table>';
 $('fullRecords').querySelectorAll('[data-full-detail]').forEach(b=>b.addEventListener('click',()=>{selected=b.dataset.fullDetail;renderDetail()}));
 if(!rows.length)$('fullRecords').innerHTML='<p>この日の総合予想はまだ保存されていません。旧モデルの保存履歴は下に残しています。</p>';
 if(selected&&data.records[selected])renderDetail();
 renderReport();
 renderVenueCoverage();
 const check=index.training?.validation||{},loss=check.test_mean_logloss||{};
 $('fullTraining').textContent='場別水面モデル／参照データ：'+(index.training?.through||'―')+'まで ／ '+(index.training?.samples??0)+'艇標本（朝・展示別） ／ コース集計 '+(index.training?.course_window_days??'―')+'日 ／ 過去情報の取得失敗 '+Object.keys(index.training?.source_errors||{}).length+'件。総合モデル開始後の成績を、旧モデルと分けて集計しています。男女構成・開催条件・相手関係を追加。調整用と最終評価用の期間を分離しています。未学習の潮汐・コメント等の仮補正は停止しました。映像AI解析は未実装です。調整 '+(check.tuning_races??'―')+'R／別期間の校正 '+(check.calibration_races??'―')+'R／さらに別期間の最終評価 '+(check.test_races??'―')+'R。市場単独への改善：'+(loss.selected!=null&&loss.market!=null&&loss.selected<loss.market?'短期評価では確認・長期未証明':'未確認')+'。要素を外した比較 '+(check.ablations?.races??0)+'R：'+Object.entries(check.ablations?.mean_logloss||{}).map(([k,v])=>({none:'全要素',behavior:'ST・進入なし',motor_history:'モーター履歴なし',course:'コース実績なし',race_conditions:'開催条件なし',wind:'場別の風なし',tide:'場別の潮汐なし'}[k]||k)+' '+Number(v).toFixed(3)).join('／')+'（対数損失：低いほど良い。短期比較です）';
}
function renderReport(){
 const choice=$('fullReportGroup')?.value||'all',group=choice==='venue'?(Number($('venue').value)?'venue:'+Number($('venue').value):'all'):choice;
 const rows=(index.forward_report?.rows||[]).filter(r=>r.group===group);
 const el=$('fullForward');if(!el)return;
 const labels={new:'新モデル12点均等',old:'旧モデル12点均等',market:'同時刻市場12点均等',allocated_paper:'オッズ選択・配分（仮想）'};
 el.innerHTML='<h3>保存後の比較検証</h3><p class="small">新旧・市場の3者比較は同じレースだけで集計します。旧版と新版の保存時刻は異なります。朝にオッズがなければ市場比較から除外。性別・開催場・予想段階別も集計しています。</p>'+(rows.length?'<table><tr><th>比較</th><th>対象</th><th>的中</th><th>回収率</th><th>的中率95%区間</th></tr>'+rows.map(r=>`<tr><td>${esc(labels[r.model]||r.model)}</td><td>${r.cohort==='same_races'?'3者共通':'取得分'} ${r.races}R</td><td>${r.hits}/${r.races}</td><td>${pct(r.roi)}</td><td>${r.hit_rate_interval95.map(pct).join('〜')}</td></tr>`).join('')+'</table>':'<p>新しい比較条件での結果確定を待っています。</p>');
}
function displayAudit(s,r){
 const out=Object.fromEntries(Object.entries(s.feature_usage||{}).map(([k,v])=>[k,{...v}])),p=s.water_context?.profile||index.training?.venue_profiles?.[String(r.venue)];
 if(out.tide){out.tide.label=(names[r.venue]||'当該場')+'の潮汐推算';if(p?.tidal_range==='なし')Object.assign(out.tide,{status:'not_applicable',reason:'公式場データで干満差なし'});else if(!s.water_context)Object.assign(out.tide,{status:'not_implemented',reason:'この保存版には場別潮汐モデルが未実装'})}
 if(out.wind){out.wind.label=(names[r.venue]||'当該場')+'の風とコース別実績';if(!s.water_context&&r.venue!==15)Object.assign(out.wind,{status:'not_implemented',reason:'この保存版には場別の風モデルが未実装'})}
 if(out.comments&&r.venue!==15&&!out.comments.available_fields?.length)Object.assign(out.comments,{status:'not_implemented',reason:'この場の選手コメント自動取得は未実装'});
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
 $('fullDetail').innerHTML=`<h3>${esc(names[r.venue])} ${esc(r.race)}R｜実際に使った情報</h3><p>計算 ${esc(s.created_at)} ／ 締切 ${esc(s.cutoff)}<br>判断：${esc(s.decision)}</p>${renderWater(s)}<div class="scroll"><table class="feature-audit"><tr><th>情報</th><th>状態</th><th>使用した項目</th></tr>${Object.entries(displayAudit(s,r)).map(([key,f])=>`<tr><td>${esc(f.label)}</td><td>${esc(statuses[f.status]||f.status)}${['not_applicable','not_implemented'].includes(f.status)?'':key==='odds'?'':`（使用 ${f.used_lanes||0}/6艇・取得 ${f.available_lanes||0}/6艇）`}${f.reason?'<br>'+esc(f.reason):''}</td><td>${esc((f.used_fields||[]).map(k=>k+'（'+(f.field_coverage?.[k]??0)+'/6艇）').join('・')||(key==='odds'?`${f.valid_combinations||0}/120組、確率への市場情報比率 ${pct(f.market_blend)}`:'―'))}${f.unused_fields?.length?'<br>取得済み・計算未使用：'+esc(f.unused_fields.join('・')):''}</td></tr>`).join('')}</table></div><h3>オッズ選択と100円単位の仮想配分</h3><p>仮想予算 ${allocation.budget??'―'}円 ／ 目標 ${allocation.target??7}倍 ／ ${allocation.status==='odds_incomplete'?'オッズ不足・配分待ち':allocation.rounded_target_met?'100円単位でも目標到達':allocation.status?'100円単位の最低払戻倍率は目標未達':'旧版・配分記録なし'}<br>最低払戻 ${num(allocation.minimum_hit_return)}円〜最高 ${num(allocation.maximum_hit_return)}円 ／ 最低払戻倍率 ${num(allocation.rounded_minimum_return_multiple)}倍<br>予算は比較用の仮想2,400円です。近似探索による候補で、最大利益や的中を保証するものではありません。</p><p>${(allocation.tickets||[]).map(t=>esc(t.combo)+'：'+t.stake+'円（'+num(t.odds)+'倍）').join('<br>')}</p><h3>展示STと本番ST・進入の予測</h3><p>過去データ：${esc(behavior.trained_through||'未集計')}まで。展示Fと正常STを分け、6艇でコースが重複しない進入候補を計算します。<br>${(behavior.st_estimates||[]).map((v,i)=>`${i+1}艇 本番ST推定 ${num(v)}`).join(' ／ ')}<br>${(behavior.scenarios||[]).map(x=>'艇番1〜6の進入：'+x.courses_by_boat.join('-')+'（'+pct(x.probability)+'）').join('<br>')}</p><h3>レース条件・当地の確認範囲</h3><p>6艇構成：${esc(({mixed:'男女混合',women_only:'女子のみ',men_only:'男子のみ',unknown:'性別未確認あり'})[ctx.field_type]||'旧版・未取得')} ／ 女子 ${ctx.female_count??'―'}艇・男子 ${ctx.male_count??'―'}艇・未確認 ${ctx.unknown_sex_count??'―'}艇<br>開催区分：${esc(ctx.meeting_type||'未取得')} ／ グレード ${esc(ctx.grade||'未取得')} ／ ${esc(ctx.stage||'未取得')}<br>当地の確認走数は保存された過去期間内の数です。公式3年分の総出走数ではありません。0.00・0％・0％の組合せを苦手の根拠には使いません。</p><h3>気象・展示の取得日時</h3><p>${Object.entries(times).map(([k,v])=>esc(({ex:'展示タイム',st:'展示ST・進入',weather:'気象',odds:'オッズ',original:'独自展示'})[k]||k)+': '+esc(v)+' ／ '+esc(previews[k]?.情報源||'配信CSV')).join('<br>')||'まだ取得できていません'}</p><h3>モーター過去3節・選手補正・今節</h3><div class="scroll"><table><tr><th>艇</th><th>期開始日・確認元</th><th>過去節</th><th>使用選手補正</th><th>今節走数</th><th>履歴</th></tr>${Object.entries(history).map(([lane,h])=>`<tr><td>${esc(lane)}</td><td>${esc(h.period)}<br>${h.period_source&&h.period_source!=='daily_motor_csv'?'公式の場共通期を照合':''}<br>${h.individual_totals_available===false?'個別の期成績は未取得':''}</td><td>${h.uses?.length||0}/3節</td><td>${h.matched_riders||0}/${h.total_riders||0}名</td><td>${h.current_series_runs||0}</td><td>${(h.uses||[]).map(u=>`${esc(u.start)}〜${esc(u.end)} ${esc(u.racer)}：${esc(u.finishes)}（全国勝率 ${num(u.racer_win_rate)}）`).join('<br>')||esc(h.status)}</td></tr>`).join('')}</table></div><p class="small warning">選手補正と確率は研究用です。風向は同じ場の過去条件として参照し、未確認の向かい風・追い風換算は行っていません。</p><h3>追加情報の根拠</h3><p>潮汐：${s.water_context?(s.water_context.tide.status==='not_applicable'?'対象外（この場は干満差なし）':esc(s.water_context.tide.station||s.water_context.tide.reason||'未取得')):tide?esc(`旧版の丸亀表：満潮 ${tide.high}／干潮 ${tide.low}`):'この旧版では未対応'}<br>根拠のない固定補正は停止しました。過去標本で学習できていない情報は記録・表示にとどめ、計算未使用を明記します。</p><p>${Object.entries(official.comments||{}).map(([lane,c])=>esc(lane)+'艇：'+esc(c.comment)).join('<br>')}</p><p>${Object.entries(official.before||{}).map(([lane,c])=>esc(lane)+'艇：プロペラ '+esc(c.propeller||'変更表示なし')+'／部品交換 '+esc(c.parts||'表示なし')).join('<br>')}</p><p>公式取得：${esc(official.observed_at||'未取得')}</p><h3>更新履歴</h3><p>${Object.values(r.revisions||{}).sort((a,b)=>a.created_at.localeCompare(b.created_at)).map(x=>`${esc(x.created_at)} ${x.complete_inputs?'全入力':'暫定'}：${esc(x.selection['12'].join(', '))}`).join('<br>')}</p>`;
}
async function loadDay(){
 const ticket=++loading;try{const day=$('fullDate').value;if(!day)return;const next=await getJSON('full_history/'+day+'.json');if(ticket!==loading)return;const keep=selected&&next.records?.[selected];data=next;if(!keep)selected=null;if(!keep)$('fullDetail').innerHTML='<span class="muted">レースの「使った情報を見る」で入力の使用状況と更新履歴を確認できます。</span>';render()}catch(e){$('fullStatus').textContent=e.message;}
}
async function load(){try{await resolveLiveRef();index=await getJSON('boat24_full_index.json');if(!$('fullDate').value)$('fullDate').value=index.latest_day||'';await loadDay()}catch(e){$('fullStatus').textContent=e.message+'。総合モデルの初回データ作成を待っています。'}}
setInterval(()=>{if(!document.hidden)load()},60000);
$('fullReportGroup')?.addEventListener('change',renderReport);
$('fullDate').addEventListener('change',loadDay);$('venue').addEventListener('change',render);$('fullReload').addEventListener('click',load);load();
})();
