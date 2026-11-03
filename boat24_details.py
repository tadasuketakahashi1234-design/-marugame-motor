"""One feature builder for live forecasts and historical replay.

Unmeasured slow/dash, start distance, video footwork and flow stay missing.
"""
import datetime as dt
import math
import statistics
from boat24_integrity import timeparse

SCHEMA='integrated-detail-1'
DETAIL_GROUPS=('exhibition_detail','start_detail','entry_detail','machine_detail',
               'series_detail','comment_detail','market_detail','interactions','data_quality','tactical_detail')
LABELS={'exhibition_detail':'展示の実測値・順位・足別比較','start_detail':'展示ST・隣艇差・ばらつき',
        'entry_detail':'枠と展示進入・進入隊形','machine_detail':'ボート・機材・調整の詳細',
        'series_detail':'今節・前半レース・得点条件','comment_detail':'足別コメント・変化・調整根拠',
        'market_detail':'市場の集中・他券種との比較','interactions':'展示・コース・相手の組合せ',
        'data_quality':'取得鮮度・情報充足度','tactical_detail':'逃がし・差され・2着3着・ST分布'}

def attach(features,code,card,data,previews,cutoff,asof,official=None):
    from boat24_context import number,safe_row
    from boat24_comments import analyze
    ex,st,orig,weather=(previews.get(k,{}) for k in ('ex','st','original','weather'))
    def val(row,lane,key):return number(row.get(f'艇{lane}_{key}'))
    def put(f,g,k,v):
        if v is not None and isinstance(v,(int,float)) and math.isfinite(v):f[g][k]=v
    rawtimes=[val(ex,i,'展示タイム') for i in range(1,7)]
    rawst=[val(st,i,'スタート展示') for i in range(1,7)]
    courses=[val(st,i,'コース') for i in range(1,7)]
    valid_entry=all(c is not None and c.is_integer() and 1<=c<=6 for c in courses) and len(set(courses))==6
    order=sorted(range(6),key=lambda j:courses[j]) if valid_entry else []
    oddsrow=previews.get('odds',{});odds={k[4:]:number(v) for k,v in oddsrow.items() if k.startswith('3連単_')}
    positive={k:v for k,v in odds.items() if v and v>0}
    market={k:1/v for k,v in positive.items()};total=sum(market.values())
    market={k:v/total for k,v in market.items()} if total else {}
    other={k:safe_row(data.get(k,{}).get(code),cutoff,asof) for k in ('od1','od2','tokuten')}
    detail={'schema':SCHEMA,'entry_verified':valid_entry,'unmeasured':['スロー・ダッシュ','起こし位置','助走距離','実流速'],
            'boats':[],'sources':{k:row.get('取得日時') for k,row in {**previews,**other}.items() if row}}
    safe_official=official or {}
    for lane,f in enumerate(features,1):
        for g in DETAIL_GROUPS:f[g]={}
        ed=f['exhibition_detail'];sd=f['start_detail'];entry=f['entry_detail'];mach=f['machine_detail'];series=f['series_detail']
        t=rawtimes[lane-1];timing=rawst[lane-1];course=courses[lane-1] if valid_entry else None
        put(f,'exhibition_detail','展示タイム秒',t)
        if t is not None:
            known=[v for v in rawtimes if v is not None]
            ed.update({'展示順位':1+sum(v<t for v in known),'展示最速差秒':t-min(known),'展示計測艇数':len(known)})
        put(f,'exhibition_detail','体重kg',val(ex,lane,'体重(kg)'))
        put(f,'exhibition_detail','調整体重kg',val(ex,lane,'体重調整(kg)'))
        w,adj=val(ex,lane,'体重(kg)'),val(ex,lane,'体重調整(kg)')
        if w is not None and adj is not None:ed['体重調整体重合計kg']=w+adj
        for slot in range(1,4):
            name=str(orig.get(f'計測項目{slot}','')).strip();values=[val(orig,i,f'値{slot}') for i in range(1,7)]
            value=values[lane-1];known=[v for v in values if v is not None]
            if name and value is not None:
                ed[name+'秒']=value;ed[name+'順位']=1+sum(v<value for v in known);ed[name+'最速差秒']=value-min(known)
        if timing is not None:
            sd['展示ST秒']=timing;sd['展示F']=int(timing<0)
            normal=[v for v in rawst if v is not None and v>=0]
            # F never wins a fastest-normal-ST ranking.
            if timing>=0:sd['正常展示ST順位']=1+sum(v<timing for v in normal)
            if len(normal)>1:sd['正常展示STばらつき']=statistics.pstdev(normal)
        if valid_entry:
            entry.update({'展示コース':course,'枠からの移動':course-lane,'枠変更艇数':sum(c!=i for i,c in enumerate(courses,1))})
            pos=order.index(lane-1)
            for offset,label in [(-1,'内隣'),(1,'外隣')]:
                j=pos+offset
                if 0<=j<6:
                    otherlane=order[j]
                    if timing is not None and rawst[otherlane] is not None:sd[label+'展示ST差秒']=timing-rawst[otherlane]
                    if t is not None and rawtimes[otherlane] is not None:ed[label+'展示タイム差秒']=t-rawtimes[otherlane]
        for key in ('ボート2連対率','ボート3連対率','モーター2連対率','モーター3連対率'):
            put(f,'machine_detail',key,number(card.get(f'艇{lane}_{key}')))
        for key in ('年齢','期別'):
            put(f,'series_detail',key,number(card.get(f'艇{lane}_{key}')))
        put(f,'machine_detail','チルト度',val(ex,lane,'チルト'))
        zenken=safe_official.get('zenken',{}).get(str(lane),{})
        zt=timeparse(zenken.get('observed_at'))
        if zt and zt<=asof and zt<cutoff and str(zenken.get('racer'))==str(card.get(f'艇{lane}_登録番号')) and zenken.get('motor')==number(card.get(f'艇{lane}_モーター番号')) and zenken.get('boat')==number(card.get(f'艇{lane}_ボート番号')):
            mach['前検タイム秒']=zenken['time_seconds']
            if t is not None:mach['前検展示差秒']=t-zenken['time_seconds']
        before=safe_official.get('before',{}).get(str(lane))
        observed=timeparse(safe_official.get('before_observed_at',safe_official.get('observed_at')))
        if before is not None and observed and observed<=asof and observed<cutoff:
            parts=str(before.get('parts',''));mach['交換表示あり']=int(bool(parts));mach['プロペラ新']=int('新' in before.get('propeller',''))
            for label,pat in {'電気':'電気','キャブ':'キャブ','ピストン':'ピストン','リング':'リング','シリンダ':'シリンダ','シャフト':'シャフト','ギヤ':'ギヤ','キャリア':'キャリア|キャリボ'}.items():mach['交換_'+label]=int(bool(__import__('re').search(pat,parts)))
        comment=safe_official.get('comments',{}).get(str(lane),{})
        ct=timeparse(comment.get('observed_at') or safe_official.get('comments_observed_at',safe_official.get('observed_at')))
        analysis=analyze(comment.get('comment','')) if ct and ct<=asof and ct<cutoff and str(comment.get('racer'))==str(card.get(f'艇{lane}_登録番号')) else None
        if analysis:
            prefix='前日_' if comment.get('comment_scope')=='previous_day' else '時点未公表_'
            f['comment_detail']={prefix+k:v for k,v in analysis['features'].items()}
            analysis.update({'publication_scope':comment.get('comment_scope','publication_time_unknown'),'comment_date':comment.get('comment_date')})
        # Previously completed same-day races only, joined by registration number.
        prior=[]
        for oldcode,row in data.get('cards',{}).items():
            if oldcode==code or oldcode[:8]!=code[:8]:continue
            res=data.get('results',{}).get(oldcode,{})
            rt=timeparse(res.get('取得日時'))
            if not rt or not rt<=asof or not rt<cutoff:continue
            for ol in range(1,7):
                if str(row.get(f'艇{ol}_登録番号'))!=str(card.get(f'艇{lane}_登録番号')):continue
                finish=next((p for p in range(1,7) if str(res.get(f'{p}着_艇番'))==str(ol)),None)
                if finish is not None:prior.append((rt,oldcode,ol,finish))
        if prior:
            rt,oldcode,ol,finish=max(prior);series['当日既走数']=len(prior);series['前走着順']=finish;series['前走結果取得から分']=(asof-rt).total_seconds()/60
            oldex=safe_row(data.get('ex',{}).get(oldcode),rt,asof)
            oldtime=val(oldex,ol,'展示タイム');oldtilt=val(oldex,ol,'チルト')
            if oldtime is not None and t is not None:series['前走展示タイム変化秒']=t-oldtime
            tilt=val(ex,lane,'チルト')
            if tilt is not None and oldtilt is not None:series['前走チルト変化度']=tilt-oldtilt
        tok=other['tokuten']
        if str(tok.get(f'艇{lane}_登録番号',''))==str(card.get(f'艇{lane}_登録番号')):
            for key in ('得点率','順位','1着時得点率','2着時得点率','3着時得点率','4着時得点率','5着時得点率','6着時得点率'):
                put(f,'series_detail',key,number(tok.get(f'艇{lane}_{key}')))
            put(f,'series_detail','ボーダー順位',number(tok.get('ボーダー順位')))
        if len(market)==120:
            md=f['market_detail'];md['市場1着周辺確率']=sum(p for k,p in market.items() if k.split('-')[0]==str(lane));md['市場3着内周辺確率']=sum(p for k,p in market.items() if str(lane) in k.split('-'));md['市場エントロピー']=-sum(p*math.log(p) for p in market.values());md['人気上位12集中度']=sum(sorted(market.values(),reverse=True)[:12])
        for key,caption in [('od1','単勝'),('od2','2連単')]:
            row=other[key]
            if key=='od1':put(f,'market_detail','単勝オッズ',number(row.get(f'単勝_{lane}')))
            else:
                vals=[number(row.get(f'2連単_{lane}-{i}')) for i in range(1,7) if i!=lane];known=[v for v in vals if v and v>0]
                if len(known)==5:f['market_detail']['2連単頭逆オッズ和']=sum(1/v for v in known)
        # Explicit interactions; no claim of causality or value until shadow tests.
        if course is not None and t is not None:put(f,'interactions','コース展示相対',course*f.get('exhibition',{}).get('展示タイム相対',0))
        if timing is not None and timing>=0:
            put(f,'interactions','ST伸び相対',timing*f.get('exhibition',{}).get('展示タイム相対',0))
        flags=safe_official.get('race_flags',{})
        ft=timeparse(safe_official.get('race_flags_observed_at',safe_official.get('observed_at')))
        if flags and ft and ft<=asof and ft<cutoff:
            for key,v in flags.items():put(f,'entry_detail',key,v)
        for kind,row in {**previews,**other}.items():
            at=timeparse(row.get('取得日時'))
            if at and at<=asof:f['data_quality'][kind+'取得経過分']=(asof-at).total_seconds()/60
        f['data_quality']['展示取得艇数']=sum(v is not None for v in rawtimes)
        detail['boats'].append({'lane':lane,'racer':str(card.get(f'艇{lane}_登録番号','')),'exhibition':ed,'start':sd,'entry':entry,'machine':mach,'series':series,'comment':analysis,'comment_source':comment.get('source'),'comment_observed_at':ct.isoformat() if ct else None})
    return detail
