"""Promotion evidence from public frozen, variable-stake paper portfolios only."""
import math,copy
from collections import defaultdict,Counter
from boat24_learning import frozen_cases,digest,POLICY_ID
from boat24_decisions import outcome
from boat24_integrity import timeparse
from boat24_settlement import amounts

def paired_frozen_report(records,decisions):
    from boat24_experiments import day_interval
    cases,audit=frozen_cases(records,decisions);groups=defaultdict(list);excluded=Counter()
    for c in cases:
        s=c['snapshot'];saved=s.get('research',{}).get('decision_arms',{});fixed=c['decision'].get('paired',{})
        if digest(saved)!=digest(fixed) or set(fixed.get('arms',{}))!={'baseline','candidate'}:
            excluded['arms_missing_or_not_frozen']+=1;continue
        row={'date':c['date'],'code':c['race_code'],'venue':c['venue'],'freeze_at':c['provenance']['freeze_at']};valid=True
        for name,arm in fixed['arms'].items():
            state,reason=outcome({**s,'purchase_plan':arm['plan']},timeparse(row['freeze_at']))
            probs=arm.get('probabilities',{})
            if state not in ('buy','skip') or not probs or any(not isinstance(p,(int,float)) or not math.isfinite(p) or p<0 for p in probs.values()) or abs(sum(probs.values())-1)>1e-6:
                valid=False;break
            plan=arm['plan'];paper=amounts(plan['tickets'],c['result']['winning_trifectas'] or {c['result']['combo']:c['result']['payout_100yen']},[]) if state=='buy' else {'stake':0,'return':0,'profit':0,'hit':False}
            row[name]={'state':state,'paper':paper,'loss':-math.log(max(probs.get(c['result']['combo'],0),1e-12)),
                       'selected_probability':sum(probs.get(t['combo'],0) for t in plan.get('tickets',[])) if state=='buy' else None}
        if not valid:excluded['arms_not_comparable']+=1;continue
        groups[c['phase']].append(row)
    reports=[]
    for phase in ('initial','preview'):
        rows=sorted(groups[phase],key=lambda r:(r['freeze_at'],r['code']));n=len(rows);days=len({r['date'] for r in rows});models={}
        for name in ('baseline','candidate'):
            stake=returned=hits=buys=gami=equity=peak=dd=streak=longest=0;bins=defaultdict(lambda:[0,0,0.])
            for r in rows:
                z=r[name];p=z['paper'];stake+=p['stake'];returned+=p['return'];hits+=int(p['hit']);equity+=p['profit'];peak=max(peak,equity);dd=max(dd,peak-equity)
                if z['state']=='buy':
                    buys+=1;gami+=int(p['hit'] and p['profit']<0);streak=streak+1 if p['profit']<0 else 0;longest=max(longest,streak)
                    prob=z['selected_probability'];b=bins[min(9,int(prob*10))];b[0]+=1;b[1]+=int(p['hit']);b[2]+=prob
            models[name]={'races':n,'purchases':buys,'skips':n-buys,'hits':hits,'stake':stake,'return':returned,'profit':returned-stake,
                          'roi':returned/stake if stake else None,'logloss':sum(r[name]['loss'] for r in rows)/n if n else None,
                          'ece':sum(abs(v[1]-v[2]) for v in bins.values())/buys if buys else None,'bins':dict(bins),
                          'gami':gami,'maximum_drawdown':dd,'longest_loss_streak':longest}
        ci=day_interval([(r['date'],r['candidate']['loss']-r['baseline']['loss']) for r in rows]);a=models['candidate'];b=models['baseline']
        checks={'races':n>=400,'days':days>=14,'purchases':a['purchases']>=100,
                'loss_improvement':bool(ci and ci[1]<0),'positive_roi':a['roi'] is not None and a['roi']>1,
                'not_worse_roi':a['roi'] is not None and (b['roi'] is None or a['roi']>=b['roi']),
                'positive_profit':a['profit']>0 and a['profit']>=b['profit'],
                'selected_portfolio_calibration':a['ece'] is not None and a['ece']<=.1 and (b['ece'] is None or a['ece']<=b['ece']),'no_realized_gami':a['gami']==0}
        approved=all(checks.values());support={str(v):{'races':sum(r['venue']==v for r in rows),'days':len({r['date'] for r in rows if r['venue']==v})} for v in range(1,25)}
        reports.append({'phase':phase,'races':n,'days':days,'models':models,'loss_delta_interval95':ci,'adoption_approved':approved,
                        'eligible_venues':[v for v,z in support.items() if approved and z['races']>=60 and z['days']>=5],
                        'venue_support':support,'required_races':400,'required_days':14,'required_purchases':100,'checks':checks,
                        'reason':'公開固定・可変配分の採用条件を充足' if approved else '公開固定・可変配分の採用条件を未達：'+','.join(k for k,v in checks.items() if not v)})
    return {'policy':POLICY_ID,'phase_reports':reports,'case_audit':audit,'comparison_exclusions':dict(excluded),
            'unit':'one publicly observed frozen race; identical pre-result controls; variable points and 100-yen stakes',
            'warning':'仮想収支。実購入の検証ではなく、標本増加や採用は利益保証ではありません。'}
