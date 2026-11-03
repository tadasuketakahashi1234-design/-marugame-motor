"""Deterministic bounded search for 12 tickets; 100-yen paper allocations."""
import math

PURCHASE_POLICY='no-gami-equal-100-v1'

def no_gami_plan(probabilities, odds, count=12):
 """Equal 100-yen tickets: every selected hit must return more than total stake.

 This is a quote-time payout constraint, not a claim about expected value.
 Never replace missing/ineligible tickets with longshots just to fill the list.
 """
 from decimal import Decimal, InvalidOperation, ROUND_FLOOR
 from boat24_integrity import valid_combo
 budget=count*100
 base={'policy':PURCHASE_POLICY,'status':'odds_incomplete','budget':budget,
       'stake_per_ticket':100,'count':count,'tickets':[],'paper_only':True}
 quotes={}
 for combo,value in odds.items():
  if not valid_combo(combo):continue
  try:q=Decimal(str(value))
  except (InvalidOperation,ValueError):continue
  if q.is_finite() and q>0:quotes[combo]=q
 if len(quotes)!=120:return base
 candidates=[]
 for combo,q in quotes.items():
  probability=probabilities.get(combo)
  if probability is None or not math.isfinite(probability) or probability<=0:continue
  payout=int((q*10).to_integral_value(rounding=ROUND_FLOOR))*10
  if payout>budget:candidates.append((combo,probability,q,payout))
 if len(candidates)<count:return dict(base,status='no_feasible_plan')
 chosen=sorted(candidates,key=lambda row:(-row[1],row[0]))[:count]
 tickets=[{'combo':c,'stake':100,'odds':float(q),'expected_return':p,'expected_profit':p-budget} for c,_,q,p in chosen]
 return dict(base,status='ready',tickets=tickets,
             minimum_hit_return=min(t['expected_return'] for t in tickets),
             minimum_hit_profit=min(t['expected_profit'] for t in tickets),
             synthetic_odds=1/sum(1/float(q) for _,_,q,_ in chosen))

def optimize(probabilities,odds,budget=2400,target=7.,count=12):
 valid={k:float(v) for k,v in odds.items() if v is not None and v>0}
 if len(valid)!=120:return {'status':'odds_incomplete','budget':budget,'target':target,'tickets':[]}
 if budget%100 or budget<count*100:raise ValueError('Budget must cover every ticket in 100-yen units')
 # Knapsack beam: maximize covered probability subject to inverse-odds <= 1/target.
 # Quantization bounds runtime. This is explicitly an approximate, not global, optimum.
 pool=sorted(valid,key=lambda k:(-probabilities[k],k));states=[{} for _ in range(count+1)];states[0][0]=(0.,0.,())
 for key in pool:
  cost=1/valid[key]
  for n in range(count,0,-1):
   for prob,spent,picks in list(states[n-1].values()):
    s=spent+cost
    if s>1/target+1e-12:continue
    bucket=math.ceil(s*20000);p=prob+probabilities[key];old=states[n].get(bucket)
    if old is None or p>old[0]:states[n][bucket]=(p,s,picks+(key,))
   if len(states[n])>350:states[n]=dict(sorted(states[n].items(),key=lambda kv:(-kv[1][0],kv[1][1]))[:350])
 feasible=list(states[count].values());fallback=sorted(pool,key=lambda k:(-valid[k],k))[:count]
 qualified=[s for s in feasible if s[0]/s[1]>=1.]
 picks=list(max(qualified or feasible,key=lambda s:s[0])[2]) if feasible else fallback
 units=budget//100;alloc={k:1 for k in picks}
 # Discrete dutching: allocate each next 100 yen to the smallest current return.
 for _ in range(units-count):
  k=min(picks,key=lambda k:(alloc[k]*valid[k],k));alloc[k]+=1
 stake=sum(alloc.values())*100;returns={k:alloc[k]*100*valid[k] for k in picks};minreturn=min(returns.values())
 return {'status':'target_feasible' if feasible else 'target_unreachable','method':'bounded_knapsack_approximation_then_discrete_dutching','budget':stake,'target':target,'tickets':[{'combo':k,'stake':alloc[k]*100,'odds':valid[k]} for k in sorted(picks,key=lambda k:-probabilities[k])], 'estimated_hit_probability':sum(probabilities[k] for k in picks),'synthetic_odds':1/sum(1/valid[k] for k in picks),'minimum_hit_return':minreturn,'maximum_hit_return':max(returns.values()),'rounded_minimum_return_multiple':minreturn/stake,'rounded_target_met':minreturn/stake>=target,'expected_roi':sum(probabilities[k]*returns[k] for k in picks)/stake,'continuous_expected_roi':sum(probabilities[k] for k in picks)/sum(1/valid[k] for k in picks),'positive_expected_value_candidate_found':bool(qualified),'paper_only':True}
