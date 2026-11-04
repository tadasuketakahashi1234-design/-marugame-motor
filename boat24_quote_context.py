"""Keep quote-only refreshes tied to the newest saved race observations."""
from boat24_integrity import timeparse


def context_time(snapshot):
    return timeparse(snapshot.get('context_snapshot_at') or snapshot.get('created_at'))


def newest_context(record):
    candidates=[]
    for snapshot in record.get('revisions',{}).values():
        created=timeparse(snapshot.get('created_at'));cutoff=timeparse(snapshot.get('cutoff'));context=context_time(snapshot)
        if snapshot.get('evaluation_eligible') is True and created and cutoff and context and context<=created<cutoff and len(snapshot.get('input_snapshot',{}).get('features',[]))==6:
            candidates.append(snapshot)
    return max(candidates,key=lambda s:(context_time(s),timeparse(s['created_at']),s['id'])) if candidates else None


def reject_obsolete_reprices(remote,incoming):
    """Reject newly unpublished stale-context quotes; preserve published history.

    The full collector can publish newer observations while the quote worker
    is fetching odds. Recheck under the publisher's lock against fetched main.
    Local observations are left intact for audit; no remote revision is removed.
    """
    out={**incoming,'records':dict(incoming.get('records',{}))}
    for code,record in out.get('records',{}).items():
        existing=remote.get('records',{}).get(code,{})
        base=newest_context(existing)
        if base is None:continue
        rejected=set()
        for sid,snapshot in record.get('revisions',{}).items():
            if sid in existing.get('revisions',{}):continue
            if snapshot.get('refresh_kind')=='official_odds_reprice' and (context_time(snapshot) is None or context_time(snapshot)<context_time(base)):
                rejected.add(sid)
        if rejected:
            out['records'][code]={**record,
                'revisions':{sid:snapshot for sid,snapshot in record.get('revisions',{}).items() if sid not in rejected},
                'offers':{oid:offer for oid,offer in record.get('offers',{}).items() if offer.get('snapshot_id') not in rejected}}
            print('Rejected unpublished obsolete-context quotes:',code,sorted(rejected),flush=True)
    return out
