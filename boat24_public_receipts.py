"""Observe public data after successful push and persist prospective receipts."""
import datetime as dt,hashlib,json,re,subprocess,tempfile,time,urllib.request
from contextlib import contextmanager
from boat24_pipeline import stage
from pathlib import Path
from boat24_integrity import JST,atomic_write
from boat24_decisions import PATH,update,report
from boat24_history_io import read_history

def git(*args,cwd):return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()
def download(url):
    req=urllib.request.Request(url+'?receipt='+str(time.time_ns()),headers={'User-Agent':'boat24-public-observation/1','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=15) as response:return response.read()

@contextmanager
def receipt_worktree(root,initial_work,attempt):
    if initial_work is not None and attempt==0:
        yield Path(initial_work);return
    git('fetch','origin','+refs/heads/main:refs/remotes/origin/main',cwd=root)
    with tempfile.TemporaryDirectory(prefix='boat24-receipts-') as tmp:
        work=Path(tmp)/'checkout';git('worktree','add','--detach',str(work),'origin/main',cwd=root)
        try:yield work
        finally:git('worktree','remove','--force',str(work),cwd=root)

def publish(root,initial_work=None,publication=None):
    remote=git('remote','get-url','origin',cwd=root)
    if not re.fullmatch(r'https://github.com/tadasuketakahashi1234-design/-marugame-motor(?:\.git)?',remote):return
    repo='tadasuketakahashi1234-design/-marugame-motor';base='https://raw.githubusercontent.com/'+repo+'/';pending=[]
    for attempt in range(3):
        trace={'started_at':dt.datetime.now(JST).isoformat(),'reused_publication_checkout':initial_work is not None and attempt==0};loaded={}
        with receipt_worktree(root,initial_work,attempt) as work:
            source=git('rev-parse','HEAD',cwd=work);index_path=work/'omura/docs/boat24_full_index.json';index=json.loads(index_path.read_text())
            with stage(trace,'public_index_fetch'):current=json.loads(download(base+'main/omura/docs/boat24_full_index.json'))
            # Confirm the public current index points to this exact view.
            day=dt.datetime.now(JST).date().isoformat();entry=index.get('days',{}).get(day);public=current.get('days',{}).get(day)
            confirmed_url=base+'main/omura/docs/boat24_full_index.json'
            if entry and (not public or entry.get('view_path')!=public.get('view_path') or entry.get('view_sha256')!=public.get('view_sha256')):
                # Match the UI's latest-ref fallback when the mutable raw URL is stale.
                # The public ref must resolve first; a locally known SHA alone is not evidence.
                with stage(trace,'public_ref_fetch'):
                    ref_url='https://api.github.com/repos/'+repo+'/git/ref/heads/main'
                    ref=json.loads(download(ref_url));public_sha=ref.get('object',{}).get('sha','')
                    if not re.fullmatch(r'[a-f0-9]{40}',public_sha):raise ValueError('Invalid public main ref')
                confirmed_url=base+public_sha+'/omura/docs/boat24_full_index.json'
                with stage(trace,'public_versioned_index_fetch'):current=json.loads(download(confirmed_url))
                public=current.get('days',{}).get(day);trace['public_ref_sha']=public_sha
            if entry and public and entry.get('view_path')==public.get('view_path') and entry.get('view_sha256')==public.get('view_sha256'):
                path=entry.get('view_path','')
                if not re.fullmatch(r'day_views/\d{4}-\d{2}-\d{2}-[a-f0-9]{16}\.json',path):raise ValueError('Unversioned public view cannot establish receipt')
                url=base+source+'/omura/docs/'+path
                with stage(trace,'public_view_fetch'):raw=download(url)
                digest=hashlib.sha256(raw).hexdigest()
                if digest!=entry.get('view_sha256'):raise ValueError('Public day view digest mismatch')
                view=json.loads(raw);observed=dt.datetime.now(JST).isoformat();trace['state']='view_confirmed'
                with stage(trace,'read_observed_archive'):ledger=read_history(work/'omura/docs'/entry['archive_path'])
                archives=ledger['records'];loaded={day:ledger}
                proof={'source_commit':source,'view_url':url,'sha256':digest,'index_confirmed_url':confirmed_url}
                pending.append((view,archives,observed,proof))
            trace.setdefault('state','index_changed_before_verification')
            target=work/PATH;doc=json.loads(target.read_text()) if target.exists() else {}
            for view,archives,observed,proof in pending:doc=update(doc,view,archives,observed,proof,inplace=True)
            # Load each prior archive before finalizing its frozen decision.
            # An empty archive would permanently mark a valid receipt unavailable.
            now=dt.datetime.now(JST).isoformat()
            from boat24_study import START_DAY
            # Study reports only need registered forward days. Older decisions
            # with existing receipts still need their archive for settlement.
            prior_days={r['race_code'][:4]+'-'+r['race_code'][4:6]+'-'+r['race_code'][6:8]
                        for r in doc.get('records',{}).values()
                        if r.get('receipts') or (r.get('decision') or {}).get('receipt')}
            prior_days.update(k for k in index.get('days',{}) if START_DAY<=k<=day)
            for key in sorted(prior_days):
                e=index.get('days',{}).get(key)
                if not e:
                    # Never finalize an old decision without its source archive.
                    continue
                ledger=loaded.get(key)
                if ledger is None:
                    with stage(trace,'read_prior_archive_'+key):ledger=read_history(work/'omura/docs'/e['archive_path'])
                    loaded[key]=ledger
                doc=update(doc,{'catalog':ledger.get('catalog',{})},ledger.get('records',{}),now,{},inplace=True)
            if not doc: return
            index['decision_report']=report(doc);index['updated_at']=now
            from boat24_study import report as study_report
            study_records=[r for book in loaded.values() for r in book.get('records',{}).values()]
            index['prospective_study']=study_report(study_records,doc,index.get('catalogs',{}),dt.datetime.now(JST))
            index.setdefault('pipeline_health',{}).update(publication=publication or index.get('pipeline_health',{}).get('publication',{}),public_observation=trace,last_observed_at=index['decision_report'].get('last_public_observed_at'))
            atomic_write(target,doc);atomic_write(index_path,index)
            git('add',PATH,'omura/docs/boat24_full_index.json',cwd=work)
            if not git('diff','--cached','--name-only',cwd=work):return
            git('-c','user.name=github-actions[bot]','-c','user.email=41898282+github-actions[bot]@users.noreply.github.com','commit','-m','Record public observations and frozen two-minute decisions',cwd=work)
            if subprocess.run(['git','push','origin','HEAD:main'],cwd=work).returncode==0:
                print('Prospective decisions:',json.dumps(index['decision_report']['counts']),flush=True);return
    raise RuntimeError('Public decision receipts could not be published; no timestamps backdated')
