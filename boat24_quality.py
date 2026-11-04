"""Observation-time gates shared by live forecasts and quote refreshes."""
import math
from boat24_integrity import timeparse

POLICY='observed-inputs-1'
WEATHER_MAX_SECONDS=600

def prepare(features,previews,now):
    row=previews.get('weather') or {}
    # A fresh HTTP fetch does not establish a fresh water observation.
    measured=timeparse(row.get('気象観測時刻') or row.get('観測時刻'))
    age=(now-measured).total_seconds() if measured else None
    state='missing' if not row else 'observation_time_unknown' if measured is None else 'future_observation' if age<0 else 'stale' if age>WEATHER_MAX_SECONDS else 'fresh'
    excluded=[]
    if state!='fresh':
        for f in features:
            for g in ('weather','wind'):
                if f.get(g):excluded.append(g)
                f[g]={}
    method_excluded=[]
    for lane,f in enumerate(features,1):
        course=f.get('course',{})
        if not course.get('決まり手確認走数') or course['決まり手確認走数']<course.get('標本数',0):
            method_excluded.append(lane)
            style=f.get('style',{})
            removed=[k for k in style if any(k.startswith(m) for m in ('逃げ','差し','まくり'))]
            for k in removed:style.pop(k)
        # Older tactical states have no proven method-label denominators.
        tactical=f.get('tactical_detail',{})
        if not tactical.get('決まり手確認走数') or tactical['決まり手確認走数']<tactical.get('実進入確認走数',0):
            for k in ('2コースイン逃げ許容率','イン敗戦確認数','イン敗戦中差され率','イン敗戦中まくられ率'):tactical.pop(k,None)
    entry=[f.get('start',{}).get('展示進入') for f in features]
    entry_ok=len(entry)==6 and set(entry)==set(range(1,7))
    exhibition_ok=len(features)==6 and all(f.get('exhibition',{}).get('展示タイム相対') is not None for f in features)
    st_ok=len(features)==6 and all(f.get('start',{}).get('展示ST符号付') is not None for f in features)
    return {'policy':POLICY,'weather':{'state':state,'measured_at':measured.isoformat() if measured else None,
                'age_seconds':age,'max_age_seconds':WEATHER_MAX_SECONDS,'excluded_from_prediction':state!='fresh',
                'source':row.get('source_url') or row.get('source'),'fetched_at':row.get('取得日時')},
            'entry_verified':entry_ok,'exhibition_complete':exhibition_ok,'start_complete':st_ok,
            'purchase_inputs_ready':entry_ok and exhibition_ok and st_ok,'excluded_groups':sorted(set(excluded)),
            'method_label_unverified_lanes':method_excluded,
            'unmeasured':['スロー・ダッシュ','起こし位置','助走距離','映像の行き足・出口の押し','競走水面の実流速']}

def wilson(wins,n):
    if not n:return None
    p=wins/n;z=1.96;den=1+z*z/n;mid=(p+z*z/(2*n))/den
    half=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return [max(0,mid-half),min(1,mid+half)]

def historical_support(model,identities,features):
    rows=[];state=model.get('course_state',{})
    for i,f in enumerate(features,1):
        identity=next((x for x in identities if x.get('lane')==i),{})
        course=int(f.get('start',{}).get('展示進入',i))
        a=state.get('racer',{}).get(str(identity.get('racer'))+'-'+str(course),{})
        n=a.get('n',0);wins=a.get('wins',0)
        rows.append({'lane':i,'course':course,'races':n,'wins':wins,'raw_win_rate':wins/n if n else None,
                     'historical_rate_wilson95':wilson(wins,n),'shrunken_win_rate':f.get('course',{}).get('1着率'),
                     'window_days':model.get('course_window_days'),'through':model.get('trained_through'),
                     'method_labelled':a.get('method_n'),'method_label_state':'known' if 'method_n' in a else 'unknown_legacy',
                     'notice':'過去の比率の区間。今回レースの勝率の信頼区間ではありません。'})
    return rows
