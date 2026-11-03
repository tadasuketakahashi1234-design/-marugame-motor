"""All-input forecasts: append immutable revisions, settle only pre-cutoff snapshots."""
import datetime as dt
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from boat24_context import (VERSION, FREEZE_MINUTES, GROUPS, predict, fingerprint, number, safe_row, valid_combo)
from boat24_integrity import JST, atomic_write, paper, timeparse
from boat24_train_context import (MODEL, ERRORS, collect_day, ensure_model, History,
                                 profiles_and_runs, race_features, by_code, fetch)

DIRECTORY=Path('omura/docs/full_history')
INDEX=Path('omura/docs/boat24_full_index.json')
from boat24_course import CourseStats, add_course_features
from boat24_priority import add_priority_features
from boat24_behavior import BehaviorStats
from boat24_water import SurfaceStats,PROFILES
from boat24_bets import optimize
from boat24_operations import catalog,health
from boat24_supplement import supplement
from boat24_forward import build_report
from boat24_official import collect as collect_official, attach as attach_official, apply_live_previews

MANIFEST=Path('boat24_full_pending.json')


def latest(rec):
    valid=[r for r in rec.get('revisions',{}).values()
           if timeparse(r.get('created_at')) and timeparse(r.get('cutoff'))
           and timeparse(r['created_at'])<timeparse(r['cutoff'])
           and r.get('evaluation_eligible') is True]
    return max(valid,key=lambda r:(r['created_at'],r['id'])) if valid else None


def make_snapshot(code,card,data,model,history,now,previous=None,clock=None):
    data={**data,'registry':model.get('registry',data.get('registry',{}))}
    day=now.date().isoformat();title=data.get('title',{}).get(code,{})
    if title.get('中止状態') or title.get('電話投票締切予定') in ('確定','中止','順延'):return None,'closed_or_cancelled'
    if data.get('results',{}).get(code) or data.get('payouts',{}).get(code):return None,'result_already_known'
    if any(number(card.get(f'艇{i}_全国勝率')) is None or not card.get(f'艇{i}_登録番号') for i in range(1,7)):
        return None,'incomplete_card'
    built=race_features(code,card,data,history,now,model.get('previous_motor_rows'))
    if not built:return None,'cutoff_unknown'
    cutoff=built['cutoff']
    if now>=cutoff-dt.timedelta(minutes=FREEZE_MINUTES):return None,'cutoff_passed'
    if timeparse(model.get('generated_at')) is None or timeparse(model['generated_at'])>now:return None,'model_timestamp_invalid'
    if model.get('trained_through','9999')>=day:return None,'model_contains_future_data'
    previews=built['previews']
    retained=[]
    # Preserve previously acquired valid previews through transient source outages.
    for kind,old in (previous or {}).get('input_snapshot',{}).get('previews',{}).items():
        if kind in previews and not previews[kind] and safe_row(old,cutoff,now):
            previews[kind]=old;retained.append(kind)
    if retained:
        # Recompute with the retained raw rows, never silently downgrade complete inputs.
        mixed={**data}
        for kind in retained:mixed[kind]={**data.get(kind,{}),code:previews[kind]}
        built=race_features(code,card,mixed,history,now,model.get('previous_motor_rows'))
    add_course_features(built['features'],card,int(code[8:10]),CourseStats(model.get('course_state')))
    built['race_context']=add_priority_features(built['features'],card,title,data['registry'],CourseStats(model.get('course_state')),int(code[8:10]),day,cutoff)
    behavior=BehaviorStats(model.get('behavior_state')).attach(built['features'],card)
    official=attach_official(built['features'],code,cutoff,data.get('official',{}))
    water=SurfaceStats(model.get('surface_state')).attach(built['features'],int(code[8:10]),cutoff,model.get('tide_book',{}))
    water['latest_official_wind']=data.get('official',{}).get('venue_weather',{}).get(code[8:10],{})
    from boat24_details import attach as attach_details,SCHEMA
    from boat24_tactics import Tactics
    from boat24_context import ALL_GROUPS
    from boat24_experiments import POLICY
    from boat24_factors import audit
    detail=attach_details(built['features'],code,card,data,built['previews'],cutoff,now,official)
    Tactics(model.get('tactical_state')).attach(built['features'],card,int(code[8:10]),day)
    # Do not append identical forecasts just because an unchanged report was
    # fetched again or the wall clock advanced. Freshness is still displayed.
    digest_features=[{k:v for k,v in f.items() if k!='data_quality'} for f in built['features']]
    comments_identity={lane:{k:c.get(k) for k in ('racer','comment','source')} for lane,c in official.get('comments',{}).items()}
    h=fingerprint(digest_features,built['previews']['odds'],model,{'before':official.get('before'),'comments':comments_identity,'race_flags':official.get('race_flags')})
    if previous and previous.get('id')==h:return None,'unchanged_inputs'
    result=predict(built['features'],int(code[8:10]),day,model,built['previews']['odds'])
    baseline=result
    candidate=predict(built['features'],int(code[8:10]),day,{**model,'enabled_groups':[g for g in ALL_GROUPS if g!='data_quality'],'phase_calibration':{}},built['previews']['odds'])
    gate=next((r for r in model.get('forward_evidence',{}).get('phase_reports',[]) if r['phase']==candidate['phase']),{})
    if gate.get('adoption_approved') and str(int(code[8:10])) in gate.get('eligible_venues',[]):
        result=candidate
        # Shadow gate does not establish calibrated candidate probabilities.
        result['probability_verified']=False
        result['decision']='候補モデルを事前比較条件で採用・確率校正は再検証中'
    compact=lambda p:{k:p[k] for k in ('phase','probabilities','selection')}
    result['research']={'policy':POLICY,'feature_schema':SCHEMA,'baseline':compact(baseline),'candidate':compact(candidate),
                        'candidate_active':result is candidate,'adoption_evidence':model.get('forward_evidence',{}),
                        'candidate_groups':model.get('candidate_groups',[]),'no_automatic_fixed_bonus':True}
    factor_rows=audit(built['features'],result['feature_usage'],model)
    result['factor_summary']={state:sum(r['state']==state for r in factor_rows) for state in ('used_unproven','shadow','awaiting_history','unavailable')}
    result['details']=detail
    valid_odds={c:number(built['previews']['odds'].get('3連単_'+c)) for c in result['probabilities']}
    result['allocation']=optimize(result['probabilities'],valid_odds)
    if len([v for v in valid_odds.values() if v and v>0])==120:
        z=sum(1/v for v in valid_odds.values());mp={c:1/v/z for c,v in valid_odds.items()}
        result['market_baseline']={'probabilities':mp,'picks':sorted(mp,key=lambda c:(-mp[c],c))[:12],'observed_at':built['previews']['odds'].get('取得日時')}
    result['behavior_forecast']=behavior
    result['water_context']=water
    required=set(GROUPS)|{'odds'}
    if int(code[8:10])==3:required.remove('original')
    result['complete_inputs']=all(result['feature_usage'][g]['status']=='used' and (g=='odds' or result['feature_usage'][g]['used_lanes']==6) for g in required)
    result['complete_inputs']=result['complete_inputs'] and all(len(c.get('uses',[]))==3 and c.get('matched_riders')==3 for c in built['contexts'].values())
    required_fields={'exhibition':{'展示タイム相対'},'start':{'ST絶対値相対','展示進入'},
                     'weather':{'風速(m)','風向','波の高さ(cm)','天候','気温(℃)','水温(℃)'},
                     'motor':{'モーター2連対率','モーター3連対率','期_勝率','期_2連対率','期_3連対率'}}
    result['complete_inputs']=result['complete_inputs'] and all(fields<=set(f[group]) for group,fields in required_fields.items() for f in built['features'])
    if int(code[8:10])!=3:
        original_keys=set().union(*(set(f['original']) for f in built['features']))
        result['complete_inputs']=result['complete_inputs'] and bool(original_keys) and all(set(f['original'])==original_keys for f in built['features'])
    result['extended_inputs_complete']=all(result['feature_usage'][g]['status']=='used' and not result['feature_usage'][g].get('unused_fields') for g in ('course','style','maintenance','comments'))
    result['extended_inputs_complete']=result['extended_inputs_complete'] and result['feature_usage']['wind']['status']=='used' and (PROFILES[str(int(code[8:10]))]['tidal_range']=='なし' or result['feature_usage']['tide']['status']=='used')
    result['complete_inputs']=result['complete_inputs'] and result['extended_inputs_complete'] and built['race_context']['unknown_sex_count']==0 and all(result['feature_usage'][g]['status']=='used' and result['feature_usage'][g]['used_lanes']==6 for g in ('race_conditions','opposition','local_support')) and all(f['local_support'].get('当地公式成績未確認')==0 for f in built['features'])
    completed=clock() if clock else now
    # Real calls must finish before the freeze, not merely start before it.
    if completed>=cutoff-dt.timedelta(minutes=FREEZE_MINUTES):return None,'computed_after_freeze'
    result.update({'id':h,'created_at':now.isoformat(),'computed_at':completed.isoformat(),'cutoff':cutoff.isoformat(),
                   'evaluation_eligible':True,'model_generated_at':model['generated_at'],'model_id':model.get('model_id'),
                   'input_snapshot':{'race_context':built['race_context'],'features':built['features'],'previews':built['previews'],
                                     'motor_history':built['contexts'],'official':official,'tide_schedule':data.get('official',{}).get('tides',{}).get(day), 'source_times':built['source_times'],
                                     'feature_schema':SCHEMA,'supplemental_previews':{k:safe_row(data.get(k,{}).get(code),cutoff,now) for k in ('tokuten','od1','od2')},
                                     'missing_data_reasons':{lane:{'motor':ctx.get('status'),'period_verified':bool(ctx.get('period'))} for lane,ctx in built['contexts'].items()},'retained_sources':retained,'captured_at':now.isoformat()}})
    return json.loads(json.dumps(result,ensure_ascii=False,allow_nan=False)),None


def settle(rec,res,pay,now):
    from boat24_settlement import settle_record
    # Keep ambiguous legacy refund cases pending until an actual course/boat map
    # proves which tickets are refundable.
    if res and any(res.get(f'{i}コース_F') for i in range(1,7)) and not any(res.get(f'{i}コース_艇番') for i in range(1,7)):
        rec['result_pending_reason']='返還艇を照合できないため集計対象外・精算保留'
        return False
    return settle_record(rec,res,pay,latest(rec),now)


def summary(records):
    settled=[r for r in records if r.get('result') and latest(r)]
    output={'saved':len(records),'settled':len(settled),'pending':sum(not r.get('result') and not r.get('result_pending_reason') for r in records),'excluded_refund':sum(bool(r.get('result_pending_reason')) for r in records),
            'complete_inputs':sum(bool((latest(r) or {}).get('complete_inputs')) for r in records)}
    for n in (12,18):
        bets=[r['result']['paper'][str(n)] for r in settled if str(n) in r['result'].get('paper',{})]
        stake=sum(b['stake'] for b in bets);returns=sum(b['return'] for b in bets);hits=sum(b['hit'] for b in bets)
        output[str(n)]={'races':len(bets),'hits':hits,'stake':stake,'return':returns,'profit':returns-stake,
                        'hit_rate':hits/len(bets) if bets else None,'roi':returns/stake if stake else None}
    return output


def build_index(directory=DIRECTORY,now=None):
    days={};all_records=[]
    catalogs={};latest_health={}
    for path in sorted(directory.glob('*.json')):
        data=json.loads(path.read_text());records=list(data.get('records',{}).values());all_records+=records
        catalogs[path.stem]=data.get('catalog',{})
        latest_health=data.get('health',{}) or latest_health
        days[path.stem]={'summary':summary(records),'venues':{str(v):summary([r for r in records if r['venue']==v]) for v in range(1,25)}}
    legacy_path=directory.parent/'boat24_ledger.json'
    legacy=json.loads(legacy_path.read_text()) if legacy_path.exists() else {}
    from boat24_experiments import paired_report
    from boat24_factors import CATALOG
    return {'integrated_learning':paired_report(all_records),'factor_catalog':CATALOG,'catalogs':catalogs,'health':latest_health,'forward_report':build_report(all_records,legacy),'schema':1,'model':VERSION,'updated_at':(now or dt.datetime.now(JST)).isoformat(),
            'latest_day':max(days) if days else None,'days':days,'summary':summary(all_records),
            'venues':{str(v):summary([r for r in all_records if r['venue']==v]) for v in range(1,25)},
            'warning':'総合予想の保存履歴には過去版も含まれます。版別比較を参照してください。確率は別期間の校正検証条件を満たす場合のみ表示し、収益性は未証明です。'}


def merge_day(remote,local):
    # Immutable revision IDs: remote observations always win on collisions.
    merged=json.loads(json.dumps(local,ensure_ascii=False));merged['catalog']=json.loads(json.dumps({**remote.get('catalog',{}),**local.get('catalog',{})}));merged['records']=json.loads(json.dumps(remote.get('records',{}),ensure_ascii=False))
    for code,incoming in local.get('records',{}).items():
        if code not in merged['records']:merged['records'][code]=incoming;continue
        rec=merged['records'][code]
        if incoming.get('result_pending_reason') and not rec.get('result'):rec['result_pending_reason']=incoming['result_pending_reason']
        for key,revision in incoming.get('revisions',{}).items():rec.setdefault('revisions',{}).setdefault(key,revision)
        for key,value in incoming.get('result_history',{}).items():rec.setdefault('result_history',{}).setdefault(key,value)
        new_result=incoming.get('result') or {};old_result=rec.get('result') or {}
        if new_result.get('id') and timeparse(new_result.get('settled_at')) and (not timeparse(old_result.get('settled_at')) or timeparse(new_result['settled_at'])>timeparse(old_result['settled_at'])):
            rec['result']=new_result;rec.pop('result_pending_reason',None)

        if not rec.get('result') and incoming.get('result'):
            rec['result']=dict(incoming['result']);snap=latest(rec)
            if snap:
                rec['result']['selection_snapshot_id']=snap['id']
                rec['result']['paper']=paper(snap['selection'],rec['result']['combo'],rec['result']['payout_100yen'])
    for code,item in merged.get('catalog',{}).items():
        if code in merged['records']:
            item['has_forecast']=True
            if merged['records'][code].get('result'):item['state']='settled'
            elif item['state'] in ('waiting_initial','closed_no_forecast','program_unconfirmed','cutoff_unknown'):item['state']='saved'
    assert set(remote.get('records',{}))<=set(merged['records'])
    for code,old in remote.get('records',{}).items():
        for key,value in old.get('revisions',{}).items():
            assert merged['records'][code]['revisions'][key]==value, 'An existing input revision changed'
    return merged


def main():
    now=dt.datetime.now(JST);day=now.date().isoformat();model,changed=ensure_model(now)
    ERRORS.clear()
    data=collect_day(now.date());now=dt.datetime.now(JST)
    registry=supplement(data,model.get('registry',{}),now)
    # Supplements are identity observations only. A new digest prevents treating changed identities as unchanged inputs.
    if registry!=model.get('registry'):
        import hashlib
        model=dict(model,registry=registry);model['model_id']=hashlib.sha256((str(model.get('model_id'))+json.dumps(registry,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()
        changed=True
        from boat24_model_io import write_json
        write_json(MODEL,model)
    if day!=now.date().isoformat():raise RuntimeError('JST date changed during collection')
    if now.hour>=8 and not data['cards'] and not data['results'] and not data['payouts']:raise RuntimeError('All race sources unavailable; existing all-input forecasts kept')
    candidates=[]
    from boat24_context import deadline
    for code,card in data['cards'].items():
        limit=next((deadline(data.get(k,{}).get(code),day) for k in ('odds','ex','st','title') if deadline(data.get(k,{}).get(code),day)),None)
        if limit and now<limit-dt.timedelta(minutes=2) and not data['results'].get(code) and not data['payouts'].get(code):candidates.append((limit,code))
    candidates=[code for limit,code in sorted(candidates) if limit<=now+dt.timedelta(minutes=30)][:32]
    data['official']=collect_official(candidates,data['cards'],now,data.get('title'))
    apply_live_previews(data,data['official'],dt.datetime.now(JST))
    history=History(model['calendars'],model['motor_histories'],model['profiles'],model['runs'])
    profiles,runs=profiles_and_runs(data,day,CourseStats(model.get('course_state')))
    for p in profiles:history.add_profile(p)
    for r in runs:history.add_run(r)
    DIRECTORY.mkdir(parents=True,exist_ok=True);path=DIRECTORY/(day+'.json')
    ledger=json.loads(path.read_text()) if path.exists() else {'schema':1,'date':day,'model':VERSION,'records':{}}
    records=ledger['records'];made=updated=settled=0;skipped={}
    for code,card in data['cards'].items():
        if not code.startswith(now.strftime('%Y%m%d')) or len(code)!=12:continue
        if not code[8:].isdigit() or not 1<=int(code[8:10])<=24 or not 1<=int(code[10:12])<=12:continue
        current=records.get(code)
        if current and current.get('result'):continue
        snap,reason=make_snapshot(code,card,data,model,history,dt.datetime.now(JST),latest(current) if current else None,clock=lambda:dt.datetime.now(JST))
        if not snap:skipped[reason]=skipped.get(reason,0)+1;continue
        if not current:
            current={'race_code':code,'date':day,'venue':int(code[8:10]),'race':int(code[10:12]),
                     'created_at':snap['created_at'],'model':VERSION,'revisions':{},'result':None}
            records[code]=current;made+=1
        else:updated+=1
        current['revisions'].setdefault(snap['id'],snap)
    for code,rec in records.items():
        settled+=settle(rec,data['results'].get(code),data['payouts'].get(code),dt.datetime.now(JST))
    ledger['catalog']=catalog(data,records,dt.datetime.now(JST))
    ledger['health']=health(data,ledger['catalog'],{**ERRORS,**data.get('supplement_errors',{}),**data.get('official',{}).get('errors',{})},dt.datetime.now(JST))
    ledger['updated_at']=dt.datetime.now(JST).isoformat();ledger['diagnostics']={'new_forecasts':made,'updated_forecasts':updated,'new_settlements':settled,'skipped':skipped,'source_errors':dict(ERRORS)}
    atomic_write(path,ledger);touched=[str(path)]
    # Retry unsettled previous dates without requiring their race cards.
    pending=[]
    for old_path in sorted(DIRECTORY.glob('*.json')):
        if old_path.stem>=day:continue
        old=json.loads(old_path.read_text())
        if old_path.stem>=(now.date()-dt.timedelta(days=14)).isoformat() or any(not r.get('result') for r in old.get('records',{}).values()):pending.append((old_path,old))
    old_index=json.loads(INDEX.read_text()) if INDEX.exists() else {};cursor=old_index.get('backfill_cursor','')
    pending=[p for p in pending if p[0].stem>cursor]+[p for p in pending if p[0].stem<=cursor]
    for old_path,old in pending[:14]:
        with ThreadPoolExecutor(max_workers=2) as pool:
            res,pay=list(pool.map(lambda k:by_code(fetch(k,old_path.stem.replace('-','/'))),('results','payouts')))
        for code,rec in old['records'].items():settle(rec,res.get(code),pay.get(code),dt.datetime.now(JST))
        atomic_write(old_path,old);touched.append(str(old_path))
    index=build_index(now=dt.datetime.now(JST));index['backfill_cursor']=pending[:14][-1][0].stem if pending else ''
    index['diagnostics']=ledger['diagnostics'];index['training']={'through':model['trained_through'],'samples':len(model['samples']),'market_prior':model['market_alpha'],'validation':model['calibration'],'source_errors':model.get('source_errors',{}),'venue_coverage':model.get('venue_coverage',{}),'venue_profiles':model.get('venue_profiles',PROFILES),'water_source_errors':model.get('water_source_errors',{}),'surface_summary':{'venues_with_wind_history':sorted({k.split('|')[0] for k in model.get('surface_state',{}).get('wind',{})}),'venues_with_tide_data':sorted(model.get('tide_book',{}))},'course_window_days':model.get('course_window_days')}
    index['training'].update({'integrated_experiments':model.get('integrated_experiments',{}),'replay':model.get('replay',{}),'candidate_policy':model.get('candidate_policy'),'feature_schema':model.get('feature_schema'),'learned_fields':sorted(model.get('scales',{})),'approved_candidate_phases':model.get('approved_candidate_phases',[])})
    atomic_write(INDEX,index)
    if changed:touched.append(str(MODEL))
    touched.append('omura/docs/boat24_official_cache.json')
    if __import__('boat24_supplement').CACHE.exists():touched.append(str(__import__('boat24_supplement').CACHE))
    atomic_write(MANIFEST,{'paths':touched,'index':str(INDEX),'version':VERSION})
    print(json.dumps({'model':VERSION,'new':made,'updated':updated,'settled':settled,'total_today':len(records),'complete_inputs':summary(list(records.values()))['complete_inputs'],'skipped':skipped},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
