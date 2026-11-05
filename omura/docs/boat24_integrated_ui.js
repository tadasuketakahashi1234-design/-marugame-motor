/* Integrated exhibition evidence, factor inventory and paired learning. */
(function(root){
'use strict';
const esc=x=>String(x??'―').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pct=x=>x==null?'標本待ち':(100*x).toFixed(1)+'%',num=x=>x==null?'未取得':Number(x).toFixed(3);
const states={used_unproven:'本番に使用・改善効果は別途検証',shadow:'候補予想で検証中',awaiting_history:'取得済み・学習標本待ち',unavailable:'未取得・未対応'};
function cell(object){return Object.entries(object||{}).map(([k,v])=>esc(k)+'：'+esc(typeof v==='number'?Number(v.toFixed(4)):v)).join('<br>')||'未取得'}
function factorRows(s,index){
 const learned=new Set(index.training?.learned_fields||[]),features=s.input_snapshot?.features||[],usage=s.feature_usage||{};
 return (index.factor_catalog||[]).map(item=>{
  const pattern=item.pattern?new RegExp(item.pattern):null;
  const keys=[...new Set(features.flatMap(f=>Object.keys(f[item.group]||{}).filter(k=>pattern?.test(k))))];
  const used=keys.filter(k=>(usage[item.group]?.used_fields||[]).includes(k)),trained=keys.some(k=>learned.has(item.group+'|'+k));
  const state=used.length?'used_unproven':trained?'shadow':keys.length?'awaiting_history':'unavailable';
  const reason=keys.length?keys.join('・'):({evidence_only:'原文の根拠として保存・数値効果未検証',requires_verified_source_or_video:'検証済み配信または映像計測が必要',requires_historical_labels:'定義をそろえた過去ラベルが必要',requires_verified_source_and_history:'公式情報の取得・履歴蓄積が必要',requires_historical_snapshots:'事前の時系列標本が必要',research_pending:'検証処理の追加が必要'})[item.collection]||'掲載・取得・時刻照合を確認できていません';
  const tests=keys.map(k=>index.training?.integrated_experiments?.field_tests?.[item.group+'|'+k]).filter(Boolean);
  return {...item,state,keys,reason,tests};
 });
}
function render(s,r,index){
 const d=s.details;if(!d)return '<p class="small muted">この保存版には展示細分化・統合学習の記録がありません。過去予想は書き換えません。</p>';
 const factors=factorRows(s,index),counts={};for(const f of factors)counts[f.state]=(counts[f.state]||0)+1;
 let out='<h3>展示・進入・足の詳細｜6艇を比較</h3><p class="small">以下は取得した実測値と派生値です。候補予想での検証と、本番買い目への採用を区別します。展示Fは正常ST順位の最速として扱いません。</p><div class="scroll"><table><tr><th>艇</th><th>展示・一周・回り足・直線</th><th>ST・隣艇差</th><th>進入</th><th>機材・調整</th><th>前走・得点条件</th></tr>';
 out+=(d.boats||[]).map(b=>`<tr><td>${esc(b.lane)}艇<br>登録${esc(b.racer)}</td><td>${cell(b.exhibition)}</td><td>${cell(b.start)}</td><td>${cell(b.entry)}</td><td>${cell(b.machine)}</td><td>${cell(b.series)}</td></tr>`).join('')+'</table></div>';
 out+='<h3>コメントの足別解釈と原文</h3>'+(d.boats||[]).map(b=>`<details><summary>${esc(b.lane)}艇：${b.comment?esc(b.comment.raw):'未取得・推測で補完しません'}</summary>${b.comment?`<p>取得 ${esc(b.comment_observed_at)} ／ ${esc(b.comment_source||'公式配信')}<br>${b.comment.publication_scope==='previous_day'?'前日コメント（'+esc(b.comment.comment_date)+'）':'発言・公開時刻は未公表'} ／ 解析版 ${esc(b.comment.version)} ／ 調整予定・不明・過去状態は現在の好材料として加点しません。</p><div class="scroll"><table><tr><th>足</th><th>根拠の文</th><th>対象</th><th>解釈</th></tr>${b.comment.evidence.map(e=>`<tr><td>${esc(e.aspect)}</td><td>${esc(e.phrase)}</td><td>${esc(({current_report:'状態の報告',previous_state:'以前の状態',plan:'予定・希望',uncertain:'不明'})[e.status])}</td><td>${e.value===1?'良いとの報告':e.value===-1?'弱いとの報告':e.value===0?'普通との報告':'数値化せず'}${e.change===1?'・改善':e.change===-1?'・悪化':''}</td></tr>`).join('')}</table></div>`:''}</details>`).join('');
 const research=s.research;
 out+='<h3>同じ時刻の統合予想・候補予想</h3>'+(research?`<p>${research.candidate_active?'候補モデルの採用条件を満たして採用。確率校正は別途確認します。':'細分化した情報は候補予想に入力し、事前保存して結果との比較を蓄積します。本番への固定加点は行いません。'}</p><p>本番の比較基準：${esc(research.baseline.selection['12'].join('、'))}<br>全候補を使う比較用12点：${esc(research.candidate.selection['12'].join('、'))}</p>`:'この版には比較用予想がありません');
 out+=`<details><summary>全候補台帳 ${factors.length}項目｜${Object.entries(counts).map(([k,v])=>esc(states[k])+v+'件').join(' ／ ')}</summary><p class="small">未取得の項目は学習済みとして扱いません。「本番に使用」は効果証明ではありません。データ源・過去標本・検証結果が揃った項目から採否を判定します。</p><div class="scroll"><table><tr><th>ID・分類</th><th>候補要素</th><th>取得・使用・学習</th><th>根拠／不足</th></tr>${factors.map(f=>`<tr><td>${esc(f.id)} ${esc(f.category)}</td><td>${esc(f.label)}</td><td>${esc(states[f.state])}</td><td>${esc(f.reason)}${f.tests.length?'<br>項目単位の過去検証：'+f.tests.map(t=>t.races+'R・全候補と除外時の誤差差 '+num(t.mean_full_minus_without)+(t.day_interval95?'（日単位95%区間 '+t.day_interval95.map(num).join('〜')+'）':'')).join('<br>'):''}</td></tr>`).join('')}</table></div></details>`;
 return out;
}
function learning(index){
 const el=typeof document!=='undefined'&&document.getElementById('fullLearning');if(!el)return;
 const x=index.integrated_learning||{},training=index.training||{},historical=training.integrated_experiments||{},replay=training.replay||{};
 const publicMode=x.policy==='public-frozen-learning-1';
 el.innerHTML=(publicMode?'<p><b>公開固定版・可変配分による検証</b>：研究用12点均等の成績を採用判定に使用しません。次のモデルへの学習反映：'+(training.learning_policy==='public-frozen-learning-1'?'公開固定 '+(replay.public_frozen??0)+'R／基準日 '+esc(training.through):'新しい学習条件での再学習待ち。現在のモデルは固定中')+'。</p><p>採用には最低400R・14日・候補の購入100R、黒字・回収率100％超・誤差改善・選択買い目の校正等を要求します。件数だけでは採用しません。</p><p>比較からの除外：'+esc(JSON.stringify(x.case_audit?.excluded||{}))+'</p>':'')+`<p>予想→結果→精算→学習→検証をこの画面で確認します。保存した事前入力からの学習：${replay.races??0}R・${replay.snapshots??0}時点。展示前と展示後は別標本です。同じレースの更新回数を独立した実績として数えません。</p><div class="scroll"><table><tr><th>事前保存の同時刻比較</th><th>レース・日数</th><th>比較基準／全候補の誤差</th><th>比較基準／全候補の回収率</th><th>採用判定</th></tr>${(x.phase_reports||[]).map(p=>`<tr><td>${p.phase==='initial'?'展示前':'展示後'}</td><td>${p.races}R・${p.days}日</td><td>${num(p.models?.baseline?.logloss)}／${num(p.models?.candidate?.logloss)}</td><td>${pct(p.models?.baseline?.roi)}／${pct(p.models?.candidate?.roi)}</td><td>${p.adoption_approved?'事前比較の採用条件を達成':esc(p.reason)}<br>最低${p.required_races}R・${p.required_days}日、誤差改善区間・回収率・校正も審査</td></tr>`).join('')}</table></div><details><summary>過去の時系列検証・要素群／細分項目を外した比較 ${historical.races??0}R</summary><p>過去CSVの再構成と、実際に事前保存した検証は別集計です。過去再構成だけで本番へ自動採用しません。</p><div class="scroll"><table><tr><th>モデル／外した要素</th><th>確率予測誤差（低いほど良い）</th><th>対応標本</th></tr>${Object.entries(historical.mean_logloss||{}).map(([key,value])=>`<tr><td>${esc(key)}</td><td>${num(value)}</td><td>${historical.family_test_races?.[key.replace('without:','')]??historical.races??0}R</td></tr>`).join('')}</table></div><details><summary>細分項目ごとの除外比較 ${Object.keys(historical.field_tests||{}).length}項目</summary><div class="scroll"><table><tr><th>項目</th><th>対応レース</th><th>全候補−除外時の誤差（負なら追加で改善）</th><th>日単位95%区間</th></tr>${Object.entries(historical.field_tests||{}).map(([k,t])=>`<tr><td>${esc(k)}</td><td>${t.races}R</td><td>${num(t.mean_full_minus_without)}</td><td>${t.day_interval95?t.day_interval95.map(num).join('〜'):'日数不足'}</td></tr>`).join('')}</table></div><p>多数項目の探索的比較です。この表だけで有効性を断定・採用しません。</p></details><p>${(historical.folds||[]).map(f=>esc(f.test_day)+'：'+f.races+'R').join(' ／ ')}</p></details>`;
}
root.Boat24Integrated={render,learning,factorRows};
})(globalThis);
