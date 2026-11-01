import csv, io, json, re, statistics, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE='https://boatracecsv.github.io/data/programs/'
JST=timezone(timedelta(hours=9))
ROOT=Path(__file__).parent

def fetch(kind, day):
    url=f'{BASE}{kind}/{day:%Y/%m/%d}.csv'
    try:
        req=urllib.request.Request(url,headers={'User-Agent':'MarugameMotorDashboard/1.0'})
        with urllib.request.urlopen(req,timeout=18) as r:
            content=r.read().decode('utf-8-sig')
        return list(csv.DictReader(io.StringIO(content)))
    except Exception as e:
        print('skip',url,str(e)[:120]); return []

def is_marugame(row):
    return str(row.get('場コード',row.get('レース場コード',''))).strip().zfill(2)=='15'

def num(v):
    try:return float(str(v).replace('%','').replace(',',''))
    except (ValueError,TypeError):return None

def ranks(s):
    # full-width numerals are converted; [1] final-race positions are included
    s=str(s).translate(str.maketrans('１２３４５６','123456'))
    return [int(c) for c in s if c in '123456']

def unique_history(rows):
    d={}
    for r in rows:
        if not is_marugame(r):continue
        n=str(r.get('モーター番号','')).strip()
        end=r.get('使用終了日','')
        if not n or not end:continue
        key=(n,end,r.get('使用者名',''))
        d[key]=r
    return d

def build(stats,history,asof):
    # Only past completed meetings. 3 latest uses per motor, avoid leakage from future dates.
    groups={}
    for (n,end,_),r in history.items():
        if end<=asof:groups.setdefault(n,[]).append(r)
    for rows in groups.values():rows.sort(key=lambda r:r.get('使用終了日',''),reverse=True)
    out=[]
    for r in stats:
        if not is_marugame(r):continue
        n=str(r.get('モーター番号','')).strip()
        if not n:continue
        recent=groups.get(n,[])[:3]
        uses=[]; deviations=[]; weights=[]
        for i,h in enumerate(recent):
            placings=ranks(h.get('着順列',''))
            if not placings:continue
            avg=statistics.mean(placings)
            # 3.5 is neutral placing for 6 boats; NOT a player-skill correction.
            deviation=(3.5-avg)/2.5*100
            w=[0.5,0.3,0.2][i]*min(1,len(placings)/5)
            deviations.append(deviation*w); weights.append(w)
            uses.append({'start':h.get('使用開始日',''),'end':h.get('使用終了日',''),
                         'racer':h.get('使用者名',''),'grade':h.get('グレード',''),
                         'finishes':h.get('着順列',''),'races':len(placings),'avg_finish':round(avg,2)})
        history_score=(sum(deviations)/sum(weights) if weights else 0)
        two=num(r.get('2連対率'))
        three=num(r.get('3連対率'))
        # Explicit provisional raw score: NOT skill-adjusted, NOT probability.
        score=round(max(0,min(100,50+0.28*history_score+0.22*((two if two is not None else 33)-33)+0.10*((three if three is not None else 50)-50))),1)
        confidence='高' if len(uses)==3 and sum(x['races'] for x in uses)>=15 else ('中' if len(uses)>=2 else '低')
        out.append({'number':n,'score':score,'rank':'S' if score>=75 else 'A' if score>=62 else 'B' if score>=48 else 'C' if score>=35 else 'D',
                    'two_rate':two,'three_rate':three,'starts':num(r.get('出走数')),
                    'period_start':r.get('モーター期起算日',''),'uses':uses,'confidence':confidence})
    out.sort(key=lambda x:(-x['score'],int(x['number']) if x['number'].isdigit() else 999))
    return out

def main():
    today=datetime.now(JST).date()
    stats=[]; stat_date=None
    for ago in range(0,22):
        day=today-timedelta(days=ago)
        rows=[r for r in fetch('motor_stats',day) if is_marugame(r)]
        if rows:stats=rows;stat_date=day;break
    if not stats:raise SystemExit('No Marugame motor_stats found in last 22 days. Existing published data left untouched.')
    # history snapshot keyed by completed meeting END DATE, not today's date
    history={}; found=[]
    for ago in range(0,95):
        day=today-timedelta(days=ago)
        rows=fetch('motor_history',day)
        selected=[r for r in rows if is_marugame(r)]
        if selected:
            history.update(unique_history(selected));found.append(day.isoformat())
            if len(found)>=5:break
    motors=build(stats,history,today.isoformat())
    if not motors:raise SystemExit('Empty motor list: abort publishing')
    output={'updated_at':datetime.now(JST).isoformat(timespec='minutes'),'stats_date':stat_date.isoformat(),
            'history_snapshot_dates':found,'stadium':'丸亀','method':'暫定・選手補正なし',
            'warning':'着順と期成績を使った暫定評価です。選手実力・コース・相手関係は未補正。予測確率ではありません。',
            'motors':motors}
(ROOT/'docs').mkdir(parents=True, exist_ok=True)
    dest=ROOT/'docs'/'data.json';dest.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(f'Published {len(motors)} motors, stats {stat_date}, history snapshots {found}')

if __name__=='__main__':main()
