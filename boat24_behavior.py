"""Prior-date exhibition/actual ST residuals and joint legal entry scenarios."""
import datetime as dt
import itertools
import math
from boat24_context import number, safe_row, deadline
from boat24_integrity import timeparse

class BehaviorStats:
 def __init__(self,state=None):self.state=state if state is not None else {'transition':{},'st':{},'through':None}
 def add(self,data):
  for code,res in data.get('results',{}).items():
   card=data.get('cards',{}).get(code);observed=timeparse(res.get('取得日時'));day=f'{code[:4]}-{code[4:6]}-{code[6:8]}'
   if not card or not observed or observed.date().isoformat()!=day:continue
   actual={str(res.get(f'{c}コース_艇番')):c for c in range(1,7)}
   if set(actual)!=set('123456'):continue
   limit=deadline(data.get('st',{}).get(code),day)
   ex=safe_row(data.get('st',{}).get(code),limit,limit-dt.timedelta(minutes=2,microseconds=1)) if limit else {}
   for lane in range(1,7):
    rid=str(card.get(f'艇{lane}_登録番号',''));course=actual[str(lane)];ec=number(ex.get(f'艇{lane}_コース'));est=number(ex.get(f'艇{lane}_スタート展示'));ast=number(res.get(f'{course}コース_スタートタイミング'))
    for phase,origin in [('initial',lane),('preview',int(ec) if ec and 1<=ec<=6 else None)]:
     if origin is None:continue
     for key in (f'{phase}|pool|{origin}',f'{phase}|{rid}|{origin}'):
      counts=self.state['transition'].setdefault(key,[0]*6);counts[course-1]+=1
    if est is not None and ast is not None and 0<=ast<=1 and not res.get(f'{course}コース_F'):
     # Negative exhibition ST is a distinct F category, never absolute-valued into a fast start.
     flag=int(est<0)
     for key in (f'pool|{course}|{flag}',f'{rid}|{course}|{flag}'):
      a=self.state['st'].setdefault(key,{'n':0,'sum':0.,'sq':0.});delta=ast-est;a['n']+=1;a['sum']+=delta;a['sq']+=delta*delta
   self.state['through']=max(self.state.get('through') or '',day)
 def attach(self,features,card):
  phase='preview' if all('展示進入' in f.get('start',{}) for f in features) else 'initial';rows=[];counts=[]
  for lane,f in enumerate(features,1):
   origin=int(f.get('start',{}).get('展示進入',lane));rid=str(card.get(f'艇{lane}_登録番号',''));pool=self.state['transition'].get(f'{phase}|pool|{origin}',[0]*6);own=self.state['transition'].get(f'{phase}|{rid}|{origin}',[0]*6)
   # Empirical pooled prior; uniform only when no transitions have been observed.
   base=[(x+1)/(sum(pool)+6) for x in pool];rows.append([(own[j]+10*base[j])/(sum(own)+10) for j in range(6)]);counts.append(sum(own))
  scenarios=[]
  for perm in itertools.permutations(range(1,7)):
   w=math.prod(rows[i][c-1] for i,c in enumerate(perm));scenarios.append((perm,w))
  total=sum(w for _,w in scenarios);marginals=[[sum(w for p,w in scenarios if p[i]==c)/total for c in range(1,7)] for i in range(6)]
  estimates=[]
  for i,f in enumerate(features):
   lane=i+1;rid=str(card.get(f'艇{lane}_登録番号',''));course=int(f.get('start',{}).get('展示進入',lane));flag=int(f.get('start',{}).get('展示F',0));pool=self.state['st'].get(f'pool|{course}|{flag}',{});own=self.state['st'].get(f'{rid}|{course}|{flag}',{});g={}
   if sum(self.state['transition'].get(f'{phase}|pool|{course}',[])):
    g.update({'予測進入コース':sum((j+1)*p for j,p in enumerate(marginals[i])),'進入変化確率':1-marginals[i][course-1],'選手進入標本数':counts[i]})
   estimate=None
   # Recover signed exhibition ST from centered absolute ST plus an externally set raw field.
   est=f.get('start',{}).get('展示ST符号付')
   if phase=='preview' and est is not None and pool.get('n'):
    n=own.get('n',0);pn=pool['n'];delta=(own.get('sum',0)+10*pool['sum']/pn)/(n+10);second=(own.get('sq',0)+10*pool['sq']/pn)/(n+10)
    estimate=est+delta;g.update({'予測本番ST':estimate,'展示本番ST差':delta,'ST差標準偏差':math.sqrt(max(0,second-delta*delta)),'選手ST標本数':n})
   f['behavior']=g;estimates.append(estimate)
  known=[v for v in estimates if v is not None]
  if known:
   center=sum(known)/len(known)
   for f,e in zip(features,estimates):
    if e is not None:f['behavior']['予測ST相対']=e-center
  return {'phase':phase,'trained_through':self.state.get('through'),'marginals':marginals,'racer_samples':counts,'scenarios':[{'courses_by_boat':list(p),'probability':w/total} for p,w in sorted(scenarios,key=lambda x:-x[1])[:5]],'st_estimates':estimates}
