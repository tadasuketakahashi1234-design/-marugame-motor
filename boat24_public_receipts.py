"""Observe public data after successful push and persist prospective receipts."""
import datetime as dt,hashlib,json,re,subprocess,tempfile,time,urllib.request
from pathlib import Path
from boat24_integrity import JST,atomic_write
from boat24_decisions import PATH,update,report
from boat24_history_io import read_history

def git(*args,cwd):return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()
def download(url):
    req=urllib.request.Request(url+'?receipt='+str(time.time_ns()),headers={'User-Agent':'boat24-public-observation/1','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=15) as response:return response.read()

def publish(root):
    remote=git('remote','get-url','origin',cwd=root)
    if not re.fullmatch(r'https://github.com/tadasuketakahashi1234-design/-marugame-motor(?:\.git)?',remote):return
    repo='tadasuketakahashi1234-design/-marugame-motor';base='https://raw.githubusercontent.com/'+repo+'/';pending=[]
    for attempt in range(3):
        git('fetch','origin','+refs/heads/main:refs/remotes/origin/main',cwd=root)
        with tempfile.TemporaryDirectory(prefix='boat24-receipts-') as tmp:
            work=Path(tmp)/'checkout';git('worktree','add','--detach',str(work),'origin/main',cwd=root)
            try:
                source=git('rev-parse','HEAD',cwd=work);index_path=work/'omura/docs/boat24_full_index.json';index=json.loads(index_path.read_text())
                current=json.loads(download(base+'main/omura/docs/boat24_full_index.json'))
                # Confirm the public current index points to this exact view.
                day=dt.datetime.now(JST).date().isoformat();entry=index.get('days',{}).get(day);public=current.get('days',{}).get(day)
                if entry and public and entry.get('view_path')==public.get('view_path') and entry.get('view_sha256')==public.get('view_sha256'):
                    path=entry.get('view_path','')
                    if not re.fullmatch(r'day_views/\d{4}-\d{2}-\d{2}-[a-f0-9]{16}\.json',path):raise ValueError('Unversioned public view cannot establish receipt')
                    url=base+source+'/omura/docs/'+path;raw=download(url);digest=hashlib.sha256(raw).hexdigest()
                    if digest!=entry.get('view_sha256'):raise ValueError('Public day view digest mismatch')
                    view=json.loads(raw);observed=dt.datetime.now(JST).isoformat();archives=read_history(work/'omura/docs'/entry['archive_path'])['records']
                    proof={'source_commit':source,'view_url':url,'sha256':digest,'index_confirmed_url':base+'main/omura/docs/boat24_full_index.json'}
                    pending.append((view,archives,observed,proof))
                target=work/PATH;doc=json.loads(target.read_text()) if target.exists() else {}
                for view,archives,observed,proof in pending:doc=update(doc,view,archives,observed,proof)
                # Settle/finalize old observed dates using local immutable data,
                # without creating any publication evidence for those dates.
                now=dt.datetime.now(JST).isoformat()
                if doc.get('protocol',{}).get('started_at'):
                    for old_day,catalog in index.get('catalogs',{}).items():
                        if old_day<day:doc=update(doc,{'catalog':catalog},{},now,{})
                for prior in sorted({r['race_code'][:8] for r in doc.get('records',{}).values() if (r.get('decision') or {}).get('state')!='historical_unverified'}):
                    key=prior[:4]+'-'+prior[4:6]+'-'+prior[6:];e=index.get('days',{}).get(key)
                    if not e:continue
                    ledger=read_history(work/'omura/docs'/e['archive_path'])
                    doc=update(doc,{'catalog':ledger.get('catalog',{})},ledger.get('records',{}),now,{})
                if not doc: return
                index['decision_report']=report(doc);index['updated_at']=now
                atomic_write(target,doc);atomic_write(index_path,index)
                git('add',PATH,'omura/docs/boat24_full_index.json',cwd=work)
                if not git('diff','--cached','--name-only',cwd=work):return
                git('-c','user.name=github-actions[bot]','-c','user.email=41898282+github-actions[bot]@users.noreply.github.com','commit','-m','Record public observations and frozen two-minute decisions',cwd=work)
                if subprocess.run(['git','push','origin','HEAD:main'],cwd=work).returncode==0:
                    print('Prospective decisions:',json.dumps(index['decision_report']['counts']),flush=True);return
            finally:git('worktree','remove','--force',str(work),cwd=root)
    raise RuntimeError('Public decision receipts could not be published; no timestamps backdated')
