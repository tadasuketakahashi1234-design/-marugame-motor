"""Predeclared public-frozen residual study. Paper portfolios; no live switching."""
import copy,datetime as dt,math,json,random,re
from collections import Counter,defaultdict
from pathlib import Path
from boat24_integrity import JST,timeparse
from boat24_learning import digest,frozen_cases
from boat24_decisions import outcome
POLICY='prospective-residual-1';START_DAY='2026-11-06'
FOOT=('ability','course','motor_history','exhibition','original','exhibition_detail','machine_detail')
DUEL=FOOT+('start','start_detail','entry_detail','behavior','style','tactical_detail','interactions','opposition')
RULES={'policy':POLICY,'start_day':START_DAY,'primary':'duel_residual','secondary_ablation':'foot_residual','foot_groups':list(FOOT),'duel_groups':list(DUEL),'context_version':__import__('boat24_context').VERSION,'mixture':'normalized_geometric_market_residual','beta_grid':[0,.125,.25,.375,.5],'penalty':.02,'minimum_training_races':30,'minimum_training_days':3,'training_window_days':28,'maximum_training_races':200,'training_price_policy':'fresh_common_four_arm_quote_at_freeze','freeze_seconds':120,'quote_max_seconds':300,'probability_haircut':.20,'price_haircut':.10,'maximum_ticket_share':.25,'promotion_races':400,'promotion_days':14,'promotion_purchases':100,'venue_races':60,'venue_days':5,'comparison':'paired_public_frozen_walk_forward','confidence':'97.5_percent_day_cluster_each_of_two_baselines','automatic_live_switch':False}
CONFIG=digest(RULES);ARMS=('current','market','foot_residual','duel_residual')
def distribution(p):
 from boat24_context import COMBOS
 return isinstance(p,dict) and set(p)==set(COMBOS) and all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in p.values()) and abs(sum(p.values())-1)<1e-6

def mixture(market,basis,beta):
 if beta==0:return dict(market)
 values={c:math.exp((1-beta)*math.log(max(p,1e-12))+beta*math.log(max(basis[c],1e-12))) for c,p in market.items()};z=sum(values.values());return {c:p/z for c,p in values.items()}

def market_for(odds):
 from boat24_context import COMBOS
 if set(odds)!=set(COMBOS) or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<=0 for v in odds.values()):return None
 z=sum(1/v for v in odds.values());return {c:1/v/z for c,v in odds.items()}

def bases(features,venue,day,model):
 from boat24_context import predict
 return {name:predict(features,venue,day,{**model,'market_alpha':0,'phase_calibration':{},'enabled_groups':list(groups)},None)['probabilities'] for name,groups in (('foot_residual',FOOT),('duel_residual',DUEL))}

def attach(snapshot,model,now):
 saved=snapshot.get('input_snapshot',{});features=saved.get('features',[])
 x={'policy':POLICY,'config_id':CONFIG,'status':'scheduled','starts_on':START_DAY,'model_id':snapshot.get('model_id'),'trained_through':model.get('trained_through'),'computed_at':now.isoformat()};snapshot['prospective_study']=x
 if now.date().isoformat()<START_DAY:return
 cut=timeparse(snapshot.get('cutoff'));quote=timeparse(snapshot.get('purchase_plan',{}).get('odds_observed_at'))
 if not cut or not now<cut-dt.timedelta(seconds=120):x['status']='after_freeze';return
 if cut-now>dt.timedelta(minutes=25):x['status']='waiting_window';return
 if model.get('trained_through','9999')>=now.date().isoformat():x['status']='model_date_invalid';return
 if not snapshot.get('input_quality',{}).get('purchase_inputs_ready') or len(features)!=6:x['status']='inputs_missing';return
 if not quote or not dt.timedelta(0)<=now-quote<=dt.timedelta(seconds=300):x['status']='quote_stale';return
 from boat24_context import number
 odds={c[4:]:number(v) for c,v in saved.get('previews',{}).get('odds',{}).items() if c.startswith('3連単_')};market=market_for(odds)
 if not market or not distribution(snapshot.get('probabilities')):x['status']='probabilities_or_quotes_incomplete';return
 raw=bases(features,int(snapshot['race_code'][8:10]),now.date().isoformat(),model)
 if not all(distribution(p) for p in raw.values()):x['status']='basis_invalid';return
 learned=model.get('prospective_study_training',{});learned=learned if learned.get('config_id')==CONFIG and learned.get('trained_through','9999')<now.date().isoformat() else {}
 x.update(status='recorded',quote_at=quote.isoformat(),quote_digest=digest(odds),input_digest=digest(features),basis=raw,fit={'status':learned.get('status','training_wait'),'training_races':learned.get('training_races',0),'training_days':learned.get('training_days',0),'case_digest':learned.get('case_digest')},arms={})
 from boat24_risk import robust_plan
 from boat24_decisions import compact_plan
 pp={'current':snapshot['probabilities'],'market':market,**{name:mixture(market,p,learned.get('betas',{}).get(name,0.)) for name,p in raw.items()}}
 for name,p in pp.items():
  plan=robust_plan(p,odds,verified=False,inputs_ready=True);plan.update(odds_observed_at=quote.isoformat(),odds_source=snapshot.get('purchase_plan',{}).get('odds_source'))
  x['arms'][name]={'probabilities':copy.deepcopy(p),'plan':compact_plan(plan),'beta':learned.get('betas',{}).get(name,0.) if name in raw else None}
 x['study_id']=digest(x)

def evidence(snapshot):
 x=snapshot.get('prospective_study')
 return {'policy':POLICY,'config_id':CONFIG,'digest':digest(x),'status':x.get('status'),'study_id':x.get('study_id')} if x and x.get('policy')==POLICY else None

def matched_study(case):
 s=case['snapshot'];x=s.get('prospective_study') or {};d=case['decision'];receipt=d.get('receipt') or {}
 if case['date']<START_DAY:return None,'before_registration'
 if x.get('policy')!=POLICY or x.get('config_id')!=CONFIG or x.get('status')!='recorded':return None,'study_not_recorded'
 if receipt.get('study_digest')!=digest(x) or d.get('study')!=x:return None,'study_not_publicly_frozen'
 if set(x.get('arms',{}))!=set(ARMS) or not all(distribution(a.get('probabilities')) for a in x['arms'].values()):return None,'study_distribution_invalid'
 a=timeparse(x.get('computed_at'));b=timeparse(s.get('computed_at') or s.get('created_at'))
 if x.get('trained_through','9999')>=case['date'] or not a or not b or a>b:return None,'study_model_or_compute_date_invalid'
 if x.get('input_digest')!=digest(s.get('input_snapshot',{}).get('features',[])):return None,'study_inputs_changed'
 f=x.get('fit',{})
 if f.get('status')=='fitted' and (f.get('training_races',0)<30 or f.get('training_days',0)<3):return None,'study_fit_support_invalid'
 return x,None

def fit(today,model,directory=Path('omura/docs/full_history')):
 from boat24_history_io import day_paths,day_key,read_history
 path=directory.parent/'boat24_decisions.json';decisions=json.loads(path.read_text()) if path.exists() else {};records=[]
 for p in day_paths(directory):
  if (today-dt.timedelta(days=28)).isoformat()<=day_key(p)<today.isoformat():records.extend(read_history(p).get('records',{}).values())
 cases,audit=frozen_cases(records,decisions,before=today,allow_prediction_only=True);rows=[];excluded=Counter()
 for c in sorted(cases,key=lambda z:(z['date'],z['race_code']))[-200:]:
  x,error=matched_study(c)
  if not x:excluded[error]+=1;continue
  freeze=timeparse(c['provenance']['freeze_at'])
  if any(outcome({**c['snapshot'],'purchase_plan':a['plan']},freeze)[0] not in ('buy','skip') for a in x['arms'].values()):excluded['training_quote_or_plan_not_comparable']+=1;continue
  raw=x.get('basis',{})
  if set(raw)!=set(('foot_residual','duel_residual')) or not all(distribution(p) for p in raw.values()):excluded['training_basis_missing']+=1;continue
  rows.append({'date':c['date'],'code':c['race_code'],'case_id':c['provenance']['case_id'],'market':x['arms']['market']['probabilities'],'basis':raw,'actual':c['result']['combo']})
 days=len({r['date'] for r in rows});ready=len(rows)>=30 and days>=3;losses={};betas={}
 for name in ('foot_residual','duel_residual'):
  losses[name]={str(b):sum(-math.log(max(mixture(r['market'],r['basis'][name],b)[r['actual']],1e-12)) for r in rows)/len(rows)+RULES['penalty']*b*b for b in RULES['beta_grid']} if rows else {}
  betas[name]=min(RULES['beta_grid'],key=lambda b:(losses[name][str(b)],b)) if ready else 0.
 return {'policy':POLICY,'config_id':CONFIG,'status':'fitted' if ready else 'training_wait','trained_through':(today-dt.timedelta(days=1)).isoformat(),'training_races':len(rows),'training_days':days,'minimum_training_races':30,'minimum_training_days':3,'case_digest':digest([r['case_id'] for r in rows]),'training_codes':[r['code'] for r in rows],'betas':betas,'training_objective':losses,'exclusions':dict(excluded),'frozen_audit':audit,'note':'Prior-date published bases only. Training loss is not forward evidence; zero weight until minimum support.'}

def score(p,actual):
 first,second,_=actual.split('-');m1=sum(v for c,v in p.items() if c.startswith(first+'-'));m2=sum(v for c,v in p.items() if c.startswith(first+'-'+second+'-'));l1=math.log(max(m1,1e-12));l2=math.log(max(m2,1e-12));l3=math.log(max(p.get(actual,0),1e-12))
 return {'logloss':-l3,'brier':sum(v*v for v in p.values())-2*p.get(actual,0)+1,'winner_logloss':-l1,'second_logloss':l1-l2,'third_logloss':l2-l3}

def element_scores(s,result):
 from boat24_context import number
 source=result.get('result_source') or {};forecast=s.get('behavior_forecast') or {};est=forecast.get('st_estimates') or [];guesses=(forecast.get('scenarios') or [{}])[0].get('courses_by_boat') or [];errors=[];hits=n=0
 for course in range(1,7):
  boat=number(source.get(f'{course}コース_艇番'))
  if boat is None or int(boat)!=boat or not 1<=boat<=6:continue
  lane=int(boat);actual=number(source.get(f'{course}コース_スタートタイミング'));pred=number(est[lane-1]) if len(est)==6 else None
  if pred is not None and actual is not None and 0<=actual<=1 and not source.get(f'{course}コース_F'):errors.append(abs(pred-actual))
  if len(guesses)==6 and sorted(guesses)==list(range(1,7)):n+=1;hits+=guesses[lane-1]==course
 return {'st_absolute_error_sum':sum(errors),'st_boats':len(errors),'entry_boats':n,'entry_hits':hits}

def interval(rows):
 grouped=defaultdict(list)
 for day,value in rows:grouped[day].append(value)
 days=sorted(grouped)
 if len(days)<3:return None
 rng=random.Random(20261106);values=[]
 for _ in range(500):
  sample=[x for _ in days for x in grouped[rng.choice(days)]];values.append(sum(sample)/len(sample))
 values.sort();return [values[int(.0125*len(values))],values[min(len(values)-1,int(.9875*len(values)))]]

def audit_row(code,item,rec,fixed,now):
 from boat24_decisions import displayed
 d=fixed.get('decision') or {};s=(rec.get('revisions',{}).get(d.get('snapshot_id')) if d else displayed(rec)) or {};result=rec.get('result') or {};features=s.get('input_snapshot',{}).get('features',[]);missing=[]
 for lane in range(1,7):
  f=features[lane-1] if lane<=len(features) else {}
  for group,key,label in (('exhibition','展示タイム相対','展示タイム'),('start','展示進入','進入'),('start','展示ST符号付','符号付きST')):
   if f.get(group,{}).get(key) is None:missing.append(str(lane)+'艇:'+label)
 entry=[f.get('start',{}).get('展示進入') for f in features]
 if len(entry)==6 and all(v is not None for v in entry) and sorted(entry)!=list(range(1,7)):missing.append('進入コースの重複・範囲異常')
 freeze=timeparse(fixed.get('freeze_at'));cut=timeparse(item.get('cutoff') or s.get('cutoff'));freeze=freeze or (cut-dt.timedelta(seconds=120) if cut else None);quote=timeparse(s.get('purchase_plan',{}).get('odds_observed_at'));observed=timeparse(d.get('receipt',{}).get('observed_at'));computed=timeparse(s.get('computed_at') or s.get('created_at'));x=s.get('prospective_study') or {};source=result.get('result_source') or {}
 full=sorted(str(source.get(f'{i}着_艇番','')) for i in range(1,7))==list('123456') and not source.get('official_finish_status');entries=[source.get(f'{i}コース_艇番') for i in range(1,7)]
 attempts=[z for z in rec.get('collection_attempts',{}).values() if timeparse(z.get('attempt_at')) and (not freeze or timeparse(z['attempt_at'])<freeze)];attempt=max(attempts,key=lambda z:z['attempt_at'],default={});proof=(d.get('receipt') or {}).get('proof') or {}
 verified=bool(observed and freeze and observed<freeze and re.fullmatch('[a-f0-9]{40}',proof.get('source_commit','')) and re.fullmatch('[a-f0-9]{64}',proof.get('sha256','')))
 return {'race_code':code,'date':code[:4]+'-'+code[4:6]+'-'+code[6:8],'venue':item.get('venue',rec.get('venue')),'race':item.get('race',rec.get('race')),'freeze_at':freeze.isoformat() if freeze else None,'snapshot_id':s.get('id'),'model_id':s.get('model_id'),'trained_through':s.get('learning_lineage',{}).get('trained_through'),'decision_state':d.get('state','waiting_freeze' if freeze and now<freeze else 'no_fixed_decision'),'decision_reason':d.get('reason'),'missing_inputs':missing,'weather_state':s.get('input_quality',{}).get('weather',{}).get('state','unknown'),'quote_at':quote.isoformat() if quote else None,'computed_at':computed.isoformat() if computed else None,'public_at':observed.isoformat() if observed else None,'public_receipt_verified':verified,'quote_age_at_freeze_seconds':(freeze-quote).total_seconds() if freeze and quote else None,'compute_to_public_seconds':(observed-computed).total_seconds() if observed and computed else None,'study_state':x.get('status','not_registered'),'study_id':x.get('study_id'),'labels':{'result_verified':result.get('refund_verified') is True,'full_six_finishes':bool(full),'actual_entry':sorted(str(v) for v in entries)==list('123456'),'actual_st_boats':sum(source.get(f'{i}コース_スタートタイミング') not in (None,'') for i in range(1,7)),'winning_method':bool(source.get('決まり手')),'refund':bool(result.get('refund_boats')),'nonfinish':bool(source.get('official_finish_status'))},'result_id':result.get('id'),'feature_coverage':{g:sum(bool(f.get(g)) for f in features) for g in ('ability','course','motor_history','exhibition','original','start','behavior','tactical_detail')},'source_times':s.get('input_snapshot',{}).get('source_times',{}),'last_acquisition_attempt':attempt,'acquisition_attempts':len(attempts),'settlement_attempts':len(rec.get('settlement_attempts',{}))}

def metrics(rows,name):
 a=[r['arms'][name] for r in rows];paired=[r['arms'][name] for r in rows if r['portfolio']];bets=[x for x in paired if x['state']=='buy'];stake=sum(x['paper']['stake'] for x in bets);returned=sum(x['paper']['return'] for x in bets);bins=defaultdict(lambda:[0,0,0.]);equity=peak=dd=streak=longest=0
 for r in rows:
  if not r['portfolio']:continue
  x=r['arms'][name];p=x['paper'];equity+=p['profit'];peak=max(peak,equity);dd=max(dd,peak-equity)
  if x['state']=='buy':
   streak=streak+1 if p['profit']<0 else 0;longest=max(longest,streak);b=bins[min(9,int(x['selected_probability']*10))];b[0]+=1;b[1]+=int(p['hit']);b[2]+=x['selected_probability']
 basis=[x['basis_logloss'] for x in a if 'basis_logloss' in x]
 out={'probability_races':len(a),'portfolio_races':len(paired),'buys':len(bets),'skips':len(paired)-len(bets),'hits':sum(x['paper']['hit'] for x in bets),'stake':stake,'return':returned,'profit':returned-stake,'roi':returned/stake if stake else None,'ece':sum(abs(b[1]-b[2]) for b in bins.values())/len(bets) if bets else None,'gami':sum(x['paper']['hit'] and x['paper']['profit']<0 for x in bets),'maximum_drawdown':dd,'longest_loss_streak':longest,'basis_logloss':sum(basis)/len(basis) if basis else None}
 out.update({key:sum(x[key] for x in a)/len(a) if a else None for key in ('logloss','brier','winner_logloss','second_logloss','third_logloss')});return out

def report(records,decisions,catalogs=None,now=None):
 now=now or dt.datetime.now(JST);record_map={r['race_code']:r for r in records};catalogs=catalogs or {};latest=max(catalogs,default=now.date().isoformat());catalog=catalogs.get(latest,{}) or {c:{'venue':r.get('venue'),'race':r.get('race')} for c,r in record_map.items() if r.get('date')==latest};audits=[audit_row(c,item,record_map.get(c,{}),decisions.get('records',{}).get(c,{}),now) for c,item in sorted(catalog.items())]
 cases,case_audit=frozen_cases(records,decisions,allow_prediction_only=True);rows=[];excluded=Counter()
 for c in cases:
  x,error=matched_study(c)
  if not x:excluded[error]+=1;continue
  s=c['snapshot'];freeze=timeparse(c['provenance']['freeze_at']);values={};portfolio=True
  for name,arm in x['arms'].items():
   state,reason=outcome({**s,'purchase_plan':arm['plan']},freeze);z={**score(arm['probabilities'],c['result']['combo']),'state':state,'reason':reason,'paper':None,'selected_probability':None}
   if state not in ('buy','skip'):portfolio=False
   elif state=='buy':
    from boat24_settlement import amounts
    z['paper']=amounts(arm['plan']['tickets'],c['result'].get('winning_trifectas') or {c['result']['combo']:c['result']['payout_100yen']},[]);z['selected_probability']=sum(arm['probabilities'][t['combo']] for t in arm['plan']['tickets'])
   else:z['paper']={'stake':0,'return':0,'profit':0,'hit':False}
   if name in x.get('basis',{}):z['basis_logloss']=score(x['basis'][name],c['result']['combo'])['logloss']
   values[name]=z
  rows.append({'code':c['race_code'],'date':c['date'],'venue':c['venue'],'freeze_at':c['provenance']['freeze_at'],'element_scores':element_scores(s,c['result']),'arms':values,'portfolio':portfolio,'fitted':x.get('fit',{}).get('status')=='fitted'})
 rows.sort(key=lambda r:(r['freeze_at'],r['code']));scored={r['code']:r for r in rows}
 for a in audits:
  z=scored.get(a['race_code'],{});a.update(probability_scored=bool(z),portfolio_scored=bool(z.get('portfolio')),element_scores=z.get('element_scores',{}),probability_errors={n:{k:v for k,v in arm.items() if k.endswith('logloss')} for n,arm in z.get('arms',{}).items()})
 arms={n:metrics(rows,n) for n in ARMS};fitted=[r for r in rows if r['fitted'] and r['portfolio']];adoption={n:metrics(fitted,n) for n in ARMS};primary=adoption['duel_residual'];ci={b:interval([(r['date'],r['arms']['duel_residual']['logloss']-r['arms'][b]['logloss']) for r in fitted]) for b in ('current','market')}
 checks={'trained_forward_races':len(fitted)>=400,'trained_forward_days':len({r['date'] for r in fitted})>=14,'purchases':primary['buys']>=100,'loss_beats_both_baselines':all(z and z[1]<0 for z in ci.values()),'positive_roi':primary['roi'] is not None and primary['roi']>1,'positive_profit':primary['profit']>0,'not_worse_roi':primary['roi'] is not None and all(adoption[b]['roi'] is None or primary['roi']>=adoption[b]['roi'] for b in ('current','market')),'calibration':primary['ece'] is not None and primary['ece']<=.1 and all(adoption[b]['ece'] is None or primary['ece']<=adoption[b]['ece'] for b in ('current','market')),'no_gami':primary['gami']==0}
 support={str(v):{'races':sum(r['venue']==v for r in fitted),'days':len({r['date'] for r in fitted if r['venue']==v})} for v in range(1,25)};counts=Counter(a['decision_state'] for a in audits);st_n=sum(r['element_scores']['st_boats'] for r in rows);en=sum(r['element_scores']['entry_boats'] for r in rows)
 elements={'st_boats':st_n,'st_mae_seconds':sum(r['element_scores']['st_absolute_error_sum'] for r in rows)/st_n if st_n else None,'entry_boats':en,'entry_accuracy':sum(r['element_scores']['entry_hits'] for r in rows)/en if en else None};daily={}
 for day,items in sorted(catalogs.items()):
  rr=audits if day==latest else [audit_row(c,item,record_map.get(c,{}),decisions.get('records',{}).get(c,{}),now) for c,item in items.items()]
  daily[day]={'scheduled':len(rr),'decision_reasons':dict(Counter(z['decision_reason'] for z in rr if z['decision_reason'])),'missing_required_inputs':sum(bool(z['missing_inputs']) for z in rr),'result_verified':sum(z['labels']['result_verified'] for z in rr),'study_probability_races':sum(r['date']==day for r in rows),'study_portfolio_races':sum(r['date']==day and r['portfolio'] for r in rows)}
 return {'policy':POLICY,'config_id':CONFIG,'rules':RULES,'starts_on':START_DAY,'state':'scheduled' if now.date().isoformat()<START_DAY else 'collecting','latest_day':latest,'element_scores':elements,'daily_coverage':daily,'coverage':{'scheduled':len(audits),'fixed':sum(a['public_receipt_verified'] for a in audits),'finalized':sum(n for k,n in counts.items() if k not in ('historical_unverified','waiting_freeze','no_fixed_decision')),'decision_states':dict(counts),'decision_reasons':dict(Counter(a['decision_reason'] for a in audits if a['decision_reason'])),'study_states':dict(Counter(a['study_state'] for a in audits))},'race_audit':audits,'case_audit':case_audit,'study_exclusions':dict(excluded),'probability_races':len(rows),'portfolio_races':sum(r['portfolio'] for r in rows),'days':dict(Counter(r['date'] for r in rows)),'arms':arms,'adoption_arms':adoption,'venue_support':support,'review_venues':[v for v,z in support.items() if all(checks.values()) and z['races']>=60 and z['days']>=5],'primary_intervals975':ci,'adoption_checks':checks,'review_eligible':all(checks.values()),'live_adopted':False,'required_next':'条件達成後に校正・場別支持・運用を審査。本番は自動切替しない。','note':'One public-frozen race, same quotes and controls. Expired price predictions never score portfolio returns; corrected labels never rewrite forecasts.'}
