"""Versioned, evidence-preserving comment extraction. No invented sentiment.

Only the observed text is interpreted. Plans and uncertain/previous-state clauses
remain evidence but are not positive/negative measurements of the current boat.
"""
import datetime as dt
import hashlib
import re
from html import unescape

VERSION = 'comment-clauses-1'
ASPECTS = {
    '出足': r'出足|出脚', '行き足': r'行き足|行き脚|起こし',
    '伸び': r'伸び|直線', '回り足': r'回り足|回り脚|ターン足',
    '掛かり': r'掛かり|かかり', '押し': r'押し|押す|押して',
    '舟の向き': r'舟の向き|艇の向き|向き',
    '乗り心地': r'乗り心地|乗りやす|乗りづら|乗りずら',
    'スタート': r'スタート|Ｓ|ST|スリット',
}
NEG = r'良くな[いかっ]|よくな[いかっ]|弱|悪|足りな|鈍|重[いかっ]|下が|劣勢|滑|乗り[づず]ら|ない|なく'
POS = r'良[いかっ]|いい|上位|抜群|力強|伸びる|乗りやす|問題な[いく]|悪くな[いく]|悪くはな[いく]'
PLAN = r'したい|していきたい|求めたい|欲しい|ほしい|してみる|していく|する予定|するつもり|調整する|調整していく'
UNKNOWN = r'分から|わから|未確認|まだ乗|乗ってな|試してな|どうか|不明'
PAST = r'前日|昨日|前半|前走|以前|前回'

def clean(value):
    return re.sub(r'\s+', ' ', unescape(re.sub(r'<[^>]*>', ' ', str(value or '')))).strip()

def analyze(value):
    raw=clean(value);evidence=[];values={};conflicts=set()
    # Split adversative clauses, preserving the exact supporting phrase.
    clauses=re.split(r'[。！？、；;]|けれど|けど|ですが|だが|(?<=[いだ])が',raw)
    for clause in clauses:
        clause=clause.strip()
        if not clause:continue
        status='uncertain' if re.search(UNKNOWN,clause) else 'plan' if re.search(PLAN,clause) else 'previous_state' if re.search(PAST,clause) else 'current_report'
        if re.search(r'良くなった|よくなった|上向|改善',clause):change=1
        elif re.search(r'悪くなった|悪化|落ちた',clause):change=-1
        else:change=None
        matches=sorted((m.start(),m.end(),aspect) for aspect,pattern in ASPECTS.items() for m in [re.search(pattern,clause,re.I)] if m)
        for idx,(start,end,aspect) in enumerate(matches):
            tail=clause[start:matches[idx+1][0]] if idx+1<len(matches) else clause[start:]
            if not re.search(NEG+'|'+POS+'|普通|中堅|平凡',tail):tail=clause[start:]
            normalized=re.sub(r'悪く(?:は)?な[いく]|問題な[いく]|下がらない|乗り[づず]らくない','良い',tail)
            signal=-1 if re.search(NEG,normalized) else 1 if re.search(POS,normalized) else 0 if re.search(r'普通|中堅|平凡',normalized) else None
            evidence.append({'aspect':aspect,'phrase':clause,'status':status,'value':signal,'change':change})
            if status=='current_report' and signal is not None:
                if aspect in values and values[aspect]!=signal:conflicts.add(aspect)
                values[aspect]=signal
            if status=='current_report' and change is not None:values[aspect+'変化']=change
    for aspect in conflicts:values.pop(aspect,None)
    return {'version':VERSION,'raw':raw,'sha256':hashlib.sha256(raw.encode()).hexdigest(),
            'features':values,'evidence':evidence,'conflicting_aspects':sorted(conflicts),
            'method':'explicit_clauses_not_validated_boat_ability','unknown_is_not_neutral':True}

def parse_pitreport(doc,code,card):
    """National official report, only when date, selected R and racer IDs match."""
    from boat24_official import text,cells
    active=re.search(r'<li class="is-active2">(.*?)</li>',doc,re.S)
    day=f'{int(code[4:6])}月{int(code[6:8])}日'
    if not active or day not in text(active[1]):return {}
    if not re.search(r'(?:hd=|name="hd" value=")'+code[:8],doc):return {}
    selected=False
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',doc,re.S|re.I):
        td=re.findall(r'<td\b([^>]*)>(.*?)</td>',row,re.S|re.I)
        if len(td)==13 and '締切予定時刻' in text(td[0][1]):selected='is-activeColor1' in td[int(code[-2:])][0]
    if not selected:
        for row in re.findall(r'<thead\b[^>]*>(.*?)</thead>',doc,re.S|re.I):
            th=re.findall(r'<th\b([^>]*)>(.*?)</th>',row,re.S|re.I)
            if len(th)==13:
                attrs,body=th[int(code[-2:])]
                selected=not attrs.strip() and bool(re.search(r'rno='+str(int(code[-2:]))+r'&(?:amp;)?jcd='+code[8:10]+r'&(?:amp;)?hd='+code[:8],body))
    if not selected or '表示対象レースではありません' in text(doc):return {}
    out={}
    for body in re.findall(r'<tbody\b[^>]*>(.*?)</tbody>',doc,re.S|re.I):
        ids=re.findall(r'toban=(\d{4})',body);c=cells(body)
        for lane in range(1,7):
            rid=str(card.get(f'艇{lane}_登録番号',''))
            if rid not in ids:continue
            # The comment is the longest table cell; do not use the racer name.
            prose=[x for x in c if len(x)>=12 and re.search(r'[。]|です|ます|出足|伸び|乗り心地',x)]
            if prose:out[str(lane)]={'racer':rid,'comment':max(prose,key=len),'publication_time_known':False}
    return out

VENUE_SOURCES={
    21:'https://www.boatrace-ashiya.com/modules/raceinfo/?page=index_racers_comment',
    23:'https://www.boatrace-karatsu.jp/modules/raceinfo/?page=index_racers_comment',
    24:'https://omurakyotei.jp/yosou/comment.php?day={day}',
}

def parse_venue_comments(doc,venue,day):
    """Dated official list; returned by racer ID, then joined to today's card."""
    from boat24_official import text,cells
    out={};plain=text(doc);date=dt.datetime.strptime(day,'%Y%m%d').date()
    if venue==24:
        if not re.search(r'<option[^>]*day='+day+r'[^>]*\bselected',doc,re.S):return {}
    else:
        # A rolling page has no archive date. Accept only a same-day capture,
        # matching visible date and an explicitly open meeting.
        from boat24_integrity import JST
        if date!=dt.datetime.now(JST).date():return {}
        if not re.search(rf'{date.month:02d}/{date.day:02d}|{date.month}/{date.day}',plain):return {}
        if '次節開催まで' in plain or '非開催' in plain and '本日開催中' not in doc:return {}
    for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',doc,re.S|re.I):
        c=cells(row)
        if venue==24:
            match=re.search(r'toban=(\d{4})',row)
            if match and len(c)>=2 and c[1]:out[match[1]]={'racer':match[1],'comment':c[1],'publication_time_known':False}
        elif len(c)>=4 and re.fullmatch(r'\d{4}',c[0]) and c[3]:
            out[c[0]]={'racer':c[0],'comment':c[3],'publication_time_known':False,
                       'comment_scope':'previous_day' if 'コメントは前日' in plain else 'publication_time_unknown'}
    return out

def race_flags(doc,code,card):
    from boat24_official import parse_before,text
    if not parse_before(doc,code,card):return {}
    # Search only the selected race heading, not navigation menus or other Rs.
    m=re.search(r'<div class="title16__add2020">.*?(?=<div class="tab)',doc,re.S)
    if not m:m=re.search(r'<h2[^>]*class="raceHeading.*?(?=<div class="tab|<ul class="tab)',doc,re.S)
    if not m:
        m=re.search(r'(<div class="race1.*?)(?=<div class="tab|<ul class="tab)',doc,re.S)
    if not m:return {}
    s=text(m[0]);length=re.search(r'(\d{3,4})m',s)
    flags={'進入固定':int('進入固定' in s),'安定板':int('安定板' in s)}
    if length:flags.update({'距離m':int(length[1]),'周回短縮':int(int(length[1])<1800)})
    return flags

def parse_zenken(doc,venue,day,meeting_title):
    from boat24_official import text,cells
    from boat24_context import number,normalized_name
    if not meeting_title or normalized_name(meeting_title) not in normalized_name(text(doc)):return {}
    if not re.search(r'jcd='+f'{venue:02d}'+r'&(?:amp;)?sort=.*?hd='+day,doc):return {}
    out={}
    for body in re.findall(r'<tbody\b[^>]*>(.*?)</tbody>',doc,re.S|re.I):
        ids=re.findall(r'toban=(\d{4})',body);c=cells(body)
        if not ids or len(c)!=9:continue
        seconds=number(c[8]);motor=number(c[4]);boat=number(c[6])
        if seconds is not None and 5<=seconds<=9 and motor is not None and boat is not None:
            out[ids[0]]={'racer':ids[0],'motor':int(motor),'boat':int(boat),'time_seconds':seconds,'meeting_title':meeting_title}
    return out

def decorate(comments,source,observed,source_day=None):
    return {lane:{**row,'source':source,'observed_at':observed,'source_day':source_day,
                  'comment_date':(dt.datetime.strptime(source_day,'%Y%m%d').date()-dt.timedelta(days=1)).isoformat() if row.get('comment_scope')=='previous_day' and source_day else None,
                  'speaker':'racer_report','analysis':analyze(row['comment'])}
            for lane,row in comments.items() if clean(row.get('comment'))}
