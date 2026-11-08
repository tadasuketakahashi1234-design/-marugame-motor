"""Venue-specific surface conditions, astronomical tides and prior-date responses.
Nearby tide predictions are explicitly proxies, never measured course currents.
"""
import datetime as dt
import email.utils
import hashlib
import html
import json
import math
from pathlib import Path
import re
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from boat24_integrity import JST,atomic_write,timeparse
CONFIG=Path(__file__).with_name('boat24_venues.json')
PROFILES=json.loads(CONFIG.read_text())['venues']
CACHE=Path('.boat24_water_cache')

def download(url):
 with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'boat24-venue-water/5','Cache-Control':'no-cache'}),timeout=18) as r:
  raw=r.read();modified=r.headers.get('Last-Modified')
 try:body=raw.decode('utf-8-sig')
 except UnicodeDecodeError:body=raw.decode('cp932')
 return body,modified

def parse_jma(body,year,station):
 out={}
 for line in body.splitlines():
  if len(line)!=136 or line[78:80]!=station:continue
  try:
   if int(line[72:74])!=year%100:continue
   day=dt.date(year,int(line[74:76]),int(line[76:78])).isoformat();hourly=[int(line[i:i+3]) for i in range(0,72,3)]
   if any(v==999 or not -500<=v<=1000 for v in hourly):continue
   row={'hourly_cm':hourly,'highs':[],'lows':[]}
   for key,start in [('highs',80),('lows',108)]:
    for i in range(start,start+28,7):
     t=line[i:i+4];h=int(line[i+4:i+7])
     if t=='9999' or h==999:continue
     hh=int(t[:2]);mm=int(t[2:]);
     if not 0<=hh<=23 or not 0<=mm<=59:raise ValueError('Invalid tide time')
     row[key].append({'minute':hh*60+mm,'height_cm':h})
   out[day]=row
  except (ValueError,TypeError):continue
 if len(out)<350:raise ValueError('Annual astronomical tide file is incomplete or station/year mismatched')
 return out

def parse_jcg(body,day):
 if '大村（大村湾）' not in body or not re.search(r'name=area\s+value=(?:\\?"|&quot;)*4250',body):raise ValueError('JCG tide station mismatch')
 for key,value in [('year',day.year),('month',day.month),('day',day.day)]:
  if not re.search(r'name='+key+r'\s+value='+str(value)+r'\b',body):raise ValueError('JCG tide date mismatch')
 values=[]
 for row in re.findall(r'<TR\b[^>]*>(.*?)</TR>',body,re.I|re.S):
  cells=[html.unescape(re.sub('<[^>]*>','',x)).strip() for x in re.findall(r'<TD\b[^>]*>(.*?)</TD>',row,re.I|re.S)]
  if len(cells)==13 and cells[0]=='(cm)':values += [float(v) for v in cells[1:]]
 if len(values)!=24 or any(not -500<=v<=1000 for v in values):raise ValueError('JCG hourly tides incomplete')
 return {'hourly_cm':values,'highs':[],'lows':[]}

def load_tide_book(today,days=28):
 start=today-dt.timedelta(days=days);end=today+dt.timedelta(days=2);tasks={};errors={};book={}
 for v,p in PROFILES.items():
  if p['tidal_range']!='あり':continue
  src=p['tide_source']
  if src['kind'].startswith('jma'):
   for year in range(start.year,end.year+1):tasks[('jma',year,src['station'])]=None
  else:
   for offset in range(-days,3):tasks[('jcg',(today+dt.timedelta(days=offset)).isoformat(),'4250')]=None
 def job(key):
  kind,period,station=key;path=CACHE/kind/(str(period)+'-'+station+'.json')
  if path.exists():return key,json.loads(path.read_text()),None
  url=(f'https://www.data.jma.go.jp/kaiyou/data/db/tide/suisan/txt/{period}/{station}.txt' if kind=='jma' else 'https://www1.kaiho.mlit.go.jp/TIDE/pred2/cgi-bin/TidePredCgi.cgi?area=4250&back=3&year='+str(dt.date.fromisoformat(period).year)+'&month='+str(dt.date.fromisoformat(period).month)+'&day='+str(dt.date.fromisoformat(period).day))
  try:
   body,modified=download(url);rows=parse_jma(body,period,station) if kind=='jma' else {period:parse_jcg(body,dt.date.fromisoformat(period))}
   # Do not train historical JMA features from a file revised after that target date.
   modified_at=email.utils.parsedate_to_datetime(modified).astimezone(JST).isoformat() if modified else None
   value={'rows':rows,'source':url,'last_modified':modified_at,'sha256':hashlib.sha256(body.encode()).hexdigest(),'kind':'astronomical_prediction','retrieved_at':dt.datetime.now(JST).isoformat()}
   atomic_write(path,value);return key,value,None
  except Exception as e:return key,None,str(e)[:180]
 with ThreadPoolExecutor(max_workers=6) as pool:
  for key,value,error in pool.map(job,tasks):
   if error:errors[str(key)]=error
   else:tasks[key]=value
 for v,p in PROFILES.items():
  if p['tidal_range']!='あり':continue
  src=p['tide_source'];rows={}
  for offset in range(-days,3):
   date=today+dt.timedelta(days=offset);day=date.isoformat();kind='jma' if src['kind'].startswith('jma') else 'jcg';key=(kind,date.year,src['station']) if kind=='jma' else (kind,day,'4250');value=tasks.get(key) or {};row=value.get('rows',{}).get(day)
   if not row:continue
   if kind=='jma' and (not value.get('last_modified') or timeparse(value['last_modified']).date()>date):
    errors[str(key)+'|'+day]='Historical issue date not established before target date';continue
   rows[day]={**row,'source':value['source'],'source_sha256':value['sha256'],'last_modified':value.get('last_modified'),'kind':src['kind'],'station':src['name'],'scope':src['scope']}
  book[v]=rows
 return book,errors

def tide_features(venue,cutoff,book):
 p=PROFILES[str(venue)]
 if p['tidal_range']=='なし':return {},{'status':'not_applicable','reason':'BOAT RACE公式場データで干満差なし'}
 row=book.get(str(venue),{}).get(cutoff.date().isoformat())
 if not row:return {},{'status':'missing','reason':'対象日・地点の潮汐推算を取得できていない'}
 values=row['hourly_cm'];hour=cutoff.hour;nextday=book.get(str(venue),{}).get((cutoff.date()+dt.timedelta(days=1)).isoformat(),{});right=values[hour+1] if hour<23 else (nextday.get('hourly_cm') or [None])[0]
 if right is None:return {},{'status':'missing','reason':'日境界の次時刻潮位なし。外挿しない'}
 level=values[hour]+(right-values[hour])*(cutoff.minute/60+cutoff.second/3600);extrema=[x['height_cm'] for k in ('highs','lows') for x in row.get(k,[])];lo=min(values+extrema);hi=max(values+extrema);amplitude=hi-lo;slope=right-values[hour]
 f={'推算潮位cm':level,'日内干満幅cm':amplitude,'潮位変化cm毎時':slope,'推算上げ潮':int(slope>0),'推算下げ潮':int(slope<0),'推算潮止まり':int(slope==0)}
 if amplitude:f['日内相対潮位']=(level-lo)/amplitude
 for k,label in [('highs','満潮'),('lows','干潮')]:
  times=[x['minute'] for x in row.get(k,[])];minute=cutoff.hour*60+cutoff.minute
  if times:f[label+'最近接分']=min((x-minute for x in times),key=abs)
 phase='rising' if slope>0 else 'falling' if slope<0 else 'slack'
 return f,{'status':'available','station':row['station'],'kind':row['kind'],'scope':row['scope'],'source':row['source'],'phase':phase,'hourly_interpolation':True,'is_measured_course_level':False,'is_current_velocity':False}

def wind_values(weather):
 from boat24_context import number
 direction=number(weather.get('風向'));speed=number(weather.get('風速(m)'));wave=number(weather.get('波の高さ(cm)'))
 if speed is None or not 0<=speed<=60:return {},None
 if speed==0:return {'北からの風成分':0.,'東からの風成分':0.,'風速二乗':0.,'無風':1.},(0,0)
 if direction is None or not direction.is_integer() or not 1<=direction<=8:return {},None
 angle=math.radians((direction-1)*45);f={'北からの風成分':speed*math.cos(angle),'東からの風成分':speed*math.sin(angle),'風速二乗':speed*speed}
 if wave is not None:f['風速波高積']=speed*wave
 return f,(int(direction),0 if speed<=2 else 1 if speed<=5 else 2)

class SurfaceStats:
 def __init__(self,state=None):self.state=state if state is not None else {'base':{},'wind':{},'tide':{},'through':None}
 def attach(self,features,venue,cutoff,book):
  tide,tm=tide_features(venue,cutoff,book);evidence=[];state_valid=not self.state.get('through') or self.state['through']<cutoff.date().isoformat()
  for lane,f in enumerate(features,1):
   course=int(f.get('start',{}).get('展示進入',lane));course=course if 1<=course<=6 else lane;wind,key=wind_values(f.get('weather',{}));f['tide']=dict(tide);f['wind']=wind
   base=self.state['base'].get(f'{venue}|{course}',{}) if state_valid else {};items={}
   keys={'wind':f'{venue}|{course}|{key[0]}|{key[1]}' if key else None,'tide':f'{venue}|{course}|{tm.get("phase")}|{min(2,int(tide.get("日内相対潮位",0)*3))}' if tide else None}
   for group,k in keys.items():
    a=self.state[group].get(k,{}) if k and state_valid else {};n=a.get('n',0);items[group]={'same_venue_course_condition_samples':n,'status':'learned' if n>=8 else 'insufficient_samples'}
    if n>=8 and base.get('n'):
     prior=base['sum']/base['n'];value=(a['sum']+8*prior)/(n+8);f[group]['同条件平均着順']=value;f[group]['同場コース平均との差']=prior-value;f[group]['同条件標本数']=n
   evidence.append(items)
  return {'profile':PROFILES[str(venue)],'tide':tm,'wind_method':'同場・同進入コースの風向8方位×風速区分の実績を学習。未確認のコース方位から向かい風を捏造しない。','condition_evidence_by_boat':evidence,'trained_through':self.state.get('through'),'condition_history_valid':state_valid}
 def add(self,venue,features,finish_map,day):
  for lane,f in enumerate(features,1):
   finish=finish_map.get(str(lane));course=int(f.get('start',{}).get('展示進入',lane));_,key=wind_values(f.get('weather',{}));tide=f.get('tide',{})
   if finish not in range(1,7) or course not in range(1,7):continue
   keys=[('base',f'{venue}|{course}')]
   if key:keys.append(('wind',f'{venue}|{course}|{key[0]}|{key[1]}'))
   if tide:
    phase='rising' if tide.get('潮位変化cm毎時',0)>0 else 'falling' if tide.get('潮位変化cm毎時',0)<0 else 'slack';keys.append(('tide',f'{venue}|{course}|{phase}|{min(2,int(tide.get("日内相対潮位",0)*3))}'))
   for group,k in keys:
    a=self.state[group].setdefault(k,{'n':0,'sum':0});a['n']+=1;a['sum']+=finish
  self.state['through']=max(self.state.get('through') or '',day)

def parse_venue_weather(body,venue,now):
 """Live BOATCAST compass directions are literal; do not reuse the 16 CSS classes."""
 from boat24_context import number
 lines=[x for x in body.splitlines() if x.strip()]
 if len(lines)!=1:raise ValueError('Unexpected daily surface weather response')
 c=lines[0].split('\t')
 if len(c)<7 or not re.fullmatch(r'\d{4}',c[0]):raise ValueError('Surface weather schema mismatch')
 h,m=int(c[0][:2]),int(c[0][2:])
 if h>23 or m>59:raise ValueError('Invalid weather observation time')
 measured=now.replace(hour=h,minute=m,second=0,microsecond=0)
 if measured>now+dt.timedelta(minutes=2) or now-measured>dt.timedelta(minutes=90):raise ValueError('Future or stale surface weather')
 compass=re.match(r'\s*(北東|南東|南西|北西|北|東|南|西)',c[3]);code={'北':1,'北東':2,'東':3,'南東':4,'南':5,'南西':6,'西':7,'北西':8}.get(compass[1]) if compass else None
 result={'venue':venue,'observed_at':now.isoformat(),'measured_at':measured.isoformat(),'wind_direction_literal':compass[1] if compass else None,'wind_quality_literal':re.search(r'[（(]([^）)]+)[）)]',c[3])[1] if re.search(r'[（(]([^）)]+)[）)]',c[3]) else None,'numeric':{}}
 # Official weather can be a Japanese label rather than a numeric code.
 # Keep the existing numeric encoding stable and reject unknown labels explicitly.
 weather_label=re.sub(r'\\s+','',c[1])
 weather_codes={'晴':1,'晴れ':1,'曇':2,'曇り':2,'くもり':2,'雨':3,'雪':4}
 weather_code=number(weather_label)
 if weather_code is None:weather_code=weather_codes.get(weather_label)
 for key,v in [('風向',code),('天候',weather_code),('波の高さ(cm)',c[2]),('風速(m)',c[4]),('気温(℃)',c[5]),('水温(℃)',c[6])]:
  n=number(v)
  if n is not None:result['numeric'][key]=str(n)
 if len(result['numeric'])!=6:raise ValueError('Incomplete official surface weather')
 return result
