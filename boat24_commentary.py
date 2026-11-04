"""Race-specific explanations from saved observations; no invented video review."""
from boat24_context import number
from boat24_integrity import timeparse

SCHEMA='race-commentary-1'

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
    partners=sorted((i for i in inside if i!=axis),key=lambda i:(-inside[i],i))[:2]
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
    weather=s.get('input_snapshot',{}).get('previews',{}).get('weather',{});w=f.get('weather',{});wc=s.get('water_context',{});official=wc.get('latest_official_wind',{})
    bits=[]
    for key,title,unit in [('風速(m)','風速','m'),('波の高さ(cm)','波高','cm'),('気温(℃)','気温','℃'),('水温(℃)','水温','℃')]:
        if w.get(key) is not None:bits.append(f'{title}{w[key]:g}{unit}')
    direction=official.get('wind_direction_literal');quality=official.get('wind_quality_literal')
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
        water+=f'軸艇の同場・同コース・同風条件は{int(n)}例、場・コース平均との着順差は{delta:+.2f}（負なら良い）。'
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
    return {'schema':SCHEMA,'snapshot_id':s['id'],'basis':'saved_inputs_and_conditional_interpretation','headline':f'◎{axis}号艇を中心、相手は{partners[0]}・{partners[1]}号艇',
            'forecast_lines':sorted(s.get('probabilities',{}),key=lambda k:(-s['probabilities'][k],k))[:3],'axis':axis_text,'opponents':opponent,'deployment':deployment,'water':water,'risks':risks,'price':price,'boats':rows,
            'context_at':s.get('context_snapshot_at',s.get('created_at')),'notice':'映像を自動解析した見解ではありません。確認できた数値・公式情報からの条件付き考察です。'}
