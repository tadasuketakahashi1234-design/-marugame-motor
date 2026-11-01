#!/usr/bin/env python3
"""Supplementary 24-venue motor analysis. Does not modify the live prediction ledger.
Uses public daily CSVs, creates a separate JSON research report. No betting guarantee.
"""
import csv, datetime as dt, io, json, math, os, pathlib, statistics, tempfile, urllib.request
from collections import defaultdict, Counter
from zoneinfo import ZoneInfo
JST=ZoneInfo('Asia/Tokyo')
ROOT='https://boatracecsv.github.io/data/'
PATHS={'cards':'programs/race_cards','results':'results/realtime','ex':'previews/tkz','st':'previews/stt','weather':'previews/sui'}
OUT=pathlib.Path('omura/docs/boat24_motor_analysis.json')
DAYS=int(os.environ.get('BOAT24_HISTORY_DAYS','28'))
DAYS=max(1,min(DAYS,90))

def number(v):
    try:return float(str(v).replace(',','').strip())
    except (ValueError,TypeError):return None

def fetch(kind,day):
    url=f'{ROOT}{PATHS[kind]}/{day:%Y/%m/%d}.csv'
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'boat24-research/1.2'})
        with urllib.request.urlopen(req,timeout=12) as f:
            return list(csv.DictReader(io.StringIO(f.read().decode('utf-8-sig')))),None
    except Exception as e:return [],type(e).__name__

def index(rows):return {r['レースコード']:r for r in rows if r.get('レースコード')}

def median_or_none(values):return round(statistics.median(values),4) if values else None

def safe_mean(values):return round(statistics.mean(values),4) if values else None

def classify_series(runs):
    # A gap is only a provisional event boundary, not a verified official series identifier.
    groups=[]
    for run in sorted(runs,key=lambda x:(x['date'],x['race_code'])):
        day=dt.date.fromisoformat(run['date'])
        if not groups or (day-dt.date.fromisoformat(groups[-1][-1]['date'])).days>2:groups.append([])
        groups[-1].append(run)
    return groups

def motor_report(runs):
    series=classify_series(runs)
    summaries=[]
    for group in series[-4:]:
        valid=[x for x in group if x['finish'] is not None]
        ex=[x['exhibition'] for x in group if x['exhibition'] is not None]
        st=[x['start_exhibition'] for x in group if x['start_exhibition'] is not None]
        summaries.append({'start':group[0]['date'],'end':group[-1]['date'],
          'race_count':len(group),'result_count':len(valid),
          'racers':sorted({x['racer'] for x in group if x['racer']}),
          'mean_finish':safe_mean([x['finish'] for x in valid]),
          'mean_exhibition':safe_mean(ex),'mean_start_exhibition':safe_mean(st),
          'mean_racer_win_rate':safe_mean([x['racer_win_rate'] for x in group if x['racer_win_rate'] is not None])})
    # Adjust finishing position for racer win-rate, lane and venue baseline, then shrink to neutral.
    adjusted=[]
    for r in runs:
        if r['finish'] is None or r['racer_win_rate'] is None:continue
        # Research-only heuristic; no calibrated predictive interpretation.
        expected=3.5-(r['racer_win_rate']-5)*0.35-(3.5-r['lane'])*0.24
        adjusted.append(max(-3,min(3,expected-r['finish'])))
    n=len(adjusted)
    score=round(50+20*(sum(adjusted)/(n+12)),2) if n else None
    trends=[]
    for group in series[-4:]:
        a=[x for x in group if x['finish'] is not None and x['racer_win_rate'] is not None]
        trends.append(safe_mean([max(-3,min(3,3.5-(x['racer_win_rate']-5)*.35-(3.5-x['lane'])*.24-x['finish'])) for x in a]))
    recent=[x for x in trends[-3:] if x is not None]
    slope=round(recent[-1]-recent[0],4) if len(recent)>=2 else None
    conditions={}
    for label,pred in [('calm',lambda x:x is not None and x<3),('windy',lambda x:x is not None and x>=3),('low_wave',lambda x:x is not None and x<5),('high_wave',lambda x:x is not None and x>=5)]:
        key='wind_speed' if 'wind' in label or label=='calm' else 'wave_height'
        sample=[x for x in runs if pred(x[key]) and x['finish'] is not None]
        conditions[label]={'races':len(sample),'mean_finish':safe_mean([x['finish'] for x in sample]),'sufficient_sample':len(sample)>=20}
    return {'races':len(runs),'series_count_provisional':len(series),'last_3_series_provisional':summaries[-3:],
      'racer_adjusted_motor_score_experimental':score,'score_validated':False,
      'series_trend_experimental':trends[-4:],'trend_change_experimental':slope,
      'weather_condition_analysis':conditions,'condition_effect_validated':False,
      'warnings':['Series boundaries inferred from date gaps; official meeting IDs unavailable',
        'Motor replacement dates not verified; do not merge across replacement cycles',
        'Weather effects confounded by racer, lane and venue; no causal claim']}

def main():
    today=dt.datetime.now(JST).date();days=[today-dt.timedelta(days=i) for i in range(DAYS-1,-1,-1)]
    motors=defaultdict(list);coverage={};errors=[];seen=set()
    for day in days:
        datasets={}
        for kind in PATHS:
            rows,error=fetch(kind,day);datasets[kind]=index(rows)
            if error:errors.append({'date':day.isoformat(),'kind':kind,'error':error})
        coverage[day.isoformat()]={k:len(v) for k,v in datasets.items()}
        for code,card in datasets['cards'].items():
            if len(code)!=12 or code in seen:continue
            seen.add(code)
            venue=int(code[8:10]);res=datasets['results'].get(code,{})
            ex=datasets['ex'].get(code,{});st=datasets['st'].get(code,{})
            weather=datasets['weather'].get(code,{})
            finishes={}
            for pos in range(1,7):
                lane=number(res.get(f'{pos}着_艇番'))
                if lane is not None:finishes[int(lane)]=pos
            for lane in range(1,7):
                motor=str(card.get(f'艇{lane}_モーター番号','')).strip().lstrip('0')
                if not motor:continue
                key=f'{venue:02d}-{motor}'
                motors[key].append({'date':day.isoformat(),'race_code':code,'lane':lane,'motor_number':motor,
                    'racer':card.get(f'艇{lane}_選手名',''),'racer_id':card.get(f'艇{lane}_登録番号',''),
                    'racer_win_rate':number(card.get(f'艇{lane}_全国勝率')),
                    'finish':finishes.get(lane),'exhibition':number(ex.get(f'艇{lane}_展示タイム')),
                    'start_exhibition':number(st.get(f'艇{lane}_スタート展示')),
                    'wind_speed':number(weather.get('風速(m)')),
                    'wind_direction':weather.get('風向'),
                    'wave_height':number(weather.get('波の高さ(cm)')),
                    'weather':weather.get('天候')})
    result={'schema':1,'generated_at':dt.datetime.now(JST).isoformat(),
      'research_only':True,'days_requested':DAYS,'coverage':coverage,'source_errors':errors,
      'data_availability_audit':{'dates_checked':len(days),'motor_records':sum(map(len,motors.values())),
        'distinct_venue_motor_keys':len(motors),'sources':list(PATHS)},
      'motors':{key:motor_report(runs) for key,runs in sorted(motors.items())},
      'limitations':{'motor_replacement_dates':'not_verified','official_series_id':'not_available',
        'tide':'not_connected','probability_training':'not_implemented',
        'validation':'No holdout validation yet; experimental scores must not drive purchases'}}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=OUT.parent,delete=False) as f:
        json.dump(result,f,ensure_ascii=False,separators=(',',':'));name=f.name
    os.replace(name,OUT)
    print(json.dumps({'motors':len(motors),'days':len(days),'errors':len(errors)},ensure_ascii=False))
if __name__=='__main__':main()
