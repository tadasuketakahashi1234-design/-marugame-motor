"""Public frozen cases and their result lineage; no retrospective publication proof."""
import copy,hashlib,json,re,datetime as dt
from collections import Counter
from boat24_integrity import timeparse
from boat24_decisions import POLICY,plan_hash,outcome

POLICY_ID='public-frozen-learning-1'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':')).encode()).hexdigest()

def frozen_cases(records,decisions,before=None,allow_prediction_only=False):
    cases=[];excluded=Counter();seen=set()
    for rec in records:
        code=rec.get('race_code','')
        if code in seen:continue
        seen.add(code)
        if before and code[:8]>=before.strftime('%Y%m%d'):continue
        fixed=decisions.get('records',{}).get(code,{})
        d=fixed.get('decision') or {};receipt=d.get('receipt') or {};proof=receipt.get('proof') or {}
        s=rec.get('revisions',{}).get(d.get('snapshot_id'));result=rec.get('result') or {}
        reason=None
        if d.get('policy')!=POLICY or d.get('state') not in (('buy','skip','pending') if allow_prediction_only else ('buy','skip')):reason='no_usable_frozen_decision'
        elif not s or receipt.get('snapshot_id')!=s.get('id'):reason='frozen_snapshot_missing'
        elif s.get('phase') not in ('initial','preview'):reason='unsupported_learning_phase'
        elif not re.fullmatch('[a-f0-9]{40}',proof.get('source_commit','')) or not re.fullmatch('[a-f0-9]{64}',proof.get('sha256','')):reason='publication_proof_missing'
        else:
            cut=timeparse(s.get('cutoff'));freeze=cut-dt.timedelta(seconds=120) if cut else None
            observed=timeparse(receipt.get('observed_at'));computed=timeparse(s.get('computed_at') or s.get('created_at'))
            if not freeze or not observed or not computed or not computed<=observed<freeze:reason='publication_or_compute_after_freeze'
            elif plan_hash(s.get('purchase_plan'))!=receipt.get('payload_hash') or plan_hash(d.get('plan'))!=receipt.get('payload_hash'):reason='frozen_plan_mismatch'
            elif outcome(s,freeze)!=(d.get('state'),d.get('reason')):reason='frozen_outcome_mismatch'
            elif not result.get('refund_verified'):reason='result_or_refund_unverified'
            elif result.get('refund_boats') or len(result.get('winning_trifectas') or {result.get('combo'):0})!=1:reason='refund_or_multiple_winners'
            elif len(s.get('input_snapshot',{}).get('features',[]))!=6:reason='six_boat_inputs_missing'
            else:
                saved=s['input_snapshot'];capt=timeparse(saved.get('captured_at') or s.get('created_at'))
                stamps=list(saved.get('source_times',{}).values())+[v.get('取得日時') for v in saved.get('previews',{}).values() if v]
                if not capt or capt>computed or any(not timeparse(t) or timeparse(t)>capt for t in stamps):reason='input_time_unverified'
        if reason:excluded[reason]+=1;continue
        provenance={'policy':POLICY_ID,'race_code':code,'snapshot_id':s['id'],'source_model_id':s.get('model_id'),
                    'public_observed_at':receipt['observed_at'],'public_commit':proof['source_commit'],
                    'result_id':result.get('id'),'result_digest':digest(result),
                    'input_digest':digest(s['input_snapshot']),'freeze_at':freeze.isoformat()}
        provenance['case_id']=digest(provenance)
        cases.append({'race_code':code,'date':rec.get('date') or code[:4]+'-'+code[4:6]+'-'+code[6:8],
                      'venue':rec.get('venue') or int(code[8:10]),'phase':s.get('phase'),
                      'snapshot':copy.deepcopy(s),'decision':copy.deepcopy(d),'result':copy.deepcopy(result),'provenance':provenance})
    return cases,{'policy':POLICY_ID,'accepted':len(cases),'excluded':dict(excluded)}

def training_result(case,fallback=None):
    """Need all six finishes; official top-three-only never invent lower places."""
    result=case['result'];row=copy.deepcopy(result.get('result_source') or {});code=case['race_code']
    if row.get('official_finish_status'):return None
    combo=lambda r:'-'.join(str(r.get(str(i)+'着_艇番','')) for i in (1,2,3))
    full=lambda r:sorted(str(r.get(str(i)+'着_艇番','')) for i in range(1,7))==list('123456')
    if not full(row):
        if not fallback or fallback.get('レースコード')!=code or not full(fallback) or combo(fallback)!=result.get('combo'):return None
        row={**copy.deepcopy(fallback),**row}
    if combo(row)!=result.get('combo'):return None
    if fallback and fallback.get('レースコード')==code and full(fallback) and all(str(fallback.get(str(i)+'着_艇番'))==str(row.get(str(i)+'着_艇番')) for i in range(1,7)):
        row={**copy.deepcopy(fallback),**row}
    row.update({'レースコード':code,'official_refund_verified':True,'official_refund_boats':[],
                'learning_result_digest':case['provenance']['result_digest']})
    return row
