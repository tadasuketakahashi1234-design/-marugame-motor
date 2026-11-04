"""Immutable saved purchase offers and a fixed first-offer evaluation protocol."""
import copy
import datetime as dt
import math
from boat24_integrity import timeparse,valid_combo
from boat24_bets import PURCHASE_POLICY

from boat24_risk import PROTOCOL_ID,POLICY as RISK_POLICY
PROTOCOL={'id':PROTOCOL_ID,'policy':PURCHASE_POLICY,'budget_cap':1200,'stake_unit':100,
          'quote_max_age_seconds':300,'freeze_seconds':120,'race_selection':'first_ready',
          'objective':'stress_hit_probability * (stress_expected_roi - 1)','risk_policy':RISK_POLICY,'basis':'saved_before_cutoff',
          'publication_time_verified':False,'profitability_proven':False}

def register_offers(rec):
    offers=rec.setdefault('offers',{})
    for s in sorted(rec.get('revisions',{}).values(),key=lambda s:(s.get('created_at',''),s.get('id',''))):
        p=s.get('purchase_plan',{});created=timeparse(s.get('created_at'));cutoff=timeparse(s.get('cutoff'));quote=timeparse(p.get('odds_observed_at'));computed=timeparse(s.get('computed_at')) or created
        if p.get('policy')!=PURCHASE_POLICY or p.get('status')!='ready' or not s.get('evaluation_eligible') or not created or not cutoff or not quote:continue
        if not (quote<=created<cutoff-dt.timedelta(seconds=120)) or created-quote>dt.timedelta(seconds=300) or computed<created or computed-quote>dt.timedelta(seconds=300) or computed>=cutoff-dt.timedelta(seconds=120):continue
        ts=p.get('tickets',[]);budget=p.get('budget')
        if not ts or not isinstance(budget,int) or not 0<budget<=1200 or len({t.get('combo') for t in ts})!=len(ts):continue
        valid=True
        for t in ts:
            stake=t.get('stake');odds=t.get('odds')
            if not valid_combo(t.get('combo')) or not isinstance(stake,int) or stake<=0 or stake%100 or not isinstance(odds,(int,float)) or not math.isfinite(odds) or odds<=0 or math.floor((odds+1e-9)*10)*10*(stake//100)<=budget:valid=False;break
        if not valid or sum(t['stake'] for t in ts)!=budget or not isinstance(p.get('estimated_roi'),(int,float)) or not math.isfinite(p['estimated_roi']) or p['estimated_roi']<=1:continue
        if p.get('protocol_id')==PROTOCOL_ID:
            from boat24_risk import validate_robust
            if not validate_robust(p):continue
        key=s['id']
        offers.setdefault(key,{'snapshot_id':key,'created_at':s['created_at'],'cutoff':s['cutoff'],
             'policy':PURCHASE_POLICY,'protocol_id':p.get('protocol_id'),'basis':'saved_before_cutoff',
             'model':s.get('model',rec.get('model','unknown')),'model_id':s.get('model_id') or s.get('model_generated_at') or 'unknown',
             'phase':s.get('phase','unknown'),'odds_observed_at':p['odds_observed_at'],
             'budget':budget,'tickets':copy.deepcopy(ts),'estimated_roi':p['estimated_roi'],
             **{k:copy.deepcopy(p[k]) for k in ('risk_policy','risk_controls','stress_expected_roi') if k in p}})
    return sorted(offers.values(),key=lambda o:(o['created_at'],o['snapshot_id']))

def report(records):
    groups={}
    for rec in records:
        result=rec.get('result') or {};offer=rec.get('offers',{}).get(result.get('purchase_snapshot_id'));bet=result.get('paper',{}).get('balanced')
        if not offer or not bet:continue
        key=(offer.get('protocol_id') or 'historical-reconstructed',offer['policy'],offer['model'],offer['model_id'],offer['phase'])
        g=groups.setdefault(key,{'protocol_id':key[0],'policy':key[1],'model':key[2],'model_id':key[3],'phase':key[4],'races':0,'hits':0,'stake':0,'return':0,'refund':0,'refund_unverified':0,'fully_refunded':0})
        g['races']+=1;g['hits']+=int(bet['hit'])
        for f in ('stake','return','refund'):g[f]+=bet.get(f,0)
        g['refund_unverified']+=not result.get('refund_verified',False);g['fully_refunded']+=bet.get('refund',0)==bet['stake']
    rows=[]
    for key,g in sorted(groups.items()):
        g.update(profit=g['return']-g['stake'],roi=g['return']/g['stake'] if g['stake'] else None);rows.append(g)
    comparison={}
    for rec in records:
        result=rec.get('result') or {};chosen={}
        for offer in sorted(rec.get('offers',{}).values(),key=lambda o:(o['created_at'],o['snapshot_id'])):
            chosen.setdefault(offer.get('protocol_id') or 'historical-reconstructed',offer)
        for protocol,offer in chosen.items():
            bet=result.get('offer_settlements',{}).get(offer['snapshot_id'])
            if not bet:continue
            key=(protocol,offer['policy'],offer['model'],offer['model_id'],offer['phase'])
            g=comparison.setdefault(key,{'protocol_id':protocol,'policy':key[1],'model':key[2],'model_id':key[3],'phase':key[4],'races':0,'hits':0,'stake':0,'return':0,'refund':0,'refund_unverified':0})
            g['races']+=1;g['hits']+=int(bet['hit']);g['refund_unverified']+=not result.get('refund_verified',False)
            for f in ('stake','return','refund'):g[f]+=bet.get(f,0)
    compare_rows=[]
    for key,g in sorted(comparison.items()):
        g.update(profit=g['return']-g['stake'],roi=g['return']/g['stake'] if g['stake'] else None);compare_rows.append(g)
    return {'protocol':PROTOCOL,'rows':rows,'protocol_comparison_rows':compare_rows,
            'comparison_selection':'first_ready_per_race_per_protocol',
            'warning':'主集計は各R最初の候補。条件別比較も各R・各条件で最初の候補1件に固定。購入・公開時刻の実証ではなく仮想検証。'}
