import copy,datetime as dt,unittest
from unittest.mock import patch,MagicMock
from boat24_context import COMBOS
from boat24_comparison_inputs import market_for,allocation_current,digest
from boat24_forward import build_report
from boat24_integrity import JST
from boat24_live import reprice
AT=dt.datetime(2026,11,4,19,0,tzinfo=JST);CODE='202611041905'
def snapshot():
 return {'id':'s','race_code':CODE,'model_id':'m','phase':'preview','evaluation_eligible':True,'created_at':AT.isoformat(),'cutoff':(AT+dt.timedelta(minutes=20)).isoformat(),'probabilities':{c:1/120 for c in COMBOS},'selection':{'12':COMBOS[:12]},'input_snapshot':{'features':[{} for _ in range(6)],'previews':{'odds':{'レースコード':CODE,'取得日時':AT.isoformat(),**{'3連単_'+c:120 for c in COMBOS}}}},'purchase_plan':{'odds_observed_at':AT.isoformat()}}
class ComparisonRepair(unittest.TestCase):
 def test_report_rebuilds_market_and_excludes_inherited_allocation_without_mutation(self):
  s=snapshot();s['market_baseline']=market_for(s);s['input_snapshot']['previews']['odds']['3連単_1-2-3']=240;s['refresh_kind']='official_odds_reprice';s['allocation']={'tickets':[{'combo':'1-2-3','stake':100,'odds':120}]}
  r={'race_code':CODE,'date':'2026-11-04','venue':19,'revisions':{'s':s},'result':{'combo':'1-2-3','payout_100yen':24000}};original=copy.deepcopy(r)
  report=build_report([r]);self.assertEqual(r,original);self.assertEqual(report['input_audit']['market_rebuilt'],1);self.assertEqual(report['input_audit']['allocation_excluded'],1)
  row=next(x for x in report['rows'] if x['group']=='all' and x['model']=='market');self.assertEqual(row['hits'],0);self.assertFalse(any(x['model']=='allocated_paper' for x in report['rows']))
 def test_future_missing_and_incomplete_quote_inputs_are_excluded(self):
  s=snapshot();s['input_snapshot']['previews']['odds']['取得日時']=(AT+dt.timedelta(minutes=1)).isoformat();self.assertIsNone(market_for(s))
  s=snapshot();s['input_snapshot']['previews']['odds'].pop('3連単_1-2-3');self.assertIsNone(market_for(s))
 def test_digest_binds_allocation_to_probability_and_quote_inputs(self):
  s=snapshot();s['allocation']={'tickets':[{'combo':'1-2-3','stake':100,'odds':120}],'comparison_input_digest':digest(s)};self.assertTrue(allocation_current(s))
  s['probabilities']['1-2-3']+=.01;self.assertFalse(allocation_current(s))
 def test_live_reprice_refreshes_both_comparisons_and_preserves_base(self):
  s=snapshot();s['market_baseline']=market_for(s);s['allocation']={'tickets':[{'combo':'1-2-3','stake':100,'odds':120}]};original=copy.deepcopy(s)
  quotes=copy.deepcopy(s['input_snapshot']['previews']['odds']);quotes['3連単_1-2-3']=240;out={'phase':'initial','probabilities':s['probabilities'],'selection':s['selection'],'feature_usage':{}}
  with patch('boat24_live.predict',return_value=out),patch('boat24_live.optimize',return_value={'tickets':[{'combo':'1-2-3','stake':100,'odds':240}]}):
   new=reprice(s,quotes,{'model_id':'m','trained_through':'2026-11-03'},CODE,AT)
  self.assertEqual(s,original);self.assertEqual(new['market_baseline'],market_for(new));self.assertNotEqual(new['market_baseline'],s['market_baseline']);self.assertTrue(allocation_current(new));self.assertEqual(new['allocation']['tickets'][0]['odds'],240)
 def test_training_replay_reaches_condition_history_after_quality_filtering(self):
  import boat24_train_context as train
  day=AT.date();res={f'{i}着_艇番':str(i) for i in range(1,7)};cut=AT+dt.timedelta(minutes=20)
  base={'features':[{'weather':{}} for _ in range(6)],'previews':{'odds':{}},'cutoff':cut,'asof':AT}
  fresh={**copy.deepcopy(base),'features':[{'weather':{'風速(m)':5,'風向':2}} for _ in range(6)],'previews':{'odds':{},'weather':{'気象観測時刻':AT.isoformat()}}}
  captured=[];surface=MagicMock();surface.add.side_effect=lambda v,f,fm,d:captured.append(copy.deepcopy(f))
  data={'cards':{CODE:{}},'results':{CODE:res},'weather':{},'ex':{},'st':{},'original':{},'motor_rows':[]}
  with patch('boat24_replay.load_observations',return_value=({(CODE,'preview'):{}},{})),patch('boat24_replay.restore_snapshot',return_value=fresh),patch.object(train,'load_registry',return_value={}),patch.object(train,'load_tide_book',return_value=({},{})),patch.object(train,'fetch',return_value=[]),patch.object(train,'calendar_and_history',return_value=({},{})),patch.object(train,'collect_day',return_value=data),patch.object(train,'profiles_and_runs',return_value=([],[])),patch.object(train,'race_features',side_effect=lambda *a,**k:copy.deepcopy(base)),patch.object(train,'CourseStats'),patch.object(train,'BehaviorStats'),patch.object(train,'SurfaceStats',return_value=surface),patch('boat24_tactics.Tactics'):
   with self.assertRaisesRegex(RuntimeError,'Insufficient historical samples'):train.build_model(day+dt.timedelta(days=1),days=1)
  self.assertEqual(len(captured),1);self.assertEqual(captured[0][0]['weather']['風速(m)'],5)
