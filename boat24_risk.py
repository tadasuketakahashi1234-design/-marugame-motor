"""Sensitivity-constrained allocations, distinct from statistical confidence."""
from decimal import Decimal,ROUND_FLOOR
import math
from boat24_bets import balanced_plan,PURCHASE_POLICY

POLICY='probability-price-stress-1'
PROTOCOL_ID='balanced-no-gami-v2-robust-1'

def validate_robust(plan):
    """Recompute stress and concentration at saving, independent of optimizer."""
    try:
        control=plan['risk_controls'];ph=control['probability_haircut'];qh=control['price_haircut'];cap=control['maximum_ticket_share']
        verified=plan.get('probability_verified') is True;budget=plan['budget'];tickets=plan['tickets']
        if plan.get('risk_policy')!=POLICY or not tickets or not isinstance(budget,int) or not 0<budget<=1200:return False
        if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (ph,qh,cap)):return False
        if not (.10 if verified else .20)<=ph<1 or not .10<=qh<1 or not 0<cap<=(.35 if verified else .25):return False
        if sum(t['stake'] for t in tickets)!=budget or len({t['combo'] for t in tickets})!=len(tickets):return False
        total=0.;mass=0.
        for t in tickets:
            p=t['estimated_probability'];q=t['odds'];stake=t['stake']
            if not isinstance(stake,int) or stake<100 or stake%100 or stake>budget*cap+1e-9:return False
            if not all(isinstance(v,(int,float)) and math.isfinite(v) for v in (p,q)) or not 0<=p<=1 or q<=0:return False
            sq=(Decimal(str(q))*Decimal(str(1-qh))).quantize(Decimal('.1'),rounding=ROUND_FLOOR)
            pay=int(sq*10)*10*(stake//100)
            if pay<=budget:return False
            total+=p*(1-ph)*pay;mass+=p
        return mass<=1+1e-6 and total>budget and math.isclose(total/budget,plan['stress_expected_roi'],rel_tol=1e-8,abs_tol=1e-8)
    except (KeyError,TypeError,ValueError,ArithmeticError):return False

def robust_plan(probabilities,odds,*,verified=False,inputs_ready=True):
    probability_haircut=.10 if verified else .20
    price_haircut=.10
    cap=.35 if verified else .25
    controls={'policy':POLICY,'probability_haircut':probability_haircut,'price_haircut':price_haircut,
              'maximum_ticket_share':cap,'probability_verified':bool(verified),
              'interpretation':'感度条件。統計的な信頼区間・利益保証ではありません。'}
    base={'policy':PURCHASE_POLICY,'risk_policy':POLICY,'protocol_id':PROTOCOL_ID,'risk_controls':controls,
          'budget_cap':1200,'tickets':[],'paper_only':True,'probability_verified':bool(verified)}
    if not inputs_ready:return dict(base,status='preview_pending',reason='全6艇の展示・進入・符号付き展示STが揃っていません')
    if not probabilities or any(not isinstance(p,(int,float)) or not math.isfinite(p) or p<0 or p>1 for p in probabilities.values()) or abs(sum(probabilities.values())-1)>1e-6:
        return dict(base,status='probabilities_invalid')
    # Individual lower bounds can sum to less than one. The residual ambiguity
    # mass is unallocated; never renormalize it back into the selected bets.
    conservative={c:p*(1-probability_haircut) for c,p in probabilities.items()}
    stressed={}
    for c,value in odds.items():
        try:
            q=Decimal(str(value))
            stressed[c]=float((q*Decimal(str(1-price_haircut))).quantize(Decimal('.1'),rounding=ROUND_FLOOR)) if q.is_finite() and q>0 else None
        except Exception:stressed[c]=None
    plan={**balanced_plan(conservative,stressed,max_ticket_share=cap,lower_probability_bounds=True),**{k:v for k,v in base.items() if k not in ('tickets',)}}
    plan['comparison_basis']='probability_and_price_stress'
    if plan['status']!='ready':
        if plan['status'] in ('no_positive_value','no_feasible_plan'):plan['status']='risk_'+plan['status']
        return plan
    plan['stress_expected_roi']=plan['estimated_roi'];plan['stress_hit_probability']=plan['estimated_hit_probability']
    plan['stress_minimum_hit_return']=plan['minimum_hit_return']
    for t in plan['tickets']:
        c=t['combo'];t['stress_return']=t['expected_return'];t['stress_probability_bound']=conservative[c]
        t['odds']=float(odds[c]);t['estimated_probability']=probabilities[c]
        t['expected_return']=math.floor((t['odds']+1e-9)*10)*10*(t['stake']//100)
        t['expected_profit']=t['expected_return']-plan['budget']
    plan['estimated_roi']=sum(t['estimated_probability']*t['expected_return'] for t in plan['tickets'])/plan['budget']
    plan['estimated_hit_probability']=sum(t['estimated_probability'] for t in plan['tickets'])
    plan['estimated_profit']=plan['budget']*(plan['estimated_roi']-1)
    plan['minimum_hit_return']=min(t['expected_return'] for t in plan['tickets'])
    plan['minimum_hit_profit']=plan['minimum_hit_return']-plan['budget']
    plan['synthetic_odds']=1/sum(1/t['odds'] for t in plan['tickets'])
    assert max(t['stake'] for t in plan['tickets'])<=plan['budget']*cap+1e-9
    assert plan['stress_minimum_hit_return']>plan['budget'] and plan['stress_expected_roi']>1
    assert validate_robust(plan)
    return plan
