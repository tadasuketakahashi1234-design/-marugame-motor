#!/usr/bin/env python3
"""Forward-only paper trading ledger. Python stdlib, no API keys."""
import csv, io, json, math, os, itertools, urllib.request, datetime as dt, pathlib, tempfile
from zoneinfo import ZoneInfo
JST=ZoneInfo('Asia/Tokyo'); ROOT='https://boatracecsv.github.io/data/'; OUT=pathlib.Path('omura/docs/boat24_ledger.json')
NOW=dt.datetime.now(JST); DAY=NOW.strftime('%Y-%m-%d'); DATEPATH=NOW.strftime('%Y/%m/%d')
KINDS={'cards':'programs/race_cards','waku':'programs/waku10','motor':'programs/motor_stats','ex':'previews/tkz','st':'previews/stt','weather':'previews/sui','odds':'previews/od3','results':'results/realtime','payouts':'results/payouts'}
def load(kind, datepath=None):
    try:
        req=urllib.request.Request(ROOT+KINDS[kind]+'/'+(datepath or DATEPATH)+'.csv',headers={'User-Agent':'boat24-research/1.0'})
        with urllib.request.urlopen(req,timeout=22) as f: raw=f.read().decode('utf-8-sig')
        return list(csv.DictReader(io.StringIO(raw)))
    except Exception as e:
        print('unavailable',kind,str(e)[:140]); return []
def num(v):
    try: return float(str(v).replace(',','').replace('円','').strip())
    except (ValueError,TypeError): return None
def parse_time(v):
    if not v: return None
    s=str(v).strip().replace('T',' ').replace('Z','+00:00')
    for fmt in ('%Y-%m-%d %H:%M:%S','%Y-%m-%d %H:%M','%Y/%m/%d %H:%M:%S','%Y/%m/%d %H:%M'):
        try: return dt.datetime.strptime(s,fmt).replace(tzinfo=JST)
        except ValueError: pass
    try:
        d=dt.datetime.fromisoformat(s)
        return d.replace(tzinfo=JST) if d.tzinfo is None else d.astimezone(JST)
    except ValueError: return None
def cutoff(row):
    v=row.get('締切時刻') or row.get('締切予定時刻')
    t=parse_time(v)
    if t: return t
    if v and ':' in str(v):
        try: return dt.datetime.combine(NOW.date(),dt.time.fromisoformat(str(v).strip()[:5]),JST)
        except ValueError: pass
    return None
def snapshot_ok(row,deadline):
    if not row or not deadline: return False
    stamp=parse_time(row.get('取得日時') or row.get('更新日時') or row.get('気象観測時刻'))
    return bool(stamp and stamp<=NOW and stamp<deadline)
def index(rows): return {r.get('レースコード'):r for r in rows if r.get('レースコード')}
def probability(card,ex,st,waku):
    # Versioned baseline; coefficients NOT calibrated. No same-series results or future motor statistics.
    score=[]
    exvals=[num(ex.get(f'艇{i}_展示タイム')) for i in range(1,7)]
    med=sorted(v for v in exvals if v is not None)
    median=med[len(med)//2] if med else None
    for i in range(1,7):
        w=num(card.get(f'艇{i}_全国勝率')) or 5
        local=num(card.get(f'艇{i}_当地勝率'))
        motor=num(card.get(f'艇{i}_モーター2連対率'))
        ms=(max(-4,min(4,(motor-35)*.11)) if motor is not None else 0)
        e=num(ex.get(f'艇{i}_展示タイム'))
        eb=max(-3,min(3,(median-e)*9)) if median is not None and e is not None else 0
        s=(w-5)*.62+(local-5)*.18 if local is not None else (w-5)*.62
        s+=([1.0,.35,0,-.25,-.48,-.65][i-1])+ms*.12+eb*.12
        score.append(s)
    combos=[]
    for a,b,c in itertools.permutations(range(6),3):
        z=score[a]*.58+score[b]*.29+score[c]*.13
        combos.append((f'{a+1}-{b+1}-{c+1}',z))
    peak=max(x[1] for x in combos)
    weights=[math.exp((x[1]-peak)*1.15) for x in combos]
    total=sum(weights)
    return {c:round(w/total,8) for (c,_),w in zip(combos,weights)}
def odds_for(row,combo): return num(row.get('3連単_'+combo))
def main():
    old=json.loads(OUT.read_text()) if OUT.exists() else {'schema':1,'model':'baseline-0.1-UNVALIDATED','predictions':{},'diagnostics':{}}
    predictions=old.setdefault('predictions',{})
    data={k:load(k) for k in KINDS}
    ix={k:index(v) for k,v in data.items() if k!='motor'}
    made=settled=0; skipped={}
    for code,card in ix['cards'].items():
        if len(code)!=12 or code[:8]!=NOW.strftime('%Y%m%d'): continue
        venue=int(code[8:10]); race=int(code[10:12])
        if not (1<=venue<=24 and 1<=race<=12): continue
        record=predictions.get(code)
        if record is None:
            odds=ix['odds'].get(code); ex=ix['ex'].get(code); st=ix['st'].get(code); waku=ix['waku'].get(code)
            deadline=cutoff(odds or ex or st or {})
            # Do not create forecasts from stale/post-deadline data or without a real odds snapshot.
            if not deadline or NOW>=deadline-dt.timedelta(minutes=2):
                skipped['cutoff_missing_or_passed']=skipped.get('cutoff_missing_or_passed',0)+1; continue
            if not snapshot_ok(odds,deadline):
                skipped['odds_snapshot_missing']=skipped.get('odds_snapshot_missing',0)+1; continue
            if ex and not snapshot_ok(ex,deadline): ex={}
            if st and not snapshot_ok(st,deadline): st={}
            p=probability(card,ex,st,waku or {})
            ranked=sorted(p,key=p.get,reverse=True)
            # Research only: positive EV cannot be asserted until calibration validated.
            selections={str(n):ranked[:n] for n in (12,18)}
            record={'race_code':code,'date':DAY,'venue':venue,'race':race,'created_at':NOW.isoformat(),
                    'cutoff':deadline.isoformat(),'model':'baseline-0.1-UNVALIDATED',
                    'decision':'見送り（予測確率未校正）','selection':selections,
                    'probabilities':p,'odds':{c:odds_for(odds,c) for c in ranked},
                    'input_availability':{'exhibition':bool(ex),'start_exhibition':bool(st),'waku':bool(waku)},
                    'result':None}
            predictions[code]=record; made+=1
        if record.get('result') is not None: continue
        result=ix['results'].get(code)
        if not result: continue
        vals=[result.get(f'{i}着_艇番') for i in (1,2,3)]
        if not all(str(v).strip() in '123456' and len(str(v).strip())==1 for v in vals): continue
        actual='-'.join(str(v).strip() for v in vals)
        if len(set(vals))!=3: continue
        payout=ix['payouts'].get(code) or {}
        pay=num(next((v for k,v in payout.items() if '3連単' in k and '払戻' in k),None))
        # Never silently assume a missing payout is zero.
        if pay is None: continue
        record['result']={'combo':actual,'payout_100yen':pay,'settled_at':NOW.isoformat(),
                          'paper':{str(n):{'hit':actual in record['selection'][str(n)],
                                            'stake':n*100,
                                            'return':pay if actual in record['selection'][str(n)] else 0} for n in (12,18)}}
        settled+=1
    # Settle forecasts from earlier days; never manufacture forecasts retrospectively.
    past_dates=sorted({r['date'] for r in predictions.values() if r.get('result') is None and r['date']!=DAY})[-14:]
    for past in past_dates:
        path=past.replace('-','/')
        prev_results=index(load('results',path)); prev_payouts=index(load('payouts',path))
        for code,record in predictions.items():
            if record['date']!=past or record.get('result') is not None: continue
            result=prev_results.get(code); payout=prev_payouts.get(code)
            if not result or not payout: continue
            vals=[str(result.get(f'{i}着_艇番','')).strip() for i in (1,2,3)]
            if any(v not in list('123456') for v in vals) or len(set(vals))!=3: continue
            pay=num(next((v for k,v in payout.items() if '3連単' in k and '払戻' in k),None))
            if pay is None: continue
            actual='-'.join(vals)
            record['result']={'combo':actual,'payout_100yen':pay,'settled_at':NOW.isoformat(),
              'paper':{str(n):{'hit':actual in record['selection'][str(n)],'stake':n*100,
              'return':pay if actual in record['selection'][str(n)] else 0} for n in (12,18)}}
            settled+=1
    old['updated_at']=NOW.isoformat();old['diagnostics']={'new_predictions':made,'new_settlements':settled,'skipped':skipped,
        'source_counts':{k:len(v) for k,v in data.items()},'notes':'Forecasts saved only before cutoff; missed runs are not backfilled.'}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=OUT.parent,delete=False) as f:
        json.dump(old,f,ensure_ascii=False,separators=(',',':')); name=f.name
    os.replace(name,OUT)
    print(json.dumps({'new':made,'settled':settled,'total':len(predictions),'skipped':skipped},ensure_ascii=False))
if __name__=='__main__':main()
