"""Prior-day saved observations become learning cases, once per race and phase.

Never rewrite forecasts or substitute post-race information into a snapshot.
"""
import copy
import datetime as dt
import json
from pathlib import Path
from boat24_integrity import timeparse

def load_observations(today,days=28,directory=Path('omura/docs/full_history')):
    selected={};diagnostics={'races':0,'snapshots':0,'rejected':0,'source':'immutable_pre_cutoff_snapshots'}
    for path in sorted(directory.glob('*.json')):
        if not (today-dt.timedelta(days=days)).isoformat()<=path.stem<today.isoformat():continue
        doc=json.loads(path.read_text())
        for code,rec in doc.get('records',{}).items():
            if len(code)!=12 or not code.isdigit() or code[:8]!=path.stem.replace('-',''):continue
            valid=[]
            for s in rec.get('revisions',{}).values():
                t=timeparse(s.get('created_at'));cut=timeparse(s.get('cutoff'));capt=timeparse(s.get('input_snapshot',{}).get('captured_at') or s.get('created_at'))
                if not s.get('evaluation_eligible') or not t or not cut or not capt or not t<=capt<cut-dt.timedelta(minutes=2) or t.date()!=cut.date() or t.strftime('%Y%m%d')!=code[:8]:
                    diagnostics['rejected']+=1;continue
                fs=s.get('input_snapshot',{}).get('features',[])
                if len(fs)!=6 or s.get('phase') not in ('initial','preview'):continue
                # Require every saved source time to have been available at capture.
                times=s.get('input_snapshot',{}).get('source_times',{}).values()
                if any(not timeparse(x) or timeparse(x)>capt for x in times):diagnostics['rejected']+=1;continue
                valid.append(s)
            if valid:diagnostics['races']+=1
            for phase in ('initial','preview'):
                options=sorted((s for s in valid if s['phase']==phase),key=lambda s:(s['created_at'],s['id']))
                if options:selected[(code,phase)]=options[0] if phase=='initial' else options[-1];diagnostics['snapshots']+=1
    return selected,diagnostics

def restore_snapshot(snapshot,code,card):
    from boat24_details import attach
    saved=copy.deepcopy(snapshot['input_snapshot']);features=copy.deepcopy(saved['features'])
    previews=saved.get('previews',{});cutoff=timeparse(snapshot['cutoff']);at=timeparse(saved.get('captured_at') or snapshot['created_at'])
    # Extra sources must have been saved with this very snapshot.
    extras={k:{code:r} for k,r in saved.get('supplemental_previews',{}).items()}
    detail=attach(features,code,card,extras,previews,cutoff,at,saved.get('official',{}))
    return {'features':features,'previews':previews,'cutoff':cutoff,'detail':detail,
            'asof':at,'snapshot_id':snapshot['id'],'race_context':saved.get('race_context',{})}
