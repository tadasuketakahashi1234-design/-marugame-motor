"""Compile one held-out race once for exact feature-family ablations."""
import math

def compile_case(model,case):
    from boat24_context import ALL_GROUPS,plackett_luce,normalize,number,COMBOS
    features=case['features'];day=case['date'];venue=case['venue'];normalizers=model.get('scales',{})
    preview=all('展示進入' in f.get('start',{}) for f in features)
    phase='preview' if preview and all('展示タイム相対' in f.get('exhibition',{}) for f in features) else 'partial' if any(f.get(g) for f in features for g in ('exhibition','start','weather','original')) else 'initial'
    pool=[s for s in model.get('samples',[]) if s.get('phase','preview' if preview else 'initial')==('preview' if preview else 'initial') and s['date']<day]
    compiled=[]
    for lane,f in enumerate(features,1):
        course=int(f.get('start',{}).get('展示進入',lane));course=course if 1<=course<=6 else lane
        candidates=[s for s in pool if s['venue']==venue and s['course']==course];items=[]
        a={g:{k:v for k,v in values.items() if g+'|'+k in normalizers} for g,values in f.items()} if normalizers else f
        for s in candidates:
            b=s['features'];parts={};terms={}
            for group in ALL_GROUPS:
                values=[];terms[group]={}
                for key,value in a.get(group,{}).items():
                    other=b.get(group,{}).get(key)
                    term=1. if other is None else float(value!=other) if group=='weather' and key in ('風向','天候') else min(9,((value-other)/normalizers.get(group+'|'+key,1))**2)
                    values.append(term);terms[group][key]=term
                if values:parts[group]=sum(values)/len(values)
            items.append((s,parts,terms))
        fallback=candidates or [s for s in pool if s['course']==course]
        compiled.append((items,sum(s['finish'] for s in fallback)/len(fallback) if fallback else 3.5))
    odds={c:number(case.get('odds',{}).get('3連単_'+c)) for c in COMBOS}
    market=normalize({c:1/v for c,v in odds.items() if v and v>0});alpha=model.get('market_alpha',.25) if len(market)==120 and phase in ('preview','partial') else 0
    prepared={}
    def predict(groups,drop_field=None):
        key=tuple(sorted(groups))
        if key not in prepared:
            allowed=set(groups)
            prepared[key]=[([(s,sum(v for g,v in parts.items() if g in allowed),sum(g in allowed for g in parts),parts,terms) for s,parts,terms in items],fallback) for items,fallback in compiled]
        scores=[]
        for items,fallback in prepared[key]:
            ranked=[]
            for sample,total,count,parts,terms in items:
                if drop_field:
                    group,field=drop_field
                    if group in key and field in terms.get(group,{}):
                        n=len(terms[group]);total-=parts[group]
                        if n>1:total+=(parts[group]*n-terms[group][field])/(n-1)
                        else:count-=1
                if count:ranked.append((total/count,sample))
            ranked.sort(key=lambda x:(x[0],x[1]['date'],x[1]['code']));ranked=ranked[:32]
            if len(ranked)<8:scores.append(fallback)
            else:
                weights=[math.exp(-d) for d,_ in ranked];scores.append(sum(w*s['finish'] for w,(_,s) in zip(weights,ranked))/sum(weights))
        context=plackett_luce(scores,model.get('temperature',1.))
        return normalize({c:(1-alpha)*context[c]+alpha*market.get(c,0) for c in COMBOS})
    return predict
