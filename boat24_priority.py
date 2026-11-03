"""Known field composition, event conditions, local support and opponent context."""
import re,unicodedata

def field_type(card,registry):
 records=registry.get('records',registry) if registry else {}
 sexes=[records.get(str(card.get(f'艇{i}_登録番号','')),{}).get('sex') for i in range(1,7)]
 women=sexes.count('female');men=sexes.count('male');unknown=6-women-men
 kind='mixed' if women and men else 'women_only' if women==6 else 'men_only' if men==6 else 'unknown'
 return {'type':kind,'women':women,'men':men,'unknown':unknown,'sexes':sexes}

def meeting_type(title):
 s=str(title.get('タイトル',''))
 if re.search('男女.?W|男女.?Ｗ|ダブル',s):return 'double_or_split'
 if re.search('オールレディース|ヴィーナスシリーズ|女子リーグ|レディースチャンピオン|レディースオールスター|クイーンズクライマックス',s):return 'women_restricted'
 return 'open_or_unconfirmed'

def add_priority_features(features,card,title,registry,stats,venue,day,cutoff):
 from boat24_context import number
 composition=field_type(card,registry);event=meeting_type(title)
 grades=[str(card.get(f'艇{i}_級別','')).strip() for i in range(1,7)]
 rates=[number(card.get(f'艇{i}_全国勝率')) for i in range(1,7)]
 grade=unicodedata.normalize('NFKC',str(title.get('グレード',''))).upper()
 grade={'GI':'G1','GII':'G2','GIII':'G3','PGI':'PG1'}.get(grade,grade)
 if grade not in ('SG','PG1','G1','G2','G3','IP'):grade='不明'
 stage=str(title.get('レース名',''));phase='優勝戦' if '優勝戦' in stage and '準優勝戦' not in stage else '準優勝戦' if '準優' in stage else '予選' if '予選' in stage else '一般・選抜等' if stage else '不明'
 conditions={'出走女子数':composition['women'],'出走男子数':composition['men'],'性別未確認数':composition['unknown'],'締切時刻時間':cutoff.hour+cutoff.minute/60}
 for label in ('women_only','men_only','mixed','unknown'):conditions['6艇構成_'+label]=int(composition['type']==label)
 for label in ('women_restricted','double_or_split','open_or_unconfirmed'):conditions['開催区分_'+label]=int(event==label)
 for label in ('SG','PG1','G1','G2','G3','IP','不明'):conditions['グレード_'+label]=int((grade or '不明')==label)
 for label in ('予選','準優勝戦','優勝戦','一般・選抜等','不明'):conditions['段階_'+label]=int(phase==label)
 day_text=unicodedata.normalize('NFKC',str(title.get('日次','')));match=re.search(r'\d+',day_text)
 if match:conditions['開催日次']=int(match[0])
 if title.get('ナイター') in ('Y','N'):conditions['ナイター']=int(title['ナイター']=='Y')
 metadata={'field_type':composition['type'],'female_count':composition['women'],'male_count':composition['men'],'unknown_sex_count':composition['unknown'],'meeting_type':event,'grade':grade or None,'stage':stage or None,'local_count_scope':'observed prior dates only; not official three-year starts'}
 for lane,f in enumerate(features,1):
  f['race_conditions']=dict(conditions);f['opposition']={};f['local_support']={}
  known=[v for j,v in enumerate(rates) if j!=lane-1 and v is not None]
  own=rates[lane-1]
  f['opposition']['相手勝率未確認人数']=5-len(known)
  f['opposition']['相手級別未確認人数']=sum(j!=lane-1 and v not in ('A1','A2','B1','B2') for j,v in enumerate(grades))
  if known:
   center=sum(known)/len(known);f['opposition']['相手平均全国勝率']=center;f['opposition']['相手最高全国勝率']=max(known);f['opposition']['相手最低全国勝率']=min(known)
   if own is not None:f['opposition']['相手平均との差']=own-center;f['opposition']['全国勝率順位']=1+sum(v>own for v in known)
  for g in ('A1','A2','B1','B2'):f['opposition']['相手'+g+'人数']=sum(j!=lane-1 and v==g for j,v in enumerate(grades))
  sex=composition['sexes'][lane-1]
  if sex:f['race_conditions']['本人女子']=int(sex=='female')
  rid=str(card.get(f'艇{lane}_登録番号',''));course=int(f.get('start',{}).get('展示進入',lane))
  for group,key,prefix in [('local',rid+'-'+str(venue),'当地'),('by_field',rid+'-'+composition['type'],'構成別'),('local_course',rid+'-'+str(venue)+'-'+str(course),'当地コース'),('course_field',rid+'-'+str(course)+'-'+composition['type'],'構成別コース')]:
   a=stats.state.get(group,{}).get(key,{}) if stats else {};n=a.get('n',0)
   f['local_support'][prefix+'確認走数']=n
   if n:
    f['local_support'][prefix+'1着率']=a['wins']/n;f['local_support'][prefix+'2連対率']=a['two']/n;f['local_support'][prefix+'3連対率']=a['three']/n;f['local_support'][prefix+'平均着順']=a['finish_sum']/n
  raw=[number(card.get(f'艇{lane}_当地{s}')) for s in ('勝率','2連対率','3連対率')]
  zero=all(v==0 for v in raw)
  f['local_support']['当地公式成績未確認']=int(zero or any(v is None for v in raw))
  if zero:
   for key in ('当地勝率','当地2連対率','当地3連対率'):f.get('ability',{}).pop(key,None)
 return metadata
