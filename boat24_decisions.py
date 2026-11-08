"""Prospective two-minute decisions; public retrieval receipts, not backdated times."""
import copy,datetime as dt,hashlib,json,math
from boat24_integrity import JST,timeparse,valid_combo
from boat24_bets import PURCHASE_POLICY
from boat24_risk import robust_plan,validate_robust
from boat24_settlement import amounts
POLICY='public-observed-freeze-120-v1'
PATH='omura/docs/boat24_decisions.json'
PROTOCOL={'id':POLICY,'freeze_seconds':120,'quote_max_age_seconds':300,'budget_cap':1200,'stake_unit':100,'selection':'latest_displayed_snapshot_observed_before_freeze','publication_basis':'successful_public_data_retrieval_upper_bound','actual_purchase_verified':False,'profitability_proven':False}

def compact_plan(plan):return copy.deepcopy({k:v for k,v in (plan or {}).items() if k not in ('frontier','comparison_by_count')})
def plan_hash(plan):return hashlib.sha256(json.dumps(compact_plan(plan),sort_keys=True,separators=(',',':')).encode()).hexdigest()
def attach_arms(snapshot,quotes,ready):
    """Capture both shadow portfolios before results under identical controls."""
    arms={}
    for name in ('baseline','candidate'):
        research=snapshot.get('research',{}).get(name,{})
        if not research.get('probabilities'):continue
        plan=robust_plan(research['probabilities'],quotes,verified=False,inputs_ready=ready)
        plan['odds_observed_at']=snapshot.get('purchase_plan',{}).get('odds_observed_at')
        arms[name]={'plan':compact_plan(plan),'probabilities':copy.deepcopy(research['probabilities'])}
    snapshot.setdefault('research',{})['decision_arms']={'policy':POLICY,'common_controls':'unverified_probability_20pct_price_10pct_share_25pct','arms':arms}

def displayed(record):
    candidates=[s for s in record.get('revisions',{}).values() if s.get('evaluation_eligible') and timeparse(s.get('created_at')) and timeparse(s.get('cutoff')) and timeparse(s['created_at'])<timeparse(s['cutoff'])]
    current=[s for s in candidates if s.get('purchase_plan',{}).get('policy')==PURCHASE_POLICY]
    return max(current or candidates,key=lambda s:(2 if s.get('phase')=='preview' else 0,timeparse(s.get('context_snapshot_at') or s['created_at']),s['created_at'],s['id']),default=None)

def outcome(snapshot,freeze):
    plan=compact_plan(snapshot.get('purchase_plan'));status=plan.get('status','missing_plan');quote=timeparse(plan.get('odds_observed_at'));computed=timeparse(snapshot.get('computed_at') or snapshot.get('created_at'))
    if not computed or computed>=freeze:return 'unavailable','computed_after_freeze'
    if plan.get('policy')!=PURCHASE_POLICY:return 'pending','unsupported_plan_policy'
    if status in ('odds_stale','odds_incomplete','preview_pending','missing_plan','probabilities_invalid'):return 'pending',status
    if not quote or quote>computed or not dt.timedelta(0)<=freeze-quote<=dt.timedelta(seconds=300):return 'pending','quote_expired_at_freeze'
    if status!='ready':return ('skip' if status in ('risk_no_positive_value','risk_no_feasible_plan','no_positive_value','no_feasible_plan') else 'pending'),status
    tickets=plan.get('tickets',[]);budget=plan.get('budget')
    try:
        valid=validate_robust(plan) and budget<=1200 and plan.get('estimated_roi',0)>1 and all(valid_combo(t['combo']) and t['expected_return']>budget for t in tickets)
    except (KeyError,TypeError):valid=False
    return ('buy','ready') if valid else ('pending','invalid_saved_allocation')

def update(doc,view,archives,observed_at,proof,*,inplace=False):
    """Only matched public payloads yield receipts; later skips override prior buys."""
    now=timeparse(observed_at);out=(doc if doc is not None else {}) if inplace else copy.deepcopy(doc or {});out.setdefault('protocol',{**PROTOCOL,'started_at':observed_at});records=out.setdefault('records',{});start=timeparse(out['protocol']['started_at'])
    for code,item in view.get('catalog',{}).items():
        cut=timeparse(item.get('cutoff'));rec=archives.get(code,{})
        if not cut:
            records.setdefault(code,{'race_code':code,'venue':item.get('venue'),'race':item.get('race'),'cutoff':None,'freeze_at':None,'receipts':{}})
            continue
        freeze=cut-dt.timedelta(seconds=120);r=records.setdefault(code,{'race_code':code,'venue':item.get('venue'),'race':item.get('race'),'cutoff':cut.isoformat(),'freeze_at':freeze.isoformat(),'receipts':{}})
        # Once a decision exists, neither later views nor results can change it.
        if 'decision' not in r:
            r.update(cutoff=cut.isoformat(),freeze_at=freeze.isoformat())
            public=displayed(view.get('records',{}).get(code,{}));s=rec.get('revisions',{}).get((public or {}).get('id'))
            if now<freeze and s and timeparse(s.get('cutoff'))==cut and plan_hash(public.get('purchase_plan'))==plan_hash(s.get('purchase_plan')):
                created=timeparse(s.get('created_at'));computed=timeparse(s.get('computed_at') or s.get('created_at'))
                if created and computed and created<=computed<=now:
                    key=hashlib.sha256(json.dumps([s['id'],observed_at,proof],sort_keys=True).encode()).hexdigest()
                    receipt={'snapshot_id':s['id'],'observed_at':observed_at,'payload_hash':plan_hash(s.get('purchase_plan')),'catalog_state':item.get('state'),'proof':copy.deepcopy(proof)}
                    from boat24_study import evidence
                    expected=evidence(s)
                    if expected and public.get('study_evidence')==expected:receipt['study_digest']=expected['digest']
                    r['receipts'].setdefault(key,receipt)
            if now>=freeze:
                prior=[v for v in r['receipts'].values() if timeparse(v['observed_at'])<freeze]
                receipt=max(prior,key=lambda x:(x['observed_at'],x['snapshot_id']),default=None)
                snap=rec.get('revisions',{}).get((receipt or {}).get('snapshot_id'))
                state,reason=('historical_unverified','protocol_started_after_freeze') if freeze<=start else ('unavailable','no_public_payload_observed_before_freeze')
                if snap and receipt and plan_hash(snap.get('purchase_plan'))==receipt['payload_hash']:
                    state,reason=('cancelled','public_cancellation_observed') if receipt.get('catalog_state')=='cancelled' else outcome(snap,freeze)
                r['decision']={'policy':POLICY,'state':state,'reason':reason,'finalized_at':observed_at,'snapshot_id':(receipt or {}).get('snapshot_id'),'receipt':copy.deepcopy(receipt),'model_id':(snap or {}).get('model_id'),'phase':(snap or {}).get('phase'),'plan':compact_plan((snap or {}).get('purchase_plan')),'paired':copy.deepcopy((snap or {}).get('research',{}).get('decision_arms',{}))}
                if snap and receipt and receipt.get('study_digest'):
                    from boat24_learning import digest
                    if receipt['study_digest']==digest(snap.get('prospective_study')):r['decision']['study']=copy.deepcopy(snap['prospective_study'])
        decision=r.get('decision');result=rec.get('result')
        if decision and result:
            settle={'result_id':result.get('id'),'combo':result['combo'],'payout_100yen':result['payout_100yen'],'refund_verified':bool(result.get('refund_verified')),'refund_boats':copy.deepcopy(result.get('refund_boats',[])),'winning_trifectas':copy.deepcopy(result.get('winning_trifectas') or {result['combo']:result['payout_100yen']}),'settled_at':observed_at}
            if result.get('refund_verified'):
                winners=result.get('winning_trifectas') or {result['combo']:result['payout_100yen']};refunds=result.get('refund_boats',[])
                if decision['state']=='buy':settle['actual_rule']=amounts(decision['plan']['tickets'],winners,refunds)
                pairs={}
                for name,arm in decision.get('paired',{}).get('arms',{}).items():
                    state,reason=outcome({'created_at':(decision.get('plan') or {}).get('odds_observed_at'),'computed_at':(decision.get('plan') or {}).get('odds_observed_at'),'purchase_plan':arm['plan']},freeze)
                    pairs[name]={'state':state,'reason':reason}
                    if state=='buy':pairs[name]['paper']=amounts(arm['plan']['tickets'],winners,refunds)
                if pairs:settle['paired']=pairs
            old=r.get('settlement') or {}
            if old.get('result_id')!=settle.get('result_id') or old.get('refund_verified')!=settle['refund_verified'] or 'refund_boats' not in old:r['settlement']=settle
    out['updated_at']=observed_at;return out

def report(doc):
    records=list((doc or {}).get('records',{}).values());counts={};rows=[];paired={};groups={};sequences={};bins={}
    for r in records:
        d=r.get('decision') or {};state=d.get('state','awaiting_freeze' if r.get('freeze_at') else 'cutoff_unknown');counts[state]=counts.get(state,0)+1;s=r.get('settlement') or {};bet=s.get('actual_rule')
        rows.append({'race_code':r['race_code'],'venue':r.get('venue'),'race':r.get('race'),'freeze_at':r['freeze_at'],'state':state,'reason':d.get('reason'),'snapshot_id':d.get('snapshot_id'),'observed_at':(d.get('receipt') or {}).get('observed_at'),'plan':compact_plan(d.get('plan')),'result':s.get('combo'),'paper':bet})
        if bet:
            key=(d.get('model_id'),d.get('phase'));g=groups.setdefault(key,{'model_id':key[0],'phase':key[1],'races':0,'hits':0,'stake':0,'return':0,'gami':0});g['races']+=1;g['hits']+=bet['hit'];g['stake']+=bet['stake'];g['return']+=bet['return'];g['gami']+=bool(bet['hit'] and bet['profit']<0)
            sequences.setdefault(key,[]).append((r['freeze_at'],r['race_code'],bet))
            probability=d.get('plan',{}).get('estimated_hit_probability')
            if isinstance(probability,(float,int)) and 0<=probability<=1 and bet.get('net_stake',0)>0 and not s.get('refund_boats') and len(s.get('winning_trifectas',{}))==1:
                b=bins.setdefault(str(min(9,int(probability*10))),{'races':0,'expected_hits':0.,'hits':0});b['races']+=1;b['expected_hits']+=probability;b['hits']+=bet['hit']
        arms=s.get('paired',{})
        if set(arms)=={'baseline','candidate'}:
            for name,arm in arms.items():
                g=paired.setdefault(name,{'comparable_races':0,'buys':0,'hits':0,'stake':0,'return':0,'skips':0,'pending':0});g['comparable_races']+=1
                if arm['state']=='buy':b=arm['paper'];g['buys']+=1;g['hits']+=b['hit'];g['stake']+=b['stake'];g['return']+=b['return']
                elif arm['state']=='skip':g['skips']+=1
                else:g['pending']+=1
    for key,sequence in sequences.items():
        balance=peak=drawdown=streak=longest=0
        for _,_,bet in sorted(sequence,key=lambda x:(x[0],x[1])):
            balance+=bet['profit'];peak=max(peak,balance);drawdown=max(drawdown,peak-balance)
            if bet.get('net_stake',0)>0:streak=streak+1 if bet['profit']<0 else 0
            longest=max(longest,streak)
        groups[key].update(max_drawdown=drawdown,max_loss_streak=longest)
    for g in [*groups.values(),*paired.values()]:g['roi']=g['return']/g['stake'] if g['stake'] else None;g['profit']=g['return']-g['stake']
    observed=max((v.get('observed_at','') for r in records for v in r.get('receipts',{}).values()),default=None)
    return {'last_public_observed_at':observed,'protocol':(doc or {}).get('protocol',{**PROTOCOL,'started_at':None}),'updated_at':(doc or {}).get('updated_at'),'counts':counts,'purchase_probability_bins':bins,'model_rows':list(groups.values()),'paired_rows':paired,'decisions':sorted(rows,key=lambda r:r['race_code']),'note':'公開データ取得確認は公開時刻の上限。購入実績ではなく仮想照合。過去の公開時刻を推定して遡及採用しない。'}
