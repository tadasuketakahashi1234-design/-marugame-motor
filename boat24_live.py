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
from concurrent.futures import ThreadPoolExecutor
from boat24_integrity import JST,timeparse,atomic_write
from boat24_context import predict,ALL_GROUPS,FREEZE_MINUTES
from boat24_bets import balanced_plan,optimize
from boat24_risk import robust_plan
from boat24_quality import prepare as prepare_quality,POLICY as INPUT_POLICY
from boat24_offers import PROTOCOL_ID,register_offers
from boat24_history_io import history_path,read_history,write_history,write_view
from boat24_model_io import read_json
from boat24_odds import collect
from boat24_quote_context import newest_context
from boat24_pipeline import stage


def reprice(base,quotes,model,code,now,clock=None,diagnostics=None):
    def reject(reason):
        if diagnostics is not None:diagnostics['rejection']=reason
        return None
    if quotes.get('レースコード')!=code:return reject('quote_identity_mismatch')
    cutoff=timeparse(base.get('cutoff'));stamp=timeparse(quotes.get('取得日時'))
    if not cutoff or now>=cutoff-dt.timedelta(minutes=FREEZE_MINUTES):return reject('freeze_reached_before_compute')
    if not stamp or not dt.timedelta(0)<=now-stamp<=dt.timedelta(minutes=5):return reject('source_quote_stale_or_unclocked')
    prior=timeparse(base.get('purchase_plan',{}).get('odds_observed_at'))
    if prior and stamp<prior:return reject('older_source_quote_rejected')
    if base.get('model_id')!=model.get('model_id') or model.get('trained_through','9999')>=now.date().isoformat():return reject('model_or_training_date_mismatch')
    features=copy.deepcopy(base.get('input_snapshot',{}).get('features',[]))
    if len(features)!=6:return reject('incomplete_boat_inputs')
    from boat24_odds import add_market
    # Market-derived features must follow the same new quotes as the blend.
    add_market(features,quotes,{},{})
    quality=prepare_quality(features,base.get('input_snapshot',{}).get('previews',{}),now)
    inference_model=model if model.get('validated_input_policy')==INPUT_POLICY else {**model,'phase_calibration':{}}
    baseline=predict(features,int(code[8:10]),now.date().isoformat(),inference_model,quotes)
    candidate=predict(features,int(code[8:10]),now.date().isoformat(),{**model,'enabled_groups':[g for g in ALL_GROUPS if g!='data_quality'],'phase_calibration':{}},quotes)
    out=copy.deepcopy(base);active=base.get('research',{}).get('candidate_active',False) and model.get('forward_evidence',{}).get('policy')=='public-frozen-learning-1'
    out.update(candidate if active else baseline)
    out['complete_inputs']=bool(base.get('complete_inputs') and out.get('complete_inputs'))
    if active or model.get('validated_input_policy')!=INPUT_POLICY:out['probability_verified']=False
    out['input_quality']=quality
    out['learning_lineage']={'model_id':model.get('model_id'),'trained_through':model.get('trained_through'),'policy':model.get('learning_policy'),'case_digest':model.get('learning_provenance_digest'),'public_cases':model.get('replay',{}).get('public_frozen',0)}
    compact=lambda p:{k:p[k] for k in ('phase','probabilities','selection')}
    out['research']={**base.get('research',{}),'baseline':compact(baseline),'candidate':compact(candidate)}
    odds={k[4:]:float(v) for k,v in quotes.items() if k.startswith('3連単_')}
    if len(odds)!=120:return reject('incomplete_quote_matrix')
    plan=robust_plan(out['probabilities'],odds,verified=bool(out.get('probability_verified')),inputs_ready=quality['purchase_inputs_ready'])
    plan.update(protocol_id=PROTOCOL_ID,odds_observed_at=quotes['取得日時'],odds_source=quotes.get('source_url'),odds_fetched_at=quotes.get('取得完了日時'))
    out['purchase_plan']=plan
    out['allocation']=optimize(out['probabilities'],odds)
    from boat24_decisions import attach_arms
    attach_arms(out,odds,quality['purchase_inputs_ready'])
    out['input_snapshot']['captured_at']=now.isoformat()
    out['input_snapshot']['features']=features
    out['input_snapshot'].setdefault('previews',{})['odds']=copy.deepcopy(quotes)
    out['input_snapshot'].setdefault('source_times',{})['odds']=quotes['取得日時']
    out.update(created_at=now.isoformat(),computed_at=now.isoformat())
    from boat24_comparison_inputs import market_for,digest
    out['market_baseline']=market_for(out)
    out['allocation']['comparison_input_digest']=digest(out)
    out['context_snapshot_at']=base.get('context_snapshot_at',base['created_at'])
    out['refresh_kind']='official_odds_reprice'
    out['id']=hashlib.sha256(json.dumps([features,quotes,model.get('model_id'),PROTOCOL_ID,quality['policy'],quality['weather']['state'],'official-reprice-6-study',__import__('boat24_study').CONFIG],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    out.update(created_at=now.isoformat(),computed_at=now.isoformat(),evaluation_eligible=True,race_code=code)
    from boat24_study import attach as attach_study
    attach_study(out,model,now)
    from boat24_reasoning import build as explain
    out['race_reasoning']=explain(out,model,include_sensitivity=quality['purchase_inputs_ready'])
    done=clock() if clock else now
    if done>=cutoff-dt.timedelta(minutes=FREEZE_MINUTES) or done-stamp>dt.timedelta(minutes=5):return reject('freeze_or_quote_expiry_during_compute')
    out['computed_at']=done.isoformat()
    return out


def capture(model):
    from boat24_full_update import DIRECTORY,INDEX,MANIFEST,latest,settle
    from boat24_official_results import collect_results,CACHE as RESULT_CACHE
    now=dt.datetime.now(JST);path=history_path(DIRECTORY,now.date().isoformat())
    if not path.exists():return False
    pipeline={'started_at':now.isoformat(),'races':{},'stages':{}}
    with stage(pipeline,'read_day'):ledger=read_history(path)
    targets=[];result_targets=[]
    for code,rec in ledger.get('records',{}).items():
        s=newest_context(rec);cut=timeparse((s or {}).get('cutoff'))
        if not rec.get('result') and cut and dt.timedelta(minutes=2)<cut-now<=dt.timedelta(minutes=25):targets.append((cut,code,s))
        if not rec.get('result') and cut and now>=cut+dt.timedelta(seconds=90):result_targets.append((cut,code))
    targets=sorted(targets)[:24]
    result_codes=[code for cut,code in sorted(result_targets,reverse=True)][:12]
    if not targets and not result_codes:return False
    from boat24_fast_context import collect as collect_context,refresh as refresh_context
    acquire_started=time.perf_counter()
    with ThreadPoolExecutor(max_workers=3) as pool:
        quotes_job=pool.submit(collect,[c for _,c,_ in targets],now)
        context_job=pool.submit(collect_context,[(c,s) for _,c,s in targets],now) if targets else None
        result_job=pool.submit(collect_results,result_codes,now,limit=12,priority_codes=result_codes)
        rows,errors=quotes_job.result()
        contexts,context_errors=context_job.result() if context_job else ({},{})
        result_rows,result_errors=result_job.result()
    pipeline['stages']['acquire']={'seconds':round(time.perf_counter()-acquire_started,4),'completed_at':dt.datetime.now(JST).isoformat(),'state':'ok' if not errors and not context_errors else 'partial'}
    unconfirmed=[code for _,code,_ in targets if contexts.get(code,{}).get('source_checks',{}).get('before',{}).get('state')!='parsed']
    pipeline['unconfirmed_previews']=unconfirmed
    if unconfirmed:pipeline['stages']['acquire']['state']='partial'
    changed=0;dirty=set()
    for _,code,s in targets:
        row_trace={'attempt_at':dt.datetime.now(JST).isoformat(),'cutoff':s.get('cutoff'),'source_checks':contexts.get(code,{}).get('source_checks',{}),'odds_error':errors.get(code)};pipeline['races'][code]=row_trace
        # Keep verified official entry independently of the quote/repricing result.
        # This is display-only evidence and does not change a prediction.
        row_trace['verified_context']={
            'previews':copy.deepcopy(contexts.get(code,{}).get('previews',{})),
            'water':copy.deepcopy(contexts.get(code,{}).get('water',{})),
            'before_body_sha256':contexts.get(code,{}).get('body_sha256'),
        }
        if code not in rows:
            # Preserve verified context-acquisition evidence even without a quote.
            # Never fabricate a forecast or advance its prediction timestamp.
            checks=row_trace['source_checks'];row_trace['context_observed']=bool(contexts.get(code,{}).get('previews'))
            row_trace['exhibition_parsed']=bool(contexts.get(code,{}).get('previews',{}).get('ex'))
            row_trace['entry_parsed']=bool(contexts.get(code,{}).get('previews',{}).get('st'))
            row_trace['weather_parsed']=checks.get('water',{}).get('state')=='parsed'
            row_trace['state']='odds_unconfirmed_context_logged'
            continue
        compute_started=time.perf_counter();row_trace['official_quote_at']=rows[code].get('取得日時');row_trace['quote_received_at']=rows[code].get('取得完了日時')
        try:
            base=refresh_context(s,contexts.get(code,{}),model,code,dt.datetime.now(JST))
            new=reprice(base,rows[code],model,code,dt.datetime.now(JST),clock=lambda:dt.datetime.now(JST),diagnostics=row_trace)
        except Exception as exc:
            row_trace.update(state='compute_failed',error=str(exc)[:180]);errors['compute_'+code]=str(exc)[:180];continue
        row_trace.update(compute_seconds=round(time.perf_counter()-compute_started,4),computed_at=dt.datetime.now(JST).isoformat(),state='saved' if new else 'not_saved_by_timing_or_model_gate')
        if new:
            row_trace.update(snapshot_id=new['id'],input_quality=new.get('input_quality'),decision_status=new.get('purchase_plan',{}).get('status'))
            new['pipeline_trace']=dict(row_trace)
        if new and base.get('context_snapshot_at')!=s.get('context_snapshot_at'):new['refresh_kind']='official_context_and_odds'
        rec=ledger['records'][code]
        if new and new['id'] in rec['revisions']:row_trace['state']='unchanged_saved_snapshot'
        if new and new['id'] not in rec['revisions']:
            rec['revisions'][new['id']]=new;register_offers(rec);changed+=1;dirty.add(code)
    from boat24_learning import digest
    for code,attempt in pipeline['races'].items():
        ledger['records'][code].setdefault('collection_attempts',{}).setdefault(digest([pipeline['started_at'],code,attempt]),copy.deepcopy(attempt));dirty.add(code)
    ledger['quote_health']={'attempt_at':dt.datetime.now(JST).isoformat(),'targets':len(targets),'confirmed':len(rows),'updated':changed,'errors':errors,'context_errors':context_errors,'interval_seconds':30,'source':'official_odds3t_and_verified_context','pipeline':pipeline}
    settled=0
    for code in result_codes:
        row=result_rows.get(code)
        if row:dirty.add(code);settled+=int(settle(ledger['records'][code],row['result'],row['payout'],dt.datetime.now(JST)))
    result_at=dt.datetime.now(JST).isoformat()
    for code in result_codes:
        attempt={'at':result_at,'confirmed':code in result_rows,'error':result_errors.get(code),'result_id':(ledger['records'][code].get('result') or {}).get('id')}
        ledger['records'][code].setdefault('settlement_attempts',{}).setdefault(digest([code,attempt]),attempt);dirty.add(code)
    ledger['result_health']={'attempt_at':result_at,'targets':result_codes,'confirmed':sum(c in result_rows for c in result_codes),'settled':settled,'errors':result_errors,'source':'official_raceresult_without_csv_gate'}
    if settled:ledger['settlement_updated_at']=result_at
    # Do not present a quote-only refresh as a fresh weather/feature collection.
    write_history(path,ledger,changed_codes=dirty);write_view(path,ledger)
    old_index=json.loads(INDEX.read_text()) if INDEX.exists() else {}
    paths=[str(path)]+([str(RESULT_CACHE)] if RESULT_CACHE.exists() else [])
    atomic_write(INDEX,old_index);atomic_write(MANIFEST,{'paths':paths,'index':str(INDEX)})
    import boat24_full_publish
    boat24_full_publish.main()
    print('Official quote capture:',json.dumps(ledger['quote_health'],ensure_ascii=False),'results:',json.dumps(ledger['result_health'],ensure_ascii=False),flush=True)
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

def start_workflow_worker():
    root=Path.cwd();work=root/'boat24-live-worker';stop=root/'.boat24-live-stop'
    if work.exists():raise RuntimeError('An existing live worktree must be inspected before starting another worker')
    stop.unlink(missing_ok=True)
    subprocess.run(['git','worktree','add','--detach',str(work),'HEAD'],check=True)
    with (root/'boat24-live-worker.log').open('a') as log:
        child=subprocess.Popen([sys.executable,'-u','boat24_live.py','--watch',str(stop)],cwd=work,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    (root/'.boat24-live-pid').write_text(str(child.pid))
    print('Live context/odds worker started before recovery:',child.pid,flush=True)

def stop_workflow_worker():
    root=Path.cwd();(root/'.boat24-live-stop').touch();pidfile=root/'.boat24-live-pid'
    if not pidfile.exists():return
    pid=int(pidfile.read_text());deadline=time.monotonic()+300
    while time.monotonic()<deadline:
        try:
            state=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0]
            if state=='Z':return
        except FileNotFoundError:return
        time.sleep(1)
    raise RuntimeError('Live worker did not stop; its worktree and log are retained for recovery')

if __name__=='__main__':
    if sys.argv[1]=='--start-workflow-worker':start_workflow_worker()
    elif sys.argv[1]=='--stop-workflow-worker':stop_workflow_worker()
    elif sys.argv[1]=='--watch':watch(sys.argv[2])
    else:raise SystemExit('Unknown live-worker command')
