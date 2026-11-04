"""Build prior-date contextual samples and period-safe motor history."""
import csv
import datetime as dt
import io
import json
import math
import os
import pathlib
import statistics
import urllib.request
import urllib.error
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from boat24_context import (VERSION, FREEZE_MINUTES, COMBOS, number, finishes, mean, safe_row, deadline,
                           motor_key, normalized_name, make_features, scales, predict)
from boat24_integrity import JST, timeparse, atomic_write
from boat24_course import CourseStats, add_course_features
from boat24_model_io import read_json, write_json
from boat24_priority import add_priority_features
from boat24_registry import load_registry
from boat24_behavior import BehaviorStats
from boat24_water import load_tide_book,SurfaceStats,PROFILES
from boat24_validation import validate_chronologically,validate_initial,ablation_report

ROOT='https://boatracecsv.github.io/data/'
PATHS={'cards':'programs/race_cards','title':'programs/title','waku':'programs/waku10',
       'motor':'programs/motor_stats','ex':'previews/tkz','st':'previews/stt',
       'weather':'previews/sui','original':'previews/original_exhibition','odds':'previews/od3',
       'results':'results/realtime','payouts':'results/payouts',
       'recent_n':'programs/recent_national','recent_l':'programs/recent_local',
       'history':'programs/motor_history','calendar':'programs/monthly_schedule'}
PATHS.update({'tokuten':'previews/tokuten_hayami','od1':'previews/od1','od2':'previews/od2'})
OPTIONAL_SOURCES={'tokuten','od1','od2'}
MODEL=pathlib.Path('omura/docs/boat24_full_model.json.gz')
ERRORS={}
SOURCE_CACHE=pathlib.Path('.boat24_source_cache')


def fetch(kind,path):
    url=ROOT+PATHS[kind]+'/'+path+'.csv'
    cache=SOURCE_CACHE/kind/(path+'.csv')
    historical=len(path)==10 and path.replace('/','-')<dt.datetime.now(JST).date().isoformat()
    if historical and cache.exists():
        return list(csv.DictReader(io.StringIO(cache.read_text(encoding='utf-8'))))
    if len(path)==10 and path.replace('/','-')==dt.datetime.now(JST).date().isoformat():url+='?v='+str(int(time.time()//30))
    error=None
    for attempt in range(2):
        try:
            req=urllib.request.Request(url,headers={'User-Agent':'boat24-context-research/5.0','Cache-Control':'no-cache'})
            with urllib.request.urlopen(req,timeout=15) as res:
                raw=res.read().decode('utf-8-sig');rows=list(csv.DictReader(io.StringIO(raw)))
            if historical:
                cache.parent.mkdir(parents=True,exist_ok=True);cache.write_text(raw,encoding='utf-8')
            ERRORS.pop(kind+'/'+path,None)
            return rows
        except Exception as exc:
            error=exc
            if isinstance(exc,urllib.error.HTTPError) and exc.code==404 and kind in OPTIONAL_SOURCES:
                ERRORS.pop(kind+'/'+path,None)
                return []
            if isinstance(exc,urllib.error.HTTPError) and exc.code not in (408,429,500,502,503,504):break
            if not attempt:time.sleep(.25)
    ERRORS[kind+'/'+path]=str(error)[:160]
    return []


def by_code(rows):return {r['レースコード']:r for r in rows if r.get('レースコード')}


def collect_day(day):
    path=day.strftime('%Y/%m/%d');kinds=[k for k in PATHS if k not in ('history','calendar')]
    with ThreadPoolExecutor(max_workers=8) as pool:rows=dict(zip(kinds,pool.map(lambda k:fetch(k,path),kinds)))
    rows['motor_rows']=rows['motor'];rows={k:(v if k in ('motor','motor_rows') else by_code(v)) for k,v in rows.items()}
    rows['_live_collection']=True
    return rows


def calendar_and_history(today):
    months=sorted({(today-dt.timedelta(days=n)).strftime('%Y/%m') for n in range(100)})
    with ThreadPoolExecutor(max_workers=4) as pool: calendars=sum(pool.map(lambda p:fetch('calendar',p),months),[])
    dates=sorted({r.get('節終了日','') for r in calendars if r.get('節終了日') and (today-dt.timedelta(days=95)).isoformat()<=r['節終了日']<today.isoformat()})
    with ThreadPoolExecutor(max_workers=8) as pool: history=sum(pool.map(lambda d:fetch('history',d.replace('-','/')),dates),[])
    return calendars,history


class History:
    def __init__(self,calendars,histories,profiles=None,runs=None):
        self.calendars=calendars;self.histories=defaultdict(list);self.profiles=defaultdict(list);self.runs=defaultdict(list)
        for row in histories:
            if row.get('場コード') and row.get('モーター番号'):
                self.histories[motor_key(row['場コード'],row['モーター番号'])].append(row)
        for profile in profiles or []:self.add_profile(profile)
        for run in runs or []:self.add_run(run)

    def add_profile(self,profile):self.profiles[normalized_name(profile['name'])].append(profile)
    def add_run(self,run):self.runs[motor_key(run['venue'],run['motor'])].append(run)

    def meeting_start(self,venue,day):
        matches=[r['節開始日'] for r in self.calendars if str(r.get('場コード')).zfill(2)==str(venue).zfill(2) and r.get('節開始日','x')<=day<=r.get('節終了日','')]
        return max(matches) if matches else None

    def rider_rate(self,name,asof):
        matches=[p for p in self.profiles[normalized_name(name)] if p['date']<=asof]
        return max(matches,key=lambda p:p['date'])['win_rate'] if matches else None

    def rider_expectation(self,name,asof):
        matches=[p for p in self.profiles[normalized_name(name)] if p['date']<=asof and p.get('expected_finish') is not None]
        return max(matches,key=lambda p:p['date'])['expected_finish'] if matches else None

    def motor(self,venue,motor,period,day,cutoff):
        key=motor_key(venue,motor);start=self.meeting_start(venue,day) or day
        # Require the period identity before joining historical individuals.
        if not period:return {'features':{},'status':'motor_period_unknown','uses':[],'matched_riders':0,'total_riders':0}
        unique={}
        for row in self.histories[key]:
            end=row.get('使用終了日','');begin=row.get('使用開始日','');ref=row.get('基準節終了日','')
            if not end or not begin or not ref or ref>=day or end>=start or begin<period:continue
            identity=(begin,end,normalized_name(row.get('使用者名')))
            if identity not in unique or row['基準節終了日']>unique[identity]['基準節終了日']:unique[identity]=row
        uses=sorted(unique.values(),key=lambda r:(r['使用終了日'],r['使用開始日']),reverse=True)[:3]
        output=[];raw=[];adjusted=[];matched=0
        for row in uses:
            fs=finishes(row.get('着順列'));avg=mean(fs);rate=self.rider_rate(row.get('使用者名'),row['使用終了日'])
            # Transparent research residual relative to racer ability; shrink below.
            expected=self.rider_expectation(row.get('使用者名'),row['使用終了日'])
            residual=expected-avg if avg is not None and expected is not None else None
            if avg is not None:raw+=fs
            if residual is not None:adjusted.append(residual);matched+=1
            output.append({'start':row['使用開始日'],'end':row['使用終了日'],'racer':row.get('使用者名'),
                           'finishes':row.get('着順列'),'mean_finish':avg,'racer_win_rate':rate,'adjusted_residual':residual})
        recent=[]
        for run in self.runs[key]:
            observed=timeparse(run.get('observed_at'))
            if run.get('period')==period and start<=run['date']<=day and observed and observed<cutoff:
                recent.append(run)
        features={}
        if raw:features['過去3節平均着順']=mean(raw)
        if adjusted:features['過去3節選手補正']=mean(adjusted)*len(adjusted)/(len(adjusted)+2)
        avgs=[u['mean_finish'] for u in output if u['mean_finish'] is not None]
        if len(avgs)>=2:features['直近節の変化']=avgs[-1]-avgs[0]
        if recent:
            features['今節平均着順']=mean([r['finish'] for r in recent])
            residuals=[r['expected_finish']-r['finish'] for r in recent if r.get('expected_finish') is not None]
            if residuals:features['今節選手補正']=mean(residuals)*len(residuals)/(len(residuals)+6)
        return {'features':features,'period':period,'meeting_start':start,'uses':output,'matched_riders':matched,
                'total_riders':len(output),'current_series_runs':len(recent),
                'status':'available' if output else 'history_missing',
                'rider_adjustment':'prior_observed_mean_finish_residual_not_causal'}


def period_rows(rows):
    return {motor_key(r['場コード'],r['モーター番号']):r for r in rows if r.get('場コード') and r.get('モーター番号')}


def profiles_and_runs(data,day,course_stats=None):
    profiles=[];runs=[];motors=period_rows(data.get('motor_rows',[]))
    for code,card in data.get('cards',{}).items():
        try:venue=int(code[8:10])
        except (ValueError,TypeError):continue
        res=data.get('results',{}).get(code,{})
        finish_map={str(res.get(f'{p}着_艇番')):p for p in range(1,7)}
        for lane in range(1,7):
            name=card.get(f'艇{lane}_選手名');rate=number(card.get(f'艇{lane}_全国勝率'));motor=card.get(f'艇{lane}_モーター番号')
            a=(course_stats.state.get('overall',{}).get(str(card.get(f'艇{lane}_登録番号')),{})) if course_stats else {}
            expected=a['finish_sum']/a['n'] if a.get('n') else None
            if name and rate is not None:profiles.append({'name':name,'win_rate':rate,'date':day,'expected_finish':expected})
            if motor and str(lane) in finish_map and res.get('取得日時'):
                ms=motors.get(motor_key(venue,motor),{})
                runs.append({'venue':venue,'motor':motor,'period':ms.get('モーター期起算日'),'date':day,
                    'finish':finish_map[str(lane)],'expected_finish':expected,'racer_win_rate':rate,'observed_at':res['取得日時']})
    return profiles,runs


def race_features(code,card,data,history,asof,previous_motor=None,course_stats=None):
    day=f'{code[:4]}-{code[4:6]}-{code[6:8]}';venue=int(code[8:10])
    limit=next((deadline(data.get(k,{}).get(code),day) for k in ('odds','ex','st','title') if deadline(data.get(k,{}).get(code),day)),None)
    if not limit:return None
    effective=min(asof,limit-dt.timedelta(minutes=FREEZE_MINUTES,microseconds=1))
    previews={k:safe_row(data.get(k,{}).get(code),limit,effective) for k in ('ex','st','weather','original','odds')}
    current_motor=period_rows(data.get('motor_rows',[]));past_motor=period_rows(previous_motor or [])
    motors={};contexts={}
    for lane in range(1,7):
        key=motor_key(venue,card.get(f'艇{lane}_モーター番号',''))
        current=current_motor.get(key,{})
        prior=past_motor.get(key,{})
        # Historical training uses the previous date's period totals; never EOD totals of its target race.
        motors[str(lane)]=prior if prior.get('モーター期起算日')==current.get('モーター期起算日') else {}
        contexts[str(lane)]=history.motor(venue,card.get(f'艇{lane}_モーター番号',''),current.get('モーター期起算日'),day,effective)
        contexts[str(lane)]['period_source']=current.get('identity_source','daily_motor_csv')
        contexts[str(lane)]['period_scope']=current.get('identity_scope','motor_row_period')
        contexts[str(lane)]['individual_totals_available']=bool(motors[str(lane)].get('出走数'))
    features=make_features(card,data.get('waku',{}).get(code),data.get('recent_n',{}).get(code),data.get('recent_l',{}).get(code),
                           motors,contexts,previews['ex'],previews['st'],previews['weather'],previews['original'],day)
    if course_stats is not None:add_course_features(features,card,venue,course_stats)
    metadata=add_priority_features(features,card,data.get('title',{}).get(code,{}),data.get('registry',{}),course_stats,venue,day,limit)
    from boat24_quality import prepare as prepare_quality
    prepare_quality(features,previews,effective)
    from boat24_details import attach
    detail=attach(features,code,card,data,previews,limit,effective)
    return {'race_context':metadata,'features':features,'contexts':contexts,'previews':previews,'cutoff':limit,'asof':effective,'detail':detail,
            'source_times':{k:r.get('取得日時') for k,r in previews.items() if r}}


def build_model(today,days=28):
    from boat24_replay import load_observations,restore_snapshot
    from boat24_details import SCHEMA,DETAIL_GROUPS
    from boat24_context import BASE_GROUPS
    observed,replay_diagnostics=load_observations(today,days)
    registry=load_registry(today)
    tide_book,water_errors=load_tide_book(today,days)
    jobs=[]
    for offset in range(days+28,0,-1):
        path=(today-dt.timedelta(days=offset)).strftime('%Y/%m/%d')
        kinds=('cards','results') if offset>days else [k for k in PATHS if k not in ('history','calendar')]
        jobs.extend((k,path) for k in kinds)
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,_ in enumerate(pool.map(lambda pair:fetch(*pair),jobs),1):
            if i%60==0:print('training sources',i,'/',len(jobs),flush=True)
    calendars,histories=calendar_and_history(today)
    history=History(calendars,histories);samples=[];validation=[];initial_validation=[];profile_rows=[];run_rows=[];coverage={}
    prior_motor=[]
    from boat24_tactics import Tactics
    course_stats=CourseStats();behavior=BehaviorStats();surface=SurfaceStats();tactics=Tactics()
    # A prior 28-day warmup supplies real course results before the training window.
    warm=[today-dt.timedelta(days=n) for n in range(days+28,days,-1)]
    def course_day(d):
        path=d.strftime('%Y/%m/%d')
        return {'cards':by_code(fetch('cards',path)),'results':by_code(fetch('results',path)),'registry':registry}
    with ThreadPoolExecutor(max_workers=6) as pool:
        for data in pool.map(course_day,warm):course_stats.add(data)
    for offset in range(days,0,-1):
        day=today-dt.timedelta(days=offset);data=collect_day(day);data['registry']=registry;d=day.isoformat()
        surface_pending=[]
        profiles,runs=profiles_and_runs(data,d,course_stats)
        # Profiles/results are inserted with source timestamps; each target filters them by its own cutoff.
        for p in profiles:history.add_profile(p)
        for r in runs:history.add_run(r)
        profile_rows+=profiles;run_rows+=runs
        for code,card in sorted(data['cards'].items()):
            res=data['results'].get(code,{})
            fm={str(res.get(f'{p}着_艇番')):p for p in range(1,7)}
            if len(fm)!=6 or set(fm)!=set('123456'):continue
            from boat24_settlement import refund_boats
            if refund_boats(res):continue
            built=race_features(code,card,data,history,dt.datetime.combine(day,dt.time(23,59,59),JST),prior_motor,course_stats)
            if not built:continue
            behavior.attach(built['features'],card)
            surface.attach(built['features'],int(code[8:10]),built['cutoff'],tide_book)
            tactics.attach(built['features'],card,int(code[8:10]),d)
            surface_pending.append((int(code[8:10]),built['features'],fm))
            initial=race_features(code,card,data,history,dt.datetime.combine(day,dt.time(7),JST),prior_motor,course_stats)
            if initial:
                behavior.attach(initial['features'],card)
                surface.attach(initial['features'],int(code[8:10]),initial['cutoff'],tide_book)
                tactics.attach(initial['features'],card,int(code[8:10]),d)
            if (code,'preview') in observed:
                replay=restore_snapshot(observed[(code,'preview')],code,card)
                built={**built,**replay}
            if (code,'initial') in observed and initial:
                initial={**initial,**restore_snapshot(observed[(code,'initial')],code,card)}
            tactics.attach(built['features'],card,int(code[8:10]),d)
            if initial:tactics.attach(initial['features'],card,int(code[8:10]),d)
            for phase,snapshot in [('preview',built),('initial',initial)]:
                if not snapshot:continue
                from boat24_quality import prepare as prepare_quality
                prepare_quality(snapshot['features'],snapshot.get('previews',{}),snapshot.get('asof') or snapshot['cutoff']-dt.timedelta(minutes=FREEZE_MINUTES,microseconds=1))
                for lane,f in enumerate(snapshot['features'],1):
                    course=int(f.get('start',{}).get('展示進入',lane))
                    samples.append({'phase':phase,'date':d,'code':code,'venue':int(code[8:10]),'course':course,'lane':lane,'finish':fm[str(lane)],'features':f,'snapshot_id':snapshot.get('snapshot_id'),'feature_schema':SCHEMA})
            if offset<=12:
                actual='-'.join(str(res.get(f'{p}着_艇番')) for p in (1,2,3))
                if actual in COMBOS and initial:initial_validation.append({'code':code,'date':d,'venue':int(code[8:10]),'features':initial['features'],'actual':actual,'snapshot_id':initial.get('snapshot_id')})
                if actual in COMBOS and built['previews']['odds']:validation.append({'code':code,'date':d,'venue':int(code[8:10]),'features':built['features'],'odds':built['previews']['odds'],'actual':actual,'snapshot_id':built.get('snapshot_id')})
        coverage[d]={'cards':len(data['cards']),'results':len(data['results']),'samples':sum(1 for s in samples if s['date']==d),
                     'weather':len(data['weather']),'exhibition':len(data['ex']),'start':len(data['st']),'original':len(data['original'])}
        for venue,features,finishes in surface_pending:surface.add(venue,features,finishes,d)
        behavior.add(data);course_stats.add(data);tactics.add(data)
        prior_motor=data['motor_rows']
        print('context training',d,'samples',len(samples),flush=True)
    if len(samples)<1000 or len({s['date'] for s in samples})<10:raise RuntimeError('Insufficient historical samples; no all-input model published')
    model={'version':VERSION,'trained_through':(today-dt.timedelta(days=1)).isoformat(),
           'generated_at':dt.datetime.now(JST).isoformat(),'samples':samples,'scales':scales(samples),
           'calendars':calendars,'motor_histories':histories,'profiles':profile_rows,'runs':run_rows,
           'tide_book':tide_book,'water_source_errors':water_errors,'surface_state':surface.state,'venue_profiles':PROFILES,'behavior_state':behavior.state,'course_state':course_stats.state,'course_window_days':days+28,
           'registry':registry,'forecast_freeze_minutes':FREEZE_MINUTES,
           'previous_motor_rows':prior_motor,'coverage':coverage,'source_errors':dict(ERRORS),
           'market_alpha':.25,'market_alpha_origin':'preset_unvalidated','calibration':{'status':'not_calibrated'},
           'feature_schema':SCHEMA,'replay':replay_diagnostics,'enabled_groups':[g for g in BASE_GROUPS if g!='comments'],
           'candidate_groups':list(DETAIL_GROUPS),'candidate_policy':'shadow_until_independent_forward_validation','tactical_state':tactics.state}
    model['venue_coverage']={}
    for venue in range(1,25):
        boats=[s for s in samples if s.get('phase')=='preview' and s['venue']==venue and s['lane']==1]
        model['venue_coverage'][str(venue)]={'training_races':len(boats),'wind_races':sum(bool(s['features'].get('wind')) for s in boats),'tide_races':sum(bool(s['features'].get('tide')) for s in boats),'days':len({s['date'] for s in boats}),'latest_day':max((s['date'] for s in boats),default=None)}
    model['calibration']=validate_chronologically(model,validation)
    model.setdefault('phase_calibration',{})['initial']=validate_initial(model,initial_validation)
    model['calibration']['initial']=model['phase_calibration']['initial']
    model['calibration']['ablations']=ablation_report(model,validation,model['calibration'].get('test_dates',[]))
    from boat24_experiments import historical_experiments
    model['integrated_experiments']=historical_experiments(model,validation)
    from boat24_experiments import prior_forward_evidence
    model['forward_evidence']=prior_forward_evidence(today)
    model['approved_candidate_phases']=[r['phase'] for r in model['forward_evidence']['phase_reports'] if r['adoption_approved']]
    import hashlib
    model['generated_at']=dt.datetime.now(JST).isoformat()
    from boat24_quality import POLICY as INPUT_POLICY
    model['input_policy']=INPUT_POLICY
    if model.get('calibration',{}).get('probability_display_approved'):model['validated_input_policy']=INPUT_POLICY
    model['model_id']=hashlib.sha256(json.dumps(model,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    return model


def ensure_model(now):
    yesterday=(now.date()-dt.timedelta(days=1)).isoformat()
    if MODEL.exists():
        previous=read_json(MODEL)
        if previous.get('version')==VERSION and (previous.get('trained_through')==yesterday or os.environ.get('BOAT24_FREEZE_MODEL')=='1' and previous.get('trained_through','9999')<now.date().isoformat() and previous.get('model_id')):return previous,False
    legacy=MODEL.with_suffix('')
    if legacy.exists():
        previous=read_json(legacy)
        if previous.get('version')==VERSION and (previous.get('trained_through')==yesterday or os.environ.get('BOAT24_FREEZE_MODEL')=='1' and previous.get('trained_through','9999')<now.date().isoformat() and previous.get('model_id')):
            write_json(MODEL,previous)
            return previous,True
    model=build_model(now.date(),int(os.environ.get('BOAT24_CONTEXT_DAYS','28')))
    write_json(MODEL,model)
    return model,True
