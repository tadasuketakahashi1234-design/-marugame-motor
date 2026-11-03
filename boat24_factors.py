"""Exhaustive task catalog: observed, shadow-tested and unavailable are distinct.

Candidate registration is not a claim that a source or predictive benefit exists.
"""
import re

CATALOG=[]
def add(category,group,items,mode='derived'):
    for label,pattern in items:
        CATALOG.append({'id':f'f{len(CATALOG)+1:03d}','category':category,'label':label,'group':group,'pattern':pattern,'collection':mode})

add('選手・当地・男女構成','ability',[(x,x) for x in ('全国勝率','全国2連対率','全国3連対率','当地勝率','当地2連対率','当地3連対率','全国平均ST','F本数','L本数')])
add('選手・当地・男女構成','recent',[('全国近況','全国近況'),('当地近況','当地近況')])
add('選手・当地・男女構成','course',[('実進入別成績','1着率|2連対率|3連対率'),('コース別ST','平均ST'),('スタート順','平均スタート順'),('標本数と補正','標本数')])
add('選手・当地・男女構成','local_support',[(x,x) for x in ('当地確認走数','当地コース確認走数','構成別確認走数','構成別コース確認走数','当地公式成績未確認')])
add('選手・当地・男女構成','race_conditions',[(x,p) for x,p in [('6艇の男女構成','6艇構成'),('本人の性別','本人女子'),('女子限定・男女W開催','開催区分'),('グレード','グレード'),('予選・準優・優勝戦','段階'),('開催日次','開催日次'),('昼夜・時間帯','ナイター|締切時刻')]])
add('選手・当地・男女構成','opposition',[('相手の能力・能力差','相手.*勝率|相手との差'),('級別構成','相手.*人数'),('本人の能力順位','全国勝率順位')])
add('進入・スタート','entry_detail',[('枠と展示コース','展示コース'),('前付け・進入変更の実測','枠からの移動|枠変更艇数'),('進入固定','進入固定'),('レース距離・短縮','距離m|周回短縮')])
add('進入・スタート','behavior',[('本番進入の複数シナリオ','予測進入コース|進入変化確率'),('展示と本番のST差','展示本番ST差'),('ST予測のばらつき','ST差標準偏差'),('選手別の確認標本','選手.*標本数')])
add('進入・スタート','start_detail',[(x,x) for x in ('展示ST秒','展示F','正常展示ST順位','正常展示STばらつき','内隣展示ST差秒','外隣展示ST差秒')])
add('進入・スタート','entry_detail',[(x,'') for x in ('スロー／ダッシュ','カド位置','3対3・4対2の隊形','起こし位置','助走距離','前付けへの抵抗')],'requires_verified_source_or_video')
add('展開・2着3着','style',[('コース別の攻め方','勝ち率'),('攻められた時の傾向','敗れ率'),('内外の隣艇','内隣|外隣')])
add('展開・2着3着','interactions',[('コースと展示の関係','コース展示相対'),('STと伸びの関係','ST伸び相対')])
add('展開・2着3着','interactions',[(x,'') for x in ('2コース逃がし率','1コース差され率・まくられ率の厳密定義','壁の成立','先攻め・競り合い','差し場の成立','攻め艇と追走艇','決まり手別2・3着分布','1マーク後の追い上げ','順位維持・逆転','勝ち切り型と連下型','隊形別の6艇同時着順')],'requires_historical_labels')
add('展示・体重・足','exhibition_detail',[(x,x) for x in ('展示タイム秒','展示順位','展示最速差秒','内隣展示タイム差秒','外隣展示タイム差秒','体重kg','調整体重kg','体重調整体重合計kg')])
add('展示・体重・足','exhibition_detail',[('一周・半周の実測と順位','一周|半周'),('まわり足の実測と順位','まわり足|回り足'),('直線の実測と順位','直線')])
add('展示・体重・足','exhibition_detail',[(x,'') for x in ('行き足の映像計測','掛かり・押し・舟の向きの映像計測','展示から本番への数値補正','艇間距離・航跡','映像計測の誤差')],'requires_verified_source_or_video')
add('機材・整備・相性','motor',[('モーター期成績','期_'),('モーター2・3連対率','モーター')])
add('機材・整備・相性','motor_history',[('過去3節','過去3節平均着順'),('使用選手補正','選手補正'),('今節評価','今節'),('直近節の変化','直近節の変化')])
add('機材・整備・相性','machine_detail',[(x,x) for x in ('ボート2連対率','ボート3連対率','チルト度','交換_電気','交換_キャブ','交換_ピストン','交換_リング','交換_シリンダ','交換_シャフト','交換_ギヤ','交換_キャリア','プロペラ新')])
add('機材・整備・相性','maintenance',[('期内整備回数','整備種別'),('整備後経過日数','メンテ後日数')])
add('機材・整備・相性','machine_detail',[(x,'') for x in ('前検タイム','前検からの変化','中間整備の内容と時刻','ボートの使用者補正','モーターとボートの組合せ','転覆・故障後の回復','選手と機材の相性','選手の調整による改善','燃料・機材制度の変更','ペラ調整量')],'requires_verified_source_and_history')
add('今節・当日・勝負条件','series_detail',[(x,x) for x in ('当日既走数','前走着順','前走結果取得から分','前走展示タイム変化秒','前走チルト変化度','得点率','順位','ボーダー順位')])
add('今節・当日・勝負条件','series_detail',[('着順別得点率','[1-6]着時得点率')])
add('今節・当日・勝負条件','series_detail',[(x,'') for x in ('前走体重・調整体重変化','前走後の整備変更','節初からの展示推移','追加あっせん・途中帰郷','出走間隔・休養明け','F発生日・未消化・休み明け','予選残り走数・同点ルール','企画レースの資格・番組条件','年齢・経験・登録期','級別審査・選出条件')],'requires_verified_source_and_history')
for aspect in ('出足','行き足','伸び','回り足','掛かり','押し','舟の向き','乗り心地','スタート'):
    add('選手コメント','comment_detail',[(aspect,aspect),(aspect+'の変化',aspect+'変化')])
add('選手コメント','comment_detail',[(x,'') for x in ('進入・前付けの発言','調整方針・予定と実施の区別','他艇との比較対象','発言時点・対象レース','発言者・転載の重複','慎重・強気な表現の選手差','コメントと実測の整合','不明・矛盾・否定表現')],'evidence_only')
add('気象・水面','weather',[(x,p) for x,p in [('気温・水温','気温|水温'),('風速・波高','風速|波の高さ'),('天候','天候')]])
add('気象・水面','wind',[('場別の風成分と実績','.')])
add('気象・水面','tide',[('天文潮位・潮位差・位相','.')])
add('気象・水面','entry_detail',[('安定板','安定板')])
add('気象・水面','weather',[(x,'') for x in ('湿度・気圧','瞬間風速・風の変動','展示後の風向変化','降雨・視界','実測潮位・流向・流速','波向・うねり','河川流入・放水・ゲート','コース形状・遮蔽物の確認値','水面改修・設備変更','近隣港との伝播差','観測点と水面の距離')],'requires_verified_source_and_history')
add('オッズ・市場','market_detail',[(x,x) for x in ('市場1着周辺確率','市場3着内周辺確率','市場エントロピー','人気上位12集中度','単勝オッズ','2連単頭逆オッズ和')])
add('オッズ・市場','market_detail',[(x,'') for x in ('他券種の完全な整合比較','展示前後のオッズ変動','締切までの時系列変動','市場規模・発売票数','モデルと市場の乖離','最終払戻への変動リスク')],'requires_historical_snapshots')
add('信用度・取得状況','data_quality',[('情報源別の鮮度','取得経過分'),('6艇の充足度','展示取得艇数')])
add('信用度・取得状況','data_quality',[(x,'') for x in ('情報源間の不一致','学習範囲からの逸脱','モデル間の不一致','微小入力変化への感度','公開までの遅延','進入・文章解釈の不確実性')],'research_pending')

for item in CATALOG:
    mapping={'2コース逃がし率':('tactical_detail','2コースイン逃げ許容率'),
             '1コース差され率・まくられ率の厳密定義':('tactical_detail','イン敗戦中'),
             '決まり手別2・3着分布':('tactical_detail','コース(?:逃げ|差し|まくり|まくり差し)勝利時の'),
             '年齢・経験・登録期':('series_detail','年齢|期別')}
    mapping.update({'前検タイム':('machine_detail','前検タイム秒'),'前検からの変化':('machine_detail','前検展示差秒')})
    if item['label'] in mapping:
        item['group'],item['pattern']=mapping[item['label']];item['collection']='derived'
add('展開・2着3着','tactical_detail',[('2着・3着を分けた適性','^2着率|^3着率'),('本番STの分布','本番ST標準偏差|本番ST中央値')])

def audit(features,usage,model):
    rows=[];normalizers=model.get('scales',{})
    for item in CATALOG:
        group=item['group'];pattern=item['pattern']
        fields=sorted({key for f in features for key in f.get(group,{}) if pattern and re.search(pattern,key)})
        used=set(usage.get(group,{}).get('used_fields',[]))&set(fields)
        learned=[key for key in fields if group+'|'+key in normalizers]
        reason='未取得・数値を作らず保留' if pattern else {
            'evidence_only':'原文の根拠として保存。数値効果は未検証',
            'requires_verified_source_or_video':'検証済みの数値配信または映像計測が必要',
            'requires_historical_labels':'定義をそろえた過去ラベルと独立検証が必要',
            'requires_verified_source_and_history':'公式情報の取得・時刻照合・履歴蓄積が必要',
            'requires_historical_snapshots':'事前の時系列保存・対応する過去標本が必要',
            'research_pending':'検証処理の追加が必要'}.get(item['collection'],'未対応')
        state='used_unproven' if used else 'shadow' if learned else 'awaiting_history' if fields else 'unavailable'
        rows.append({**item,'fields':fields,'available_lanes':sum(any(k in f.get(group,{}) for k in fields) for f in features),
                     'used_fields':sorted(used),'learned_fields':learned,'state':state,
                     'reason':('本番計算に使用。精度改善の証明とは別' if used else '候補モデルで検証・本番への効果は未採用' if learned else '取得済み。過去の対応標本待ち' if fields else reason),
                     'validated_improvement':False})
    return rows
