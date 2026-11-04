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

def write_history(path,value):
    path=Path(path);plain=Path(str(path)[:-3]) if path.suffix=='.gz' else path
    size=len(json.dumps(value,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode())
    sharded=(plain.parent/day_key(plain)).exists() or size>COMPRESS_AFTER_BYTES
    if sharded:
        paths={}
        for code,record in value.get('records',{}).items():
            if not re.fullmatch(r'\d{12}',code) or code[:8]!=day_key(plain).replace('-',''):raise ValueError('Invalid history race code')
            name=day_key(plain)+'/'+code+'.json.gz';dest=plain.parent/name
            write_json(dest,record)
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

def compact_day(doc):
    from boat24_full_update import latest
    out={k:copy.deepcopy(v) for k,v in doc.items() if k!='records'};out['records']={};out['view_schema']=1
    for code,record in doc.get('records',{}).items():
        rec={k:copy.deepcopy(v) for k,v in record.items() if k not in ('revisions','result_history')}
        revisions=record.get('revisions',{});keep=set()
        chosen=latest(record)
        if chosen:
            keep.add(chosen['id'])
            from boat24_commentary import build as commentary
            rec['race_commentary']=commentary(chosen)
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
        rec['revision_count']=len(revisions)
        rec['revision_history']=[{k:s.get(k) for k in ('id','created_at','cutoff','phase','model','complete_inputs')} for s in sorted(revisions.values(),key=lambda s:(s['created_at'],s['id']))]
        out['records'][code]=rec
    return out

def write_view(history_file,doc):
    path=Path(history_file);dest=path.parent.parent/'day_views'/(day_key(path)+'.json')
    write_json(dest,compact_day(doc));return dest
