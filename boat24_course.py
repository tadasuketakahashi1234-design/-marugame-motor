"""Prior-date racer/actual-course and winner-style statistics, with shrinkage."""
import math
from collections import defaultdict
from boat24_integrity import timeparse
POINTS={1:10,2:8,3:6,4:4,5:2,6:1}
METHODS=('逃げ','差し','まくり','まくり差し')

def empty():return {'n':0,'wins':0,'two':0,'three':0,'points':0,'finish_sum':0,'st':0.,'st_n':0,'rank':0.,'rank_n':0,'methods':{m:0 for m in METHODS},'allowed':{m:0 for m in METHODS}}

class CourseStats:
 def __init__(self,state=None):
  self.state=state if state is not None else {}
  for key in ('racer','venue','overall','local','by_field','local_course','course_field'):self.state.setdefault(key,{})
 def add(self,data):
  from boat24_context import number
  for code,res in data.get('results',{}).items():
   card=data.get('cards',{}).get(code)
   if not card:continue
   observed=timeparse(res.get('取得日時'))
   if not observed or observed.strftime('%Y%m%d')!=code[:8]:continue
   finishes={str(res.get(f'{p}着_艇番')):p for p in range(1,7)}
   courses={str(res.get(f'{c}コース_艇番')):c for c in range(1,7)}
   if set(finishes)!=set('123456') or set(courses)!=set('123456'):continue
   sts={c:number(res.get(f'{c}コース_スタートタイミング')) for c in range(1,7)}
   method=res.get('決まり手');venue=int(code[8:10])
   from boat24_priority import field_type
   composition=field_type(card,data.get('registry',{}))['type']
   for lane in range(1,7):
    racer=str(card.get(f'艇{lane}_登録番号',''));course=courses[str(lane)];finish=finishes[str(lane)]
    if not racer.isdigit():continue
    groups=[('racer',racer+'-'+str(course)),('venue',str(venue)+'-'+str(course)),('overall',racer),('local',racer+'-'+str(venue)),('local_course',racer+'-'+str(venue)+'-'+str(course))]
    if composition!='unknown':groups += [('by_field',racer+'-'+composition),('course_field',racer+'-'+str(course)+'-'+composition)]
    for group,key in groups:
     a=self.state[group].setdefault(key,empty());a['n']+=1;a['wins']+=finish==1;a['two']+=finish<=2;a['three']+=finish<=3;a['points']+=POINTS[finish];a['finish_sum']+=finish
     st=sts[course]
     if st is not None and st>=0 and not res.get(f'{course}コース_F'):
      a['st']+=st;a['st_n']+=1;a['rank']+=1+sum(v<st for v in sts.values() if v is not None and v>=0);a['rank_n']+=1
     if method in METHODS:
      if finish==1:a['methods'][method]+=1
      else:a['allowed'][method]+=1
 def features(self,racer,venue,course):
  a=self.state['racer'].get(str(racer)+'-'+str(course));b=self.state['venue'].get(str(venue)+'-'+str(course));o=self.state['overall'].get(str(racer))
  if not a or not b or not a['n'] or not b['n']:return {},{}
  n=a['n'];k=10.;base=b['n'];f={'標本数':n}
  for key,label in [('wins','1着率'),('two','2連対率'),('three','3連対率'),('points','勝率得点')]:
   v=(a[key]+k*b[key]/base)/(n+k);f[label]=v
   if o and o['n']:f[label+'全コース差']=v-o[key]/o['n']
  if a['st_n']:f['平均ST']=a['st']/a['st_n']
  if a['rank_n']:f['平均スタート順']=a['rank']/a['rank_n']
  style={}
  for key,label in [('methods','勝ち'),('allowed','敗れ')]:
   for m in METHODS:style[m+label+'率']=(a[key][m]+k*b[key][m]/base)/(n+k)
  return f,style

def add_course_features(features,card,venue,stats):
 for lane,f in enumerate(features,1):
  course=int(f.get('start',{}).get('展示進入',lane));course=course if 1<=course<=6 else lane
  f['course'],f['style']=stats.features(card.get(f'艇{lane}_登録番号'),venue,course)
 # Adjacent opponents are ordered by exhibition course, not boat number.
 ordered=sorted(enumerate(features,1),key=lambda x:x[1].get('start',{}).get('展示進入',x[0]))
 for i,(_,f) in enumerate(ordered):
  for offset,label in [(-1,'内隣'),(1,'外隣')]:
   j=i+offset
   if 0<=j<len(ordered):
    other=ordered[j][1]
    for key in ('平均ST','1着率'):
     if key in other['course']:f['style'][label+key]=other['course'][key]
