/* All-input forecasts and the exact input evidence used by each immutable revision. */
(function(){
'use strict';
const $=id=>document.getElementById(id),esc=x=>String(x??'―').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const names=['全24場','桐生','戸田','江戸川','平和島','多摩川','浜名湖','蒲郡','常滑','津','三国','びわこ','住之江','尼崎','鳴門','丸亀','児島','宮島','徳山','下関','若松','芦屋','福岡','唐津','大村'];
const statuses={not_contributing_market_only:'検証で市場のみ採用・文脈は未採用',used:'計算に使用',missing:'未取得',partial:'一部のみ取得',historical_sample_insufficient:'参照できる過去標本が不足'};
const pct=x=>x==null?'未集計':(100*x).toFixed(1)+'%',num=x=>x==null?'未取得':Number(x).toFixed(2);
let index=null,data=null,selected=null,loading=0;
const latest=r=>r.revisions?.[r.result?.selection_snapshot_id]||Object.values(r.revisions||{}).filter(s=>s.evaluation_eligible&&Date.parse(s.created_at)<Date.parse(s.cutoff)).sort((a,b)=>b.created_at.localeCompare(a.created_at)||b.id.localeCompare(a.id))[0];
async function getJSON(path){
 const root='https://raw.githubusercontent.com/tadasuketakahashi1234-design/-marugame-motor/main/omura/docs/';
 const urls=[root+path,'./'+path];
 const got=await Promise.allSettled(urls.map(async u=>{const r=await fetch(u+'?t='+Date.now(),{cache:'no-store',signal:AbortSignal.timeout(20000)});if(!r.ok)throw Error('HTTP '+r.status);return r.json()}));
 const valid=got.filter(r=>r.status==='fulfilled').map(r=>r.value);
 if(!valid.length)throw Error('総合予想データを読み込めません');
 return valid.sort((a,b)=>Date.parse(b.updated_at||b.generated_at||0)-Date.parse(a.updated_at||a.generated_at||0))[0];
}
function records(){const venue=Number($('venue').value);return Object.values(data?.records||{}).filter(r=>!venue||Number(r.venue)===venue).sort((a,b)=>b.race_code.localeCompare(a.race_code))}
function render(){
 if(!index||!data)return;
 const list=records(),venue=String(Number($('venue').value)),day=$('fullDate').value;
 const group=index.days?.[day],stats=venue==='0'?group?.summary:group?.venues?.[venue];
 $('fullStatus').textContent='総合予想更新：'+(data.updated_at||index.updated_at)+' ／ '+(index.model||'')+' ／ 取得できた情報で再計算';
 let tiles=[`<div class="metric">当日の総合予想<strong>${list.length}</strong>必須情報使用 ${stats?.complete_inputs??0}件<br>結果確定 ${stats?.settled??0}件 ／ 待ち ${stats?.pending??0}件</div>`];
 for(const n of [12,18]){const s=stats?.[n]||{};tiles.push(`<div class="metric">${n}点的中率<strong>${pct(s.hit_rate)}</strong>${s.hits??0}/${s.races??0}レース</div><div class="metric">${n}点回収率<strong>${pct(s.roi)}</strong>仮想収支 ${s.profit??0}円</div>`)}
 $('fullMetrics').innerHTML=tiles.join('');
 $('fullRecords').innerHTML='<table><thead><tr><th>場・R</th><th>情報状態</th><th>最終計算／締切</th><th>12点買い目</th><th>12点推定・合成オッズ</th><th>結果</th></tr></thead><tbody>'+list.map(r=>{const s=latest(r);if(!s)return '';const status=s.feature_usage?.odds?.market_blend===1?'市場分布のみ採用':s.complete_inputs?'必須情報を使用':'未採用・未取得の情報あり';const m=s.market_metrics?.['12']||{};return `<tr data-full-code="${esc(r.race_code)}"><td>${esc(names[r.venue])} ${esc(r.race)}R</td><td>${status}<br><button type="button" data-full-detail="${esc(r.race_code)}">使った情報を見る</button></td><td>${esc(s.created_at.slice(11,19))}<br>締切 ${esc(s.cutoff.slice(11,16))}<br>履歴 ${Object.keys(r.revisions||{}).length}版</td><td>${esc((s.selection?.['12']||[]).join(', '))}</td><td>推定 ${pct(m.estimated_hit_probability)}<br>合成 ${num(m.synthetic_odds)}倍<br><span class="muted">未校正・仮想検証</span></td><td>${esc(r.result?.combo||r.result_pending_reason||'結果待ち')}<br>${r.result?esc(r.result.payout_100yen)+'円':''}</td></tr>`}).join('')+'</tbody></table>';
 $('fullRecords').querySelectorAll('[data-full-detail]').forEach(b=>b.addEventListener('click',()=>{selected=b.dataset.fullDetail;renderDetail()}));
 if(!list.length)$('fullRecords').innerHTML='<p>この日の総合予想はまだ保存されていません。旧モデルの保存履歴は下に残しています。</p>';
 if(selected&&data.records[selected])renderDetail();
 const check=index.training?.validation||{},loss=check.test_mean_logloss||{};
 $('fullTraining').textContent='参照データ：'+(index.training?.through||'―')+'まで ／ '+(index.training?.samples??0)+'走 ／ コース集計 '+(index.training?.course_window_days??'―')+'日 ／ 過去情報の取得失敗 '+Object.keys(index.training?.source_errors||{}).length+'件。総合モデル開始後の成績を、旧モデルと分けて集計しています。男女構成・開催条件・相手関係を追加。調整用と最終評価用の期間を分離しています。未学習の潮汐・コメント等の仮補正は停止しました。映像AI解析は未実装です。調整 '+(check.tuning_races??'―')+'R／別期間の最終評価 '+(check.test_races??'―')+'R。市場単独への改善：'+(loss.selected!=null&&loss.market!=null&&loss.selected<loss.market?'短期評価では確認・長期未証明':'未確認')+'。';
}
function renderDetail(){
 const r=data?.records?.[selected],s=r&&latest(r);if(!s)return;
 const history=s.input_snapshot?.motor_history||{},previews=s.input_snapshot?.previews||{},official=s.input_snapshot?.official||{},tide=s.input_snapshot?.tide_schedule;
 const times=s.input_snapshot?.source_times||{},ctx=s.input_snapshot?.race_context||{};
 $('fullDetail').innerHTML=`<h3>${esc(names[r.venue])} ${esc(r.race)}R｜実際に使った情報</h3><p>計算 ${esc(s.created_at)} ／ 締切 ${esc(s.cutoff)}<br>判断：${esc(s.decision)}</p><div class="scroll"><table><tr><th>情報</th><th>状態</th><th>使用した項目</th></tr>${Object.entries(s.feature_usage||{}).map(([key,f])=>`<tr><td>${esc(f.label)}</td><td>${esc(statuses[f.status]||f.status)}${key==='odds'?'':`（${f.used_lanes||0}/6艇）`}</td><td>${esc((f.used_fields||[]).map(k=>k+'（'+(f.field_coverage?.[k]??0)+'/6艇）').join('・')||(key==='odds'?`${f.valid_combinations||0}/120組、確率への市場情報比率 ${pct(f.market_blend)}`:'―'))}${f.unused_fields?.length?'<br>取得済み・計算未使用：'+esc(f.unused_fields.join('・')):''}</td></tr>`).join('')}</table></div><h3>レース条件・当地の確認範囲</h3><p>6艇構成：${esc(({mixed:'男女混合',women_only:'女子のみ',men_only:'男子のみ',unknown:'性別未確認あり'})[ctx.field_type]||'旧版・未取得')} ／ 女子 ${ctx.female_count??'―'}艇・男子 ${ctx.male_count??'―'}艇・未確認 ${ctx.unknown_sex_count??'―'}艇<br>開催区分：${esc(ctx.meeting_type||'未取得')} ／ グレード ${esc(ctx.grade||'未取得')} ／ ${esc(ctx.stage||'未取得')}<br>当地の確認走数は保存された過去期間内の数です。公式3年分の総出走数ではありません。0.00・0％・0％の組合せを苦手の根拠には使いません。</p><h3>気象・展示の取得日時</h3><p>${Object.entries(times).map(([k,v])=>esc(k)+': '+esc(v)).join('<br>')||'まだ取得できていません'}</p><h3>モーター過去3節・選手補正・今節</h3><div class="scroll"><table><tr><th>艇</th><th>期開始日</th><th>過去節</th><th>使用選手補正</th><th>今節走数</th><th>履歴</th></tr>${Object.entries(history).map(([lane,h])=>`<tr><td>${esc(lane)}</td><td>${esc(h.period)}</td><td>${h.uses?.length||0}/3節</td><td>${h.matched_riders||0}/${h.total_riders||0}名</td><td>${h.current_series_runs||0}</td><td>${(h.uses||[]).map(u=>`${esc(u.start)}〜${esc(u.end)} ${esc(u.racer)}：${esc(u.finishes)}（全国勝率 ${num(u.racer_win_rate)}）`).join('<br>')||esc(h.status)}</td></tr>`).join('')}</table></div><p class="small warning">選手補正と確率は研究用です。風向は同じ場の過去条件として参照し、未確認の向かい風・追い風換算は行っていません。</p><h3>追加情報の根拠</h3><p>潮汐：${tide?esc(`満潮 ${tide.high}／干潮 ${tide.low}／${tide.cycle}`):'未取得・対象外'}<br>根拠のない固定補正は停止しました。過去標本で学習できていない情報は記録・表示にとどめ、計算未使用を明記します。</p><p>${Object.entries(official.comments||{}).map(([lane,c])=>esc(lane)+'艇：'+esc(c.comment)).join('<br>')}</p><p>${Object.entries(official.before||{}).map(([lane,c])=>esc(lane)+'艇：プロペラ '+esc(c.propeller||'変更表示なし')+'／部品交換 '+esc(c.parts||'表示なし')).join('<br>')}</p><p>公式取得：${esc(official.observed_at||'未取得')}</p><h3>更新履歴</h3><p>${Object.values(r.revisions||{}).sort((a,b)=>a.created_at.localeCompare(b.created_at)).map(x=>`${esc(x.created_at)} ${x.complete_inputs?'全入力':'暫定'}：${esc(x.selection['12'].join(', '))}`).join('<br>')}</p>`;
}
async function loadDay(){
 const ticket=++loading;try{const day=$('fullDate').value;if(!day)return;const next=await getJSON('full_history/'+day+'.json');if(ticket!==loading)return;data=next;selected=null;$('fullDetail').innerHTML='<span class="muted">レースの「使った情報を見る」で入力の使用状況と更新履歴を確認できます。</span>';render()}catch(e){$('fullStatus').textContent=e.message;}
}
async function load(){try{index=await getJSON('boat24_full_index.json');if(!$('fullDate').value)$('fullDate').value=index.latest_day||'';await loadDay()}catch(e){$('fullStatus').textContent=e.message+'。総合モデルの初回データ作成を待っています。'}}
$('fullDate').addEventListener('change',loadDay);$('venue').addEventListener('change',render);$('fullReload').addEventListener('click',load);load();
})();
