"""Merge immutable all-input daily histories into the latest main branch."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import tempfile
import time
from boat24_integrity import JST, atomic_write, timeparse, merge_ledgers
from boat24_full_update import MANIFEST, merge_day, build_index
from boat24_official import merge_cache
from boat24_quote_context import reject_obsolete_reprices
from boat24_model_io import read_json, write_json
from boat24_history_io import read_history,write_history,write_view,day_key,history_files,view_files


def git(*args,cwd=None):return subprocess.check_output(['git',*args],cwd=cwd,text=True).strip()


def _publish():
    root=Path(git('rev-parse','--show-toplevel'));manifest=json.loads((root/MANIFEST).read_text())
    local={p:(read_history(root/p) if day_key(p) and Path(p).parent.name=='full_history' else read_json(root/p)) for p in manifest['paths']}
    old_index=json.loads((root/manifest['index']).read_text())
    for attempt in range(5):
        git('fetch','origin','+refs/heads/main:refs/remotes/origin/main',cwd=root)
        with tempfile.TemporaryDirectory(prefix='boat24-full-publish-') as tmp:
            work=Path(tmp)/'checkout';git('worktree','add','--detach',str(work),'origin/main',cwd=root)
            try:
                paths=[]
                for path,incoming in local.items():
                    dest=work/path
                    if day_key(dest) and dest.parent.name=='full_history':
                        legacy=Path(str(dest)[:-3]) if dest.suffix=='.gz' else Path(str(dest)+'.gz')
                        source=dest if dest.exists() else legacy
                        remote=read_history(source) if source.exists() else {}
                    else:remote=read_json(dest) if dest.exists() else {}
                    if path.endswith('boat24_ledger.json'):
                        chosen=merge_ledgers(remote,incoming)
                    elif path.endswith('boat24_comparison.json'):
                        chosen=merge_ledgers(remote,incoming,key='records')
                    elif path.endswith('boat24_identity_cache.json'):
                        chosen=dict(incoming,records={**remote.get('records',{}),**incoming.get('records',{})})
                    elif path.endswith('boat24_official_results.json'):
                        from boat24_official_results import merge_cache as merge_results
                        chosen=merge_results(remote,incoming)
                    elif path.endswith('boat24_official_cache.json'):
                        chosen=merge_cache(remote,incoming)
                    elif path.endswith(('boat24_full_model.json','boat24_full_model.json.gz')):
                        a=remote.get('trained_through','');b=incoming.get('trained_through','')
                        chosen=remote if a>b or a==b and remote.get('generated_at','')>incoming.get('generated_at','') else incoming
                    else:chosen=merge_day(remote,reject_obsolete_reprices(remote,incoming))
                    if day_key(dest) and dest.parent.name=='full_history':
                        original=dest;had_original=original.exists()
                        cache_dir=dest.parent.parent/'day_views';before_views=set(cache_dir.glob(day_key(dest)+'-*.json'))
                        dest=write_history(dest,chosen);view=write_view(dest,chosen)
                        removed_views=before_views-set(cache_dir.glob(day_key(dest)+'-*.json'))
                        paths.extend([str(p.relative_to(work)) for p in history_files(dest)]+[str(p.relative_to(work)) for p in view_files(dest)]+[str(p.relative_to(work)) for p in removed_views])
                        if had_original and not original.exists():paths.append(str(original.relative_to(work)))
                    else:write_json(dest,chosen);paths.append(path)
                index=build_index(work/'omura/docs/full_history',dt.datetime.now(JST))
                for key in ('training','diagnostics','backfill_cursor','recovery'):
                    if key in old_index:index[key]=old_index[key]
                atomic_write(work/manifest['index'],index);paths.append(manifest['index'])
                git('add','-A','--',*paths,cwd=work)
                if not git('diff','--cached','--name-only',cwd=work):print('All-input observations already saved');return
                git('-c','user.name=github-actions[bot]','-c','user.email=41898282+github-actions[bot]@users.noreply.github.com','commit','-m','Save all-input forecasts and immutable input revisions',cwd=work)
                if subprocess.run(['git','push','origin','HEAD:main'],cwd=work).returncode==0:
                    print('All-input model and daily history saved');return
            finally:git('worktree','remove','--force',str(work),cwd=root)
        time.sleep(2)
    raise SystemExit('All-input publication failed; local observations remain in the failure artifact')


def main():
    # Both collectors share the same Git common directory, including worktrees.
    # Only publication is serialized; odds retrieval and model work remain parallel.
    import fcntl
    root=Path(git('rev-parse','--show-toplevel'))
    common=Path(git('rev-parse','--git-common-dir',cwd=root))
    if not common.is_absolute():common=root/common
    with (common/'boat24-publication.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try:return _publish()
        finally:fcntl.flock(lock,fcntl.LOCK_UN)

if __name__=='__main__':main()
