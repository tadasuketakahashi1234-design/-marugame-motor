"""Verified official identity supplements. Unknowns remain explicitly unknown."""
import datetime as dt
import http.cookiejar
import re
import json
from pathlib import Path
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from boat24_integrity import JST,atomic_write,timeparse
CACHE=Path('omura/docs/boat24_identity_cache.json')


def read(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'boat24-verifiable-inputs/4'}),timeout=12) as r:return r.read().decode('cp932')

def motor_identity(venue,now):
 base=f'https://race.boatcast.jp/hp_txt/{venue:02d}/';period=read(base+f'bc_mst_{venue:02d}.txt').strip()
 if not re.fullmatch(r'\d{8}',period):raise ValueError('Invalid motor period response')
 date=dt.datetime.strptime(period,'%Y%m%d').date()
 if date>now.date():raise ValueError('Future motor period')
 url=base+f'bc_mdc_{period}_{venue:02d}.txt';rows=[]
 for line in read(url).splitlines():
  a=line.split('\t')
  if len(a)<33 or a[0]!=period or not a[1].isdigit() or int(a[1])!=venue or not a[2].isdigit():continue
  # Identity only: current rolling totals cannot be imported into historical training.
  rows.append({'記録日':now.date().isoformat(),'モーター期起算日':date.isoformat(),'場コード':str(venue),'モーター番号':str(int(a[2])),'identity_source':url,'identity_observed_at':now.isoformat()})
 if not rows:raise ValueError('No independently verified motor rows')
 return rows

def parse_filtered_identity(html,rid,sex):
 # Require echoed exact ID range, selected sex, and a profile link matching both.
 for suffix in ('Left','Right'):
  if not re.search(r'name="[^"]*:inToban'+suffix+r'"[^>]*value="'+rid+r'"',html):return False
 select=re.search(r'<select[^>]*name="[^"]*:TDATP311A_6"[^>]*>(.*?)</select>',html,re.S)
 if not select or not re.search(r'<option\s+value="'+sex+r'"\s+selected="selected"',select[1]):return False
 return bool(re.search(r'href="/owpc/pc/data/racersearch/profile\?toban='+rid+r'&amp;toban_left='+rid+r'&amp;toban_right='+rid+r'&amp;sexval='+sex+r'"',html))

def racer_identity(rid):
 url='https://www.boatrace.jp/owpc/pc/data/racersearch/index';op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));op.open(url,timeout=12).read()
 for sex,label in [('1','male'),('2','female')]:
  values={'TDATP310A_2':'TDATP310A_2','inBoatracerName':'','inTobanLeft':rid,'inTobanRight':rid,'inCultivationTerm':'','TDATP310A_3':'SELECTALL','TDATP310A_4':'SELECTALL','TDATP310A_5':'SELECTALL','TDATP310A_6':sex,'TDATP310A_7':''}
  params={(k if k=='TDATP310A_2' else 'TDATP310A_2:'+k):v for k,v in values.items()};params['javax.faces.ViewState']='stateless'
  with op.open(urllib.request.Request(url,data=urllib.parse.urlencode(params).encode(),headers={'Referer':url}),timeout=12) as r:html=r.read().decode()
  if parse_filtered_identity(html,rid,sex):return {'sex':label,'source':url,'verification':'exact_registration_range_and_echoed_sex_filter','observed_at':dt.datetime.now(JST).isoformat()}
 return None

def supplement(data,registry,now):
 from boat24_context import motor_key
 import copy
 cache=json.loads(CACHE.read_text()) if CACHE.exists() else {'records':{},'motors':{},'failures':{}}
 registry=copy.deepcopy(registry);records=registry.setdefault('records',{});records.update(cache.get('records',{}));errors={};existing={motor_key(r['場コード'],r['モーター番号']) for r in data.get('motor_rows',[]) if r.get('場コード') and r.get('モーター番号')}
 wanted=set();ids=set()
 for code,card in data.get('cards',{}).items():
  for i in range(1,7):
   rid=str(card.get(f'艇{i}_登録番号',''));motor=card.get(f'艇{i}_モーター番号')
   if rid.isdigit() and rid not in records:ids.add(rid)
   if motor and motor_key(int(code[8:10]),motor) not in existing:wanted.add(int(code[8:10]))
 def job(pair):
  kind,key=pair
  try:
   cached=cache.get('motors',{}).get(str(key),{}) if kind=='motor' else {}
   observed=timeparse(cached.get('observed_at'))
   if observed and observed.date()==now.date() and dt.timedelta(0)<=now-observed<dt.timedelta(minutes=30):return pair,cached['rows'],None
   return pair,(motor_identity(key,now) if kind=='motor' else racer_identity(key)),None
  except Exception as e:return pair,None,str(e)[:160]
 jobs=[('motor',v) for v in sorted(wanted)]+[('sex',r) for r in sorted(ids)]
 jobs=[pair for pair in jobs if not (timeparse(cache.get('failures',{}).get(str(pair))) and dt.timedelta(0)<=now-timeparse(cache['failures'][str(pair)])<dt.timedelta(minutes=30))]
 jobs=[pair for pair in jobs if pair[0]=='motor']+[pair for pair in jobs if pair[0]=='sex'][:8]
 with ThreadPoolExecutor(max_workers=4) as pool:
  for (kind,key),value,error in pool.map(job,jobs):
   if error or not value:
    errors[f'{kind}:{key}']=error or 'official_identity_not_confirmed';cache.setdefault('failures',{})[str((kind,key))]=now.isoformat();continue
   if kind=='sex':records[key]=value;cache.setdefault('records',{})[key]=value
   else:
    cache.setdefault('motors',{})[str(key)]={'observed_at':value[0].get('identity_observed_at',now.isoformat()),'rows':copy.deepcopy(value)}
    periods={r['モーター期起算日'] for r in value}
    if len(periods)==1:
     period=next(iter(periods));assigned=set()
     for code,card in data.get('cards',{}).items():
      if int(code[8:10])!=key:continue
      for lane in range(1,7):
       motor=card.get(f'艇{lane}_モーター番号','')
       if str(motor).isdigit() and motor_key(key,motor) not in existing and motor_key(key,motor) not in assigned:
        value.append({'記録日':now.date().isoformat(),'場コード':str(key),'モーター番号':str(int(motor)),'モーター期起算日':period,'identity_source':f'https://race.boatcast.jp/hp_txt/{key:02d}/bc_mst_{key:02d}.txt','identity_scope':'official_venue_current_period_only; individual_totals_missing','identity_observed_at':now.isoformat(),'assignment_race_code':code});assigned.add(motor_key(key,motor))
    for row in value:
     k=motor_key(row['場コード'],row['モーター番号'])
     if k not in existing:data['motor_rows'].append(row);existing.add(k)
 cache['updated_at']=now.isoformat();atomic_write(CACHE,cache)
 data['registry']=registry;data['supplement_errors']=errors
 return registry
