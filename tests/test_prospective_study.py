import copy,datetime as dt,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from boat24_context import COMBOS
from boat24_integrity import JST
from boat24_risk import robust_plan
from boat24_decisions import update
from boat24_history_io import compact_day
from boat24_learning import frozen_cases,digest
import boat24_study as study

def fixture(day='2026-11-06',race=1,quote_age=0,fitted=True,public_study=True):
 date=dt.date.fromisoformat(day);now=dt.datetime.combine(date,dt.time(12,4),JST);cut=now+dt.timedelta(minutes=6);code=day.replace('-','')+'19'+str(race).zfill(2);quote=now-dt.timedelta(minutes=quote_age);odds={c:10. for c in COMBOS};p={c:((1-116e-6)/4 if c in COMBOS[:4] else 1e-6) for c in COMBOS};plan=robust_plan(p,odds);plan['odds_observed_at']=quote.isoformat()
 fs=[{'ability':{'全国勝率':5.},'exhibition':{'展示タイム相対':0.},'start':{'展示進入':i,'展示ST符号付':.1}} for i in range(1,7)]
 s={'id':'s'+code,'race_code':code,'phase':'preview','evaluation_eligible':True,'created_at':now.isoformat(),'computed_at':now.isoformat(),'cutoff':cut.isoformat(),'model_id':'m','probabilities':p,'purchase_plan':plan,'input_quality':{'purchase_inputs_ready':True},'learning_lineage':{'trained_through':(date-dt.timedelta(days=1)).isoformat()},'input_snapshot':{'features':fs,'source_times':{'odds':quote.isoformat()},'captured_at':now.isoformat(),'previews':{'odds':{'取得日時':quote.isoformat(),**{'3連単_'+c:v for c,v in odds.items()}}}}}
 trained={'config_id':study.CONFIG,'status':'fitted' if fitted else 'training_wait','trained_through':(date-dt.timedelta(days=1)).isoformat(),'training_races':40 if fitted else 0,'training_days':4 if fitted else 0,'betas':{'foot_residual':.25 if fitted else 0.,'duel_residual':.375 if fitted else 0.}};m={'trained_through':trained['trained_through'],'prospective_study_training':trained}
 with patch.object(study,'bases',return_value={'foot_residual':p,'duel_residual':p}):study.attach(s,m,now)
 r={'race_code':code,'date':day,'venue':19,'race':race,'revisions':{s['id']:s}};cat={code:{'race_code':code,'venue':19,'race':race,'cutoff':cut.isoformat(),'state':'saved'}};v=compact_day({'date':day,'catalog':cat,'records':{code:r}})
 if not public_study:v['records'][code]['revisions'][s['id']].pop('study_evidence',None)
 proof={'source_commit':'a'*40,'sha256':'b'*64};d=update({},v,{code:r},(now+dt.timedelta(seconds=10)).isoformat(),proof);d=update(d,v,{code:r},cut.isoformat(),proof)
 r['result']={'id':'r'+code,'combo':COMBOS[0],'payout_100yen':1000,'winning_trifectas':{COMBOS[0]:1000},'refund_verified':True,'refund_boats':[],'result_source':{'レースコード':code,**{f'{i}着_艇番':str(i) for i in range(1,7)}}};return r,d,cat,now,m

def out(r,d,cat,now):return study.report([r],d,{r['date']:cat},now)
def snap(r):return next(iter(r['revisions'].values()))
class ProspectiveStudy(unittest.TestCase):
 def test_four_arms_are_frozen_with_identical_controls(self):
  r,d,c,n,m=fixture();x=snap(r)['prospective_study'];self.assertEqual(set(x['arms']),set(study.ARMS));controls=[a['plan']['risk_controls'] for a in x['arms'].values()];self.assertTrue(all(z==controls[0] for z in controls));self.assertEqual(d['records'][r['race_code']]['decision']['study'],x);self.assertEqual(out(r,d,c,n)['portfolio_races'],1);self.assertFalse(out(r,d,c,n)['live_adopted'])
 def test_public_view_contains_digest_without_large_vectors(self):
  r,d,c,n,m=fixture();s=compact_day({'catalog':c,'records':{r['race_code']:r}})['records'][r['race_code']]['revisions'][snap(r)['id']];self.assertIn('study_evidence',s);self.assertNotIn('prospective_study',s)
 def test_archive_only_study_cannot_be_backdated_as_public(self):
  r,d,c,n,m=fixture(public_study=False);self.assertNotIn('study',d['records'][r['race_code']]['decision']);self.assertEqual(out(r,d,c,n)['probability_races'],0)
 def test_study_mutation_after_results_is_excluded(self):
  r,d,c,n,m=fixture();snap(r)['prospective_study']['fit']['training_races']+=1;self.assertEqual(out(r,d,c,n)['probability_races'],0)
 def test_expired_quote_scores_probabilities_but_no_price_returns(self):
  r,d,c,n,m=fixture(quote_age=2);self.assertFalse(frozen_cases([r],d)[0]);self.assertEqual(len(frozen_cases([r],d,allow_prediction_only=True)[0]),1);z=out(r,d,c,n);self.assertEqual(z['probability_races'],1);self.assertEqual(z['portfolio_races'],0);self.assertTrue(all(a['roi'] is None for a in z['arms'].values()))
 def test_missing_inputs_do_not_produce_a_study(self):
  r,d,c,n,m=fixture();s=copy.deepcopy(snap(r));s['input_quality']['purchase_inputs_ready']=False;study.attach(s,m,n);self.assertEqual(s['prospective_study']['status'],'inputs_missing');self.assertNotIn('arms',s['prospective_study'])
 def test_before_registration_is_scheduled(self):
  r,d,c,n,m=fixture(day='2026-11-05');self.assertEqual(snap(r)['prospective_study']['status'],'scheduled');self.assertEqual(out(r,d,c,n)['state'],'scheduled')
 def test_future_model_is_rejected(self):
  r,d,c,n,m=fixture();s=copy.deepcopy(snap(r));m['trained_through']=r['date'];study.attach(s,m,n);self.assertEqual(s['prospective_study']['status'],'model_date_invalid')
 def test_freeze_and_window_gates(self):
  r,d,c,n,m=fixture();s=copy.deepcopy(snap(r));study.attach(s,m,n+dt.timedelta(minutes=4));self.assertEqual(s['prospective_study']['status'],'after_freeze');s['cutoff']=(n+dt.timedelta(minutes=30)).isoformat();study.attach(s,m,n);self.assertEqual(s['prospective_study']['status'],'waiting_window')
 def test_partial_quote_matrix_not_renormalized(self):
  r,d,c,n,m=fixture();s=copy.deepcopy(snap(r));s['input_snapshot']['previews']['odds'].pop('3連単_'+COMBOS[0]);study.attach(s,m,n);self.assertEqual(s['prospective_study']['status'],'probabilities_or_quotes_incomplete');self.assertIsNone(study.market_for({COMBOS[0]:10}))
 def test_bases_remove_market_and_separate_start_groups(self):
  calls=[];p={c:1/120 for c in COMBOS}
  def predict(f,v,d,m,o):calls.append(m);return {'probabilities':p}
  with patch('boat24_context.predict',side_effect=predict):study.bases([{}]*6,19,'2026-11-06',{'market_alpha':1})
  self.assertTrue(all(m['market_alpha']==0 and m['phase_calibration']=={} for m in calls));self.assertNotIn('start',calls[0]['enabled_groups']);self.assertIn('start',calls[1]['enabled_groups'])
 def test_duplicates_do_not_increase_race_count(self):
  r,d,c,n,m=fixture();self.assertEqual(study.report([r,r],d,{r['date']:c},n)['probability_races'],1);old=copy.deepcopy(d['records'][r['race_code']]['decision']);v=compact_day({'catalog':c,'records':{r['race_code']:r}});later=update(d,v,{r['race_code']:r},(n+dt.timedelta(hours=2)).isoformat(),{});self.assertEqual(later['records'][r['race_code']]['decision'],old)
 def test_result_correction_rescores_without_rewriting_forecast(self):
  r,d,c,n,m=fixture();old=copy.deepcopy(r['revisions']);a=out(r,d,c,n);r['result'].update(id='corrected',payout_100yen=200,winning_trifectas={COMBOS[0]:200});b=out(r,d,c,n);self.assertEqual(b['probability_races'],1);self.assertLess(b['arms']['current']['return'],a['arms']['current']['return']);self.assertEqual(r['revisions'],old)
 def test_refunds_and_unverified_results_excluded(self):
  for field,value in [('refund_verified',False),('refund_boats',[6])]:
   r,d,c,n,m=fixture();r['result'][field]=value;self.assertEqual(out(r,d,c,n)['probability_races'],0)
 def test_missing_race_visible_with_each_boat_deficit(self):
  r,d,c,n,m=fixture();z=study.report([],d,{r['date']:c},n);self.assertEqual(z['coverage']['scheduled'],1);self.assertEqual(len(z['race_audit'][0]['missing_inputs']),18)
 def test_unfitted_rows_do_not_enter_adoption_cohort(self):
  r,d,c,n,m=fixture(fitted=False);z=out(r,d,c,n);self.assertEqual(z['arms']['current']['probability_races'],1);self.assertEqual(z['adoption_arms']['current']['probability_races'],0);x=snap(r)['prospective_study'];self.assertEqual(x['arms']['market']['probabilities'],x['arms']['duel_residual']['probabilities'])
 def test_model_dates_and_input_mutation_are_excluded(self):
  for kind in ('date','input'):
   r,d,c,n,m=fixture();s=snap(r);x=s['prospective_study']
   if kind=='date':x['trained_through']=r['date']
   else:s['input_snapshot']['features'][0]['ability']['全国勝率']=9
   dd=d['records'][r['race_code']]['decision'];dd['study']=copy.deepcopy(x);dd['receipt']['study_digest']=digest(x);self.assertEqual(out(r,d,c,n)['probability_races'],0)
 def test_fit_uses_prior_dates_and_fails_closed_when_small(self):
  r,d,c,n,m=fixture()
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);dr=root/'full_history';dr.mkdir();(dr/(r['date']+'.json')).write_text(json.dumps({'records':{r['race_code']:r}}));(root/'boat24_decisions.json').write_text(json.dumps(d));a=study.fit(n.date(),m,dr);b=study.fit(n.date()+dt.timedelta(days=1),m,dr)
  self.assertEqual(a['training_races'],0);self.assertEqual(b['training_races'],1);self.assertEqual(b['status'],'training_wait');self.assertEqual(set(b['betas'].values()),{0.})
 def test_fit_updates_weights_after_minimum_support(self):
  ds={'records':{}}
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);dr=root/'full_history';dr.mkdir()
   for k in range(3):
    day=(dt.date(2026,11,6)+dt.timedelta(days=k)).isoformat();rr={}
    for race in range(1,11):
     r,d,c,n,m=fixture(day=day,race=race);rr[r['race_code']]=r;ds['records'].update(d['records'])
    (dr/(day+'.json')).write_text(json.dumps({'records':rr}))
   (root/'boat24_decisions.json').write_text(json.dumps(ds));z=study.fit(dt.date(2026,11,9),m,dr)
  self.assertEqual(z['status'],'fitted');self.assertEqual(z['training_races'],30);self.assertEqual(z['training_days'],3);self.assertGreater(z['betas']['duel_residual'],0);self.assertEqual(len(z['training_codes']),30);self.assertEqual(len(z['case_digest']),64)
 def test_scoring_and_cluster_interval(self):
  p={c:1/120 for c in COMBOS};z=study.score(p,COMBOS[0]);self.assertAlmostEqual(z['brier'],119/120);self.assertAlmostEqual(sum(z[k] for k in ('winner_logloss','second_logloss','third_logloss')),z['logloss']);self.assertIsNone(study.interval([('a',-1),('b',-2)]));a=[(str(i),-.1) for i in range(4)];self.assertEqual(study.interval(a),study.interval(a));self.assertLess(study.interval(a)[1],0)
 def test_attempt_journals_merge_and_compact(self):
  from boat24_full_update import merge_day
  r,d,c,n,m=fixture();code=r['race_code'];r['collection_attempts']={'old':{'state':'timeout','attempt_at':n.isoformat()}};a={'records':{code:r},'catalog':c};b=copy.deepcopy(a);b['records'][code]['collection_attempts']={'old':{'state':'rewritten'},'next':{'state':'saved'}};z=merge_day(a,b)['records'][code]['collection_attempts'];self.assertEqual(z['old']['state'],'timeout');self.assertEqual(z['next']['state'],'saved');v=compact_day(a)['records'][code];self.assertNotIn('collection_attempts',v);self.assertEqual(v['collection_attempt_count'],1)
 def test_only_pre_freeze_attempts_explain_frozen_inputs(self):
  r,d,c,n,m=fixture();r['collection_attempts']={'a':{'attempt_at':n.isoformat(),'state':'timeout'},'b':{'attempt_at':(n+dt.timedelta(hours=1)).isoformat(),'state':'saved'}};z=study.audit_row(r['race_code'],c[r['race_code']],r,d['records'][r['race_code']],n);self.assertEqual(z['last_acquisition_attempt']['state'],'timeout');self.assertEqual(z['acquisition_attempts'],1)
 def test_comma_quotes_use_shared_parser(self):
  r,d,c,n,m=fixture();s=copy.deepcopy(snap(r));s['input_snapshot']['previews']['odds']['3連単_'+COMBOS[0]]='1,000.0'
  with patch.object(study,'bases',return_value={'foot_residual':s['probabilities'],'duel_residual':s['probabilities']}):study.attach(s,m,n)
  self.assertEqual(s['prospective_study']['status'],'recorded')
 def test_actual_st_mapping_and_f_exclusion(self):
  s={'behavior_forecast':{'st_estimates':[.1]*6,'scenarios':[{'courses_by_boat':[2,1,3,4,5,6]}]}};source={f'{i}コース_艇番':str(i) for i in range(1,7)};source.update({f'{i}コース_スタートタイミング':'.2' for i in range(1,7)});source['2コース_F']=True;z=study.element_scores(s,{'result_source':source});self.assertEqual(z['st_boats'],5);self.assertAlmostEqual(z['st_absolute_error_sum'],.5);self.assertEqual(z['entry_hits'],4)
 def test_failed_quote_acquisition_persists_without_forecast(self):
  import boat24_live as live
  import boat24_full_update as full
  r,d,c,n,m=fixture();r['result']=None;code=r['race_code'];book={'date':r['date'],'records':{code:r},'catalog':c}
  class Clock(dt.datetime):
   @classmethod
   def now(cls,tz=None):return n
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);dr=root/'full_history';dr.mkdir();(dr/(r['date']+'.json')).write_text('{}')
   with patch.object(full,'DIRECTORY',dr),patch.object(full,'INDEX',root/'index.json'),patch.object(full,'MANIFEST',root/'pending.json'),patch.object(live,'read_history',return_value=book),patch.object(live,'collect',return_value=({}, {code:'timeout'})),patch('boat24_fast_context.collect',return_value=({code:{'source_checks':{'before':{'state':'unconfirmed','error':'timeout'}}}},{})),patch('boat24_official_results.collect_results',return_value=({},{})),patch.object(live.dt,'datetime',Clock),patch.object(live,'write_history') as write,patch.object(live,'write_view'),patch('boat24_full_publish.main'):self.assertTrue(live.capture(m))
  self.assertIn(code,write.call_args.kwargs['changed_codes']);z=list(r['collection_attempts'].values());self.assertEqual(z[0]['state'],'odds_unconfirmed');self.assertEqual(z[0]['odds_error'],'timeout')
 def test_expired_predictions_do_not_fit_price_weights(self):
  r,d,c,n,m=fixture(quote_age=2)
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);dr=root/'full_history';dr.mkdir();(dr/(r['date']+'.json')).write_text(json.dumps({'records':{r['race_code']:r}}));(root/'boat24_decisions.json').write_text(json.dumps(d));z=study.fit(n.date()+dt.timedelta(days=1),m,dr)
  self.assertEqual(z['training_races'],0);self.assertEqual(z['exclusions']['training_quote_or_plan_not_comparable'],1)
 def test_zero_weight_is_exact_market(self):
  p={c:(i+1)/7260 for i,c in enumerate(COMBOS)};self.assertEqual(study.mixture(p,{c:1/120 for c in COMBOS},0),p)
