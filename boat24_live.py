"""A separate worktree keeps near-cutoff quotes moving during full collection."""
import copy
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from boat24_integrity import JST,timeparse,atomic_write
from boat24_context import predict,ALL_GROUPS,FREEZE_MINUTES
from boat24_bets import balanced_plan
from boat24_offers import PROTOCOL_ID,register_offers
from boat24_history_io import history_path,read_history,write_history,write_view
from boat24_model_io import read_json
from boat24_odds import collect
from boat24_quote_context import newest_context


def reprice(base,quotes,model,code,now,clock=None):
    if quotes.get('レースコード')!=code:return None
    cutoff=timeparse(base.get('cutoff'));stamp=timeparse(quotes.get('取得日時'))
    if not cutoff or now>=cutoff-dt.timedelta(minutes=FREEZE_MINUTES):return None
    if not stamp or not dt.timedelta(0)<=now-stamp<=dt.timedelta(minutes=5):return None
    prior=timeparse(base.get('purchase_plan',{}).get('odds_observed_at'))
    if prior and stamp<prior:return None
    if base.get('model_id')!=model.get('model_id') or model.get('trained_through','9999')>=now.date().isoformat():return None
    features=copy.deepcopy(base.get('input_snapshot',{}).get('features',[]))
    if len(features)!=6:return None
    from boat24_odds import add_market
    # Market-derived features must follow the same new quotes as the blend.
    add_market(features,quotes,{},{})
    baseline=predict(features,int(code[8:10]),now.date().isoformat(),model,quotes)
    candidate=predict(features,int(code[8:10]),now.date().isoformat(),{**model,'enabled_groups':[g for g in ALL_GROUPS if g!='data_quality'],'phase_calibration':{}},quotes)
    out=copy.deepcopy(base);active=base.get('research',{}).get('candidate_active',False)
    out.update(candidate if active else baseline)
    out['complete_inputs']=bool(base.get('complete_inputs') and out.get('complete_inputs'))
    if active:out['probability_verified']=False
    compact=lambda p:{k:p[k] for k in ('phase','probabilities','selection')}
    out['research']={**base.get('research',{}),'baseline':compact(baseline),'candidate':compact(candidate)}
    odds={k[4:]:float(v) for k,v in quotes.items() if k.startswith('3連単_')}
    if len(odds)!=120:return None
    plan=balanced_plan(out['probabilities'],odds)
    plan.update(protocol_id=PROTOCOL_ID,odds_observed_at=quotes['取得日時'],odds_source=quotes.get('source_url'),odds_fetched_at=quotes.get('取得完了日時'))
    out['purchase_plan']=plan
    out['input_snapshot']['captured_at']=now.isoformat()
    out['input_snapshot']['features']=features
    out['input_snapshot'].setdefault('previews',{})['odds']=copy.deepcopy(quotes)
    out['input_snapshot'].setdefault('source_times',{})['odds']=quotes['取得日時']
    out['context_snapshot_at']=base.get('context_snapshot_at',base['created_at'])
    out['refresh_kind']='official_odds_reprice'
    done=clock() if clock else now
    if done>=cutoff-dt.timedelta(minutes=FREEZE_MINUTES) or done-stamp>dt.timedelta(minutes=5):return None
    out['id']=hashlib.sha256(json.dumps([base['input_snapshot'].get('features'),quotes,model.get('model_id'),PROTOCOL_ID,'official-reprice-1'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    out.update(created_at=now.isoformat(),computed_at=done.isoformat(),evaluation_eligible=True)
    return out


def capture(model):
    from boat24_full_update import DIRECTORY,INDEX,MANIFEST
    now=dt.datetime.now(JST);path=history_path(DIRECTORY,now.date().isoformat())
    if not path.exists():return False
    ledger=read_history(path);targets=[]
    for code,rec in ledger.get('records',{}).items():
        s=newest_context(rec);cut=timeparse((s or {}).get('cutoff'))
        if not rec.get('result') and cut and dt.timedelta(minutes=2)<cut-now<=dt.timedelta(minutes=25):targets.append((cut,code,s))
    targets=sorted(targets)[:24]
    if not targets:return False
    rows,errors=collect([c for _,c,_ in targets],now);changed=0
    for _,code,s in targets:
        if code not in rows:continue
        new=reprice(s,rows[code],model,code,dt.datetime.now(JST),clock=lambda:dt.datetime.now(JST))
        rec=ledger['records'][code]
        if new and new['id'] not in rec['revisions']:
            rec['revisions'][new['id']]=new;register_offers(rec);changed+=1
    ledger['quote_health']={'attempt_at':dt.datetime.now(JST).isoformat(),'targets':len(targets),'confirmed':len(rows),'updated':changed,'errors':errors,'interval_seconds':30,'source':'official_odds3t'}
    # Do not present a quote-only refresh as a fresh weather/feature collection.
    write_history(path,ledger);write_view(path,ledger)
    old_index=json.loads(INDEX.read_text()) if INDEX.exists() else {}
    atomic_write(INDEX,old_index);atomic_write(MANIFEST,{'paths':[str(path)],'index':str(INDEX)})
    import boat24_full_publish
    boat24_full_publish.main()
    print('Official quote capture:',json.dumps(ledger['quote_health'],ensure_ascii=False),flush=True)
    return True


def watch(stop):
    from boat24_full_publish import main as publish
    from boat24_train_context import MODEL
    model=None;model_stamp=None;pending=False
    while not Path(stop).exists():
        start=time.monotonic()
        try:
            if pending:publish();pending=False
            subprocess.run(['git','fetch','origin','+refs/heads/main:refs/remotes/origin/main'],check=True,stdout=subprocess.DEVNULL)
            # This is an isolated, agent-created worktree. Only reset after all
            # its previously generated observations have been published.
            subprocess.run(['git','reset','--hard','origin/main'],check=True,stdout=subprocess.DEVNULL)
            if MODEL.exists() and MODEL.stat().st_mtime_ns!=model_stamp:
                model=read_json(MODEL);model_stamp=MODEL.stat().st_mtime_ns
            if model:
                pending=True;capture(model);pending=False
        except Exception as exc:print('Official quote worker retry:',str(exc),flush=True)
        for _ in range(max(1,int(30-(time.monotonic()-start)))):
            if Path(stop).exists():break
            time.sleep(1)
    if pending:
        publish()


@contextmanager
def worker():
    if os.environ.get('BOAT24_LIVE_ODDS_WORKER')!='1':yield;return
    root=Path.cwd();work=root/'boat24-live-worker';stop=root/'.boat24-live-stop'
    stop.unlink(missing_ok=True)
    subprocess.run(['git','worktree','add','--detach',str(work),'HEAD'],check=True)
    child=subprocess.Popen([sys.executable,'-u','boat24_live.py','--watch',str(stop)],cwd=work,start_new_session=True)
    try:yield
    finally:
        stop.touch()
        try:child.wait(timeout=90)
        except subprocess.TimeoutExpired:
            import signal
            os.killpg(child.pid,signal.SIGTERM);child.wait(timeout=10)
        # Keep generated files available in the failure artifact, rather than
        # removing a worker directory that may contain an unpublished quote.
        if child.returncode!=0:raise RuntimeError('Official quote worker stopped; retained its worktree in the recovery artifact')
        subprocess.run(['git','worktree','remove','--force',str(work)],check=True)
        stop.unlink(missing_ok=True)

if __name__=='__main__':watch(sys.argv[2])
