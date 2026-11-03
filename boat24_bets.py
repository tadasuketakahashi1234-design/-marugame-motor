"""Deterministic bounded search for 12 tickets; 100-yen paper allocations."""
import math

LEGACY_PURCHASE_POLICY='no-gami-equal-100-v1'
PURCHASE_POLICY='balanced-no-gami-v2'

def no_gami_plan(probabilities, odds, count=12):
 """Equal 100-yen tickets: every selected hit must return more than total stake.

 This is a quote-time payout constraint, not a claim about expected value.
 Never replace missing/ineligible tickets with longshots just to fill the list.
 """
 from decimal import Decimal, InvalidOperation, ROUND_FLOOR
 from boat24_integrity import valid_combo
 budget=count*100
 base={'policy':LEGACY_PURCHASE_POLICY,'status':'odds_incomplete','budget':budget,
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


def _balanced_fixed_budget(probabilities,odds,budget=1200,frontier_limit=256):
 """Compare variable ticket counts and integer stakes on a Pareto frontier.

 Balance score = hit probability * (estimated ROI - 1). Positive estimated
 edge and a strictly positive quote-time profit on every hit are mandatory.
 The bounded frontier is an approximation; never claim a global optimum.
 """
 from decimal import Decimal,InvalidOperation,ROUND_FLOOR
 from boat24_integrity import valid_combo
 if not isinstance(budget,int) or budget<100 or budget%100 or budget>1200:
  raise ValueError('Budget must be 100..1200 yen in 100-yen units')
 if frontier_limit<2:raise ValueError('Frontier limit must retain both extremes')
 base={'policy':PURCHASE_POLICY,'status':'odds_incomplete','budget':budget,
       'budget_cap':budget,'tickets':[],'paper_only':True,'search_exact':True,
       'objective':'hit_probability_times_positive_expected_roi_excess',
       'probability_verified':False,'method':'bounded_pareto_integer_allocation'}
 quotes={}
 for c,value in odds.items():
  if not valid_combo(c):continue
  try:q=Decimal(str(value))
  except (InvalidOperation,ValueError):continue
  if q.is_finite() and q>0:quotes[c]=(float(q),int((q*10).to_integral_value(rounding=ROUND_FLOOR))*10)
 if len(quotes)!=120:return base
 try:ps={c:float(probabilities[c]) for c in quotes}
 except (KeyError,TypeError,ValueError):return dict(base,status='probabilities_invalid')
 if any(not math.isfinite(p) or p<0 or p>1 for p in ps.values()) or abs(sum(ps.values())-1)>1e-6:
  return dict(base,status='probabilities_invalid')
 if max(ps[c]*pay/100 for c,(_,pay) in quotes.items())<=1+1e-12:
  return dict(base,status='no_positive_value')
 units=budget//100;states=[[] for _ in range(units+1)];states[0]=[(0.,0.,())]
 truncated=False
 def prune(rows):
  nonlocal truncated
  # At equal stake, higher coverage and higher expected payout dominate.
  rows.sort(key=lambda r:(-r[0],-r[1],r[2]));out=[];best=-1.
  for row in rows:
   if row[1]>best+1e-9:out.append(row);best=row[1]
  if len(out)>frontier_limit:
   truncated=True
   indices={round(i*(len(out)-1)/(frontier_limit-1)) for i in range(frontier_limit)}
   out=[out[i] for i in sorted(indices)]
  return out
 for c in sorted(quotes,key=lambda c:(-ps[c],c)):
  q,pay=quotes[c];p=ps[c]
  if pay<=0 or p<=0:continue
  minimum=budget//pay+1
  if minimum>units:continue
  previous=states;states=[list(rows) for rows in previous]
  for spent in range(minimum,units+1):
   for bet in range(minimum,spent+1):
    states[spent].extend((hit+p,expected+p*pay*bet,picks+((c,bet),)) for hit,expected,picks in previous[spent-bet])
   states[spent]=prune(states[spent])
 feasible=states[units]
 positive=[r for r in feasible if r[1]>budget+1e-9]
 if not positive:return dict(base,status='no_positive_value' if feasible else 'no_feasible_plan',search_exact=not truncated)
 hit,expected,picks=max(positive,key=lambda r:(r[0]*(r[1]/budget-1),r[0],r[1],r[2]))
 tickets=[{'combo':c,'stake':bet*100,'odds':quotes[c][0],
           'expected_return':quotes[c][1]*bet,'expected_profit':quotes[c][1]*bet-budget,
           'estimated_probability':ps[c]} for c,bet in sorted(picks,key=lambda x:(-ps[x[0]],x[0]))]
 # Recheck the integer constraints after selection, including rounding.
 assert sum(t['stake'] for t in tickets)==budget
 assert all(t['expected_profit']>0 for t in tickets)
 frontier=[{'count':len(picks),'estimated_hit_probability':h,'estimated_roi':e/budget,
            'balance_score':h*(e/budget-1)} for h,e,picks in positive]
 return dict(base,status='ready',tickets=tickets,count=len(tickets),
             search_exact=not truncated,frontier=frontier,
             estimated_hit_probability=hit,estimated_roi=expected/budget,
             estimated_profit=expected-budget,balance_score=hit*(expected/budget-1),
             minimum_hit_return=min(t['expected_return'] for t in tickets),
             minimum_hit_profit=min(t['expected_profit'] for t in tickets),
             synthetic_odds=1/sum(1/t['odds'] for t in tickets))


def balanced_plan(probabilities,odds,budget=1200,frontier_limit=256):
 """Budget is a cap, not a spending target; prefer less stake on equal scores."""
 maximum=_balanced_fixed_budget(probabilities,odds,budget,frontier_limit)
 if maximum['status'] in ('odds_incomplete','probabilities_invalid','no_positive_value'):
  return maximum
 plans=[_balanced_fixed_budget(probabilities,odds,b,frontier_limit) for b in range(100,budget,100)]+[maximum]
 ready=[p for p in plans if p['status']=='ready']
 if not ready:return maximum
 best=dict(max(ready,key=lambda p:(round(p['balance_score'],12),round(p['estimated_hit_probability'],12),round(p['estimated_roi'],12),-p['budget'])))
 best['budget_cap']=budget
 best['search_exact']=all(p['search_exact'] for p in plans)
 best['budgets_compared']=[p['budget'] for p in plans]
 by_count={}
 for plan in ready:
  for row in plan.get('frontier',[]):
   n=row['count'];candidate=dict(row,budget=plan['budget'])
   if n not in by_count or (candidate['balance_score'],-candidate['budget'])>(by_count[n]['balance_score'],-by_count[n]['budget']):by_count[n]=candidate
 best['comparison_by_count']=[by_count[n] for n in sorted(by_count)]
 return best

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
