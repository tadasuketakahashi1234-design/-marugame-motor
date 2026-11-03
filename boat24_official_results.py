"""Official finish, payout and explicit refund joins, including absent boats."""
import datetime as dt
import hashlib
import html
import json
from pathlib import Path
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse,parse_qs
from boat24_integrity import JST,atomic_write,timeparse
from boat24_official import get,text,cells

CACHE=Path('omura/docs/boat24_official_results.json')

def parse_result(doc,code,observed_at,source):
    if not re.fullmatch(r'\d{12}',code):return None
    active=re.search(r'<li\b[^>]*class="is-active2"[^>]*>(.*?)</li>',doc,re.S)
    if not active or f'{int(code[4:6])}月{int(code[6:8])}日' not in text(active[1]):return None
    # The selected race's tabs echo the exact date, venue and race.
    selected=False
    for link in re.findall(r'href="([^"]+)"',doc):
        u=urlparse(html.unescape(link));q=parse_qs(u.query)
        if u.path.endswith('/racelist') and q.get('hd')==[code[:8]] and q.get('jcd')==[code[8:10]] and q.get('rno')==[str(int(code[-2:]))]:selected=True
    if not selected:return None
    finishes={};lanes=set();refunds=None;winners={}
    for table in re.findall(r'<table\b[^>]*>(.*?)</table>',doc,re.S|re.I):
        headings=[unicodedata.normalize('NFKC',text(v)) for v in re.findall(r'<th\b[^>]*>(.*?)</th>',table,re.S|re.I)]
        if '枠' in headings and '着' in headings:
            for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',table,re.S|re.I):
                c=cells(row)
                if len(c)<3:continue
                place=unicodedata.normalize('NFKC',c[0]);lane=c[1].strip()
                if lane not in '123456' or len(lane)!=1:continue
                lanes.add(lane)
                if place in ('1','2','3'):finishes[place]=lane
        if headings==['返還']:
            body=re.search(r'<tbody\b[^>]*>(.*?)</tbody>',table,re.S|re.I)
            if not body:return None
            nums=re.findall(r'<span\b[^>]*class="[^"]*numberSet1_number[^"\n]*"[^>]*>\s*([1-6])\s*</span>',body[1])
            refunds=sorted(set(nums))
            if not nums and re.search(r'[1-6]',text(body[1])):return None
        if '勝式' in headings and '払戻金' in headings:
            kind=None
            for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',table,re.S|re.I):
                c=cells(row)
                if not c:continue
                if c[0] in ('3連単','3連複','2連単','2連複','拡連複','単勝','複勝'):kind=c.pop(0)
                if kind!='3連単' or len(c)<2:continue
                nums=re.findall(r'[1-6]',unicodedata.normalize('NFKC',c[0]));money=re.sub(r'[^0-9]','',c[1])
                if len(nums)==3 and len(set(nums))==3 and money and int(money)>0:winners['-'.join(nums)]=int(money)
    if len(lanes)!=6 or set(finishes)!=set('123') or refunds is None or not winners:return None
    combo='-'.join(finishes[str(i)] for i in (1,2,3))
    if combo not in winners or any(set(c.split('-'))&set(refunds) for c in winners):return None
    res={'レースコード':code,**{f'{i}着_艇番':finishes[str(i)] for i in (1,2,3)},'取得日時':observed_at,
         'official_refund_verified':True,'official_refund_boats':refunds,'official_result_source':source}
    pay={'レースコード':code,'3連単_組番':combo,'3連単_払戻金':str(winners[combo]),'取得日時':observed_at,'official_payout_source':source}
    if len(winners)>1:pay['winning_trifectas']=[{'combo':c,'payout_100yen':p} for c,p in winners.items()]
    return {'race_code':code,'result':res,'payout':pay,'source':source,'observed_at':observed_at,'body_sha256':hashlib.sha256(doc.encode()).hexdigest()}

def merge_cache(remote,local):
    out={**remote,**local,'records':dict(remote.get('records',{}))}
    for code,row in local.get('records',{}).items():
        if row.get('observed_at','')>=out['records'].get(code,{}).get('observed_at',''):out['records'][code]=row
    return out

def collect_results(codes,now,cache_path=None,limit=24):
    path=cache_path or CACHE;cache=json.loads(path.read_text()) if path.exists() else {'schema':1,'records':{},'failures':{}}
    wanted=[];errors={}
    for code in sorted(set(codes)):
        saved=cache.get('records',{}).get(code,{});at=timeparse(saved.get('observed_at'));failed=timeparse(cache.get('failures',{}).get(code))
        if at and dt.timedelta(0)<=now-at<dt.timedelta(minutes=30):continue
        if failed and dt.timedelta(0)<=now-failed<dt.timedelta(minutes=5):continue
        wanted.append(code)
    def job(code):
        url=f'https://www.boatrace.jp/owpc/pc/race/raceresult?hd={code[:8]}&jcd={code[8:10]}&rno={int(code[-2:])}'
        try:
            row=parse_result(get(url),code,dt.datetime.now(JST).isoformat(),url)
            return code,row,None if row else 'official_result_or_refund_not_confirmed'
        except Exception as exc:return code,None,str(exc)[:180]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for code,row,error in pool.map(job,wanted[:limit]):
            if row:cache.setdefault('records',{})[code]=row;cache.setdefault('failures',{}).pop(code,None)
            else:cache.setdefault('failures',{})[code]=now.isoformat();errors[code]=error
    cache['updated_at']=now.isoformat();atomic_write(path,cache)
    return cache.get('records',{}),errors

def attach_results(data,codes,now):
    rows,errors=collect_results(codes,now)
    for code in codes:
        row=rows.get(code)
        if not row:continue
        data.setdefault('results',{})[code]={**data.get('results',{}).get(code,{}),**row['result']}
        data.setdefault('payouts',{})[code]={**data.get('payouts',{}).get(code,{}),**row['payout']}
    return errors
