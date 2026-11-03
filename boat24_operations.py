"""Complete daily race catalog and explicit collection health; no backfilled forecasts."""
import datetime as dt
import os
from boat24_context import deadline
from boat24_integrity import JST,timeparse

def catalog(data,records,now):
 venues=sorted({int(c[8:10]) for k in ('cards','title') for c in data.get(k,{}) if len(c)==12 and c.isdigit() and c[:8]==now.strftime('%Y%m%d') and 1<=int(c[8:10])<=24})
 out={}
 for venue in venues:
  for race in range(1,13):
   code=now.strftime('%Y%m%d')+f'{venue:02d}{race:02d}';title=data.get('title',{}).get(code,{});known=bool(data.get('cards',{}).get(code) or title)
   limit=next((deadline(data.get(k,{}).get(code),now.date().isoformat()) for k in ('odds','ex','st','title') if deadline(data.get(k,{}).get(code),now.date().isoformat())),None)
   rec=records.get(code);state='saved' if rec else 'waiting_initial'
   if not known:state='program_unconfirmed'
   elif title.get('中止状態') or title.get('電話投票締切予定') in ('中止','順延'):state='cancelled'
   elif not limit:state='cutoff_unknown' if not rec else 'saved'
   elif not rec and now>=limit-dt.timedelta(minutes=2):state='closed_no_forecast'
   if rec and rec.get('result'):state='settled'
   elif rec and limit and now>=limit:state='result_pending'
   out[code]={'race_code':code,'venue':venue,'race':race,'cutoff':limit.isoformat() if limit else None,'state':state,'program_confirmed':known,'has_forecast':bool(rec)}
 return out

def health(data,catalog,errors,now):
 counts={k:len(data.get(k,{}) or {}) for k in ('cards','title','ex','st','weather','odds','results','payouts')}
 missing=[c for c,r in catalog.items() if r['state'] in ('waiting_initial','cutoff_unknown')]
 return {'attempt_at':now.isoformat(),'successful_collection_at':now.isoformat() if counts['cards'] and counts['title'] else None,'state':'degraded' if errors or missing or not counts['cards'] or not counts['title'] else 'ok','source_counts':counts,'source_errors':dict(errors),'missing_forecasts':missing,'run_url':('https://github.com/'+os.environ['GITHUB_REPOSITORY']+'/actions/runs/'+os.environ['GITHUB_RUN_ID']) if os.environ.get('GITHUB_RUN_ID') else None,'stale_after_minutes':12,'schedule_note':'GitHub Actions scheduled runs can be delayed or dropped; timestamps are monitored, execution is not guaranteed.'}
