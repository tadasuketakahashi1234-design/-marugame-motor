"""Size-bounded history storage and small public day views.

Full immutable revisions stay in the archive. The browser reads only the
latest snapshots by default; compression is a storage change, not a rewrite.
"""
import copy
import json
from pathlib import Path
import re
from boat24_model_io import read_json,write_json

COMPRESS_AFTER_BYTES=16*1024*1024

def day_key(path):
    name=Path(path).name
    return name[:10] if re.fullmatch(r'\d{4}-\d{2}-\d{2}\.json(?:\.gz)?',name) else None

def day_paths(directory):
    found={}
    for p in sorted(Path(directory).glob('*.json*')):
        key=day_key(p)
        if key and (key not in found or p.suffix=='.gz'):found[key]=p
    return [found[k] for k in sorted(found)]

def history_path(directory,day):
    plain=Path(directory)/(day+'.json');zipped=Path(str(plain)+'.gz')
    return zipped if zipped.exists() else plain

def _read_archive(path):
    path=Path(path);value=read_json(path)
    storage=value.get('history_storage',{})
    if storage.get('schema')==2:
        records={}
        for code,name in storage['record_paths'].items():
            expected=day_key(path)+'/'+code+'.json.gz'
            if name!=expected or not re.fullmatch(r'\d{12}',code) or code[:8]!=day_key(path).replace('-',''):
                raise ValueError('Invalid archived record path')
            record=read_json(path.parent/name)
            if record.get('race_code')!=code:raise ValueError('Archive race code mismatch')
            records[code]=record
        value={k:v for k,v in value.items() if k!='history_storage'};value['records']=records
    return value

def read_history(path):
    path=Path(path);value=_read_archive(path)
    other=Path(str(path)[:-3]) if path.suffix=='.gz' else Path(str(path)+'.gz')
    if other.exists():
        from boat24_full_update import merge_day
        # A legacy collector may have written one final plain observation.
        a,b=_read_archive(other),value
        value=merge_day(a,b) if a.get('updated_at','')<=b.get('updated_at','') else merge_day(b,a)
    return value

def write_history(path,value,previous=None,changed_codes=None):
    path=Path(path);plain=Path(str(path)[:-3]) if path.suffix=='.gz' else path
    # A legacy plain/gzip fork may contribute revisions not yet in shards.
    if plain.exists() and Path(str(plain)+'.gz').exists():previous=None;changed_codes=None
    sharded=(plain.parent/day_key(plain)).exists()
    if not sharded:sharded=len(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())>COMPRESS_AFTER_BYTES
    if sharded:
        authoritative={}
        if (previous is not None or changed_codes is not None) and path.suffix!='.gz' and plain.exists() and not Path(str(plain)+'.gz').exists():
            storage=read_json(plain).get('history_storage',{})
            if storage.get('schema')==2:authoritative=storage.get('record_paths',{})
        paths={}
        for code,record in value.get('records',{}).items():
            if not re.fullmatch(r'\d{12}',code) or code[:8]!=day_key(plain).replace('-',''):raise ValueError('Invalid history race code')
            name=day_key(plain)+'/'+code+'.json.gz';dest=plain.parent/name
            unchanged=authoritative.get(code)==name and dest.exists() and ((previous is not None and previous.get('records',{}).get(code)==record) or (changed_codes is not None and code not in changed_codes))
            if not unchanged:write_json(dest,record)
            if dest.stat().st_size>=90*1024*1024:raise RuntimeError('One race archive exceeds safe publication size')
            paths[code]=name
        meta={k:v for k,v in value.items() if k!='records'}
        meta['history_storage']={'schema':2,'record_paths':paths,'revision_count':sum(len(r.get('revisions',{})) for r in value.get('records',{}).values())}
        write_json(plain,meta)
        if path!=plain and path.exists():path.unlink()
        return plain
    write_json(path,value);return path

def history_files(path):
    path=Path(path);value=read_json(path)
    return [path]+[path.parent/name for name in value.get('history_storage',{}).get('record_paths',{}).values()]

def compact_day(doc,cache_root=None):
    from boat24_full_update import latest
    out={k:copy.deepcopy(v) for k,v in doc.items() if k!='records'};out['records']={};out['view_schema']=1
    cache_path=(Path(cache_root) if cache_root is not None else Path.cwd())/'omura/docs/boat24_official_cache.json'
    cache=read_json(cache_path) if cache_path.exists() else {}
    for code,record in doc.get('records',{}).items():
        rec={k:copy.deepcopy(v) for k,v in record.items() if k not in ('revisions','result_history','collection_attempts','settlement_attempts')}
        rec['collection_attempt_count']=len(record.get('collection_attempts',{}));rec['settlement_attempt_count']=len(record.get('settlement_attempts',{}))
        revisions=record.get('revisions',{});keep=set()
        chosen=latest(record)
        if chosen:
            keep.add(chosen['id'])
            from boat24_commentary import build as commentary
            rec['race_commentary']=commentary(chosen)
            rec['boat_comparison']=__import__('boat24_boat_comparison').build(chosen,doc.get('records'))
            # Verified live observations are display-only. Never revise frozen
            # predictions, odds, purchase decisions or learning inputs.
            from boat24_live_observation import latest_verified
            observed=latest_verified(code,record,chosen)
            if not observed and cache.get('date')==code[:4]+'-'+code[4:6]+'-'+code[6:8]:
                from boat24_live_observation import verified_from_cache
                observed=verified_from_cache(code,cache,chosen.get('cutoff'))
            if observed:
                rec['latest_verified_entry']=observed
                for boat in rec['boat_comparison']['boats']:
                    lane=boat['lane']
                    course=observed['courses'].get(str(lane))
                    if course is not None:boat['course']=course
                    boat['exhibition_time']=observed.get('exhibition_times',{}).get(str(lane))
                    boat['exhibition_st']=observed.get('exhibition_starts',{}).get(str(lane))
                rec['boat_comparison']['entry_observed_at']=observed['observed_at']
                rec['boat_comparison']['entry_scope']='展示進入は直近の公式確認値（予想計算への使用とは別）'
        valid=[s for s in revisions.values() if s.get('evaluation_eligible')]
        if valid:keep.add(max(valid,key=lambda s:(s['created_at'],s['id']))['id'])
        plans=[s for s in valid if s.get('purchase_plan')]
        if plans:keep.add(max(plans,key=lambda s:(s['created_at'],s['id']))['id'])
        # Offer metadata retains every portfolio. Keep only the headline offer's
        # large input snapshot here; all other inputs are available per race.
        pointer=record.get('result',{}).get('selection_snapshot_id') if record.get('result') else None
        if pointer in revisions:keep.add(pointer)
        offers=sorted(record.get('offers',{}).values(),key=lambda o:(o['created_at'],o['snapshot_id']))
        if offers and offers[0]['snapshot_id'] in revisions:keep.add(offers[0]['snapshot_id'])
        fields=('id','created_at','computed_at','cutoff','evaluation_eligible','phase','complete_inputs','model','model_id','purchase_plan','refresh_kind','context_snapshot_at')
        rec['revisions']={k:{**{f:copy.deepcopy(revisions[k][f]) for f in fields if f in revisions[k]},'_details_compacted':True} for k in keep if k in revisions}
        from boat24_study import evidence
        for sid,public in rec['revisions'].items():
            proof=evidence(revisions[sid])
            if proof:public['study_evidence']=proof
        for s in rec['revisions'].values():
            if s.get('purchase_plan'):
                # Search frontiers stay in the full immutable archive. The
                # first screen needs quotes, stakes and checks, not every state.
                s['purchase_plan']={k:v for k,v in s['purchase_plan'].items() if k not in ('frontier','comparison_by_count')}
        rec['revision_count']=len(revisions)
        rec['revision_history']=[{k:s.get(k) for k in ('id','created_at','cutoff','phase','model','complete_inputs')} for s in sorted(revisions.values(),key=lambda s:(s['created_at'],s['id']))]
        out['records'][code]=rec
    return out

def write_view(history_file,doc,cache_root=None):
    import hashlib
    path=Path(history_file);day=day_key(path);directory=path.parent.parent/'day_views';dest=directory/(day+'.json')
    view=compact_day(doc,cache_root=cache_root);raw=json.dumps(view,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    digest=hashlib.sha256(raw).hexdigest();version=directory/(day+'-'+digest[:16]+'.json');pointer=directory/(day+'.pointer.json')
    try:
        old=read_json(pointer) if pointer.exists() else {}
    except (OSError,ValueError,TypeError):
        old={}
    if not isinstance(old,dict):old={}
    previous=old.get('previous_paths',[])
    if not isinstance(previous,list):previous=[]
    history=[]
    for name in [old.get('path'),*previous]:
        if isinstance(name,str) and re.fullmatch(re.escape(day)+r'-[0-9a-f]{16}\.json',name) and name!=version.name and (directory/name).is_file() and name not in history:history.append(name)
    # Keep the latest view plus two rollback versions. Full immutable forecast
    # history remains in full_history and is never pruned here.
    history=history[:2]
    write_json(version,view);write_json(dest,view)
    write_json(pointer,{'path':version.name,'sha256':digest,'previous_paths':history})
    # Display caches are expendable; all immutable inputs remain in full_history.
    for item in directory.glob(day+'-*.json'):
        if re.fullmatch(day+r'-[0-9a-f]{16}\.json',item.name) and item.name not in [version.name,*history]:item.unlink()
    return dest

def view_files(history_file):
    path=Path(history_file);day=day_key(path);directory=path.parent.parent/'day_views';pointer=directory/(day+'.pointer.json')
    info=read_json(pointer)
    name=info.get('path') if isinstance(info,dict) else None
    if not isinstance(name,str) or not re.fullmatch(re.escape(day)+r'-[0-9a-f]{16}\.json',name):
        raise ValueError('Invalid day view pointer for '+day)
    return [directory/(day+'.json'),pointer,directory/name]
