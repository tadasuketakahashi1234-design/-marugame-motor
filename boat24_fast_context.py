"""Bounded near-cutoff acquisition of verified exhibition, foot times and water."""
import copy
import csv
import datetime as dt
import io
import json
import hashlib,time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from boat24_integrity import JST,timeparse
from boat24_context import make_features,safe_row,number
from boat24_official import parse_before,parse_live_previews

def card_for(s):
    card=copy.deepcopy(s.get('input_snapshot',{}).get('card',{}))
    for b in s.get('boat_identities',[]):
        i=b['lane'];card.setdefault(f'艇{i}_登録番号',b.get('racer'));card.setdefault(f'艇{i}_選手名',b.get('name'));card.setdefault(f'艇{i}_モーター番号',b.get('motor'))
        for k,v in s['input_snapshot']['features'][i-1].get('ability',{}).items():card.setdefault(f'艇{i}_{k}',v)
    return card

def download(url,timeout=8):
    req=urllib.request.Request(url,headers={'User-Agent':'boat24-public-data/3.0','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        raw=r.read();encoding=r.headers.get_content_charset()
    if encoding:return raw.decode(encoding)
    try:return raw.decode('utf-8-sig')
    except UnicodeDecodeError:return raw.decode('cp932')

def collect(targets,now):
    """One CSV per day, one water feed per venue, one joined before page per R."""
    rows={code:{} for code,s in targets};errors={};token=str(int(now.timestamp()//30))
    def acquire(task):
        kind,key=task
        try:
            if kind=='before':
                s=dict(targets)[key];u=f'https://www.boatrace.jp/owpc/pc/race/beforeinfo?hd={key[:8]}&jcd={key[8:10]}&rno={int(key[-2:])}'
                # Retry transient official-site timeouts with a strict bounded budget.
                # The second attempt uses a fresh connection, never a stale cache.
                try:
                    body=download(u+'&v='+token)
                except (TimeoutError, OSError) as first_error:
                    try:
                        body=download(u+'&v='+token+'&retry=1')
                    except (TimeoutError, OSError) as second_error:
                        raise OSError(f'beforeinfo retry exhausted: {type(first_error).__name__}; {type(second_error).__name__}') from second_error
                at=dt.datetime.now(JST).isoformat();card=card_for(s);before=parse_before(body,key,card)
                if not before:raise ValueError('Race/date/all six racer identities not verified')
                preview=parse_live_previews(body,key,card,at)
                for row in preview.values():row['source_url']=u
                return kind,key,{'previews':preview,'before':before,'observed_at':at,'source':u,'body_sha256':hashlib.sha256(body.encode()).hexdigest()},None
            if kind=='water':
                from boat24_water import parse_venue_weather
                u=f'https://race.boatcast.jp/m_txt/{key}/bc_sui_{now.strftime("%Y%m%d")}_{key}.txt'
                surface=parse_venue_weather(download(u+'?v='+token),int(key),dt.datetime.now(JST));surface['source']=u
                return kind,key,surface,None
            u='https://boatracecsv.github.io/data/previews/original_exhibition/'+now.strftime('%Y/%m/%d')+'.csv?v='+token
            body=download(u,4).lstrip('\ufeff')
            return kind,key,{r['レースコード']:r for r in csv.DictReader(io.StringIO(body)) if r.get('レースコード') in rows},None
        except Exception as e:return kind,key,None,str(e)[:160]
    def job(task):
        started=dt.datetime.now(JST).isoformat();tick=time.perf_counter();kind,key,value,error=acquire(task)
        trace={'started_at':started,'completed_at':dt.datetime.now(JST).isoformat(),'seconds':round(time.perf_counter()-tick,4),'state':'unconfirmed' if error else 'parsed','error':error}
        if kind=='before' and value:
            trace.update(identity_verified=True,exhibition_parsed=bool(value['previews'].get('ex')),entry_parsed=bool(value['previews'].get('st')),body_sha256=value['body_sha256'])
            if not trace['exhibition_parsed'] or not trace['entry_parsed']:trace['state']='verified_page_preview_incomplete'
        return kind,key,value,error,trace
    tasks=[('before',code) for code,s in targets]+[('water',v) for v in sorted({c[8:10] for c,s in targets})]+[('original','today')]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for kind,key,value,error,trace in pool.map(job,tasks):
            for code in rows:
                if kind=='original' or kind=='before' and code==key or kind=='water' and code[8:10]==key:rows[code].setdefault('source_checks',{})[kind]=trace
            if error:errors[kind+'_'+key]=error;continue
            if kind=='before':rows[key].update(value)
            elif kind=='water':
                for code in rows:
                    if code[8:10]==key:rows[code]['water']=value
            else:
                for code,row in value.items():rows[code]['original']=row
    return rows,errors

def refresh(base,bundle,model,code,now):
    out=copy.deepcopy(base);saved=out['input_snapshot'];previews=saved.setdefault('previews',{});limit=timeparse(base['cutoff'])
    before_key=lambda rows:json.dumps({k:{a:v for a,v in row.items() if a not in ('取得日時','取得完了日時','source_url','情報源')} for k,row in rows.items()},sort_keys=True,ensure_ascii=False)
    prior=before_key(previews)
    for kind,row in bundle.get('previews',{}).items():
        if kind=='weather':continue # Unstamped previous-R water is supplemental only.
        valid=safe_row(row,limit,now) if row.get('レースコード')==code else {}
        if valid:previews[kind]=valid
    original=safe_row(bundle.get('original'),limit,now) if bundle.get('original',{}).get('レースコード')==code else {}
    if original:previews['original']=original
    water=bundle.get('water',{});observed=timeparse(water.get('observed_at'));measured=timeparse(water.get('measured_at'))
    old_measure=timeparse(previews.get('weather',{}).get('気象観測時刻'))
    if water.get('venue')==int(code[8:10]) and observed and measured and measured.date()==now.date() and measured<=now and observed<=now and observed<limit and (old_measure is None or measured>=old_measure):
        previews['weather']={**water['numeric'],'レースコード':code,'取得日時':observed.isoformat(),'気象観測時刻':measured.isoformat(),'source_url':water['source']}
        out.setdefault('water_context',{})['latest_official_wind']=water
    if before_key(previews)==prior and not bundle.get('before'):return out
    fs=saved['features'];card=card_for(out);saved['card']=card
    fresh=make_features(card,{},{},{},{},{},previews.get('ex',{}),previews.get('st',{}),previews.get('weather',{}),previews.get('original',{}),now.date().isoformat())
    for f,new in zip(fs,fresh):
        for g in ('exhibition','start','weather','original'):f[g]=new[g]
    from boat24_course import CourseStats,add_course_features
    from boat24_behavior import BehaviorStats
    from boat24_water import SurfaceStats
    from boat24_tactics import Tactics
    from boat24_details import attach
    stats=CourseStats(model.get('course_state'));add_course_features(fs,card,int(code[8:10]),stats)
    # Update course-specific local support after an observed entry change.
    composition=saved.get('race_context',{}).get('field_type','unknown')
    for i,f in enumerate(fs,1):
        rid=str(card.get(f'艇{i}_登録番号'));course=int(f.get('start',{}).get('展示進入',i));g=f.setdefault('local_support',{})
        for group,key,prefix in [('local_course',f'{rid}-{int(code[8:10])}-{course}','当地コース'),('course_field',f'{rid}-{course}-{composition}','構成別コース')]:
            for k in list(g):
                if k.startswith(prefix):g.pop(k)
            a=stats.state.get(group,{}).get(key,{});n=a.get('n',0);g[prefix+'確認走数']=n
            if n:g.update({prefix+'1着率':a['wins']/n,prefix+'2連対率':a['two']/n,prefix+'3連対率':a['three']/n,prefix+'平均着順':a['finish_sum']/n})
    out['behavior_forecast']=BehaviorStats(model.get('behavior_state')).attach(fs,card)
    surface=SurfaceStats(model.get('surface_state')).attach(fs,int(code[8:10]),limit,model.get('tide_book',{}))
    surface['latest_official_wind']=out.get('water_context',{}).get('latest_official_wind',{});out['water_context']=surface
    official=saved.setdefault('official',{})
    parts_changed=bool(bundle.get('before')) and bundle['before']!=official.get('before')
    if bundle.get('before'):official.update(before=bundle['before'],before_observed_at=bundle['observed_at'])
    data={'cards':{code:card},**{k:{code:v} for k,v in saved.get('supplemental_previews',{}).items()}}
    keep=[{g:copy.deepcopy(f.get(g,{})) for g in ('series_detail','comment_detail')} for f in fs]
    out['details']=attach(fs,code,card,data,previews,limit,now,official)
    for f,old in zip(fs,keep):
        for g in ('series_detail','comment_detail'):f[g]={**old[g],**f.get(g,{})}
    Tactics(model.get('tactical_state')).attach(fs,card,int(code[8:10]),now.date().isoformat())
    # Retrieval alone does not advance context time; actual non-price values do.
    if before_key(previews)!=prior or parts_changed:out['context_snapshot_at']=now.isoformat()
    saved['source_times']={k:v.get('取得日時') for k,v in previews.items() if v}
    return out
