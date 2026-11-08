"""Strict official-source joins. Missing observations never imply no maintenance."""
import datetime as dt
import html
import json
import math
from pathlib import Path
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from boat24_integrity import JST,atomic_write
CACHE=Path('omura/docs/boat24_official_cache.json')
BASE='https://www.marugameboat.jp'
TIDE=BASE+'/01shiomi/shiomi.htm'
def text(s):return re.sub(r'\s+',' ',html.unescape(re.sub('<[^>]*>',' ',s))).strip()
def cells(row):return [text(c) for c in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>',row,re.S|re.I)]
def get(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'boat24-public-data/3.0'}),timeout=12) as r:
  raw=r.read();encoding=r.headers.get_content_charset() or ('utf-8' if b'utf-8' in raw[:3000].lower() else 'cp932')
 return raw.decode(encoding,errors='replace')
def parse_tides(doc):
 year=re.search(r'class="ym"[^>]*>\s*(\d{4})\.(\d{1,2})\.',doc)
 if not year:return {}
 y,month=map(int,year.groups());out={}
 for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',doc,re.S|re.I):
  c=cells(row)
  if len(c)!=5:continue
  match=re.fullmatch(r'(\d{1,2})/\s*(\d{1,2})',c[0])
  if not match or not all(re.fullmatch(r'\d{1,2}:\d{2}',v) for v in c[2:4]):continue
  m,d=map(int,match.groups());yr=y+(1 if month==12 and m==1 else 0)
  try:day=dt.date(yr,m,d).isoformat()
  except ValueError:continue
  out[day]={'high':c[2],'low':c[3],'cycle':c[4]}
 return out

def parse_comments(doc,code,card):
 # The rolling official URL must prove both race date and race number.
 if not re.search('raceDate='+code[:8]+r'(?:&|&amp;)',doc) or not re.search('raceNumber='+str(int(code[-2:]))+r'(?:&|&amp;)',doc):return {}
 out={}
 for table in re.findall(r'<table\b[^>]*>(.*?)</table>',doc,re.S|re.I):
  if '選手コメント' not in table:continue
  for body in re.findall(r'<tbody\b[^>]*>(.*?)</tbody>',table,re.S|re.I):
   ids=re.findall(r'toban=(\d+)',body);c=cells(body)
   if not ids or len(c)<3:continue
   try:lane=int(c[0])
   except ValueError:continue
   if 1<=lane<=6 and str(card.get(f'艇{lane}_登録番号'))==ids[0]:
    out[str(lane)]={'racer':ids[0],'comment':c[2]}
 return out if len(out)==6 else {}

def parse_before(doc,code,card):
 # Reject a different date selected by a redirect or a stale race selector.
 if not re.search(r'(?:hd=|name="hd" value=")'+code[:8],doc):return {}
 active=re.search(r'<li class="is-active2">(.*?)</li>',doc,re.S)
 expected=f'{int(code[4:6])}月{int(code[6:8])}日'
 if not active or expected not in text(active[1]):return {}
 selected=False
 for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',doc,re.S|re.I):
  td=re.findall(r'<td\b([^>]*)>(.*?)</td>',row,re.S|re.I)
  if len(td)==13 and '締切予定時刻' in text(td[0][1]):
   selected='is-activeColor1' in td[int(code[-2:])][0]
 if not selected:return {}
 out={}
 for body in re.findall(r'<tbody\b[^>]*>(.*?)</tbody>',doc,re.S|re.I):
  lane=re.search(r'class="is-boatColor([1-6])\b',body);racer=re.search(r'toban=(\d+)',body)
  row=re.search(r'<tr\b[^>]*>(.*?)</tr>',body,re.S|re.I)
  if not lane or not racer or not row:continue
  lane=lane[1];rid=racer[1];c=cells(row[1])
  if str(card.get(f'艇{lane}_登録番号'))!=rid or len(c)<8:continue
  out[lane]={'racer':rid,'propeller':c[6],'parts':c[7]}
 return out if len(out)==6 else {}

def comment_signals(comment):
 # Bounded, explicit research rules, not an LLM or a calibrated judgement.
 # Separate clauses and negations: 「良くない」 must not count as positive.
 s=re.sub('悪く(?:は)?ない','良い',text(comment));pos=neg=0
 for clause in re.split('[。！？、]',s):
  if re.search('分から|わから|どうか|不明',clause):continue
  if re.search('良くな[いかっ]|よくな[いかっ]|悪|弱|重い|滑|足りない|下が|劣勢|乗り[づず]ら',clause):neg+=1
  elif re.search('良[いかっ]|いい|上向|上位|抜群|伸びる|乗りやす|力強|悪くない',clause):pos+=1
 return max(-1,min(1,(pos-neg)/2))

def tide_features(row,cutoff):
 if not row:return {}
 high=dt.datetime.combine(cutoff.date(),dt.time.fromisoformat(row['high']),JST)
 low=dt.datetime.combine(cutoff.date(),dt.time.fromisoformat(row['low']),JST)
 f={'満潮まで分':(high-cutoff).total_seconds()/60,'干潮まで分':(low-cutoff).total_seconds()/60}
 for name in ('大潮','中潮','小潮','長潮','若潮'):f['潮周り_'+name]=int(row['cycle']==name)
 # Only infer rising/falling between the two published extrema, never outside.
 if low<=cutoff<=high:f['上げ潮']=1.;f['下げ潮']=0.
 elif high<=cutoff<=low:f['上げ潮']=0.;f['下げ潮']=1.
 return f

def collect(codes,cards,now,titles=None):
 cache=json.loads(CACHE.read_text()) if CACHE.exists() else {'schema':1,'races':{}}
 if cache.get('date')!=now.date().isoformat():cache={'schema':1,'date':now.date().isoformat(),'races':{}}
 errors={}
 from boat24_comments import VENUE_SOURCES,parse_venue_comments,parse_pitreport,decorate,race_flags,parse_zenken
 import hashlib
 venue_comments={};comment_sources={}
 titles=titles or {}
 for venue in sorted({int(c[8:10]) for c in codes}):
  key=str(venue);stored=cache.get('zenken_lists',{}).get(key,{})
  if stored.get('date')==now.strftime('%Y%m%d') and stored.get('rows'):continue
  title=next((titles.get(c,{}).get('タイトル') for c in codes if int(c[8:10])==venue and titles.get(c,{}).get('タイトル')),None)
  if not title:continue
  u=f'https://www.boatrace.jp/owpc/pc/race/rankingmotor?hd={now.strftime("%Y%m%d")}&jcd={venue:02d}'
  try:
   doc=get(u);rows=parse_zenken(doc,venue,now.strftime('%Y%m%d'),title)
   cache.setdefault('zenken_lists',{})[key]={'date':now.strftime('%Y%m%d'),'rows':rows,'source':u,'observed_at':dt.datetime.now(JST).isoformat(),'body_sha256':hashlib.sha256(doc.encode()).hexdigest()}
  except Exception as e:errors['zenken_'+key]=str(e)
 for venue in sorted({int(c[8:10]) for c in codes} & set(VENUE_SOURCES)):
  u=VENUE_SOURCES[venue].format(day=now.strftime('%Y%m%d'))
  saved=cache.get('comment_lists',{}).get(str(venue),{});at=__import__('boat24_integrity').timeparse(saved.get('observed_at'))
  if at and now-at<dt.timedelta(minutes=10):
   venue_comments[venue]=saved.get('comments',{});comment_sources[venue]=saved.get('source',u);continue
  try:
   doc=get(u);rows=parse_venue_comments(doc,venue,now.strftime('%Y%m%d'));observed=dt.datetime.now(JST).isoformat()
   cache.setdefault('comment_lists',{})[str(venue)]={'comments':rows,'observed_at':observed,'source':u,'body_sha256':hashlib.sha256(doc.encode()).hexdigest()}
   venue_comments[venue]=rows;comment_sources[venue]=u
  except Exception as e:errors['comments_'+str(venue)]=str(e)
 from boat24_water import download,parse_venue_weather
 def surface_job(venue):
  u=f'https://race.boatcast.jp/m_txt/{venue:02d}/bc_sui_{now.strftime("%Y%m%d")}_{venue:02d}.txt'
  try:
   body,_=download(u+'?v='+str(int(dt.datetime.now(JST).timestamp()//30)));row=parse_venue_weather(body,venue,dt.datetime.now(JST));row['source']=u;return str(venue).zfill(2),row,None
  except Exception as e:return str(venue).zfill(2),None,str(e)
 with ThreadPoolExecutor(max_workers=6) as pool:
  for venue,row,error in pool.map(surface_job,sorted({int(c[8:10]) for c in codes})):
   if row:cache.setdefault('venue_weather',{})[venue]=row
   else:errors['weather_'+venue]=error
 try:cache['tides']=parse_tides(get(TIDE));cache['tide_observed_at']=dt.datetime.now(JST).isoformat();cache['tide_url']=TIDE
 except Exception as e:errors['tide']=str(e)
 def job(code):
  venue=int(code[8:10]);race=int(code[-2:]);record={'observed_at':dt.datetime.now(JST).isoformat(),'sources':{}}
  zr=cache.get('zenken_lists',{}).get(str(venue),{})
  record['zenken']={str(i):{**zr['rows'][str(cards[code].get(f'艇{i}_登録番号'))],'observed_at':zr['observed_at'],'source':zr['source']} for i in range(1,7) if str(cards[code].get(f'艇{i}_登録番号')) in zr.get('rows',{})}
  u=f'https://www.boatrace.jp/owpc/pc/race/beforeinfo?hd={code[:8]}&jcd={venue:02d}&rno={race}'
  try:
   doc=get(u);record['before']=parse_before(doc,code,cards[code]);record['sources']['maintenance']=u
   record['race_flags']=race_flags(doc,code,cards[code]);record['before_body_sha256']=hashlib.sha256(doc.encode()).hexdigest()
   record['live_previews']=parse_live_previews(doc,code,cards[code],dt.datetime.now(JST).isoformat())
   for row in record['live_previews'].values():row['source_url']=u
  except Exception as e:record['maintenance_error']=str(e)
  if venue==15:
   u=BASE+f'/asp/kyogi/15/pc/yoso05{race:02d}.htm'
   try:
    doc=get(u);record['comments']=decorate(parse_comments(doc,code,cards[code]),u,dt.datetime.now(JST).isoformat(),code[:8]);record['sources']['comments']=u;record['comments_body_sha256']=hashlib.sha256(doc.encode()).hexdigest()
   except Exception as e:record['comments_error']=str(e)
  elif venue in venue_comments:
   rows={str(lane):venue_comments[venue][str(cards[code].get(f'艇{lane}_登録番号'))] for lane in range(1,7) if str(cards[code].get(f'艇{lane}_登録番号')) in venue_comments[venue]}
   record['comments']=decorate(rows,comment_sources[venue],cache['comment_lists'][str(venue)]['observed_at'],code[:8]);record['sources']['comments']=comment_sources[venue]
  # The national official report is supported across all 24 venues, but is
  # published for selected races only. Absence is not a neutral comment.
  if not record.get('comments'):
   u=f'https://www.boatrace.jp/owpc/pc/race/pitreport?hd={code[:8]}&jcd={venue:02d}&rno={race}'
   try:
    doc=get(u);record['comments']=decorate(parse_pitreport(doc,code,cards[code]),u,dt.datetime.now(JST).isoformat(),code[:8]);record['sources']['comments']=u;record['comments_body_sha256']=hashlib.sha256(doc.encode()).hexdigest()
    record['comments_status']='available' if record['comments'] else 'not_published_or_not_verified'
   except Exception as e:record['comments_error']=str(e)
  if venue==15:
   u=BASE+f'/replay/replay_movie/tenji/{code[:8]}{race:02d}.htm'
   try:
    doc=get(u)
    if re.search('raceDate='+code[:8]+r'(?:&|&amp;)',doc):
     found=re.findall(r'(北西|北東|南西|南東|北|南)\s*[（(](?:向い風|向かい風|追い風)[）)]',text(doc))
     if found:record['wind_direction_text']=found[-1];record['sources']['wind']=u
   except Exception as e:record['wind_error']=str(e)
  record['observed_at']=dt.datetime.now(JST).isoformat()
  return code,record
 with ThreadPoolExecutor(max_workers=6) as pool:
  for code,rec in pool.map(job,codes):
   old=cache['races'].get(code,{})
   for key in ('before','comments','wind_direction_text','live_previews','race_flags','zenken'):
    if rec.get(key):rec[key+'_observed_at']=rec['observed_at']
    elif old.get(key):
     rec[key]=old[key];rec[key+'_observed_at']=old.get(key+'_observed_at',old.get('observed_at'))
   # A later partial official response must not erase previously verified
   # exhibition fields for the same race. Keep each kind independently.
   if old.get('live_previews'):
    merged=dict(old['live_previews'])
    merged.update(rec.get('live_previews') or {})
    rec['live_previews']=merged
   cache['races'][code]=rec
   for key in ('comments_error','maintenance_error'):
    if rec.get(key):errors[code+'_'+key]=rec[key]
 cache['updated_at']=dt.datetime.now(JST).isoformat();cache['errors']=errors;atomic_write(CACHE,cache)
 return cache

def attach(features,code,cutoff,cache,model_generated_at=None):
 from boat24_context import number
 from boat24_integrity import timeparse
 observed=timeparse(cache.get('tide_observed_at'));rec=cache.get('races',{}).get(code,{})
 safe=timeparse(rec.get('observed_at')) and timeparse(rec['observed_at'])<cutoff
 for lane,f in enumerate(features,1):
  f['tide']={};f.setdefault('maintenance',{});f['comments']={};f['wind']={}
  if int(code[8:10])==15 and observed and observed<cutoff:
   f['tide']=tide_features(cache.get('tides',{}).get(cutoff.date().isoformat()),cutoff)
  if safe:
   before_time=timeparse(rec.get('before_observed_at',rec.get('observed_at')))
   comments_time=timeparse(rec.get('comments_observed_at',rec.get('observed_at')))
   b=rec.get('before',{}).get(str(lane)) if before_time and before_time<cutoff else None
   if b is not None:
    f['maintenance']['プロペラ新']=int('新' in b.get('propeller',''));f['maintenance']['部品交換あり']=int(bool(b.get('parts')))
   c=rec.get('comments',{}).get(str(lane)) if comments_time and comments_time<cutoff else None
   if c and c.get('comment'):f['comments']['コメント気配']=comment_signals(c['comment'])
 return rec

def merge_cache(remote,incoming):
 import copy
 if remote.get('date','')!=incoming.get('date',''):
  return copy.deepcopy(remote if remote.get('date','')>incoming.get('date','') else incoming)
 chosen=copy.deepcopy(remote if remote.get('updated_at','')>incoming.get('updated_at','') else incoming)
 races=copy.deepcopy(remote.get('races',{}))
 for code,rec in incoming.get('races',{}).items():
  if code not in races or races[code].get('observed_at','')<=rec.get('observed_at',''):races[code]=copy.deepcopy(rec)
 chosen['races']=races
 chosen['venue_weather']=copy.deepcopy(remote.get('venue_weather',{}))
 for v,row in incoming.get('venue_weather',{}).items():
  if row.get('observed_at','')>=chosen['venue_weather'].get(v,{}).get('observed_at',''):chosen['venue_weather'][v]=copy.deepcopy(row)
 return chosen

def parse_live_previews(doc,code,card,observed):
 """Parse the verified target race's exhibition; never use previous-result ST cells."""
 from boat24_context import number
 if not parse_before(doc,code,card):return {}
 cutoff=None
 for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',doc,re.S|re.I):
  c=cells(row)
  if len(c)==13 and '締切予定時刻' in c[0]:cutoff=c[int(code[-2:])]
 if not cutoff or not re.fullmatch(r'\d{1,2}:\d{2}',cutoff):return {}
 base={'レースコード':code,'締切時刻':cutoff,'取得日時':observed,'情報源':'BOAT RACE公式・対象Rと全6登録番号照合'};ex=dict(base);st=dict(base);lanes=set()
 for body in re.findall(r'<tbody\b[^>]*>(.*?)</tbody>',doc,re.S|re.I):
  lane=re.search(r'class="is-boatColor([1-6])\b',body);rid=re.search(r'toban=(\d+)',body);rows=re.findall(r'<tr\b[^>]*>(.*?)</tr>',body,re.S|re.I)
  if not lane or not rid or not rows:continue
  lane=int(lane[1]);c=cells(rows[0])
  if len(c)<8 or str(card.get(f'艇{lane}_登録番号'))!=rid[1]:continue
  time=number(c[4]);weight=number(c[3].replace('kg',''));tilt=number(c[5])
  if time is None or not 5<=time<=9:continue
  ex[f'艇{lane}_展示タイム']=str(time)
  if weight is not None:ex[f'艇{lane}_体重(kg)']=str(weight)
  if tilt is not None:ex[f'艇{lane}_チルト']=str(tilt)
  if len(rows)>=3:
   adjust=number(cells(rows[2])[0]) if cells(rows[2]) else None
   if adjust is not None:ex[f'艇{lane}_体重調整(kg)']=str(adjust)
  lanes.add(lane)
 if lanes!=set(range(1,7)):return {}
 course=0;boats=[]
 for block in re.findall(r'<div class="table1_boatImage1">(.*?)</div>',doc,re.S):
  boat=re.search(r'table1_boatImage1Number[^>]*>\s*([1-6])\s*</span>',block);value=re.search(r'table1_boatImage1Time[^>]*>(.*?)</span>',block,re.S)
  if not boat or not value:continue
  course+=1;lane=int(boat[1]);v=text(value[1]);timing=number(v[1:] if v.startswith('F') else v)
  if timing is None or not 0<=abs(timing)<=1:return {'ex':ex}
  st[f'艇{lane}_コース']=str(course);st[f'艇{lane}_スタート展示']=str(-timing if v.startswith('F') else timing);boats.append(lane)
 out={'ex':ex}
 if len(boats)==6 and set(boats)==set(range(1,7)):out['st']=st
 # The latest venue weather may be labelled for the previous race; preserve that label.
 wm=re.search(r'水面気象情報\s*(\d+)R時点',text(doc));weather=dict(base)
 if wm:
  weather['参考レース']=int(wm[1]);weather['情報源']+='・水面気象は'+wm[1]+'R時点'
  for marker,key,unit in [('is-direction','気温(℃)','℃'),('is-wind','風速(m)','m'),('is-waterTemperature','水温(℃)','℃'),('is-wave','波の高さ(cm)','cm')]:
   block=re.search(r'<div class="weather1_bodyUnit '+marker+r'">(.*?)</div>\s*</div>',doc,re.S)
   if block:
    value=re.search(r'weather1_bodyUnitLabelData[^>]*>(.*?)</span>',block[1],re.S);v=number(text(value[1]).replace(unit,'')) if value else None
    if v is not None:weather[key]=str(v)
  if len(weather)>len(base)+1:out['weather']=weather
 return out

def apply_live_previews(data,cache,now):
 from boat24_context import deadline,FREEZE_MINUTES
 from boat24_integrity import timeparse
 used={}
 for code,rec in cache.get('races',{}).items():
  surface=cache.get('venue_weather',{}).get(code[8:10],{})
  if surface:
   old=data.get('weather',{}).get(code,{})
   limit=next((deadline(data.get(k,{}).get(code),now.date().isoformat()) for k in ('odds','ex','st','title') if deadline(data.get(k,{}).get(code),now.date().isoformat())),None)
   observed=timeparse(surface.get('observed_at'));measured=timeparse(surface.get('measured_at'))
   if limit and observed and measured and measured<=observed<=now and observed<limit-dt.timedelta(minutes=FREEZE_MINUTES):
    old_measure=str(old.get('気象観測時刻',''));old_at=timeparse(old.get('取得日時'));old_measured=timeparse(old_measure)
    if re.fullmatch(r'\d{4}',old_measure):
     try:old_measured=now.replace(hour=int(old_measure[:2]),minute=int(old_measure[2:]),second=0,microsecond=0)
     except ValueError:old_measured=None
    if (not old_at or observed>old_at) and (not old_measured or measured>=old_measured):
     data.setdefault('weather',{})[code]={**surface['numeric'],'レースコード':code,'締切時刻':limit.isoformat(),'取得日時':observed.isoformat(),'気象観測時刻':surface['measured_at'],'情報源':'BOATCAST公式・'+surface.get('wind_direction_literal','')+'風 '+(surface.get('wind_quality_literal') or ''),'source_url':surface['source']}
  for kind,row in rec.get('live_previews',{}).items():
   observed=timeparse(row.get('取得日時'));limit=deadline(row,now.date().isoformat());old=data.get(kind,{}).get(code,{})
   if not observed or not limit or observed>now or observed>=limit-dt.timedelta(minutes=FREEZE_MINUTES):continue
   if kind=='weather' and old:continue
   prior=timeparse(old.get('取得日時'))
   if not prior or observed>prior:data.setdefault(kind,{})[code]=row;used.setdefault(code,[]).append(kind)
 return used
