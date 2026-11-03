"""Separate chronological tuning and final testing; no forced nonzero weights."""
import math
from collections import defaultdict
from boat24_context import predict,scales,COMBOS,number,plackett_luce

def balanced(cases,cap=90):
 buckets=defaultdict(list)
 for c in cases:buckets[(c['date'],c['venue'])].append(c)
 out=[];keys=sorted(buckets)
 while keys and len(out)<cap:
  next_keys=[]
  for k in keys:
   if len(out)>=cap:break
   if buckets[k]:out.append(buckets[k].pop(0))
   if buckets[k]:next_keys.append(k)
  keys=next_keys
 return out

def validate_chronologically(model,cases):
 dates=sorted({c['date'] for c in cases})
 model['temperature']=1.;model['market_alpha']=0.;model['market_alpha_origin']='not_fitted_context_only'
 if len(dates)<4:return {'status':'insufficient_distinct_dates','dates':dates}
 cut=len(dates)//2;tune_dates=dates[:cut];test_dates=dates[cut:]
 vm=dict(model);vm['scales']=scales([s for s in model['samples'] if s['date']<tune_dates[0]])
 def observations(part):
  for c in balanced(part):
   base=predict(c['features'],c['venue'],c['date'],vm,{})
   if any(e['neighbours']<8 for e in base['neighbour_evidence']):continue
   odds={k:number(c['odds'].get('3連単_'+k)) for k in COMBOS}
   if any(v is None or v<=0 for v in odds.values()):continue
   z=sum(1/v for v in odds.values());market={k:1/v/z for k,v in odds.items()}
   yield c,[e.get('mean_finish_estimate',3.5) for e in base['neighbour_evidence']],market
 tune=list(observations([c for c in cases if c['date'] in tune_dates]));test=list(observations([c for c in cases if c['date'] in test_dates]))
 grid=(0,.25,.5,.75,1);temperatures=(.5,1.,2.)
 def loss(rows,alpha,temp):
  if not rows:return None
  total=0.
  for c,scores,market in rows:
   p=plackett_luce(scores,temp)
   total-=math.log(max((1-alpha)*p[c['actual']]+alpha*market[c['actual']],1e-12))
  return total/len(rows)
 tuning={f'{temp}|{a}':loss(tune,a,temp) for temp in temperatures for a in grid}
 if len(tune)>=30:
  temp,alpha=min(((t,a) for t in temperatures for a in grid),key=lambda pair:tuning[f'{pair[0]}|{pair[1]}'])
  model['temperature']=temp;model['market_alpha']=alpha;model['market_alpha_origin']='chronological_tuning_only'
 alpha=model['market_alpha'];bins=defaultdict(lambda:{'races':0,'hits':0,'sum_probability':0})
 for c,scores,m in test:
  p=plackett_luce(scores,model['temperature'])
  combined={k:(1-alpha)*p[k]+alpha*m[k] for k in COMBOS};picks=sorted(combined,key=lambda k:(-combined[k],k))[:12];prob=sum(combined[k] for k in picks);key=str(min(9,int(prob*10)))
  b=bins[key];b['races']+=1;b['hits']+=c['actual'] in picks;b['sum_probability']+=prob
 final={'context':loss(test,0,model['temperature']),'market':loss(test,1,model['temperature']),'selected':loss(test,alpha,model['temperature'])}
 return {'status':'independent_chronological_test_not_calibrated','tuning_dates':tune_dates,'test_dates':test_dates,'tuning_races':len(tune),'test_races':len(test),'selected_alpha':alpha,'selected_temperature':model['temperature'],'tuning_mean_logloss':tuning,'test_mean_logloss':final,'top12_reliability_bins':dict(bins),'context_beats_market_on_test':final['context']<final['market'] if test else None,'warning':'Final-test results did not select weights. One short test does not establish accuracy or profitability.'}
