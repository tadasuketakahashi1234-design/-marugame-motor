"""Blocking local financial/history checks, independent of public CDN availability."""
import datetime as dt
from boat24_integrity import JST,timeparse
from boat24_history_io import read_history,history_path
from boat24_bets import PURCHASE_POLICY
from boat24_risk import POLICY,validate_robust

def validate(doc):
    count=0
    for rec in doc.get('records',{}).values():
        for s in rec.get('revisions',{}).values():
            if not s.get('evaluation_eligible'):continue
            assert timeparse(s['created_at'])<timeparse(s['cutoff']), 'Forecast saved after cutoff'
            assert len(s['input_snapshot']['features'])==6, 'Missing boat inputs'
            p=s.get('purchase_plan',{})
            if p.get('policy')==PURCHASE_POLICY and p.get('status')=='ready':
                tickets=p['tickets'];total=sum(t['stake'] for t in tickets)
                assert tickets and len({t['combo'] for t in tickets})==len(tickets)
                assert total==p['budget'] and 0<total<=min(p['budget_cap'],1200) and p['estimated_roi']>1
                assert all(isinstance(t['stake'],int) and t['stake']>0 and t['stake']%100==0 and t['expected_return']>total for t in tickets)
                if p.get('risk_policy')==POLICY:assert validate_robust(p), 'Invalid stress allocation'
            count+=1
    return count

if __name__=='__main__':
    from boat24_full_update import DIRECTORY
    path=history_path(DIRECTORY,dt.datetime.now(JST).date().isoformat())
    assert path.exists(), 'Today history missing'
    print('Local immutable inputs and purchase checks PASS:',validate(read_history(path)))
