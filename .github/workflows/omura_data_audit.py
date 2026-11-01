"""Audit live BoatraceCSV data schemas and availability on GitHub Actions."""
import csv, io, json, urllib.request, urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path
JST=timezone(timedelta(hours=9))
today=datetime.now(JST).date()
DATASETS={
 'race_cards':'programs/race_cards',
 'waku10':'programs/waku10',
 'motor_history':'programs/motor_history',
 'motor_stats':'programs/motor_stats',
 'exhibition':'previews/tkz',
 'start_exhibition':'previews/stt',
 'weather':'previews/sui',
 'original_exhibition':'previews/original_exhibition',
 'odds_3t':'previews/od3',
 'realtime_results':'results/realtime',
 'payouts':'results/payouts',
}

def probe(path,date):
 url=f'https://boatracecsv.github.io/data/{path}/{date:%Y/%m/%d}.csv'
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0 OmuraDataAudit/1.0'})
  with urllib.request.urlopen(req,timeout=20) as resp:
   raw=resp.read()
  content=raw.decode('utf-8-sig')
  reader=csv.DictReader(io.StringIO(content))
  headers=reader.fieldnames or []
  count=0; omura=0; examples=[]
  for row in reader:
   count+=1
   code=row.get('レースコード','')
   venue=row.get('場コード',row.get('レース場コード',''))
   if (len(code)>=10 and code[8:10]=='24') or str(venue).strip().zfill(2)=='24':
    omura+=1
    if len(examples)<2: examples.append({k:v for k,v in row.items() if v not in ('',None) and ('艇1_' in k or k in ('レースコード','場コード','レース場コード','1着_艇番','2着_艇番','3着_艇番'))})
  return {'status':'ok','url':url,'rows':count,'omura_rows':omura,'headers':headers,'examples':examples,'bytes':len(raw)}
 except Exception as e:
  return {'status':'error','url':url,'error':str(e)[:350]}

def main():
 dates=[today-timedelta(days=i) for i in range(0,8)]
 out={'generated_at':datetime.now(JST).isoformat(),'dates':{},'note':'Data audit only. No prediction or accuracy claims.'}
 for date in dates:
  day={}
  for name,path in DATASETS.items():
   if date!=today and date!=today-timedelta(days=1) and name not in ('race_cards','exhibition','weather','realtime_results','payouts'):
    continue
   print(date,name,flush=True)
   day[name]=probe(path,date)
  out['dates'][date.isoformat()]=day
 target=Path('omura/docs/data_audit.json');target.parent.mkdir(parents=True,exist_ok=True)
 target.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Saved',target,'ok:',sum(v['status']=='ok' for d in out['dates'].values() for v in d.values()))
if __name__=='__main__':main()
