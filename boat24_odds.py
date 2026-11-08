"""Verified official trifecta quotes, independent of delayed CSV publication."""
import datetime as dt
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse,parse_qs
import html
from boat24_official import get,text,cells
from boat24_integrity import JST,timeparse


def parse_odds(doc,code,observed):
    if not re.fullmatch(r'\d{12}',code):return None
    active=re.search(r'<li\b[^>]*class="is-active2"[^>]*>(.*?)</li>',doc,re.S)
    if not active or f'{int(code[4:6])}月{int(code[6:8])}日' not in text(active[1]):return None
    target=False
    for href in re.findall(r'href="([^"]+)"',doc):
        u=urlparse(html.unescape(href));q=parse_qs(u.query)
        if u.path.endswith('/racelist') and q.get('hd')==[code[:8]] and q.get('jcd')==[code[8:10]] and q.get('rno')==[str(int(code[-2:]))]:target=True
    if not target:return None
    stamp=re.search(r'オッズ更新時間\s*(\d{1,2}:\d{2})',text(doc))
    if not stamp:return None
    try:at=dt.datetime.combine(dt.datetime.strptime(code[:8],'%Y%m%d').date(),dt.time.fromisoformat(stamp[1].zfill(5)),JST)
    except ValueError:return None
    observed=timeparse(observed)
    if not observed or at>observed+dt.timedelta(seconds=60):return None
    table=next((t for t in re.findall(r'<table\b[^>]*>(.*?)</table>',doc,re.S) if 'oddsPoint' in t),None)
    if not table:return None
    head=re.search(r'<thead\b[^>]*>(.*?)</thead>',table,re.S)
    headings=cells(head[1]) if head else []
    if headings[::2]!=list('123456') or len(headings)!=12:return None
    body=re.search(r'<tbody\b[^>]*>(.*?)</tbody>',table,re.S)
    rows=re.findall(r'<tr\b[^>]*>(.*?)</tr>',body[1],re.S) if body else []
    if len(rows)!=20:return None
    quotes={}
    for n,row in enumerate(rows):
        cs=re.findall(r'<td\b([^>]*)>(.*?)</td>',row,re.S)
        width=3 if n%4==0 else 2
        if len(cs)!=6*width:return None
        for first in range(1,7):
            second=[v for v in range(1,7) if v!=first][n//4]
            third=[v for v in range(1,7) if v not in (first,second)][n%4]
            block=cs[(first-1)*width:first*width]
            if width==3 and text(block[0][1])!=str(second):return None
            if text(block[-2][1])!=str(third) or 'oddsPoint' not in block[-1][0]:return None
            value=text(block[-1][1]).replace(',','')
            if not re.fullmatch(r'\d+(?:\.\d)?',value) or float(value)<=0:return None
            quotes[f'3連単_{first}-{second}-{third}']=value
    if len(quotes)!=120:return None
    return {'レースコード':code,'取得日時':at.isoformat(),'公式更新時刻':at.isoformat(),
            '取得完了日時':observed.isoformat(),'情報源':'BOAT RACE公式3連単・120通り照合',
            'body_sha256':hashlib.sha256(doc.encode()).hexdigest(),**quotes}


def collect(codes,now):
    rows={};errors={}
    def job(code):
        url=f'https://www.boatrace.jp/owpc/pc/race/odds3t?hd={code[:8]}&jcd={code[8:10]}&rno={int(code[-2:])}'
        try:
            # A new fetch timestamp never makes an old official update fresh.
            token=str(int(dt.datetime.now(JST).timestamp()//20))
            doc=get(url+'&v='+token)
            row=parse_odds(doc,code,dt.datetime.now(JST))
            if not row:
                # The official page can be mid-update. One bounded refetch
                # recovers transient partial tables without accepting bad data.
                doc=get(url+'&v='+token+'&retry=1')
                row=parse_odds(doc,code,dt.datetime.now(JST))
            if not row:return code,None,'公式オッズの対象R・120通り・更新時刻を再取得後も照合できません'
            row['source_url']=url;return code,row,None
        except Exception as exc:return code,None,str(exc)[:160]
    with ThreadPoolExecutor(max_workers=8) as pool:
        for code,row,error in pool.map(job,list(dict.fromkeys(codes))):
            if row:rows[code]=row
            else:errors[code]=error
    return rows,errors


def attach(data,codes,now):
    rows,errors=collect(codes,now)
    for code,row in rows.items():
        prior=data.get('odds',{}).get(code,{})
        observed=timeparse(row.get('取得日時'))
        age=dt.datetime.now(JST)-observed if observed else None
        if age is not None and dt.timedelta(0)<=age<=dt.timedelta(minutes=5):
            # Cutoff comes from the independently saved race schedule.
            data.setdefault('odds',{})[code]={**{k:v for k,v in prior.items() if not k.startswith('3連単_')},**row}
        else:
            # A successfully parsed but unusable quote must not disappear silently.
            errors[code]='official_quote_timestamp_missing' if age is None else ('official_quote_timestamp_future' if age<dt.timedelta(0) else 'official_quote_stale_over_5min')
    return errors



def validate_quotes(quotes):
    """Require exactly the 120 legal, finite, positive trifecta quotes."""
    import itertools, math
    expected={'3連単_'+'-'.join(map(str,p)) for p in itertools.permutations(range(1,7),3)}
    found={k for k in quotes if k.startswith('3連単_')}
    if found!=expected:return False
    try:return all(math.isfinite(float(quotes[k])) and float(quotes[k])>0 for k in expected)
    except (TypeError,ValueError,OverflowError):return False


def add_market(features,quotes,*unused):
    import math
    odds={k[4:]:float(v) for k,v in quotes.items() if k.startswith('3連単_') and float(v)>0}
    if len(odds)!=120:raise ValueError('All 120 official quotes required')
    z=sum(1/v for v in odds.values());market={c:1/v/z for c,v in odds.items()}
    for lane,f in enumerate(features,1):
        md=f.setdefault('market_detail',{})
        md.update({'市場1着周辺確率':sum(p for c,p in market.items() if c.split('-')[0]==str(lane)),
                   '市場3着内周辺確率':sum(p for c,p in market.items() if str(lane) in c.split('-')),
                   '市場エントロピー':-sum(p*math.log(p) for p in market.values()),
                   '人気上位12集中度':sum(sorted(market.values(),reverse=True)[:12])})
