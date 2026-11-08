"""One bounded update window with repeated collection and one commit per capture."""
import argparse
import datetime as dt
import json
import os
import time
from pathlib import Path
from boat24_integrity import JST,atomic_write
from boat24_history_io import history_path,read_history,write_history
from boat24_migration import preserve_collection_during_rebuild

def _main(seconds=180):
 import boat24_daily,boat24_compare,boat24_full_update,boat24_full_publish
 start=time.monotonic();attempt=0
 while True:
  if attempt and dt.datetime.now(JST).hour<7:break
  tick=time.monotonic();attempt+=1
  legacy=dt.datetime.now(JST).hour>=8 and os.environ.get('BOAT24_SKIP_LEGACY')!='1'
  legacy_error=None
  if legacy:
   try:boat24_daily.main();boat24_compare.main()
   except Exception as exc:
    legacy=False;legacy_error=str(exc);print('Legacy collector failed; continue new forecasts:',legacy_error,flush=True)
  try:
   with preserve_collection_during_rebuild(boat24_full_update.MODEL,__import__('boat24_context').VERSION):boat24_full_update.main()
  except Exception as exc:
   # Publish the last saved observation even for short scheduled cycles.
   # The failed collector remains an error, never a false successful run.
   today=dt.datetime.now(JST).date().isoformat();dayfile=history_path(boat24_full_update.DIRECTORY,today)
   if dayfile.exists():
    ledger=read_history(dayfile);h=ledger.setdefault('health',{});h.update({'state':'degraded','attempt_at':dt.datetime.now(JST).isoformat(),'collection_mode':'live_watch'});h.setdefault('source_errors',{})['collector']=str(exc);dayfile=write_history(dayfile,ledger)
    # A failed collector must still publish the retained observation.
    # Reading the index here served no purpose and could fail recovery.
    atomic_write(boat24_full_update.MANIFEST,{'paths':[str(dayfile)],'index':str(boat24_full_update.INDEX)})
    try:
     boat24_full_publish.main()
    except Exception as publish_exc:
     # Do not mask the collector failure with a secondary recovery error.
     print('Saved forecast recovery publication failed:',str(publish_exc),flush=True)
   print('Live capture failed; retry while retaining history:',str(exc),flush=True)
   if seconds<3600 or time.monotonic()-start+60>=seconds:raise
   time.sleep(30);continue
  if seconds>=3600:
   today=dt.datetime.now(JST).date().isoformat();dayfile=history_path(boat24_full_update.DIRECTORY,today);ledger=read_history(dayfile);ledger.setdefault('health',{})['collection_mode']='live_watch';dayfile=write_history(dayfile,ledger)
  if legacy_error:
   today=dt.datetime.now(JST).date().isoformat();dayfile=history_path(boat24_full_update.DIRECTORY,today);ledger=read_history(dayfile);ledger.setdefault('health',{}).setdefault('source_errors',{})['legacy_collector']=legacy_error;ledger['health']['state']='degraded';dayfile=write_history(dayfile,ledger)
  manifest=json.loads(boat24_full_update.MANIFEST.read_text())
  if not isinstance(manifest,dict) or not isinstance(manifest.get('paths'),list) or not isinstance(manifest.get('index'),str):
   raise ValueError('Forecast collection manifest is invalid; publication stopped safely')
  if legacy:
   for item in ('omura/docs/boat24_ledger.json','omura/docs/boat24_comparison.json'):
    if Path(item).is_file() and item not in manifest['paths']:
     manifest['paths'].append(item)
  atomic_write(boat24_full_update.MANIFEST,manifest)
  boat24_full_publish.main()
  if time.monotonic()-start+60>=seconds:
   if legacy_error:
    # The independent new-forecast pipeline has already published successfully.
    # A legacy-only failure is recorded as degraded health above; do not block
    # the downstream site verification or another near-cutoff collection.
    print('Legacy collector degraded but new forecasts published:',legacy_error,flush=True)
   break
  print('Next collection in 60 seconds; capture',attempt,dt.datetime.now(JST).isoformat(),flush=True)
  time.sleep(max(1,60-(time.monotonic()-tick)))

def main(seconds=180):
 from boat24_live import worker
 with worker():_main(seconds)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=180);main(p.parse_args().seconds)
