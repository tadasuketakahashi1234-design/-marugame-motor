"""Ticket-level paper settlement; forecasts stay immutable on corrections."""
import hashlib
import json
import copy
from boat24_integrity import valid_combo,timeparse

def refund_boats(result):
    from boat24_context import number
    if result.get('official_refund_verified') is True:
        values=result.get('official_refund_boats')
        if not isinstance(values,list) or any(str(v) not in '123456' or len(str(v))!=1 for v in values):raise ValueError('Invalid official refund boats')
        return sorted({str(v) for v in values})
    out=set()
    for course in range(1,7):
        lane=str(result.get(f'{course}コース_艇番',''));st=number(result.get(f'{course}コース_スタートタイミング'))
        flags=[str(result.get(f'{course}コース_{k}','')).strip().upper() for k in ('F','L')]
        if lane in '123456' and len(lane)==1 and (any(v in ('1','TRUE','F','L') for v in flags) or st is not None and st<0):out.add(lane)
    return sorted(out)

def amounts(tickets,winners,refunds):
    stake=returned=refunded=0
    for ticket in tickets:
        combo=ticket['combo'];bet=ticket['stake']
        if not valid_combo(combo) or not isinstance(bet,int) or bet<=0 or bet%100:raise ValueError('Invalid saved paper ticket')
        stake+=bet
        if set(combo.split('-'))&set(refunds):refunded+=bet
        elif combo in winners:returned+=bet//100*winners[combo]
    return {'stake':stake,'return':returned+refunded,'winnings':returned,'refund':refunded,
            'net_stake':stake-refunded,'hit':returned>0,'profit':returned+refunded-stake}

def canonical(res,pay):
    from boat24_context import number
    combo='-'.join(str(res.get(f'{i}着_艇番','')).strip() for i in (1,2,3))
    # Standard CSV proves one combination. Multiple winning combinations are
    # accepted only through an explicit, validated list, never guessed.
    rows=pay.get('winning_trifectas')
    winners={}
    if isinstance(rows,list):
        for row in rows:
            money=number(row.get('payout_100yen'));key=row.get('combo')
            if not valid_combo(key) or money is None or money<=0 or not money.is_integer():return None
            winners[key]=int(money)
        if not winners or combo not in winners:return None
    else:
        money=number(pay.get('3連単_払戻金'))
        if not valid_combo(combo) or pay.get('3連単_組番')!=combo or money is None or money<=0 or not money.is_integer():return None
        winners[combo]=int(money)
    refunds=refund_boats(res)
    if any(set(k.split('-'))&set(refunds) for k in winners):return None
    return {'combo':combo,'payout_100yen':winners[combo],'winning_trifectas':winners,'refund_boats':refunds}

def settle_record(rec,res,pay,snapshot,now):
    if not snapshot or not res or not pay or res.get('レースコード')!=rec['race_code'] or pay.get('レースコード')!=rec['race_code']:return False
    value=canonical(res,pay)
    if value is None:return False
    old=rec.get('result')
    # A temporary official-source outage must not erase a verified refund join.
    if old and old.get('refund_verified') and not res.get('official_refund_verified') and old.get('combo')==value['combo'] and old.get('winning_trifectas')==value['winning_trifectas']:
        res={**res,**{k:v for k,v in old.get('result_source',{}).items() if k.startswith('official_')}}
        value=canonical(res,pay)
        if value is None:return False
    from boat24_offers import register_offers
    from boat24_bets import PURCHASE_POLICY
    offers=register_offers(rec)
    purchase=offers[0] if offers else None
    purchase_id=purchase['snapshot_id'] if purchase else None
    value['refund_verified']=res.get('official_refund_verified') is True
    value['settlement_schema']=2
    value['offer_ids']=[o['snapshot_id'] for o in offers]
    label_values={k:v for k,v in res.items() if k.endswith('着_艇番') or k.startswith(tuple(str(i)+'コース_' for i in range(1,7))) or k in ('決まり手','official_finish_status')}
    result_id=hashlib.sha256(json.dumps([value,purchase_id,snapshot['id'],label_values],sort_keys=True).encode()).hexdigest()
    if old and old.get('id')==result_id:return False
    paper={}
    for n,picks in snapshot.get('selection',{}).items():
        if n in ('12','18') and len(picks)==int(n) and len(set(picks))==int(n):paper[n]=amounts([{'combo':k,'stake':100} for k in picks],value['winning_trifectas'],value['refund_boats'])
    plan=snapshot.get('purchase_plan',{})
    if plan.get('status')=='ready' and len(plan.get('tickets',[]))==12:
        paper['no_gami']=amounts(plan['tickets'],value['winning_trifectas'],value['refund_boats'])
    value['offer_settlements']={o['snapshot_id']:amounts(o['tickets'],value['winning_trifectas'],value['refund_boats']) for o in offers}
    if purchase:
        paper['balanced']=value['offer_settlements'][purchase_id]
    if purchase:
        value['purchase_snapshot_id']=purchase_id
        value['purchase_policy']=PURCHASE_POLICY
    value.update({'id':result_id,'settled_at':now.isoformat(),'selection_snapshot_id':snapshot['id'],'paper':paper,
                  'result_source':copy.deepcopy(res),'payout_source':copy.deepcopy(pay),'labels':{'actual_entry':{str(c):res.get(f'{c}コース_艇番') for c in range(1,7)},'actual_st':{str(c):res.get(f'{c}コース_スタートタイミング') for c in range(1,7)},'finish':{str(p):res.get(f'{p}着_艇番') for p in range(1,7)},'winning_method':res.get('決まり手')}})
    history=rec.setdefault('result_history',{})
    if old:
        oldid=old.get('id') or hashlib.sha256(json.dumps(old,sort_keys=True).encode()).hexdigest();history.setdefault(oldid,old)
    history.setdefault(result_id,value);rec['result']=value;rec.pop('result_pending_reason',None)
    return True


def settle_legacy(rec,res,pay,now):
    """Upgrade research-ledger refunds only with an explicit official result join."""
    if not res or not pay or res.get('official_refund_verified') is not True:return False
    if any(row.get('レースコード')!=rec.get('race_code') for row in (res,pay)):return False
    value=canonical(res,pay)
    if not value:return False
    old=rec.get('result') or {}
    proof={**value,'refund_verified':True,'result_source':copy.deepcopy(res),'payout_source':copy.deepcopy(pay)}
    if all(old.get(k)==proof[k] for k in ('combo','winning_trifectas','refund_boats','refund_verified')):return False
    from boat24_integrity import result_paper
    if old:rec.setdefault('result_history',{})[hashlib.sha256(json.dumps(old,sort_keys=True).encode()).hexdigest()]=copy.deepcopy(old)
    rec['result']={**proof,'settled_at':now.isoformat()}
    rec['result']['paper']=result_paper(rec)
    if rec.get('final_snapshot'):rec['result']['paper_final']=result_paper(rec,True)
    return True
