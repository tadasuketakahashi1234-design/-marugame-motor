import copy,datetime as dt,json,math,unittest
from pathlib import Path
from unittest.mock import patch
from boat24_integrity import JST
from boat24_context import predict,scales,ALL_GROUPS
from boat24_water import PROFILES,parse_jma,parse_jcg,tide_features,wind_values,SurfaceStats,parse_venue_weather

NOW=dt.datetime(2026,11,3,14,30,tzinfo=JST)
def features(venue=4,direction=1,speed=3):
 return [{**{g:{} for g in ALL_GROUPS},'weather':{'風向':direction,'風速(m)':speed,'波の高さ(cm)':2},'start':{'展示進入':i},'exhibition':{'展示タイム相対':0}} for i in range(1,7)]
def row(heights=None):return {'hourly_cm':heights or list(range(0,240,10)),'highs':[],'lows':[],'station':'東京','kind':'jma_astronomical_nearby_station','scope':'近隣港・実測流速ではない','source':'https://www.data.jma.go.jp/test'}

class VenueWaterTests(unittest.TestCase):
 def test_all_24_official_profiles_and_12_tidal_venues(self):
  self.assertEqual(set(PROFILES),{str(i) for i in range(1,25)});self.assertEqual(sum(p['tidal_range']=='あり' for p in PROFILES.values()),12)
  self.assertTrue(all(p['source'].startswith('https://www.boatrace.jp/') and len(p['source_sha256'])==64 for p in PROFILES.values()))
 def test_sea_or_brackish_does_not_imply_tides(self):
  for venue in (7,8,9):
   self.assertIn(PROFILES[str(venue)]['water_type'],('海水','汽水'));f,m=tide_features(venue,NOW,{str(venue):{'2026-11-03':row()}});self.assertFalse(f);self.assertEqual(m['status'],'not_applicable')
 def test_all_non_tidal_venues_get_no_tide_bonus(self):
  for venue,p in PROFILES.items():
   if p['tidal_range']=='なし':self.assertEqual(tide_features(int(venue),NOW,{})[1]['status'],'not_applicable')
 def test_every_tidal_venue_has_its_own_source_and_scope(self):
  for v,p in PROFILES.items():
   if p['tidal_range']=='あり':self.assertIsNotNone(p['tide_source']);self.assertTrue(p['tide_source']['scope'])
  self.assertEqual(PROFILES['24']['tide_source']['area'],'4250');self.assertIn('大村',PROFILES['24']['tide_source']['name'])
 def test_tide_interpolation_is_prediction_not_current_velocity(self):
  f,m=tide_features(4,NOW,{'4':{'2026-11-03':row()}});self.assertEqual(f['推算潮位cm'],145);self.assertEqual(f['潮位変化cm毎時'],10);self.assertFalse(m['is_current_velocity']);self.assertFalse(m['is_measured_course_level'])
 def test_missing_tide_data_is_not_treated_as_no_tides(self):
  f,m=tide_features(4,NOW,{});self.assertFalse(f);self.assertEqual(m['status'],'missing');self.assertEqual(PROFILES['4']['tidal_range'],'あり')
 def test_no_extrapolation_at_midnight(self):
  f,m=tide_features(4,NOW.replace(hour=23),{'4':{'2026-11-03':row()}});self.assertFalse(f)
  f,m=tide_features(4,NOW.replace(hour=23),{'4':{'2026-11-03':row(),'2026-11-04':row([0]*24)}});self.assertEqual(f['推算潮位cm'],115)
 def test_compass_vectors_preserve_cardinal_direction_and_do_not_invent_headwind(self):
  north,_=wind_values({'風向':1,'風速(m)':3});south,_=wind_values({'風向':5,'風速(m)':3});self.assertAlmostEqual(north['北からの風成分'],3);self.assertAlmostEqual(south['北からの風成分'],-3);self.assertNotIn('向かい風成分',north)
 def test_invalid_16_class_codes_not_interpreted_as_compass8(self):
  self.assertEqual(wind_values({'風向':16,'風速(m)':3}),({},None));f,key=wind_values({'風速(m)':0});self.assertEqual(f['無風'],1)
 def test_current_day_condition_results_cannot_leak_into_query(self):
  stats=SurfaceStats();f=features();stats.attach(f,4,NOW,{});stats.add(4,f,{str(i):i for i in range(1,7)},'2026-11-03');r=stats.attach(f,4,NOW,{})
  self.assertFalse(r['condition_history_valid']);self.assertNotIn('同条件平均着順',f[0]['wind'])
 def test_same_venue_course_samples_do_not_cross_venues(self):
  stats=SurfaceStats();f=features()
  for _ in range(10):stats.add(4,f,{str(i):i for i in range(1,7)},'2026-11-02')
  a=features();stats.attach(a,4,NOW,{});b=features();stats.attach(b,15,NOW,{})
  self.assertIn('同条件平均着順',a[0]['wind']);self.assertNotIn('同条件平均着順',b[0]['wind'])
 def test_all_24_venues_attach_wind_features_and_correct_tide_applicability(self):
  for venue in range(1,25):
   f=features();m=SurfaceStats().attach(f,venue,NOW,{})
   self.assertTrue(all('北からの風成分' in x['wind'] for x in f));self.assertEqual(m['profile']['name'],PROFILES[str(venue)]['name']);self.assertEqual(m['tide']['status'],'not_applicable' if PROFILES[str(venue)]['tidal_range']=='なし' else 'missing')
 def test_venue_wind_signal_can_change_predictions(self):
  samples=[]
  for venue in (4,15):
   for sign in (1,-1):
    for lane in range(1,7):
     for n in range(12):samples.append({'date':'2026-10-01','phase':'preview','venue':venue,'course':lane,'code':str(n),'finish':lane if sign==1 else 7-lane,'features':{'wind':{'北からの風成分':sign*3},'start':{'展示進入':lane},'exhibition':{'展示タイム相対':0}}})
  model={'samples':samples,'scales':scales(samples),'market_alpha':0};a=features();b=features()
  for f in a:f['wind']={'北からの風成分':3}
  for f in b:f['wind']={'北からの風成分':-3}
  self.assertNotEqual(predict(a,4,'2026-11-03',model)['probabilities'],predict(b,4,'2026-11-03',model)['probabilities'])
 def test_official_live_wind_quality_literal_not_hardcoded_to_marugame_north(self):
  r=parse_venue_weather('1420\t1\t2\t西　(向い風)\t3\t+20.0\t+23.0\n',15,NOW);self.assertEqual(r['numeric']['風向'],'7.0');self.assertEqual(r['wind_quality_literal'],'向い風')
 def test_stale_or_future_observations_rejected(self):
  for stamp in ('1700','0900'):
   with self.assertRaises(ValueError):parse_venue_weather(stamp+'\t1\t2\t北　(追い風)\t3\t+20\t+23',4,NOW)
 def test_jma_fixed_width_wrong_station_or_year_rejected(self):
  lines=[]
  start=dt.date(2026,1,1)
  for n in range(365):
   d=start+dt.timedelta(days=n);lines.append(''.join(f'{h:3}' for h in range(24))+f'{26:2}{d.month:2}{d.day:2}TK'+'9999999'*8)
  body='\n'.join(lines);self.assertEqual(len(parse_jma(body,2026,'TK')),365)
  for year,station in ((2025,'TK'),(2026,'TX')):
   with self.assertRaises(ValueError):parse_jma(body,year,station)
 def test_jcg_omura_requires_exact_station_date_and_24_values(self):
  body='大村（大村湾）<input name=area value="4250"><input name=year value=2026><input name=month value=11><input name=day value=3>'
  body+=''.join('<TR><TD>(cm)</TD>'+''.join('<TD>50</TD>' for _ in range(12))+'</TR>' for _ in range(2))
  self.assertEqual(len(parse_jcg(body,NOW.date())['hourly_cm']),24)
  with self.assertRaises(ValueError):parse_jcg(body.replace('value=3>','value=4>'),NOW.date())
  with self.assertRaises(ValueError):parse_jcg(body.replace('大村（大村湾）','佐世保'),NOW.date())

class TidePredictionInfluenceTests(unittest.TestCase):
 def test_learned_tide_features_can_change_predictions_at_same_venue(self):
  samples=[]
  for state in (0,1):
   for lane in range(1,7):
    for n in range(12):samples.append({'date':'2026-10-01','phase':'preview','venue':4,'course':lane,'code':str(n),'finish':lane if state==0 else 7-lane,'features':{'tide':{'日内相対潮位':state},'start':{'展示進入':lane},'exhibition':{'展示タイム相対':0}}})
  m={'samples':samples,'scales':scales(samples),'market_alpha':0};a=features();b=features()
  for f in a:f['tide']={'日内相対潮位':0}
  for f in b:f['tide']={'日内相対潮位':1}
  self.assertNotEqual(predict(a,4,'2026-11-03',m)['probabilities'],predict(b,4,'2026-11-03',m)['probabilities'])
 def test_newer_csv_measurement_is_not_replaced_by_stale_official_measurement(self):
  from boat24_official import apply_live_previews
  code='202611030410';d={'title':{code:{'電話投票締切予定':'15:00'}},'weather':{code:{'取得日時':'2026-11-03T14:25:00+09:00','気象観測時刻':'1425','風速(m)':'9'}}}
  surface=parse_venue_weather('1410\t1\t2\t北　(追い風)\t3\t+20\t+23',4,NOW);surface['source']='https://race.boatcast.jp/test';apply_live_previews(d,{'races':{code:{}},'venue_weather':{'04':surface}},NOW);self.assertEqual(d['weather'][code]['風速(m)'],'9')

class ModelMigrationTests(unittest.TestCase):
 def test_current_model_or_local_environment_does_not_spawn_previous_collector(self):
  import tempfile,os
  from boat24_model_io import write_json
  from boat24_migration import needs_previous_collector
  with tempfile.TemporaryDirectory() as t:
   model=Path(t)/'model.json';marker=Path(t)/'marker';write_json(model,{'version':'new'});marker.write_text(json.dumps({'previous_source_commit':'a'*40}))
   with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):self.assertIsNone(needs_previous_collector(model,'new',marker))
   write_json(model,{'version':'old'})
   with patch.dict(os.environ,{'GITHUB_ACTIONS':'false'}):self.assertIsNone(needs_previous_collector(model,'new',marker))
 def test_existing_deployed_model_selects_verified_previous_commit(self):
  import tempfile,os
  from boat24_model_io import write_json
  from boat24_migration import needs_previous_collector
  with tempfile.TemporaryDirectory() as t:
   model=Path(t)/'model.json';marker=Path(t)/'marker';write_json(model,{'version':'old'});marker.write_text(json.dumps({'previous_source_commit':'b'*40}))
   with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):self.assertEqual(needs_previous_collector(model,'new',marker),'b'*40)
   marker.write_text(json.dumps({'previous_source_commit':'main; unsafe'}))
   with patch.dict(os.environ,{'GITHUB_ACTIONS':'true'}):self.assertIsNone(needs_previous_collector(model,'new',marker))
 def test_previous_collector_is_stopped_and_worktree_removed_on_training_failure(self):
  from unittest.mock import Mock
  from boat24_migration import preserve_collection_during_rebuild
  child=Mock();child.wait.return_value=0
  with patch('boat24_migration.needs_previous_collector',return_value='c'*40),patch('boat24_migration.subprocess.run') as run,patch('boat24_migration.subprocess.Popen',return_value=child):
   with self.assertRaisesRegex(RuntimeError,'training failed'):
    with preserve_collection_during_rebuild('model.json.gz','new'):raise RuntimeError('training failed')
  child.wait.assert_called_once_with(timeout=120);self.assertEqual(run.call_count,2);self.assertEqual(run.call_args.args[0][:3],['git','worktree','remove'])
