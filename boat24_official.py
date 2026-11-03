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

def collect(codes,cards,now):
 cache=json.loads(CACHE.read_text()) if CACHE.exists() else {'schema':1,'races':{}}
 if cache.get('date')!=now.date().isoformat():cache={'schema':1,'date':now.date().isoformat(),'races':{}}
 errors={}
 try:cache['tides']=parse_tides(get(TIDE));cache['tide_observed_at']=dt.datetime.now(JST).isoformat();cache['tide_url']=TIDE
 except Exception as e:errors['tide']=str(e)
 def job(code):
  venue=int(code[8:10]);race=int(code[-2:]);record={'observed_at':dt.datetime.now(JST).isoformat(),'sources':{}}
  u=f'https://www.boatrace.jp/owpc/pc/race/beforeinfo?hd={code[:8]}&jcd={venue:02d}&rno={race}'
  try:record['before']=parse_before(get(u),code,cards[code]);record['sources']['maintenance']=u
  except Exception as e:record['maintenance_error']=str(e)
  if venue==15:
   u=BASE+f'/asp/kyogi/15/pc/yoso05{race:02d}.htm'
   try:record['comments']=parse_comments(get(u),code,cards[code]);record['sources']['comments']=u
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
 with ThreadPoolExecutor(max_workers=3) as pool:
  for code,rec in pool.map(job,codes):
   old=cache['races'].get(code,{})
   for key in ('before','comments','wind_direction_text'):
    if rec.get(key):rec[key+'_observed_at']=rec['observed_at']
    elif old.get(key):
     rec[key]=old[key];rec[key+'_observed_at']=old.get(key+'_observed_at',old.get('observed_at'))
   cache['races'][code]=rec
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
  # Cardinal mapping from CSV is not assumed. A verified literal direction is required.
  wind_time=timeparse(rec.get('wind_direction_text_observed_at',rec.get('observed_at')))
  direction=rec.get('wind_direction_text') if wind_time and wind_time<cutoff else None
  speed=number(f.get('weather',{}).get('風速(m)'))
  if int(code[8:10])==15 and direction in ('北','北西','北東','南','南西','南東') and speed is not None:
   f['wind']['向かい風成分']=speed*(1 if direction.startswith('北') else -1)
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
 return chosen
