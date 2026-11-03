import copy,datetime as dt,math,unittest
from unittest.mock import patch
from boat24_behavior import BehaviorStats
from boat24_bets import optimize
from boat24_context import COMBOS,predict,scales
from boat24_integrity import JST
from boat24_operations import catalog,health
from boat24_supplement import parse_filtered_identity
from boat24_validation import validate_initial
from test_extended_inputs import data

class BatchUpgradeTests(unittest.TestCase):
 def setUp(self):
  # Cycle tests mock collection; never launch a real previous collector on CI.
  from contextlib import nullcontext
  p=patch('boat24_cycle.preserve_collection_during_rebuild',lambda *args:nullcontext());p.start();self.addCleanup(p.stop)
 def test_catalog_shows_all_twelve_without_creating_past_forecasts(self):
  now=dt.datetime(2026,11,3,14,0,tzinfo=JST);code='202611031512';d={'cards':{code:{}},'title':{code:{'電話投票締切予定':'13:00'}}};records={}
  c=catalog(d,records,now);self.assertEqual(len(c),12);self.assertEqual(c[code]['state'],'closed_no_forecast');self.assertEqual(c['202611031501']['state'],'program_unconfirmed');self.assertFalse(records)
 def test_health_identifies_missing_forecasts_and_source_failures(self):
  now=dt.datetime(2026,11,3,10,tzinfo=JST);h=health({'cards':{'x':{}}},{'x':{'state':'waiting_initial'}},{'odds':'timeout'},now);self.assertEqual(h['state'],'degraded');self.assertEqual(h['missing_forecasts'],['x']);self.assertIsNone(h['successful_collection_at'])
 def test_discrete_allocation_preserves_budget_and_unique_twelve(self):
  p={c:1/120 for c in COMBOS};a=optimize(p,{c:120 for c in COMBOS});self.assertEqual(len(a['tickets']),12);self.assertEqual(len({t['combo'] for t in a['tickets']}),12);self.assertEqual(sum(t['stake'] for t in a['tickets']),2400);self.assertTrue(all(t['stake']%100==0 and t['stake']>=100 for t in a['tickets']));self.assertTrue(a['rounded_target_met'])
 def test_infeasible_odds_and_partial_odds_are_not_reported_as_target_met(self):
  p={c:1/120 for c in COMBOS};a=optimize(p,{c:5 for c in COMBOS});self.assertEqual(a['status'],'target_unreachable');self.assertFalse(a['rounded_target_met']);self.assertFalse(optimize(p,{'1-2-3':10})['tickets'])
 def test_larger_probability_is_selected_under_same_odds(self):
  p={c:(120-i)/7260 for i,c in enumerate(COMBOS)};a=optimize(p,{c:120 for c in COMBOS});self.assertEqual({t['combo'] for t in a['tickets']},set(COMBOS[:12]))
 def test_unverified_probabilities_are_hidden_by_default(self):
  r=predict([{} for _ in range(6)],15,'2026-11-03',{'samples':[]});self.assertFalse(r['probability_verified']);self.assertFalse(r['calibration_applied'])
 def test_calibration_requires_same_input_domain(self):
  m={'samples':[],'phase_calibration':{'initial':{'temperature':2,'requires_market':False,'display_approved':True}}};r=predict([{} for _ in range(6)],15,'2026-11-03',m);self.assertTrue(r['calibration_applied']);self.assertFalse(r['probability_verified'])
 def test_filtered_official_identity_requires_id_and_sex_proof(self):
  h='<input name="x:inTobanLeft" value="5477"><input name="x:inTobanRight" value="5477"><select name="TDATP311A_2:TDATP311A_6"><option value="1" selected="selected">男性</option></select><a href="/owpc/pc/data/racersearch/profile?toban=5477&amp;toban_left=5477&amp;toban_right=5477&amp;sexval=1">'
  self.assertTrue(parse_filtered_identity(h,'5477','1'));self.assertFalse(parse_filtered_identity(h,'5477','2'));self.assertFalse(parse_filtered_identity(h.replace('value="5477"','value="4502"'),'5477','1'))
 def test_joint_entry_scenarios_are_valid_permutations(self):
  b=BehaviorStats();f=[{'start':{'展示進入':i}} for i in range(1,7)];r=b.attach(f,{});self.assertEqual(len(r['scenarios']),5)
  for row in r['marginals']:self.assertAlmostEqual(sum(row),1)
  for x in r['scenarios']:self.assertEqual(set(x['courses_by_boat']),set(range(1,7)))
 def test_behavior_actual_course_joins_racer_by_boat(self):
  d=data();code=next(iter(d['cards']));d['st']={code:{'取得日時':'2026-11-02T13:00:00+09:00','締切時刻':'14:00'}}
  for i in range(1,7):d['st'][code].update({f'艇{i}_コース':str(i),f'艇{i}_スタート展示':'0.10'})
  b=BehaviorStats();b.add(d);self.assertEqual(b.state['transition']['preview|4001|1'][0],1);self.assertGreater(b.state['st']['4001|1|0']['n'],0)
 def test_behavior_rejects_late_exhibition_and_actual_F(self):
  d=data();code=next(iter(d['cards']));d['st']={code:{'取得日時':'2026-11-02T13:59:00+09:00','締切時刻':'14:00','艇1_コース':'1','艇1_スタート展示':'0.10'}};b=BehaviorStats();b.add(d);self.assertFalse(b.state['st']);self.assertNotIn('preview|4001|1',b.state['transition'])
 def test_behavior_can_change_context_predictions_when_historically_supported(self):
  samples=[]
  for lane in range(1,7):
   for signal in (0,10):
    for i in range(12):samples.append({'phase':'initial','date':'2026-10-01','venue':15,'course':lane,'code':str(i),'finish':lane if signal==0 else 7-lane,'features':{'behavior':{'signal':signal}}})
  m={'samples':samples,'scales':scales(samples)};a=predict([{'behavior':{'signal':0}}]*6,15,'2026-11-03',m);b=predict([{'behavior':{'signal':10}}]*6,15,'2026-11-03',m);self.assertNotEqual(a['probabilities'],b['probabilities'])
 def test_initial_prediction_does_not_borrow_preview_samples(self):
  samples=[{'phase':'preview','date':'2026-10-01','venue':15,'course':lane,'code':str(i),'finish':lane,'features':{}} for lane in range(1,7) for i in range(12)];r=predict([{}]*6,15,'2026-11-03',{'samples':samples});self.assertTrue(all(e['neighbours']==0 for e in r['neighbour_evidence']))
 def test_initial_calibration_needs_three_independent_date_blocks(self):
  r=validate_initial({'samples':[]},[{'date':'2026-10-01'}]);self.assertFalse(r['display_approved'])

class ForwardReportTests(unittest.TestCase):
 def test_same_race_comparison_excludes_post_deadline_old_prediction(self):
  from boat24_forward import build_report
  p={c:1/120 for c in COMBOS};snap={'id':'s','created_at':'2026-11-03T10:00:00+09:00','cutoff':'2026-11-03T11:00:00+09:00','evaluation_eligible':True,'selection':{'12':COMBOS[:12]},'probabilities':p,'market_baseline':{'picks':COMBOS[:12],'probabilities':p},'input_snapshot':{'race_context':{'field_type':'mixed'}},'allocation':{'tickets':[{'combo':'1-2-3','stake':200}]}}
  r={'race_code':'202611031501','date':'2026-11-03','venue':15,'revisions':{'s':snap},'result':{'combo':'1-2-3','payout_100yen':1000}}
  old={'created_at':'2026-11-03T11:01:00+09:00','cutoff':snap['cutoff'],'selection':snap['selection'],'probabilities':p};report=build_report([r],{'predictions':{r['race_code']:old}});self.assertFalse(any(row['cohort']=='same_races' for row in report['rows']))
  old['created_at']='2026-11-03T09:00:00+09:00';report=build_report([r],{'predictions':{r['race_code']:old}});common=[row for row in report['rows'] if row['group']=='all' and row['cohort']=='same_races'];self.assertEqual(len(common),3);self.assertEqual({x['races'] for x in common},{1})
  allocated=next(row for row in report['rows'] if row['group']=='all' and row['model']=='allocated_paper');self.assertEqual(allocated['return'],2000);self.assertEqual(allocated['stake'],200)
 def test_merged_catalog_never_claims_existing_forecast_missing(self):
  from boat24_full_update import merge_day
  remote={'records':{'x':{'revisions':{'s':{'id':'s'}},'result':None}}};local={'records':{},'catalog':{'x':{'state':'closed_no_forecast','has_forecast':False}}};m=merge_day(remote,local);self.assertTrue(m['catalog']['x']['has_forecast']);self.assertEqual(m['catalog']['x']['state'],'saved');self.assertFalse(local['catalog']['x']['has_forecast'])

class SupplementCacheTests(unittest.TestCase):
 def test_motor_cache_keeps_original_observation_time_and_no_individual_stats(self):
  import json,tempfile
  from pathlib import Path
  from boat24_supplement import supplement
  now=dt.datetime(2026,11,3,10,tzinfo=JST);observed=now-dt.timedelta(minutes=5);rows=[{'場コード':'15','モーター番号':'40','モーター期起算日':'2026-09-17','identity_observed_at':observed.isoformat()}]
  d={'cards':{'202611031501':{'艇1_登録番号':'4001','艇1_モーター番号':'58'}},'motor_rows':[]};registry={'records':{'4001':{'sex':'male'}}}
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'cache.json';path.write_text(json.dumps({'motors':{'15':{'observed_at':observed.isoformat(),'rows':rows}}}))
   with patch('boat24_supplement.CACHE',path),patch('boat24_supplement.motor_identity',side_effect=AssertionError('Unnecessary network request')):supplement(d,registry,now)
   cache=json.loads(path.read_text());self.assertEqual(cache['motors']['15']['observed_at'],observed.isoformat());row=next(r for r in d['motor_rows'] if r['モーター番号']=='58');self.assertEqual(row['モーター期起算日'],'2026-09-17');self.assertNotIn('勝率',row);self.assertIn('individual_totals_missing',row['identity_scope'])
 def test_expired_motor_identity_is_refetched(self):
  import json,tempfile
  from pathlib import Path
  from boat24_supplement import supplement
  now=dt.datetime(2026,11,3,10,tzinfo=JST);d={'cards':{'202611031501':{'艇1_登録番号':'4001','艇1_モーター番号':'58'}},'motor_rows':[]}
  with tempfile.TemporaryDirectory() as t:
   path=Path(t)/'cache.json';path.write_text(json.dumps({'motors':{'15':{'observed_at':(now-dt.timedelta(minutes=31)).isoformat(),'rows':[]}}}))
   with patch('boat24_supplement.CACHE',path),patch('boat24_supplement.motor_identity',return_value=[{'場コード':'15','モーター番号':'58','モーター期起算日':'2026-09-17','identity_observed_at':now.isoformat()}]) as fetch:supplement(d,{'records':{'4001':{'sex':'male'}}},now)
   fetch.assert_called_once_with(15,now)

class OfficialLivePreviewTests(unittest.TestCase):
 def fixture(self):
  card={f'艇{i}_登録番号':str(4000+i) for i in range(1,7)}
  header='<a href="?hd=20261103"></a><li class="is-active2">11月3日</li><tr><td>締切予定時刻</td>'+''.join('<td class="'+('is-activeColor1' if i==9 else '')+'">14:29</td>' for i in range(1,13))+'</tr>'
  bodies=''.join(f'<tbody><tr><td class="is-boatColor{i}">{i}</td><td><a href="?toban={4000+i}"></a></td><td>選手</td><td>52.0kg</td><td>{6.6+i*.01}</td><td>-0.5</td><td></td><td></td></tr><tr></tr><tr><td>0.5</td></tr></tbody>' for i in range(1,7))
  start=''.join(f'<div class="table1_boatImage1"><span class="table1_boatImage1Number is-type{i}">{i}</span><span class="table1_boatImage1Time">'+('F.01' if i==1 else '.12')+'</span></div>' for i in range(1,7))
  return card,header+bodies+start
 def test_verified_exhibition_and_signed_F_are_parsed(self):
  from boat24_official import parse_live_previews
  c,h=self.fixture();r=parse_live_previews(h,'202611030209',c,'2026-11-03T14:20:00+09:00');self.assertAlmostEqual(float(r['ex']['艇1_展示タイム']),6.61);self.assertEqual(r['st']['艇1_スタート展示'],'-0.01');self.assertEqual(r['st']['艇6_コース'],'6');self.assertEqual(r['ex']['艇1_体重調整(kg)'],'0.5')
 def test_other_race_or_changed_registration_is_rejected(self):
  from boat24_official import parse_live_previews
  c,h=self.fixture();self.assertFalse(parse_live_previews(h,'202611030208',c,'2026-11-03T14:20:00+09:00'));c['艇6_登録番号']='9999';self.assertFalse(parse_live_previews(h,'202611030209',c,'2026-11-03T14:20:00+09:00'))
 def test_missing_exhibition_is_not_filled_with_previous_race_ST(self):
  from boat24_official import parse_live_previews
  c,h=self.fixture();self.assertFalse(parse_live_previews(h.replace('<td>6.609999999999999</td>','<td></td>').replace('<td>6.61</td>','<td></td>'),'202611030209',c,'2026-11-03T14:20:00+09:00'))
 def test_official_preview_applies_before_freeze_and_never_after(self):
  from boat24_official import parse_live_previews,apply_live_previews
  c,h=self.fixture();code='202611030209';r=parse_live_previews(h,code,c,'2026-11-03T14:20:00+09:00');d={};cache={'races':{code:{'live_previews':r}}};apply_live_previews(d,cache,dt.datetime(2026,11,3,14,21,tzinfo=JST));self.assertEqual(d['ex'][code]['情報源'],'BOAT RACE公式・対象Rと全6登録番号照合')
  for row in r.values():row['取得日時']='2026-11-03T14:27:00+09:00'
  d={};apply_live_previews(d,cache,dt.datetime(2026,11,3,14,28,tzinfo=JST));self.assertFalse(d)

class CaptureWindowTests(unittest.TestCase):
 def setUp(self):
  from contextlib import nullcontext
  p=patch('boat24_cycle.preserve_collection_during_rebuild',lambda *args:nullcontext());p.start();self.addCleanup(p.stop)
 def test_capture_repeats_instead_of_stopping_after_first_success(self):
  import tempfile,json
  from pathlib import Path
  import boat24_cycle,boat24_full_update
  now=dt.datetime(2026,11,3,14,tzinfo=JST)
  with tempfile.TemporaryDirectory() as t:
   manifest=Path(t)/'manifest.json';manifest.write_text(json.dumps({'paths':[],'index':'index.json'}))
   with patch('boat24_cycle.dt.datetime') as clock,patch('boat24_cycle.time.monotonic',side_effect=[0,0,10,10,60,180]),patch('boat24_cycle.time.sleep') as sleep,patch('boat24_daily.main'),patch('boat24_compare.main'),patch('boat24_full_update.MANIFEST',manifest),patch('boat24_full_update.main') as capture,patch('boat24_full_publish.main') as publish:
    clock.now.return_value=now;boat24_cycle.main(180)
   self.assertEqual(capture.call_count,2);self.assertEqual(publish.call_count,2);sleep.assert_called_once_with(50)
 def test_long_watch_retries_source_failure_and_preserves_saved_records(self):
  import tempfile,json
  from pathlib import Path
  import boat24_cycle
  now=dt.datetime(2026,11,3,14,tzinfo=JST)
  with tempfile.TemporaryDirectory() as t:
   directory=Path(t);day=directory/'2026-11-03.json';day.write_text(json.dumps({'records':{'existing':{'revisions':{'immutable':{'value':1}}}},'health':{}}));index=directory/'index';index.write_text('{}');manifest=directory/'manifest';manifest.write_text(json.dumps({'paths':[str(day)],'index':str(index)}))
   with patch('boat24_cycle.dt.datetime') as clock,patch('boat24_cycle.time.monotonic',side_effect=[0,0,10,60,4000]),patch('boat24_cycle.time.sleep'),patch('boat24_daily.main'),patch('boat24_compare.main'),patch('boat24_full_update.DIRECTORY',directory),patch('boat24_full_update.INDEX',index),patch('boat24_full_update.MANIFEST',manifest),patch('boat24_full_update.main',side_effect=[RuntimeError('source timeout'),None]) as capture,patch('boat24_full_publish.main') as publish:
    clock.now.return_value=now;boat24_cycle.main(4000)
   saved=json.loads(day.read_text());self.assertEqual(saved['records']['existing']['revisions']['immutable']['value'],1);self.assertEqual(capture.call_count,2);self.assertEqual(publish.call_count,2);self.assertEqual(saved['health']['collection_mode'],'live_watch')
