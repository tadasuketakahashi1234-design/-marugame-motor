"""Race-specific explanations from saved observations; no invented video review."""
from boat24_context import number
from boat24_integrity import timeparse

SCHEMA='race-commentary-2'

def build(s):
    fs=s.get('input_snapshot',{}).get('features',[])
    if len(fs)!=6:return None
    ids={b['lane']:b for b in s.get('boat_identities',[])}
    label=lambda i:f'{i}号艇'+('・'+str(ids[i]['name']) if ids.get(i,{}).get('name') else '')
    first={i:0. for i in range(1,7)};inside={i:0. for i in range(1,7)}
    for combo,p in s.get('probabilities',{}).items():
        boats=combo.split('-')
        if len(boats)!=3:continue
        first[int(boats[0])]+=p
        for boat in boats:inside[int(boat)]+=p
    order=sorted(first,key=lambda i:(-first[i],i));axis=order[0]
    from boat24_reasoning import build as reasoning
    trace=reasoning(s)
    partners=[r['lane'] for r in trace['axis_opponents'][:2]] if trace else sorted((i for i in inside if i!=axis),key=lambda i:(-inside[i],i))[:2]
    f=fs[axis-1];ed=f.get('exhibition_detail',{});ability=f.get('ability',{});course=f.get('course',{})
    def evidence(i):
        x=fs[i-1];a=x.get('ability',{});e=x.get('exhibition_detail',{});sd=x.get('start_detail',{});out=[]
        if a.get('全国勝率') is not None:out.append(f"全国勝率{a['全国勝率']:.2f}")
        for key,title in [('展示タイム秒','展示'),('一周秒','一周'),('まわり足秒','まわり足'),('直線秒','直線')]:
            if e.get(key) is not None:
                rank=e.get({'展示タイム秒':'展示順位','一周秒':'一周順位','まわり足秒':'まわり足順位','直線秒':'直線順位'}[key])
                out.append(f'{title}{e[key]:.2f}秒'+(f'・{int(rank)}番手' if rank else ''))
        if sd.get('展示ST秒') is not None:out.append(f"展示ST {'F'+format(abs(sd['展示ST秒']),'.2f') if sd.get('展示F') else format(sd['展示ST秒'],'.2f')}")
        return out
    axis_text=f"中心評価は{label(axis)}。"+'、'.join(evidence(axis)[:4])+'を確認できる。能力と当日の実測を分けて照合する。'
    alpha=s.get('feature_usage',{}).get('odds',{}).get('market_blend')
    if alpha==1:axis_text+='今回の計算順位は市場情報のみ。展示や水面の考察を確率に加点した結果ではない。'
    motor=f.get('motor',{}).get('モーター2連対率');lap=ed.get('一周順位')
    if motor is not None and lap:
        axis_text+=f' モーター期2連対率{motor:.1f}％に対し、本日の一周は{int(lap)}番手。期率は使用選手や番組の影響も含むため、このRの足と同一視しない。'
    axis_rate=number(ability.get('全国勝率'))
    rivals=[(number(x.get('ability',{}).get('全国勝率')),i) for i,x in enumerate(fs,1) if i!=axis and number(x.get('ability',{}).get('全国勝率')) is not None]
    if axis_rate is not None and rivals:
        rival_rate,rival=max(rivals)
        if rival_rate>axis_rate:
            axis_text+=f' 能力比較では{label(rival)}の全国勝率{rival_rate:.2f}が軸艇{axis_rate:.2f}を上回る。軸艇の先行が崩れる場合は、この相手の逆転も考える。'
        else:
            axis_text+=f' 全国勝率は相手最高{rival_rate:.2f}に対し{axis_rate-rival_rate:.2f}高い。一方、能力差がそのまま今回の着順差になるとは限らず、進入と当日の足を合わせて判断する。'
    if s.get('phase')=='initial':axis_text+='展示前の暫定評価。スタートや当日の足を確認した最終評価ではない。'
    elif ed.get('展示順位',0)>=4:
        axis_text+='ただし展示タイム順位は上位ではなく、能力評価だけで押し切るとは読まない。'
    if course.get('標本数'):
        axis_text+=f" 保存期間内の当該進入実績は{int(course['標本数'])}走。少数標本なので、この数字だけで軸を固定しない。"
    opponent='相手の中心は'+ '、'.join(label(i) for i in partners)+'。'+' '.join(label(i)+'は'+'、'.join(evidence(i)[1:4] or evidence(i)[:1])+'。' for i in partners)
    scenarios=s.get('behavior_forecast',{}).get('scenarios',[]);entry=None
    if scenarios and len(scenarios[0].get('courses_by_boat',[]))==6:
        courses=scenarios[0]['courses_by_boat'];entry='-'.join(str(i) for i in sorted(range(1,7),key=lambda i:courses[i-1]))
    exhibition=[(x.get('entry_detail',{}).get('展示コース'),i) for i,x in enumerate(fs,1)]
    observed_entry='-'.join(str(i) for c,i in sorted(exhibition)) if all(c for c,i in exhibition) and len({c for c,i in exhibition})==6 else None
    axis_course=f.get('entry_detail',{}).get('展示コース')
    attack=next((i for i in order if i!=axis and fs[i-1].get('entry_detail',{}).get('展示コース',i)>=3),partners[0])
    deployment=(f'展示の並びは{observed_entry}。' if observed_entry else '展示の進入は未確認。')+(f'本番の統計上の第一想定は{entry}。' if entry else '本番の進入想定は未確認。')
    if axis_course==1 or axis_course is None and axis==1:
        deployment+=f'{label(axis)}がインを確保して先に1マークを回れば、'+ '・'.join(str(i)+'号艇' for i in partners)+'の追走を本線に置く。'+f'一方、{label(attack)}がスタートで内を先行できれば、攻めと内の差し残りで相手順が変わる。これは条件付きの展開想定。'
    else:
        deployment+=f'{label(axis)}は先行艇を捕まえる展開が必要。{label(attack)}の攻めが届く場合と内側が残る場合を分け、枠番どおりに決まる前提では組まない。'
    weather=s.get('input_snapshot',{}).get('previews',{}).get('weather',{});w={k:number(v) for k,v in (f.get('weather',{}) or weather).items() if number(v) is not None};wc=s.get('water_context',{});official=wc.get('latest_official_wind',{})
    bits=[]
    for key,title,unit in [('風速(m)','風速','m'),('波の高さ(cm)','波高','cm'),('気温(℃)','気温','℃'),('水温(℃)','水温','℃')]:
        if w.get(key) is not None:bits.append(f'{title}{w[key]:g}{unit}')
    same_water_observation=not weather.get('気象観測時刻') or weather.get('気象観測時刻')==official.get('measured_at')
    direction=official.get('wind_direction_literal') if same_water_observation else None;quality=official.get('wind_quality_literal') if same_water_observation else None
    water=('当該場の観測は'+ '・'.join(bits)+'。') if bits else '当日の風・波は未取得。平水面や無風として扱わない。'
    if direction:water+=f'公式の風向表示は{direction}'+(f'／{quality}' if quality else '')+'。'
    measured=weather.get('気象観測時刻') or official.get('measured_at') or weather.get('取得日時')
    if measured:
        water+='観測・配信時刻 '+str(measured)+'。'
        at=timeparse(measured);created=timeparse(s.get('created_at'))
        if at and created and (created-at).total_seconds()>600:water+=f'予想時点で観測から{int((created-at).total_seconds()/60)}分経過しており、直前の水面としての評価は保留。'
    if weather.get('参考レース') is not None:water+=f" {weather['参考レース']}R時点の参考観測で、今回Rの実測と同一ではない。"
    n=f.get('wind',{}).get('同条件標本数');delta=f.get('wind',{}).get('同場コース平均との差')
    if n and delta is not None:
        water+=f'軸艇の同場・同コース・同風条件は{int(n)}例、場・コース平均との着順差は{delta:+.2f}（正なら良い）。'
        water+= '差は小さく、風による明確な上乗せ根拠は薄い。' if abs(delta)<.25 else '条件別の過去比較であり、今回の風による因果効果を示す数字ではない。'
    if number(w.get('風速(m)')) is not None and w['風速(m)']>=5:water+='風が強いためスタートのばらつきとターンの流れを警戒するが、風速だけで特定艇の有利を断定しない。'
    profile=wc.get('profile',{})
    if profile.get('tidal_range')=='なし':water+='この場は公式場データ上の干満差なし。潮汐を上乗せ材料にしない。'
    elif wc.get('tide',{}).get('status')=='available':water+='潮位は'+str(wc['tide'].get('station','近隣港'))+'の天文推算で、競走水面の実測流速ではない。'
    risks=[]
    flanes=[str(i) for i,x in enumerate(fs,1) if x.get('start_detail',{}).get('展示F')]
    if flanes:risks.append('展示Fは'+ '・'.join(flanes)+'号艇。展示の踏み込みを本番の先行保証や正常ST最速として評価しない。')
    if observed_entry and observed_entry!='1-2-3-4-5-6':risks.append('展示で枠なりからの入れ替わりがあり、本番も同じ並びになるとは限らない。')
    h=s.get('input_snapshot',{}).get('motor_history',{}).get(str(axis),{})
    if h and h.get('matched_riders',0)<h.get('total_riders',0):risks.append(f"軸艇の過去3節の使用選手照合は{h.get('matched_riders',0)}/{h.get('total_riders',0)}名。モーター補正の確度には限界がある。")
    risks.append('進入の変更、内側のスタート遅れ、観測後の風・波の変化で本線は崩れる。取得した数値と、この文章の展開解釈を区別している。')
    plan=s.get('purchase_plan',{});tickets=plan.get('tickets',[])
    heads=sorted({t['combo'].split('-')[0] for t in tickets})
    price=('購入候補は'+ '・'.join(i+'号艇頭' for i in heads)+'。中心評価と、オッズを踏まえた購入対象は一致するとは限らない。全買い目の取得時払戻が総購入額を超える配分に限定する。') if tickets and plan.get('status')=='ready' else '買い目の採否は上の購入判定で確認。オッズ未取得・更新遅延と、最新オッズでも期待値条件に届かない見送りを分けて表示する。'
    rows=[{'lane':i,'name':ids.get(i,{}).get('name'),'mark':('◎' if i==axis else '○' if i==partners[0] else '▲' if i==partners[1] else '△'),'evidence':evidence(i),'motor_two_rate':fs[i-1].get('motor',{}).get('モーター2連対率')} for i in range(1,7)]
    if trace:
        comp=trace['components'];rival=trace['first_candidates'][1];final=trace['marginals'];place=trace['place_axis']
        axis_text=f"1着評価の先頭は{label(axis)}、連軸の先頭は{label(place)}。最終1着評価の{label(rival)}との差は{trace['axis_gap']*100:.1f}ポイント。"
        if trace['axis_gap']<.05:axis_text+='頭固定を強く推すほどの差ではなく、両艇を頭候補として併記する。'
        context,market=comp.get('context'),comp.get('market')
        if context:
            independent=max(context,key=lambda x:x['first'])['lane']
            axis_text+=f" 独自データ部分の先頭は{label(independent)}。{label(axis)} {context[axis-1]['first']*100:.1f}％、{label(rival)} {context[rival-1]['first']*100:.1f}％。"
            if independent!=axis:axis_text+='市場情報との混合で順位が逆転した評価である。'
        if market:axis_text+=f" 混合前の市場比率は{comp['market_weight']*100:.0f}％。市場由来の1着評価は{label(axis)} {market[axis-1]['first']*100:.1f}％、{label(rival)} {market[rival-1]['first']*100:.1f}％。"
        axis_text+=' 軸艇の観測：'+'、'.join(evidence(axis))+'。'
        support=next((r for r in trace.get('support',[]) if r['lane']==axis),{})
        if support.get('races'):
            axis_text+=f" 当該実進入コースの保存実績は{support['races']}走{support['wins']}勝。"
            interval=support.get('historical_rate_wilson95')
            if interval:axis_text+=f"過去比率の95％区間は{interval[0]*100:.1f}〜{interval[1]*100:.1f}％で、今回の勝率の区間ではない。"
            if support['races']<20:axis_text+='20走未満のため、この実績だけで軸を固定しない。'
        elif course.get('標本数'):
            axis_text+=f" 当該進入コースの保存標本は{int(course['標本数'])}走。元の勝数・区間がこの版に保存されていないため、補正済みの率を今回の勝率と同一視しない。"
        if s.get('phase')=='initial':axis_text+='展示前の暫定評価。'
        sensitivity=trace.get('sensitivity',{})
        if sensitivity.get('rows'):
            effects=sorted(sensitivity['rows'],key=lambda r:-abs(r['first_delta'][axis-1]))[:4]
            axis_text+=' 独自部分の感度確認：'+'／'.join(f"{r['label']} {r['first_delta'][axis-1]*100:+.1f}ポイント" for r in effects)+'。要素を外した場合との差で、足し合わせる寄与率ではない。'
        opponent=f'{label(axis)}が1着になる条件で、2・3着候補を比較する。'
        for r in trace['axis_opponents']:
            i=r['lane'];opponent+=f" {label(i)}：条件付き2着{r['second']*100:.1f}％・3着{r['third']*100:.1f}％。"+'、'.join(evidence(i))+'。'
            ed2=fs[i-1].get('exhibition_detail',{});co=fs[i-1].get('entry_detail',{}).get('展示コース')
            if co:opponent+=f'展示{int(co)}コース。'
            if ed2.get('展示順位')==1:opponent+='展示同率最速を含む上位艇。相手から外す際は価格条件と展開上の反証を確認する。'
        arrangement=trace.get('observed_entry')
        deployment=('展示の進入は'+'-'.join(map(str,arrangement))+'。') if arrangement else '展示進入は未確認。インを確保する条件を含め、隊形が確認できるまで暫定評価。'
        deployment+='頭候補ごとに、モデルが想定する2着・3着を比較する。攻め方の成立条件と反証は下に示す。まくり・差しが成立する確率は未推定。'
        quality=trace.get('quality',{}).get('weather',{})
        if quality.get('excluded_from_prediction'):water+=' この観測は鮮度条件を満たさず、今回の天候・風の数値特徴を計算から除外した。直前の有利・不利の加点には使用していない。'
        risks+=['軸の印、条件別比較値、取得時の価格条件は別の判断。1着先頭でも、頭固定の根拠や収益性が実証されたことにはならない。']
        for row in rows:
            row['evidence']+=['モデル内1着 '+format(final[row['lane']-1]['first']*100,'.1f')+'％／3着内 '+format(final[row['lane']-1]['top3']*100,'.1f')+'％']
    headline=f'◎{axis}号艇を中心、相手は{partners[0]}・{partners[1]}号艇'
    if trace and trace['axis_gap']<.05:
        headline=f"頭候補{axis}・{trace['first_candidates'][1]}号艇の接戦／連軸{trace['place_axis']}号艇"
        for row in rows:
            row['mark']='頭候補' if row['lane'] in trace['first_candidates'] else row['mark']
            if row['lane']==trace['place_axis']:row['mark']+='・連軸'
    return {'schema':SCHEMA,'snapshot_id':s['id'],'basis':'saved_inputs_and_conditional_interpretation','headline':headline,
            'forecast_lines':sorted(s.get('probabilities',{}),key=lambda k:(-s['probabilities'][k],k))[:3],'axis':axis_text,'opponents':opponent,'deployment':deployment,'water':water,'risks':risks,'price':price,'boats':rows,
            'water_analysis':__import__('boat24_water_commentary').build(s),'reasoning':trace,'context_at':s.get('context_snapshot_at',s.get('created_at')),'notice':'数値はモデル内比較で、検証済みの的中確率ではありません。映像の行き足・起こし位置・助走距離・旋回出口は未計測です。'}
