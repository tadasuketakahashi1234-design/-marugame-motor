"""Display-only verified exhibition entry from append-only acquisition attempts."""
from boat24_context import number
from boat24_integrity import timeparse

def latest_verified(code, record, snapshot):
    cutoff=timeparse(snapshot.get('cutoff'))
    if not cutoff:return None
    chosen=None
    for attempt in (record.get('collection_attempts') or {}).values():
        evidence=(attempt.get('verified_context') or {}).get('previews') or {}
        st=evidence.get('st') or {}
        if st.get('レースコード')!=code:continue
        observed=timeparse(st.get('取得日時'))
        if not observed or observed>=cutoff:continue
        courses={}
        for lane in range(1,7):
            value=number(st.get(f'艇{lane}_コース'))
            if value is not None and value==int(value) and 1<=value<=6:
                courses[str(lane)]=int(value)
        if len(courses)!=6 or len(set(courses.values()))!=6:continue
        ex=evidence.get('ex') or {}
        times={}
        if ex.get('レースコード')==code and ex.get('取得日時')==st.get('取得日時'):
            for lane in range(1,7):
                v=number(ex.get(f'艇{lane}_展示タイム'))
                if v is not None and 5<=v<=9:times[str(lane)]=v
        starts={}
        for lane in range(1,7):
            v=number(st.get(f'艇{lane}_スタート展示'))
            if v is not None and -1<=v<=1:starts[str(lane)]=v
        if chosen is None or observed>chosen[0]:
            chosen=(observed,{'observed_at':observed.isoformat(),'courses':courses,'exhibition_times':times,'exhibition_starts':starts,'source':'official_beforeinfo','prediction_used':False})
    return chosen[1] if chosen else None


def verified_from_cache(code, cache, cutoff):
    """Use already verified official cache when append-only attempt missed it.

    Only an exact race and pre-cutoff observation may enter the display.
    This never changes the forecast or its frozen input snapshot.
    """
    from boat24_integrity import timeparse
    record=(cache.get('races') or {}).get(code) or {}
    previews=record.get('live_previews') or {}
    st=previews.get('st') or {}
    ex=previews.get('ex') or {}
    if not st and not ex:return None
    at=timeparse((st or ex).get('取得日時'))
    limit=timeparse(cutoff)
    if not at or not limit or at>=limit:return None
    return latest_verified(code,{'collection_attempts':{'official_cache':{'verified_context':{'previews':previews}}}},{'cutoff':cutoff})
