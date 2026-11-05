import datetime as dt,unittest
from boat24_water_commentary import build
from boat24_water import SurfaceStats
from boat24_integrity import JST
class WaterCommentaryTests(unittest.TestCase):
 def snapshot(self):
  return {'created_at':'2026-11-06T12:05:00+09:00','input_quality':{'weather':{'state':'fresh'}},'input_snapshot':{'previews':{'weather':{'気象観測時刻':'2026-11-06T12:00:00+09:00','風向':1,'風速(m)':3,'波の高さ(cm)':4}},'features':[{'start':{'展示進入':i},'wind':{'同条件標本数':30,'同場コース平均との差':d},'tide':{'同条件標本数':25,'同場コース平均との差':-d}} for i,d in enumerate([.5,-.5,.1,0,.4,-.4],1)]},'water_context':{'condition_history_valid':True,'trained_through':'2026-11-05','tide':{'status':'available','phase':'rising'}},'feature_usage':{'odds':{'market_blend':1}}}
 def test_positive_means_better_finish_not_worse(self):
  x=build(self.snapshot());self.assertEqual(x['rows'][0]['wind']['label'],'良化傾向');self.assertEqual(x['rows'][1]['wind']['label'],'悪化傾向');self.assertEqual(x['rows'][2]['wind']['label'],'差が小さい');self.assertEqual(x['rows'][0]['tide']['label'],'悪化傾向');self.assertIn('市場のみ',x['prediction_use'])
 def test_stale_wind_never_becomes_advantage(self):
  s=self.snapshot();s['input_quality']['weather']['state']='stale';x=build(s);self.assertFalse(x['fresh']);self.assertTrue(all(r['wind']['delta'] is None for r in x['rows']));self.assertEqual(x['rows'][0]['tide']['label'],'悪化傾向')
 def test_small_samples_no_claim_and_course_mapping(self):
  s=self.snapshot();s['input_snapshot']['features'][0]['start']['展示進入']=4;s['input_snapshot']['features'][0]['wind']['同条件標本数']=19;x=build(s);self.assertEqual(x['rows'][0]['course'],4);self.assertEqual(x['rows'][0]['wind']['label'],'標本不足');self.assertIsNone(x['rows'][0]['wind']['delta'])
 def test_missing_tide_not_calm_and_joint_wave_not_claimed(self):
  s=self.snapshot();s['water_context']['tide']={'status':'missing'};x=build(s);self.assertEqual(x['rows'][0]['tide']['label'],'潮位未取得');self.assertIn('未集計',x['missing'])
 def test_same_day_state_is_not_historical_support(self):
  s=self.snapshot();s['water_context']['condition_history_valid']=False;x=build(s);self.assertTrue(all(r['wind']['delta'] is None for r in x['rows']))
 def test_saved_surface_delta_is_base_minus_condition(self):
  f=[{'weather':{'風向':1,'風速(m)':3},'start':{'展示進入':i}} for i in range(1,7)]
  state={'through':'2026-11-05','base':{'4|1':{'n':100,'sum':350}},'wind':{'4|1|1|1':{'n':30,'sum':60}},'tide':{}}
  SurfaceStats(state).attach(f,4,dt.datetime(2026,11,6,12,tzinfo=JST),{});self.assertGreater(f[0]['wind']['同場コース平均との差'],0)
