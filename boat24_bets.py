"""Deterministic bounded search for 12 tickets; 100-yen paper allocations."""
import math

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
