"""Publish storage and settlement recovery independently of expensive model training."""
import datetime as dt
import json
from pathlib import Path
from boat24_integrity import JST,atomic_write,summarize
from boat24_history_io import day_paths,read_history,write_history,write_view
from boat24_full_update import DIRECTORY,INDEX,MANIFEST,build_index,settle
from boat24_offers import register_offers
from boat24_official_results import collect_results,CACHE
from boat24_settlement import settle_legacy

def main():
    now=dt.datetime.now(JST);paths=[];days=[(p,read_history(p)) for p in day_paths(DIRECTORY)]
    legacy_path=DIRECTORY.parent/'boat24_ledger.json';legacy=json.loads(legacy_path.read_text()) if legacy_path.exists() else {}
    codes={code for _,day in days for code,r in day.get('records',{}).items() if r.get('result')}
    codes|={code for code,r in legacy.get('predictions',{}).items() if r.get('result')}
    # Only known completed races. Never turn a future or absent forecast into a prediction.
    rows,errors=collect_results(codes,now,limit=240)
    changes=offers=0
    for path,day in days:
        for code,rec in day.get('records',{}).items():
            offers+=len(register_offers(rec));saved=rows.get(code);old=rec.get('result') or {}
            res=saved['result'] if saved else old.get('result_source');pay=saved['payout'] if saved else old.get('payout_source')
            # Preserve original course/weather fields when adding official proof.
            if saved:res={**old.get('result_source',{}),**res};pay={**old.get('payout_source',{}),**pay}
            changes+=settle(rec,res,pay,now)
        path=write_history(path,day);write_view(path,day);paths.append(str(path))
    for code,rec in legacy.get('predictions',{}).items():
        if code in rows:settle_legacy(rec,rows[code]['result'],rows[code]['payout'],now)
    if legacy:
        legacy['summary']=summarize(legacy['predictions']);legacy['summary_final']=summarize(legacy['predictions'],True)
        atomic_write(legacy_path,legacy);paths.append(str(legacy_path))
    before=json.loads(INDEX.read_text()) if INDEX.exists() else {};index=build_index(now=now)
    for key in ('training','diagnostics','backfill_cursor'):
        if key in before:index[key]=before[key]
    index['recovery']={'at':now.isoformat(),'settlement_changes':changes,'saved_offers':offers,'official_errors':errors,'official_confirmed':len(rows)}
    atomic_write(INDEX,index)
    if CACHE.exists():paths.append(str(CACHE))
    atomic_write(MANIFEST,{'paths':paths,'index':str(INDEX),'version':index['model']})
    print(json.dumps(index['recovery'],ensure_ascii=False),flush=True)
    import boat24_full_publish
    boat24_full_publish.main()

if __name__=='__main__':main()
