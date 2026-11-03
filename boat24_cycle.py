"""One bounded update window with repeated collection and one commit per capture."""
import argparse
import datetime as dt
import json
import time
from pathlib import Path
from boat24_integrity import JST,atomic_write

def main(seconds=180):
 import boat24_daily,boat24_compare,boat24_full_update,boat24_full_publish
 start=time.monotonic();attempt=0
 while True:
  attempt+=1
  legacy=dt.datetime.now(JST).hour>=8
  legacy_error=None
  if legacy:
   try:boat24_daily.main();boat24_compare.main()
   except Exception as exc:
    legacy=False;legacy_error=str(exc);print('Legacy collector failed; continue new forecasts:',legacy_error,flush=True)
  boat24_full_update.main()
  if legacy_error:
   today=dt.datetime.now(JST).date().isoformat();dayfile=boat24_full_update.DIRECTORY/(today+'.json');ledger=json.loads(dayfile.read_text());ledger.setdefault('health',{}).setdefault('source_errors',{})['legacy_collector']=legacy_error;ledger['health']['state']='degraded';atomic_write(dayfile,ledger)
  manifest=json.loads(boat24_full_update.MANIFEST.read_text());manifest['paths']+=(['omura/docs/boat24_ledger.json','omura/docs/boat24_comparison.json'] if legacy else []);atomic_write(boat24_full_update.MANIFEST,manifest)
  boat24_full_publish.main()
  if time.monotonic()-start+60>=seconds:
   if legacy_error:raise RuntimeError('Legacy collector failed; new forecasts were published with degraded health: '+legacy_error)
   break
  print('Next collection in 60 seconds; capture',attempt,dt.datetime.now(JST).isoformat(),flush=True)
  time.sleep(60)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--seconds',type=int,default=180);main(p.parse_args().seconds)
