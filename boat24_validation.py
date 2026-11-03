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
 cut=len(dates)//3 if len(dates)>=9 else len(dates)//2
 tune_dates=dates[:cut];calibration_dates=dates[cut:2*cut] if len(dates)>=9 else [];test_dates=dates[2*cut:] if calibration_dates else dates[cut:]
 vm=dict(model);vm['scales']=scales([s for s in model['samples'] if s['date']<tune_dates[0]])
 def observations(part,cap=90):
  for c in balanced(part,cap=cap):
   base=predict(c['features'],c['venue'],c['date'],vm,{})
   if any(e['neighbours']<8 for e in base['neighbour_evidence']):continue
   odds={k:number(c['odds'].get('3連単_'+k)) for k in COMBOS}
   if any(v is None or v<=0 for v in odds.values()):continue
   z=sum(1/v for v in odds.values());market={k:1/v/z for k,v in odds.items()}
   yield c,[e.get('mean_finish_estimate',3.5) for e in base['neighbour_evidence']],market
 calibration=list(observations([c for c in cases if c['date'] in calibration_dates]))
 tune=list(observations([c for c in cases if c['date'] in tune_dates]));test=list(observations([c for c in cases if c['date'] in test_dates],cap=480))
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
 alpha=model['market_alpha']
 def distribution(scores,market):
  base=plackett_luce(scores,model['temperature']);return {k:(1-alpha)*base[k]+alpha*market[k] for k in COMBOS}
 def calibrated(p,t):
  weights={k:max(v,1e-12)**(1/t) for k,v in p.items()};z=sum(weights.values());return {k:v/z for k,v in weights.items()}
 candidates=(.7,.85,1.,1.15,1.35,1.6,2.,2.5,3.)
 ct=min(candidates,key=lambda t:sum(-math.log(max(calibrated(distribution(scores,m),t)[c['actual']],1e-12)) for c,scores,m in calibration)) if len(calibration)>=60 else None
 cbins=defaultdict(lambda:{'races':0,'hits':0,'sum_probability':0});cal_loss=0.;raw_loss=0.
 for c,scores,m in test:
  raw=distribution(scores,m);p=calibrated(raw,ct or 1.);picks=sorted(p,key=lambda k:-p[k])[:12];prob=sum(p[k] for k in picks);b=cbins[str(min(9,int(prob*10)))];b['races']+=1;b['hits']+=c['actual'] in picks;b['sum_probability']+=prob
  cal_loss-=math.log(max(p[c['actual']],1e-12));raw_loss-=math.log(max(raw[c['actual']],1e-12))
 ece=sum(abs(b['hits']-b['sum_probability']) for b in cbins.values())/len(test) if test else None
 approved=bool(ct and len(test)>=90 and len(calibration_dates)>=3 and len(test_dates)>=3 and cal_loss<=raw_loss and ece<=.10)
 venue_counts={str(v):sum(c['venue']==v for c,_,_ in test) for v in range(1,25)}
 model.setdefault('phase_calibration',{})['preview']={'venue_test_races':venue_counts,'temperature':ct,'requires_market':True,'display_approved':approved,'calibration_dates':calibration_dates,'test_dates':test_dates,'calibration_races':len(calibration),'test_races':len(test),'test_top12_ece':ece,'test_calibrated_logloss':cal_loss/len(test) if test else None,'warning':'Short historical validation; profitability is not established.'}
 bins=defaultdict(lambda:{'races':0,'hits':0,'sum_probability':0})
 for c,scores,m in test:
  p=plackett_luce(scores,model['temperature'])
  combined={k:(1-alpha)*p[k]+alpha*m[k] for k in COMBOS};picks=sorted(combined,key=lambda k:(-combined[k],k))[:12];prob=sum(combined[k] for k in picks);key=str(min(9,int(prob*10)))
  b=bins[key];b['races']+=1;b['hits']+=c['actual'] in picks;b['sum_probability']+=prob
 final={'context':loss(test,0,model['temperature']),'market':loss(test,1,model['temperature']),'selected':loss(test,alpha,model['temperature'])}
 return {'status':'three_block_calibrated_validation' if ct else 'independent_chronological_test_not_calibrated','calibration_dates':calibration_dates,'calibration_races':len(calibration),'calibrated_top12_reliability_bins':dict(cbins),'probability_display_approved':approved,'tuning_dates':tune_dates,'test_dates':test_dates,'tuning_races':len(tune),'test_races':len(test),'selected_alpha':alpha,'selected_temperature':model['temperature'],'tuning_mean_logloss':tuning,'test_mean_logloss':final,'top12_reliability_bins':dict(bins),'context_beats_market_on_test':final['context']<final['market'] if test else None,'warning':'Final-test results did not select weights. One short test does not establish accuracy or profitability.'}

def validate_initial(model,cases):
 """Separate exhibition-free calibration. Never borrow pre-close market odds."""
 dates=sorted({c['date'] for c in cases});out={'display_approved':False,'requires_market':False,'temperature':None}
 if len(dates)<9:return out
 cut=len(dates)//3;blocks=[dates[:cut],dates[cut:2*cut],dates[2*cut:]];vm=dict(model,market_alpha=0,phase_calibration={});vm['scales']=scales([s for s in model['samples'] if s['date']<blocks[0][0]])
 rows=[]
 for block_index,days in enumerate(blocks):
  part=[]
  for c in balanced([c for c in cases if c['date'] in days],cap=480 if block_index==2 else 90):
   prediction=predict(c['features'],c['venue'],c['date'],vm,{})
   if all(e['neighbours']>=8 for e in prediction['neighbour_evidence']):part.append((c,prediction['probabilities']))
  rows.append(part)
 def transform(p,t):
  q={k:max(v,1e-12)**(1/t) for k,v in p.items()};z=sum(q.values());return {k:v/z for k,v in q.items()}
 # The first block reports development coverage; calibration uses only block two.
 temp=min((.7,.85,1.,1.15,1.35,1.6,2.,2.5,3.),key=lambda t:sum(-math.log(max(transform(p,t)[c['actual']],1e-12)) for c,p in rows[1])) if len(rows[1])>=60 else None
 bins=defaultdict(lambda:{'races':0,'hits':0,'sum_probability':0});loss=raw=0.
 for c,p in rows[2]:
  q=transform(p,temp or 1);picks=sorted(q,key=lambda k:-q[k])[:12];prob=sum(q[k] for k in picks);b=bins[str(min(9,int(prob*10)))];b['races']+=1;b['hits']+=c['actual'] in picks;b['sum_probability']+=prob
  loss-=math.log(max(q[c['actual']],1e-12));raw-=math.log(max(p[c['actual']],1e-12))
 n=len(rows[2]);ece=sum(abs(b['hits']-b['sum_probability']) for b in bins.values())/n if n else None
 return {**out,'venue_test_races':{str(v):sum(c['venue']==v for c,_ in rows[2]) for v in range(1,25)},'temperature':temp,'display_approved':bool(temp and n>=90 and loss<=raw and ece<=.10),'development_dates':blocks[0],'calibration_dates':blocks[1],'test_dates':blocks[2],'calibration_races':len(rows[1]),'test_races':n,'test_top12_ece':ece,'test_calibrated_logloss':loss/n if n else None,'top12_reliability_bins':dict(bins)}

def ablation_report(model,cases,test_dates):
 """Fixed final-period diagnostics only, never used to choose weights."""
 import copy
 rows=balanced([c for c in cases if c['date'] in test_dates],cap=24);totals=defaultdict(float)
 vm=dict(model,phase_calibration={});vm['scales']=scales([s for s in model['samples'] if s['date']<min(test_dates)]) if test_dates else {}
 for c in rows:
  for group in ('none','behavior','motor_history','course','race_conditions','wind','tide'):
   features=copy.deepcopy(c['features'])
   if group!='none':
    for f in features:f[group]={}
   p=predict(features,c['venue'],c['date'],vm,c['odds'])['probabilities'];totals[group]-=math.log(max(p[c['actual']],1e-12))
 return {'races':len(rows),'dates':test_dates,'mean_logloss':{k:v/len(rows) for k,v in totals.items()} if rows else {},'note':'none = full model; each other key removes that feature family. Fixed held-out diagnostics, not a guarantee of improvement; not used to select weights.'}
