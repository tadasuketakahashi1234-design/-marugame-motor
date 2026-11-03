"""Contextual nearest-neighbour research model; no calibrated betting edge claim.
Every available feature family participates in neighbour weighting. Weather is
conditioned on venue and observed course rather than an invented head/tailwind.
"""
import datetime as dt
import hashlib
import itertools
import json
import math
import statistics
import unicodedata
from collections import defaultdict
from boat24_integrity import JST, timeparse, valid_combo

VERSION = 'all-input-context-6-INTEGRATED'
FREEZE_MINUTES = 2
COMBOS = ['-'.join(map(str,c)) for c in itertools.permutations(range(1,7),3)]
GROUPS = ('ability','waku','recent','motor','motor_history','exhibition','start','original','weather')
EXTRA_GROUPS = ('course','style','maintenance','comments','tide','wind','race_conditions','opposition','local_support','behavior')
ALL_GROUPS = GROUPS + EXTRA_GROUPS
from boat24_details import DETAIL_GROUPS, LABELS as DETAIL_LABELS
BASE_GROUPS = ALL_GROUPS
ALL_GROUPS = BASE_GROUPS + DETAIL_GROUPS
LABELS = {'behavior':'展示と本番のST差・進入変化の実測学習','race_conditions':'6艇の男女構成・開催条件','opposition':'相手関係・級別構成','local_support':'当地・男女構成別実績と確認走数','course':'選手別・実進入コース別の得意不得意','style':'決まり手・隣艇との関係','maintenance':'整備履歴・部品交換・プロペラ','comments':'選手コメントの気配','tide':'開催場の潮汐推算・水面条件','wind':'開催場の風向・風速とコース別実績','ability':'選手の全国・当地成績','waku':'枠別過去10走','recent':'全国・当地近況',
          'motor':'モーター期成績','motor_history':'過去3節・使用選手補正・今節',
          'exhibition':'展示タイム・体重・チルト','start':'スタート展示・進入',
          'original':'一周・まわり足・直線等','weather':'天候・風速・風向・波高・気温・水温','odds':'3連単オッズ'}
LABELS.update(DETAIL_LABELS)


def number(x):
    try:
        x=float(unicodedata.normalize('NFKC',str(x)).replace(',','').replace('円','').strip())
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None


def finishes(text):
    # Preserve F/L/withdrawals as missing results, not fabricated sixth places.
    text=unicodedata.normalize('NFKC',str(text or ''))
    return [int(c) for c in text if c in '123456']


def mean(values):
    a=[v for v in values if v is not None]
    return sum(a)/len(a) if a else None


def safe_row(row,cutoff,asof):
    observed=timeparse((row or {}).get('取得日時'))
    return row if row and observed and observed<=asof and observed<cutoff else {}


def deadline(row,day=None):
    row=row or {};s=row.get('締切時刻') or row.get('電話投票締切予定') or row.get('締切予定時刻')
    t=timeparse(s)
    if t:return t
    try:
        date=dt.date.fromisoformat(row.get('レース日') or day or dt.datetime.strptime(row['レースコード'][:8],'%Y%m%d').date().isoformat())
        return dt.datetime.combine(date,dt.time.fromisoformat(str(s)),JST)
    except (ValueError,TypeError,KeyError):return None


def motor_key(venue,motor):
    return f'{int(venue):02d}-{str(motor).strip().lstrip("0")}'


def normalized_name(name):
    return ''.join(unicodedata.normalize('NFKC',str(name)).split())


def original_values(row):
    result={}
    for slot in range(1,4):
        label=str((row or {}).get(f'計測項目{slot}','')).strip()
        if label:
            vals=[number(row.get(f'艇{i}_値{slot}')) for i in range(1,7)]
            center=mean(vals)
            result[label]=[v-center if v is not None and center is not None else None for v in vals]
    return result


def make_features(card,waku,recent_n,recent_l,motor_stats,history,ex,st,weather,original,day):
    """Keep raw numeric values. Normalization is learned only from prior dates."""
    outputs=[];originals=original_values(original)
    ex_values=[number((ex or {}).get(f'艇{i}_展示タイム')) for i in range(1,7)]
    ex_center=mean(ex_values)
    st_values=[number((st or {}).get(f'艇{i}_スタート展示')) for i in range(1,7)]
    st_center=mean([abs(v) for v in st_values if v is not None])
    for lane in range(1,7):
        f={g:{} for g in ALL_GROUPS}
        def add(group,key,value):
            value=number(value)
            if value is not None:f[group][key]=value
        for suffix in ('全国勝率','全国2連対率','全国3連対率','当地勝率','当地2連対率','当地3連対率','全国平均ST','F本数','L本数','ボート2連対率','ボート3連対率'):
            add('ability',suffix,card.get(f'艇{lane}_{suffix}'))
        for suffix in ('枠番別勝率','枠番別平均ST','枠番別平均スタート順'):
            add('waku',suffix,(waku or {}).get(f'艇{lane}_{suffix}'))
        last=[number((waku or {}).get(f'艇{lane}_過去{i}走_着順')) for i in range(1,11)]
        add('waku','過去10走平均着順',mean([v for v in last if v and 1<=v<=6]))
        for name,row in [('全国',recent_n),('当地',recent_l)]:
            values=[]
            for idx in range(1,6):
                end=(row or {}).get(f'艇{lane}_前{idx}節_終了日','')
                if end and end<day:values+=finishes((row or {}).get(f'艇{lane}_前{idx}節_着順列'))
            add('recent',name+'近況平均着順',mean(values))
        ms=(motor_stats or {}).get(str(lane),{}) or {}
        for suffix in ('モーター2連対率','モーター3連対率'):
            add('motor',suffix,card.get(f'艇{lane}_{suffix}'))
        for name in ('勝率','2連対率','3連対率','出走数','平均ラップ秒'):
            add('motor','期_'+name,ms.get(name))
        for n in range(1,7):add('maintenance',f'整備種別{n}回数',ms.get(f'整備種別{n}回数'))
        date=str(ms.get('直近メンテ日',''))
        try:
            age=(dt.date.fromisoformat(day)-dt.date.fromisoformat(date)).days
            if age>=0:add('maintenance','メンテ後日数',age)
        except ValueError:pass
        for name,value in ((history or {}).get(str(lane),{}).get('features') or {}).items():add('motor_history',name,value)
        value=ex_values[lane-1]
        add('exhibition','展示タイム相対',value-ex_center if value is not None and ex_center is not None else None)
        for name in ('体重(kg)','体重調整(kg)','チルト'):add('exhibition',name,(ex or {}).get(f'艇{lane}_{name}'))
        value=st_values[lane-1]
        # Exhibition F is not a race disqualification and is not rewarded as a fast start.
        add('start','ST絶対値相対',abs(value)-st_center if value is not None and st_center is not None else None)
        add('start','展示ST符号付',value)
        add('start','展示F',int(value<0) if value is not None else None)
        add('start','展示進入',(st or {}).get(f'艇{lane}_コース'))
        for label,values in originals.items():add('original',label+'相対',values[lane-1])
        for name in ('風速(m)','風向','波の高さ(cm)','天候','気温(℃)','水温(℃)'):add('weather',name,(weather or {}).get(name))
        outputs.append(f)
    return outputs


def scales(samples):
    values=defaultdict(list)
    for s in samples:
        for group,fields in s['features'].items():
            for key,value in fields.items():values[group+'|'+key].append(value)
    output={}
    for key,a in values.items():
        if key.endswith('|風向') or key.endswith('|天候'):output[key]=1.0;continue
        std=statistics.pstdev(a) if len(a)>1 else 0
        output[key]=max(std,0.01)
    return output


def distance_parts(a,b,normalizers):
    parts={}
    for group in ALL_GROUPS:
        xs=[]
        for key,value in a.get(group,{}).items():
            other=b.get(group,{}).get(key)
            if other is None:continue
            if group=='weather' and key in ('風向','天候'):
                # Direction is a venue-specific category. No compass-to-course claim.
                d=0.0 if value==other else 1.0
            else:d=min(9,((value-other)/normalizers.get(group+'|'+key,1))**2)
            xs.append(d)
        expected=len(a.get(group,{}))
        if expected:
            xs.extend([1.0]*(expected-len(xs)))
        if xs:
            parts[group]=(sum(xs)/len(xs),len(xs) if any(k in b.get(group,{}) for k in a.get(group,{})) else 0)
    return parts

def distance(a,b,normalizers,enabled_groups=None):
    parts=distance_parts(a,b,normalizers)
    enabled=set(enabled_groups or ALL_GROUPS)
    distances=[part for g,(part,_) in parts.items() if g in enabled]
    used={g:n for g,(_,n) in parts.items() if g in enabled and n}
    return (sum(distances)/len(distances),used) if distances else (float('inf'),{})


def normalize(weights):
    total=sum(weights.values())
    return {key:value/total for key,value in weights.items()} if total>0 else {}


def plackett_luce(scores,temperature=1.0):
    strengths=[math.exp(max(-4,min(4,(3.5-s)*temperature))) for s in scores]
    total=sum(strengths);result={}
    for a,b,c in itertools.permutations(range(6),3):
        result[f'{a+1}-{b+1}-{c+1}']=strengths[a]/total*strengths[b]/(total-strengths[a])*strengths[c]/(total-strengths[a]-strengths[b])
    return normalize(result)


def predict(features,venue,day,model,odds=None):
    phase='preview' if all('展示進入' in f.get('start',{}) and '展示タイム相対' in f.get('exhibition',{}) for f in features) else 'partial' if any(f.get(g) for f in features for g in ('exhibition','start','weather','original')) else 'initial'
    pool_phase='preview' if all('展示進入' in f.get('start',{}) for f in features) else 'initial'
    pool=[s for s in model.get('samples',[]) if s.get('phase',pool_phase)==pool_phase];normalizers=model.get('scales',{})
    scores=[];evidence=[];used=defaultdict(set);used_lanes=defaultdict(set)
    for lane,f in enumerate(features,1):
        course=int(f.get('start',{}).get('展示進入',lane))
        if not 1<=course<=6:course=lane
        candidates=[s for s in pool if s['venue']==venue and s['course']==course and s['date']<day]
        learned_f={g:{k:v for k,v in fields.items() if g+'|'+k in normalizers} for g,fields in f.items()} if normalizers else f
        ranked=[]
        for sample in candidates:
            cache=model.get('_distance_cache')
            if cache is None:d,groups=distance(learned_f,sample['features'],normalizers,model.get('enabled_groups'))
            else:
                key=(lane,id(sample))
                if key not in cache:cache[key]=distance_parts(learned_f,sample['features'],normalizers)
                enabled=set(model.get('enabled_groups') or ALL_GROUPS);parts=cache[key]
                distances=[v for g,(v,_) in parts.items() if g in enabled]
                d=sum(distances)/len(distances) if distances else float('inf')
                groups={g:n for g,(_,n) in parts.items() if g in enabled and n}
            if math.isfinite(d):ranked.append((d,sample,groups))
        ranked.sort(key=lambda x:(x[0],x[1]['date'],x[1]['code']))
        neighbours=ranked[:32]
        # Use a conservative baseline if a venue/course has insufficient history.
        if len(neighbours)<8:
            prior=candidates or [s for s in pool if s['course']==course and s['date']<day]
            score=sum(s['finish'] for s in prior)/len(prior) if prior else 3.5
            evidence.append({'lane':lane,'course':course,'neighbours':len(neighbours),'status':'historical_sample_insufficient'})
        else:
            weights=[math.exp(-d) for d,_,_ in neighbours]
            total=sum(weights)
            score=sum(w*s['finish'] for w,(_,s,_) in zip(weights,neighbours))/total
            for _,sample,groups in neighbours:
                for group in groups:
                    used_lanes[group].add(lane)
                    for key in set(f.get(group,{}))&set(sample['features'].get(group,{})):used[group].add(key)
            evidence.append({'lane':lane,'course':course,'neighbours':len(neighbours),
                'status':'context_used','mean_finish_estimate':score,
                'neighbour_dates':sorted({s['date'] for _,s,_ in neighbours})})
        # Unlearned commentary/tide/maintenance rules have no numerical effect.
        evidence[-1]['research_rules']=[]
        scores.append(score)
    context=plackett_luce(scores,model.get('temperature',1.0))
    valid_odds={c:number((odds or {}).get('3連単_'+c)) for c in COMBOS}
    market=normalize({c:1/o for c,o in valid_odds.items() if o and o>0})
    complete_market=len(market)==120
    alpha=model.get('market_alpha',.25) if complete_market and phase in ('preview','partial') else 0
    p=normalize({c:(1-alpha)*context[c]+alpha*market.get(c,0) for c in COMBOS})
    cal=model.get('phase_calibration',{}).get(phase,{})
    calibration_applied=bool(cal.get('temperature') and bool(alpha>0)==bool(cal.get('requires_market')))
    if calibration_applied:
        p=normalize({k:max(v,1e-12)**(1/cal['temperature']) for k,v in p.items()})
    probability_verified=calibration_applied and cal.get('display_approved',False) and cal.get('venue_test_races',{}).get(str(venue),0)>=20 and all(e['neighbours']>=8 for e in evidence)
    audit={}
    for group in ALL_GROUPS:
        available=sorted({k for f in features for k in f.get(group,{})})
        active=sorted(used.get(group,set()))
        status='used' if active else 'historical_sample_insufficient' if available else 'missing'
        if available and not active and model.get('enabled_groups') and group not in model['enabled_groups'] and any(group+'|'+k in normalizers for k in available):status='shadow'
        audit[group]={'label':LABELS[group],'status':status,'available_fields':available,'used_fields':active,
                      'available_lanes':sum(bool(f.get(group)) for f in features),'used_lanes':len(used_lanes[group]),
                      'field_coverage':{k:sum(k in f.get(group,{}) for f in features) for k in available},
                      'unused_fields':sorted(set(available)-set(active)),
                      'method':'prior_date_context_only'}
    if alpha==1:
        for item in audit.values():
            item['status']='not_contributing_market_only';item['used_fields']=[];item['used_lanes']=0;item['unused_fields']=item['available_fields']
    audit['odds']={'label':LABELS['odds'],'status':'used' if alpha>0 else 'partial' if market else 'missing',
                   'valid_combinations':len(market),'market_blend':alpha,
                   'weight_origin':model.get('market_alpha_origin','preset_unvalidated')}
    from boat24_water import PROFILES
    profile=PROFILES.get(str(venue),{})
    audit['tide']['label']=profile.get('name','当該場')+'の潮汐推算'
    audit['wind']['label']=profile.get('name','当該場')+'の風とコース別実績'
    if profile.get('tidal_range')=='なし':
        audit['tide'].update(status='not_applicable',reason='公式の場データで干満差なし',used_fields=[],used_lanes=0)
    if not audit['comments']['available_fields']:
        audit['comments']['reason']='公式コメントの掲載・日付と登録番号の照合・取得を確認できていません'
    for item in audit.values():
        if item['status']=='used' and (item.get('unused_fields') or item.get('used_lanes',6)<item.get('available_lanes',6)):item['status']='partial_used'
    selection={str(n):sorted(p,key=lambda c:(-p[c],c))[:n] for n in (12,18)}
    metrics={}
    for n,picks in selection.items():
        os=[valid_odds[c] for c in picks]
        metrics[n]={'estimated_hit_probability':sum(p[c] for c in picks),
            'synthetic_odds':1/sum(1/o for o in os) if all(o and o>0 for o in os) else None,
            'flat_stake_expected_roi':sum(p[c]*valid_odds[c] for c in picks)/len(picks) if all(o and o>0 for o in os) else None}
    return {'phase':phase,'probability_verified':probability_verified,'calibration_applied':calibration_applied,'calibration_evidence':cal,'model':VERSION,'probabilities':p,'selection':selection,'market_metrics':metrics,
            'feature_usage':audit,'neighbour_evidence':evidence,
            'model_trained_through':model.get('trained_through'),
            'complete_inputs':all(audit[g]['status']=='used' for g in ('exhibition','start','weather','motor_history','odds')),
            'decision':'見送り（総合モデルは未校正・収益性未検証）'}


def fingerprint(features,odds,model,extra=None):
    value={'features':features,'odds':odds,'extra':extra,'version':VERSION,'trained_through':model.get('trained_through'),'model_id':model.get('model_id')}
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
