"""Comparison inputs derived from the exact immutable forecast, never later odds."""
import hashlib
import json
import math
from boat24_context import COMBOS,number
from boat24_integrity import timeparse
POLICY='same-snapshot-comparison-1'

def quotes_for(snapshot):
    row=snapshot.get('input_snapshot',{}).get('previews',{}).get('odds',{})
    at=timeparse(row.get('取得日時'));capt=timeparse(snapshot.get('computed_at') or snapshot.get('created_at'));cut=timeparse(snapshot.get('cutoff'))
    if not at or not capt or not cut or not at<=capt<cut:return None
    quotes={c:number(row.get('3連単_'+c)) for c in COMBOS}
    if any(q is None or not math.isfinite(q) or q<=0 for q in quotes.values()):return None
    return row,quotes

def market_for(snapshot):
    saved=quotes_for(snapshot)
    if not saved:return None
    row,quotes=saved;z=sum(1/q for q in quotes.values());p={c:1/q/z for c,q in quotes.items()}
    return {'probabilities':p,'picks':sorted(p,key=lambda c:(-p[c],c))[:12],'observed_at':row['取得日時'],'basis':POLICY}

def digest(snapshot):
    saved=quotes_for(snapshot)
    if not saved:return None
    return hashlib.sha256(json.dumps([snapshot.get('probabilities',{}),saved[0]['取得日時'],saved[1]],sort_keys=True,separators=(',',':')).encode()).hexdigest()

def allocation_current(snapshot):
    allocation=snapshot.get('allocation',{});tickets=allocation.get('tickets',[]);saved=quotes_for(snapshot)
    if not tickets or not saved:return False
    if allocation.get('comparison_input_digest'):return allocation['comparison_input_digest']==digest(snapshot)
    # A legacy reprice inherited both old allocation and old market baseline.
    if snapshot.get('refresh_kind','').startswith('official_'):return False
    try:return all(t['combo'] in saved[1] and math.isclose(float(t['odds']),saved[1][t['combo']],rel_tol=1e-12) for t in tickets)
    except (KeyError,TypeError,ValueError):return False

def market_matches(saved,derived):
    if not saved or not derived or saved.get('observed_at')!=derived['observed_at']:return False
    p=saved.get('probabilities',{})
    return set(p)==set(COMBOS) and saved.get('picks')==derived['picks'] and all(math.isclose(p[c],derived['probabilities'][c],rel_tol=1e-10,abs_tol=1e-12) for c in COMBOS)
