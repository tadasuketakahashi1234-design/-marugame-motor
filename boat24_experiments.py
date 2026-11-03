from boat24_history_io import day_paths,day_key,read_history
"""Paired temporal experiments in the same product and immutable race history."""
import copy
import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path
from boat24_integrity import timeparse

POLICY='paired-forward-1'

def day_interval(rows,repeats=400):
    """Paired day-cluster bootstrap; not a guarantee or an IID-race interval."""
    groups=defaultdict(list)
    for day,delta in rows:groups[day].append(delta)
    days=sorted(groups)
    if len(days)<3:return None
    rng=random.Random(20261103);means=[]
    for _ in range(repeats):
        sample=[rng.choice(days) for _ in days];values=[v for d in sample for v in groups[d]]
        means.append(sum(values)/len(values))
    means.sort();return [means[int(.025*repeats)],means[min(repeats-1,int(.975*repeats))]]

def historical_experiments(model,cases):
    """Temporal folds, all families ablated, fitted scales from preceding dates.

    Diagnostics only: these observed test results cannot promote a model.
    """
    from boat24_context import predict,scales,ALL_GROUPS
    from boat24_case_engine import compile_case
    ALL_GROUPS=tuple(g for g in ALL_GROUPS if g!='data_quality')
    from boat24_validation import balanced
    dates=sorted({c['date'] for c in cases});folds=[]
    # All final cases, balanced across date/venue, bounded at 120 for runner cost.
    test_dates=model.get('calibration',{}).get('test_dates',[])
    rows=balanced([c for c in cases if c['date'] in test_dates],cap=120)
    totals=defaultdict(float);coverage=defaultdict(int);per_day=defaultdict(list);field_totals=defaultdict(float);field_coverage=defaultdict(int);field_deltas=defaultdict(list)
    groups=[g for g in ALL_GROUPS if any(any(f.get(g) for f in c['features']) for c in rows)]
    # Case ablations use the same trained reference samples and normalization.
    # Exclusion from the distance is equivalent to refitting this nonparametric
    # model with that family removed. No fitted cross-feature weights exist.
    for day in sorted({c['date'] for c in rows}):
        vm=dict(model,phase_calibration={},scales=scales([s for s in model['samples'] if s['date']<day]),enabled_groups=list(ALL_GROUPS))
        subset=[c for c in rows if c['date']==day]
        for c in subset:
            compiled=compile_case(vm,c)
            p=compiled(ALL_GROUPS);full=-math.log(max(p[c['actual']],1e-12));totals['all_candidates']+=full
            baseline=compiled(model['enabled_groups']);base=-math.log(max(baseline[c['actual']],1e-12));totals['champion']+=base;per_day['candidate_delta'].append((day,full-base))
            for group in groups:
                if not any(f.get(group) for f in c['features']):continue
                q=compiled([g for g in ALL_GROUPS if g!=group]);loss=-math.log(max(q[c['actual']],1e-12));totals['without:'+group]+=loss;coverage[group]+=1
                per_day[group].append((day,full-loss))
            # Exact leave-one-field-out diagnostics for every available numeric
            # input, including each subdivided exhibition and comment aspect.
            for group in ALL_GROUPS:
                fields={k for f in c['features'] for k in f.get(group,{}) if group+'|'+k in vm['scales']}
                for field in sorted(fields):
                    q=compiled(ALL_GROUPS,(group,field));loss=-math.log(max(q[c['actual']],1e-12));key=group+'|'+field
                    field_totals[key]+=loss;field_coverage[key]+=1;field_deltas[key].append((day,full-loss))
        folds.append({'test_day':day,'races':len(subset),'training_through_before':day,'independent_races':len({c.get('code',str(i)) for i,c in enumerate(subset)})})
        print('Integrated temporal experiments',day,len(subset),'races;',len(field_totals),'fields',flush=True)
    n=len(rows)
    return {'policy':POLICY,'kind':'historical_reconstruction_diagnostics','races':n,'folds':folds,
            'mean_logloss':{k:v/(coverage[k[8:]] if k.startswith('without:') else n) for k,v in totals.items()} if n else {},
            'family_test_races':dict(coverage),'paired_day_interval95':{k:day_interval(v) for k,v in per_day.items()},
            'field_tests':{k:{'races':field_coverage[k],'mean_logloss_without':v/field_coverage[k],'mean_full_minus_without':sum(d for _,d in field_deltas[k])/field_coverage[k],'day_interval95':day_interval(field_deltas[k])} for k,v in field_totals.items()},
            'selection_basis':'fixed prior final period; no automatic promotion from this report',
            'source_warning':'CSV is a historical reconstruction; saved snapshot IDs identify actual captures. Unknown historical publication times remain a limitation.'}

def paired_report(records):
    rows=[];seen=set()
    for rec in records:
        result=rec.get('result') or {};actual=result.get('combo');money=result.get('payout_100yen')
        if not actual or not money or result.get('refund_boats'):continue
        snapshots=defaultdict(list)
        for s in rec.get('revisions',{}).values():
            r=s.get('research',{});t=timeparse(s.get('computed_at') or s.get('created_at'));cut=timeparse(s.get('cutoff'))
            if r.get('policy')!=POLICY or not s.get('evaluation_eligible') or not t or not cut or t>=cut:continue
            if r.get('baseline',{}).get('phase')!=r.get('candidate',{}).get('phase'):continue
            snapshots[s.get('phase')].append(s)
        for phase,options in snapshots.items():
            if phase not in ('initial','preview'):continue
            options.sort(key=lambda s:(s['created_at'],s['id']));s=options[0] if phase=='initial' else options[-1]
            key=(rec['race_code'],phase)
            if key in seen:continue
            seen.add(key);metrics={}
            for name in ('baseline','candidate'):
                p=s['research'][name];ps=p['probabilities'];picks=p['selection']['12'];hit=actual in picks
                metrics[name]={'loss':-math.log(max(ps.get(actual,0),1e-12)),'hit':hit,'prob':sum(ps[c] for c in picks),'stake':1200,'return':money if hit else 0}
            rows.append({'date':rec['date'],'venue':rec['venue'],'phase':phase,**metrics})
    out=[]
    for phase in ('initial','preview'):
        a=[r for r in rows if r['phase']==phase];n=len(a);days=len({r['date'] for r in a})
        delta=[(r['date'],r['candidate']['loss']-r['baseline']['loss']) for r in a];ci=day_interval(delta)
        models={}
        for name in ('baseline','candidate'):
            bins=defaultdict(lambda:[0,0.,0.])
            for r in a:
                m=r[name];b=bins[min(9,int(m['prob']*10))];b[0]+=1;b[1]+=m['hit'];b[2]+=m['prob']
            models[name]={'races':n,'hits':sum(r[name]['hit'] for r in a),'logloss':sum(r[name]['loss'] for r in a)/n if n else None,
                          'roi':sum(r[name]['return'] for r in a)/(n*1200) if n else None,
                          'ece':sum(abs(b[1]-b[2]) for b in bins.values())/n if n else None,
                          'bins':dict(bins)}
        # Conservative gate uses real saved paired forecasts, not reconstructed data.
        # One predeclared all-candidate comparison per phase avoids cherry-picking.
        approved=bool(n>=400 and days>=14 and ci and ci[1]<0 and models['candidate']['roi']>=models['baseline']['roi'] and models['candidate']['ece']<=models['baseline']['ece'] and models['candidate']['ece']<=.1)
        venue_support={str(v):{'races':sum(r['venue']==v for r in a),'days':len({r['date'] for r in a if r['venue']==v})} for v in range(1,25)}
        eligible_venues=[v for v,c in venue_support.items() if c['races']>=60 and c['days']>=5] if approved else []
        out.append({'phase':phase,'races':n,'days':days,'models':models,'loss_delta_interval95':ci,'adoption_approved':approved,'eligible_venues':eligible_venues,'venue_support':venue_support,
                    'required_races':400,'required_days':14,'reason':'事前保存の同時刻比較で審査' if approved else '標本数・日数・誤差改善区間・回収率・校正の採用条件を未達'})
    return {'policy':POLICY,'phase_reports':out,'unit':'one race per phase; same snapshot and odds',
            'warning':'Paper returns; promotion is not a guarantee of profit.'}

def prior_forward_evidence(today,directory=Path('omura/docs/full_history')):
    records=[]
    for p in day_paths(directory):
        if day_key(p)<today.isoformat():records+=list(read_history(p).get('records',{}).values())
    return paired_report(records)
