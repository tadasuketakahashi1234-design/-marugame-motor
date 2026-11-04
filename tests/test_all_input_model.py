import copy,datetime as dt,unittest
from boat24_context import VERSION,GROUPS,COMBOS,scales,predict
from boat24_train_context import History,race_features
from boat24_full_update import make_snapshot,latest,merge_day,settle,summary
from boat24_integrity import JST
NOW=dt.datetime(2026,11,3,14,0,tzinfo=JST);CODE='202611031501'

def fixture():
 c={'レースコード':CODE,'レース日':'2026-11-03'};base={**c,'締切時刻':'14:10','取得日時':'2026-11-03T13:59:00+09:00'}
 ex=dict(base);st=dict(base);org={**base,'計測項目1':'一周','計測項目2':'まわり足','計測項目3':'直線'};waku={};recent={}
 for i in range(1,7):
  for k,v in {'登録番号':4000+i,'選手名':'選手'+str(i),'全国勝率':5+i/10,'全国2連対率':35,'全国3連対率':50,'当地勝率':5,'当地2連対率':30,'当地3連対率':45,'全国平均ST':.15,'F本数':0,'L本数':0,'モーター番号':i,'モーター2連対率':35,'モーター3連対率':50,'ボート2連対率':30,'ボート3連対率':45}.items():c[f'艇{i}_{k}']=str(v)
  for k,v in {'展示タイム':6.8+i*.01,'体重(kg)':52,'体重調整(kg)':0,'チルト':-.5}.items():ex[f'艇{i}_{k}']=str(v)
  st[f'艇{i}_スタート展示']=str(.1+i*.01);st[f'艇{i}_コース']=str(i)
  for k,v in enumerate((37+i*.1,5+i*.01,7+i*.01),1):org[f'艇{i}_値{k}']=str(v)
  for k,v in {'枠番別勝率':5,'枠番別平均ST':.16,'枠番別平均スタート順':3,'過去1走_着順':2,'過去2走_着順':3}.items():waku[f'艇{i}_{k}']=str(v)
  recent[f'艇{i}_前1節_終了日']='2026-10-31';recent[f'艇{i}_前1節_着順列']='１２３４５６'
 weather={**base,'気象観測時刻':base['取得日時'],'風速(m)':'2','風向':'8','波の高さ(cm)':'3','天候':'2','気温(℃)':'21','水温(℃)':'23'}
 odds={**base,**{'3連単_'+c:str(10+j%20) for j,c in enumerate(COMBOS)}}
 motor=[{'場コード':'15','モーター番号':str(i),'モーター期起算日':'2026-04-01','勝率':'5','2連対率':'35','3連対率':'50','出走数':'100','平均ラップ秒':'15'} for i in range(1,7)]
 d={'cards':{CODE:c},'title':{CODE:{'レースコード':CODE,'電話投票締切予定':'14:10'}},'waku':{CODE:waku},'recent_n':{CODE:recent},'recent_l':{CODE:recent},'ex':{CODE:ex},'st':{CODE:st},'original':{CODE:org},'weather':{CODE:weather},'odds':{CODE:odds},'motor_rows':motor,'results':{},'payouts':{}}
 cal=[{'場コード':'15','節開始日':'2026-11-01','節終了日':'2026-11-06'}];hist=[];profiles=[]
 for i in range(1,7):
  for j,end in enumerate(('2026-10-28','2026-10-20','2026-10-12')):
   name='過去選手'+str(j);hist.append({'場コード':'15','モーター番号':str(i),'基準節終了日':end,'使用開始日':end[:8]+str(int(end[-2:])-4).zfill(2),'使用終了日':end,'使用者名':name,'着順列':'１２３４１２'});profiles.append({'name':name,'date':'2026-10-01','win_rate':6,'expected_finish':3.0})
 h=History(cal,hist,profiles,[]);built=race_features(CODE,c,d,h,NOW,motor);samples=[]
 for i,f in enumerate(built['features'],1):
  for j in range(20):samples.append({'venue':15,'course':i,'lane':i,'date':'2026-10-25','code':str(j),'finish':i,'features':copy.deepcopy(f)})
 m={'version':VERSION,'generated_at':'2026-11-03T05:00:00+09:00','trained_through':'2026-11-02','samples':samples,'scales':scales(samples),'market_alpha':.25,'previous_motor_rows':motor}
 return c,d,h,m

class AllInputTests(unittest.TestCase):
 def test_all_input_families_are_extracted(self):
  c,d,h,m=fixture();x=race_features(CODE,c,d,h,NOW,m['previous_motor_rows'])
  for f in x['features']:
   self.assertTrue(all(f[g] for g in GROUPS));self.assertEqual(set(f['weather']),{'風速(m)','風向','波の高さ(cm)','天候','気温(℃)','水温(℃)'})
   self.assertIn('過去3節選手補正',f['motor_history']);self.assertIn('一周相対',f['original'])
 def test_each_input_family_can_change_predictions(self):
  for group in GROUPS:
   with self.subTest(group=group):
    samples=[]
    for lane in range(1,7):
     for state in (0,10):
      for n in range(12):samples.append({'venue':15,'course':lane,'lane':lane,'date':'2026-10-25','code':str(n),'finish':lane if state==0 else 7-lane,'features':{g:{'signal':state if g==group else 0} for g in GROUPS}})
    m={'samples':samples,'scales':scales(samples),'trained_through':'2026-11-02'};a=[{g:{'signal':0} for g in GROUPS} for _ in range(6)];b=copy.deepcopy(a)
    for f in b:f[group]['signal']=10
    pa=predict(a,15,'2026-11-03',m)['probabilities'];pb=predict(b,15,'2026-11-03',m)['probabilities'];self.assertGreater(pa['1-2-3'],pb['1-2-3'])
 def test_odds_change_probabilities_and_expected_values(self):
  c,d,h,m=fixture();f=race_features(CODE,c,d,h,NOW,m['previous_motor_rows'])['features'];a={'3連単_'+c:100 for c in COMBOS};b=dict(a);b['3連単_6-5-4']=2
  pa=predict(f,15,'2026-11-03',m,a);pb=predict(f,15,'2026-11-03',m,b)
  self.assertGreater(pb['probabilities']['6-5-4'],pa['probabilities']['6-5-4']);self.assertEqual(pb['feature_usage']['odds']['status'],'used');self.assertTrue(all(v is not None for v in pb['market_metrics']['12'].values()))
 def test_zero_and_partial_odds_are_not_invented(self):
  _,_,_,m=fixture();p=predict([{g:{} for g in GROUPS} for _ in range(6)],15,'2026-11-03',m,{'3連単_1-2-3':0})
  self.assertEqual(p['feature_usage']['odds']['status'],'missing');self.assertIsNone(p['market_metrics']['12']['synthetic_odds'])
 def test_future_weather_and_previews_never_enter_features(self):
  c,d,h,m=fixture()
  for k in ('ex','st','weather','original','odds'):d[k][CODE]['取得日時']='2026-11-03T14:11:00+09:00'
  for f in race_features(CODE,c,d,h,NOW,m['previous_motor_rows'])['features']:
   for g in ('exhibition','start','weather','original'):self.assertFalse(f[g])
 def test_exhibition_f_is_flagged_not_negative_fast_time(self):
  c,d,h,m=fixture();d['st'][CODE]['艇1_スタート展示']='-0.12';f=race_features(CODE,c,d,h,NOW,m['previous_motor_rows'])['features'][0]['start'];self.assertEqual(f['展示F'],1);self.assertGreater(f['ST絶対値相対'],-.1)
 def test_future_result_labels_are_excluded(self):
  c,d,h,m=fixture();f=race_features(CODE,c,d,h,NOW,m['previous_motor_rows'])['features'];a=predict(f,15,'2026-11-03',m)
  m['samples'] += [{**copy.deepcopy(s),'date':'2026-11-03','finish':7-s['finish']} for s in m['samples']]
  self.assertEqual(a['probabilities'],predict(f,15,'2026-11-03',m)['probabilities'])
 def test_motor_cycle_and_series_boundaries(self):
  _,_,h,_=fixture();self.assertEqual(len(h.motor(15,1,'2026-04-01','2026-11-03',NOW)['uses']),3);self.assertEqual(h.motor(15,1,'2026-11-01','2026-11-03',NOW)['uses'],[]);self.assertEqual(h.motor(15,1,None,'2026-11-03',NOW)['status'],'motor_period_unknown');self.assertEqual(h.motor(15,1,'2026-04-01','2026-10-20',NOW)['uses'][0]['end'],'2026-10-12')
 def test_current_series_rejects_results_after_cutoff(self):
  _,_,h,_=fixture()
  for clock,pos in [('13:00',1),('15:00',6)]:h.add_run({'venue':15,'motor':1,'period':'2026-04-01','date':'2026-11-03','finish':pos,'racer_win_rate':6,'observed_at':'2026-11-03T'+clock+':00+09:00'})
  x=h.motor(15,1,'2026-04-01','2026-11-03',NOW);self.assertEqual(x['current_series_runs'],1);self.assertEqual(x['features']['今節平均着順'],1)
 def test_snapshot_normalization_and_evidence(self):
  c,d,h,m=fixture();s,e=make_snapshot(CODE,c,d,m,h,NOW);self.assertIsNone(e);self.assertAlmostEqual(sum(s['probabilities'].values()),1);self.assertEqual(len(s['probabilities']),120);self.assertFalse(s['complete_inputs']);self.assertTrue(all(s['feature_usage'][g]['status']=='used' for g in GROUPS+('odds',)));self.assertEqual(s['input_snapshot']['motor_history']['1']['matched_riders'],3)
 def test_one_boat_missing_exhibition_time_is_not_complete(self):
  c,d,h,m=fixture();d['ex'][CODE].pop('艇6_展示タイム');s,_=make_snapshot(CODE,c,d,m,h,NOW)
  self.assertFalse(s['complete_inputs']);self.assertEqual(s['feature_usage']['exhibition']['field_coverage']['展示タイム相対'],5)
 def test_partial_rider_matching_is_not_complete(self):
  c,d,h,m=fixture();h.profiles.clear();s,_=make_snapshot(CODE,c,d,m,h,NOW)
  self.assertFalse(s['complete_inputs']);self.assertEqual(s['input_snapshot']['motor_history']['1']['matched_riders'],0)
 def test_input_change_produces_new_immutable_revision(self):
  c,d,h,m=fixture();s,_=make_snapshot(CODE,c,d,m,h,NOW);self.assertEqual(make_snapshot(CODE,c,d,m,h,NOW,s)[1],'unchanged_inputs');d['weather'][CODE]['風速(m)']='8';new,_=make_snapshot(CODE,c,d,m,h,NOW+dt.timedelta(minutes=1),s);self.assertNotEqual(s['id'],new['id']);self.assertEqual(s['input_snapshot']['previews']['weather']['風速(m)'],'2')
 def test_late_forecast_known_results_and_future_models_are_rejected(self):
  c,d,h,m=fixture();self.assertEqual(make_snapshot(CODE,c,d,m,h,NOW+dt.timedelta(minutes=9))[1],'cutoff_passed');d['results'][CODE]={'state':'known'};self.assertEqual(make_snapshot(CODE,c,d,m,h,NOW)[1],'result_already_known');d['results'].clear();m['trained_through']='2026-11-03';self.assertEqual(make_snapshot(CODE,c,d,m,h,NOW)[1],'model_contains_future_data')
 def test_transient_missing_previews_reuse_valid_saved_inputs(self):
  c,d,h,m=fixture();s,_=make_snapshot(CODE,c,d,m,h,NOW)
  for k in ('weather','ex'):d[k]={}
  x,e=make_snapshot(CODE,c,d,m,h,NOW+dt.timedelta(minutes=1),s);self.assertIsNone(x);self.assertEqual(e,'unchanged_inputs')
 def test_results_use_latest_valid_pre_cutoff_revision(self):
  c,d,h,m=fixture();s,_=make_snapshot(CODE,c,d,m,h,NOW);s2=copy.deepcopy(s);s2.update({'id':'new','created_at':'2026-11-03T14:05:00+09:00'});s2['selection']['12']=COMBOS[-12:]
  r={'race_code':CODE,'date':'2026-11-03','venue':15,'race':1,'created_at':s['created_at'],'revisions':{s['id']:s},'result':None};a={'records':{CODE:copy.deepcopy(r)}};b={'records':{CODE:{**copy.deepcopy(r),'revisions':{s['id']:s,'new':s2}}}};out=merge_day(a,b);self.assertEqual(out['records'][CODE]['revisions'][s['id']],s)
  r=out['records'][CODE];combo='6-5-4';res={'レースコード':CODE,**{f'{i}着_艇番':v for i,v in enumerate(combo.split('-'),1)}};pay={'レースコード':CODE,'3連単_組番':combo,'3連単_払戻金':'2500'}
  self.assertTrue(settle(r,res,pay,NOW+dt.timedelta(minutes=20)));self.assertEqual(r['result']['selection_snapshot_id'],'new');self.assertTrue(r['result']['paper']['12']['hit']);self.assertFalse(settle(r,res,pay,NOW));self.assertEqual(summary([r])['12']['return'],2500)
 def test_merge_preserves_all_remote_records_and_revisions(self):
  a={'records':{'remote':{'revisions':{'old':{'x':1}},'result':None}}};b={'records':{'local':{'revisions':{},'result':None},'remote':{'revisions':{'old':{'x':2},'new':{'x':3}},'result':None}}};x=merge_day(a,b);self.assertEqual(set(x['records']),{'remote','local'});self.assertEqual(x['records']['remote']['revisions']['old'],{'x':1});self.assertIn('new',x['records']['remote']['revisions'])

if __name__=='__main__':unittest.main()
