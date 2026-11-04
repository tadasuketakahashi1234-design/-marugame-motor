"""Saved quantitative explanations and conditional, falsifiable race branches."""
from collections import OrderedDict
import hashlib
import json
import math
from decimal import Decimal,ROUND_FLOOR
from boat24_context import normalize,predict,ALL_GROUPS
from boat24_quality import historical_support

SCHEMA='race-evidence-2'
_CACHE=OrderedDict()
FAMILIES=[('能力',['ability']),('コース実績',['course']),('展示',['exhibition']),('展示ST・進入',['start']),
          ('モーター履歴',['motor_history']),('天候・風',['weather','wind']),('本番ST・進入推定',['behavior'])]

def marginals(probabilities):
    return [{'lane':i,'first':sum(p for c,p in probabilities.items() if c.split('-')[0]==str(i)),
             'second':sum(p for c,p in probabilities.items() if c.split('-')[1]==str(i)),
             'third':sum(p for c,p in probabilities.items() if c.split('-')[2]==str(i)),
             'top3':sum(p for c,p in probabilities.items() if str(i) in c.split('-'))} for i in range(1,7)]

def components(s):
    p=s.get('probabilities',{});row=s.get('input_snapshot',{}).get('previews',{}).get('odds',{})
    try:market=normalize({c:1/float(row['3連単_'+c]) for c in p})
    except (KeyError,ValueError,TypeError,ZeroDivisionError):market={}
    alpha=s.get('feature_usage',{}).get('odds',{}).get('market_blend',0)
    cal=s.get('calibration_evidence',{}).get('temperature') if s.get('calibration_applied') else None
    pre=normalize({c:v**cal for c,v in p.items()}) if cal else p
    context=None
    if market and 0<=alpha<1:
        raw={c:(pre[c]-alpha*market[c])/(1-alpha) for c in p}
        if min(raw.values(),default=-1)>=-1e-8:context=normalize({c:max(0,v) for c,v in raw.items()})
    elif alpha==0:context=pre
    return {'market_weight':alpha,'context':marginals(context) if context else None,
            'market':marginals(market) if market else None,'mixed':marginals(pre) if pre else None,
            'final':marginals(p) if p else None,'calibration_temperature':cal,
            'notice':'市場との混合前後を比較したモデル内部値。今回の的中確率の実証ではありません。'}

def sensitivity(s,model):
    fs=s['input_snapshot']['features']
    active=s.get('research',{}).get('candidate_active',False)
    groups=[g for g in ALL_GROUPS if g!='data_quality'] if active else model.get('enabled_groups',ALL_GROUPS)
    identity=s.get('race_code') or s.get('input_snapshot',{}).get('previews',{}).get('odds',{}).get('レースコード','')
    key=hashlib.sha256(json.dumps([identity,s['created_at'][:10],model.get('model_id'),groups,[{g:f[g] for g in groups if f.get(g)} for f in fs]],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if key in _CACHE:
        _CACHE.move_to_end(key);return _CACHE[key]
    m={**model,'market_alpha':0,'phase_calibration':{},'_distance_cache':{},'enabled_groups':groups}
    code=s.get('race_code') or s.get('input_snapshot',{}).get('previews',{}).get('odds',{}).get('レースコード','')
    if len(code)!=12:return {'status':'race_identity_missing','rows':[]}
    baseline=marginals(predict(fs,int(code[8:10]),s['created_at'][:10],m,{})['probabilities']);rows=[]
    for label,drop in FAMILIES:
        if not any(g in groups and any(f.get(g) for f in fs) for g in drop):continue
        without=marginals(predict(fs,int(code[8:10]),s['created_at'][:10],{**m,'enabled_groups':[g for g in groups if g not in drop]}, {})['probabilities'])
        rows.append({'label':label,'groups':drop,'first_delta':[a['first']-b['first'] for a,b in zip(baseline,without)],
                     'top3_delta':[a['top3']-b['top3'] for a,b in zip(baseline,without)]})
    out={'status':'computed','context_baseline':baseline,'rows':rows,
         'notice':'独自データ部分で、その要素を外した再計算との差。加算できる寄与率や因果効果ではありません。'}
    _CACHE[key]=out
    while len(_CACHE)>24:_CACHE.popitem(last=False)
    return out

def conditional_rows(p,winner):
    mass=sum(v for c,v in p.items() if c.startswith(str(winner)+'-'))
    if mass<=0:return []
    return sorted([{'lane':i,'second':sum(v for c,v in p.items() if c.split('-')[:2]==[str(winner),str(i)])/mass,
                    'third':sum(v for c,v in p.items() if c.split('-')[0]==str(winner) and c.split('-')[2]==str(i))/mass,
                    'either':sum(v for c,v in p.items() if c.split('-')[0]==str(winner) and str(i) in c.split('-')[1:])/mass}
                   for i in range(1,7) if i!=winner],key=lambda r:(-r['either'],r['lane']))

def start_duel(attacker,inner):
    """Gated sensitivity reference; not a calibrated actual-start probability."""
    a,b=attacker.get('behavior',{}),inner.get('behavior',{})
    ns=[a.get('選手ST標本数',0),b.get('選手ST標本数',0)]
    if min(ns)<20:return {'status':'insufficient_racer_samples','racer_samples':ns,'minimum':20}
    values=[a.get('予測本番ST'),b.get('予測本番ST'),a.get('ST差標準偏差'),b.get('ST差標準偏差')]
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in values) or not all(0<=v<=1 for v in values[:2]) or min(values[2:])<=0:return {'status':'distribution_unverified'}
    ma,mb,sa,sb=values;p=.5*(1+math.erf((mb-ma)/math.sqrt(2*(sa*sa+sb*sb))))
    return {'status':'uncalibrated_normal_reference','earlier_probability':p,'racer_samples':ns,
            'notice':'独立正規近似の参考値。風の共通変動・艇間相関を扱わず、本番の先行確率として未校正。'}

def price_audit(s):
    p=s.get('probabilities',{});raw=s.get('input_snapshot',{}).get('previews',{}).get('odds',{})
    plan=s.get('purchase_plan',{});controls=plan.get('risk_controls',{})
    if not controls:return []
    selected={t['combo'] for t in plan.get('tickets',[])};keys=list(selected)
    keys+=sorted(p,key=lambda c:-p[c])[:8]
    for head in '123456':
        choices=[c for c in p if c.startswith(head+'-')]
        if choices:keys.append(max(choices,key=lambda c:p[c]))
    rows=[]
    for c in dict.fromkeys(keys):
        try:q=Decimal(str(raw['3連単_'+c]))
        except (KeyError,ValueError,ArithmeticError):continue
        if not q.is_finite() or q<=0:continue
        sq=(q*Decimal(str(1-controls['price_haircut']))).quantize(Decimal('.1'),rounding=ROUND_FLOOR)
        nominal=p[c]*int(q*10)/10;stress=p[c]*(1-controls['probability_haircut'])*int(sq*10)/10
        reason='配分全体の比較で非採用'
        if c in selected:reason='採用：下振れ条件を含む配分で成立'
        elif float(sq)*controls['maximum_ticket_share']<=1:reason='下振れ時のガミ回避と1点集中上限が両立しない'
        elif stress<=1:reason='この目単独の下振れ期待値は100％以下。配分全体で比較'
        rows.append({'combo':c,'odds':float(q),'model_probability':p[c],'unit_expected_roi':nominal,'stress_unit_expected_roi':stress,'selected':c in selected,'reason':reason})
    return sorted(rows,key=lambda r:(not r['selected'],-r['model_probability'],r['combo']))

def build(s,model=None,include_sensitivity=True):
    fs=s.get('input_snapshot',{}).get('features',[]);p=s.get('probabilities',{})
    if len(fs)!=6 or not p:return None
    ms=marginals(p);order=sorted(ms,key=lambda a:(-a['first'],a['lane']));axis=order[0]['lane']
    place=max(ms,key=lambda a:(a['top3'],-a['lane']))['lane']
    entry=[f.get('entry_detail',{}).get('展示コース',f.get('start',{}).get('展示進入')) for f in fs]
    verified=set(entry)==set(range(1,7))
    arrangement=sorted(range(1,7),key=lambda i:entry[i-1]) if verified else None
    heads=[a['lane'] for a in order[:2]]
    fast=[i for i,f in enumerate(fs,1) if f.get('exhibition_detail',{}).get('展示順位')==1 or f.get('start_detail',{}).get('正常展示ST順位')==1]
    heads=list(dict.fromkeys(heads+fast));branches=[]
    for winner in heads:
        f=fs[winner-1];course=entry[winner-1];st=f.get('start_detail',{});inside=arrangement[:arrangement.index(winner)] if arrangement else []
        rows=conditional_rows(p,winner);pairs=sorted(((c,v) for c,v in p.items() if c.startswith(str(winner)+'-')),key=lambda x:-x[1])[:3]
        conditions=[];counter=[];unknown=['1マークの攻め方と成立確率は未計測。着順条件の数値と区別する。']
        if not verified:conditions.append('本番の進入を確認するまで、コース別の攻め方は確定しない。')
        elif course==1:
            conditions.append(f'{winner}号艇がインを確保し、'+str(arrangement[1])+'号艇に対して先マイできること。')
            conditions.append(f'{arrangement[1]}号艇が外の攻めに対して壁となるか、差しに構えるかで追走順が変わる。')
        else:
            conditions.append(f'展示{int(course)}コース。内側の'+ '・'.join(map(str,inside))+'号艇とのスタート位置と1マークの進路が成立すること。')
            conditions.append('まくりなら外の追随、差し・まくり差しなら内の残りを別に検討する。決まり手の成立確率は付けない。')
        if st.get('展示F'):counter.append('展示F。展示の先行を本番の先行保証として採用しない。')
        if st.get('展示ST秒') is not None and inside:
            neighbour=inside[-1];inner=fs[neighbour-1].get('start_detail',{})
            if not st.get('展示F') and not inner.get('展示F') and inner.get('展示ST秒') is not None:
                gap=st['展示ST秒']-inner['展示ST秒'];conditions.append(f'内隣{neighbour}号艇との正常展示ST差は{gap:+.2f}秒（正なら遅い）。本番の逆転率は未検証。')
        duel=start_duel(f,fs[inside[-1]-1]) if inside else {'status':'no_inner_neighbour'}
        if f.get('exhibition_detail',{}).get('展示順位',0)>=4:counter.append('展示タイムは上位3艇に入っていない。')
        b=f.get('behavior',{});n=b.get('選手ST標本数',0)
        if b.get('予測本番ST') is not None:
            spread=f"{b['ST差標準偏差']:.2f}秒" if b.get('ST差標準偏差') is not None else '未取得'
            conditions.append(f"本番ST推定{b['予測本番ST']:.2f}秒／補正残差の標準偏差{spread}／本人{int(n)}例。")
            if n<20:counter.append('本人の展示→本番ST標本が20例未満。点推定だけで先行・壁を断定しない。')
        if not any(k in f.get('exhibition_detail',{}) for k in ('まわり足秒','一周秒','直線秒')):unknown.append('一周・回り足・直線の実測が不足。旋回後の残りを足の優位だけで断定できない。')
        branches.append({'winner':winner,'course':course,'conditions':conditions,'counter_evidence':counter,'unknown':unknown,
                         'start_comparison':duel,
                         'opponents':rows,'combos':[{'combo':c,'conditional_probability':v/sum(vv for cc,vv in p.items() if cc.startswith(str(winner)+'-'))} for c,v in pairs],
                         'probability_basis':'existing_joint_distribution_conditioned_on_winner','method_probability':None})
        from boat24_tactics import method_reference
        if model:
            code=s.get('race_code') or s.get('input_snapshot',{}).get('previews',{}).get('odds',{}).get('レースコード','')
            branches[-1]['method_reference']=method_reference(model.get('tactical_state',{}),int(code[8:10]),arrangement,winner,s['created_at'][:10]) if len(code)==12 else {'status':'race_identity_missing'}
        else:
            saved=next((b for b in s.get('race_reasoning',{}).get('branches',[]) if b['winner']==winner),{})
            if saved.get('method_reference'):branches[-1]['method_reference']=saved['method_reference']
    out={'schema':SCHEMA,'snapshot_id':s['id'],'axis':axis,'place_axis':place,'axis_gap':order[0]['first']-order[1]['first'],
         'first_candidates':[a['lane'] for a in order[:2]],'marginals':ms,'components':components(s),
         'axis_opponents':conditional_rows(p,axis),'observed_entry':arrangement,'branches':branches,
         'quality':s.get('input_quality',{}),'probability_verified':bool(s.get('probability_verified')),
         'price_audit':price_audit(s),
         'numerical_notice':'条件別のモデル内比較。展開の成立確率・検証済み的中確率ではありません。'}
    if model:
        out['support']=historical_support(model,s.get('boat_identities',[]),fs)
        out['sensitivity']=sensitivity(s,model) if include_sensitivity else {'status':'scheduled_near_cutoff','rows':[]}
    else:
        saved=s.get('race_reasoning',{})
        for key in ('support','sensitivity'):
            if key in saved:out[key]=saved[key]
    return out
