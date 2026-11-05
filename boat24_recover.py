"""Publish storage and settlement recovery independently of expensive model training."""
import datetime as dt
import json
from boat24_integrity import JST,atomic_write,summarize,timeparse
from boat24_history_io import day_paths,day_key,read_history,write_history,write_view
from boat24_full_update import DIRECTORY,INDEX,MANIFEST,build_index,settle,latest
from boat24_offers import register_offers
from boat24_official_results import collect_results,CACHE
from boat24_settlement import settle_legacy

def publish(days,legacy,rows,errors,phase):
    now=dt.datetime.now(JST);paths=[];changes=offers=0
    legacy_path=DIRECTORY.parent/'boat24_ledger.json'
    for path,day in days:
        day_changes=0;dirty=set()
        for code,rec in day.get('records',{}).items():
            before_offers=dict(rec.get('offers',{}));offers+=len(register_offers(rec))
            if rec.get('offers',{})!=before_offers:dirty.add(code)
            saved=rows.get(code);old=rec.get('result') or {}
            res=saved['result'] if saved else old.get('result_source');pay=saved['payout'] if saved else old.get('payout_source')
            if saved:res={**old.get('result_source',{}),**res};pay={**old.get('payout_source',{}),**pay}
            pending_before=rec.get('result_pending_reason')
            if settle(rec,res,pay,now):day_changes+=1;dirty.add(code)
            if rec.get('result_pending_reason')!=pending_before:dirty.add(code)
        changes+=day_changes
        if day_changes:day['settlement_updated_at']=now.isoformat()
        pointer=path.parent.parent/'day_views'/(day_key(path)+'.pointer.json')
        if dirty or not pointer.exists():
            path=write_history(path,day,changed_codes=dirty);write_view(path,day);paths.append(str(path))
    legacy_changed=False
    for code,rec in legacy.get('predictions',{}).items():
        if code in rows:legacy_changed=settle_legacy(rec,rows[code]['result'],rows[code]['payout'],now) or legacy_changed
    if legacy and legacy_changed:
        legacy['summary']=summarize(legacy['predictions']);legacy['summary_final']=summarize(legacy['predictions'],True)
        atomic_write(legacy_path,legacy);paths.append(str(legacy_path))
    if not paths:
        print(json.dumps({'phase':phase,'unchanged':True,'official_errors':errors,'official_confirmed':len(rows)}),flush=True)
        return
    before=json.loads(INDEX.read_text()) if INDEX.exists() else {};index=build_index(now=now)
    for key in ('training','diagnostics','backfill_cursor'):
        if key in before:index[key]=before[key]
    index['recovery']={'at':now.isoformat(),'phase':phase,'settlement_changes':changes,'saved_offers':offers,'official_errors':errors,'official_confirmed':len(rows)}
    atomic_write(INDEX,index)
    if CACHE.exists():paths.append(str(CACHE))
    atomic_write(MANIFEST,{'paths':paths,'index':str(INDEX),'version':index['model']})
    print(json.dumps(index['recovery'],ensure_ascii=False),flush=True)
    import boat24_full_publish
    boat24_full_publish.main()

def main(today_only=False):
    today=dt.datetime.now(JST).date().isoformat()
    paths=[p for p in day_paths(DIRECTORY) if not today_only or day_key(p)==today]
    days=[(p,read_history(p)) for p in paths]
    legacy_path=DIRECTORY.parent/'boat24_ledger.json';legacy=json.loads(legacy_path.read_text()) if legacy_path.exists() and not today_only else {}
    # Restore small views and saved offers first, even if official HTTP stalls.
    publish(days,legacy,{}, {},'storage_and_saved_offers')
    codes={code for _,day in days for code,r in day.get('records',{}).items() if r.get('result')}
    codes|={code for code,r in legacy.get('predictions',{}).items() if r.get('result')}
    now=dt.datetime.now(JST);due=[]
    for _,day in days:
        for code,rec in day.get('records',{}).items():
            cut=timeparse((latest(rec) or {}).get('cutoff'))
            if not rec.get('result') and cut and now>=cut+dt.timedelta(seconds=90):due.append((cut,code))
    priority=[code for cut,code in sorted(due,reverse=True)]
    rows,errors=collect_results(codes|set(priority),now,limit=24,priority_codes=priority)
    publish(days,legacy,rows,errors,'official_settlements')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--today-only',action='store_true')
    main(today_only=p.parse_args().today_only)
