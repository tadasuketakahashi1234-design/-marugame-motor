import copy,datetime as dt,unittest
from unittest.mock import patch
from boat24_priority import field_type,meeting_type,add_priority_features
from boat24_course import CourseStats
from boat24_context import predict,ALL_GROUPS,scales,VERSION
from boat24_validation import validate_chronologically,balanced
from boat24_integrity import JST
from boat24_registry import parse_registry
from test_all_input_model import fixture,NOW,CODE
from boat24_train_context import race_features

def registry():return {'records':{str(4000+i):{'sex':'female' if i%2 else 'male'} for i in range(1,7)}}
class PriorityTests(unittest.TestCase):
 def test_field_sex_known_mixed_unknown_and_all_female(self):
  card={f'艇{i}_登録番号':str(4000+i) for i in range(1,7)};r=registry()
  self.assertEqual(field_type(card,r)['type'],'mixed')
  for v in r['records'].values():v['sex']='female'
  self.assertEqual(field_type(card,r)['type'],'women_only');r['records'].pop('4006');self.assertEqual(field_type(card,r)['type'],'unknown')
 def test_sex_is_not_inferred_from_name_or_meeting(self):
  card={f'艇{i}_選手名':'女性らしい名前' for i in range(1,7)};self.assertEqual(field_type(card,{})['unknown'],6);self.assertEqual(meeting_type({'タイトル':'一般競走'}),'open_or_unconfirmed')
 def test_meeting_classification_separate_from_actual_six(self):
  self.assertEqual(meeting_type({'タイトル':'オールレディース競走'}),'women_restricted');self.assertEqual(meeting_type({'タイトル':'男女Ｗ優勝戦'}),'double_or_split')
 def test_zero_local_rates_are_missing_evidence_not_poor_ability(self):
  c,d,h,m=fixture();c.update({f'艇1_当地{k}':'0' for k in ('勝率','2連対率','3連対率')});f=race_features(CODE,c,d,h,NOW,m['previous_motor_rows'])['features'];self.assertNotIn('当地勝率',f[0]['ability']);self.assertEqual(f[0]['local_support']['当地公式成績未確認'],1);self.assertEqual(f[0]['local_support']['当地確認走数'],0)
 def test_opponent_strength_and_grades_are_used(self):
  c,d,h,m=fixture();c['艇2_全国勝率']='9';c['艇2_級別']='A1';d['registry']=registry();d['title'][CODE].update({'グレード':'ＧⅠ','レース名':'準優勝戦','日次':'４日目','ナイター':'Y'})
  f=race_features(CODE,c,d,h,NOW,m['previous_motor_rows'])['features'][0];self.assertEqual(f['opposition']['相手A1人数'],1);self.assertGreater(f['opposition']['相手最高全国勝率'],8);self.assertEqual(f['race_conditions']['6艇構成_mixed'],1);self.assertEqual(f['race_conditions']['段階_準優勝戦'],1)
 def test_training_freeze_matches_live_two_minute_freeze(self):
  c,d,h,m=fixture()
  for k in ('weather','ex','st','original','odds'):d[k][CODE]['取得日時']='2026-11-03T14:09:00+09:00'
  x=race_features(CODE,c,d,h,NOW+dt.timedelta(hours=4),m['previous_motor_rows'])
  for k in ('weather','ex','st','original','odds'):self.assertFalse(x['previews'][k])
 def test_local_gender_and_course_counts_are_distinct(self):
  from test_extended_inputs import data
  d=data();d['registry']=registry();stats=CourseStats();stats.add(d);self.assertEqual(stats.state['local']['4001-15']['n'],1);self.assertEqual(stats.state['by_field']['4001-mixed']['n'],1);self.assertEqual(stats.state['local_course']['4001-15-1']['n'],1)
 def test_unknown_field_does_not_contaminate_gender_stats(self):
  from test_extended_inputs import data
  stats=CourseStats();stats.add(data());self.assertFalse(stats.state['by_field'])
 def test_registry_byte_layout_uses_byte_48(self):
  # 4+16+15+4+2+1+6 = 48 bytes before sex; age is a different field.
  prefix=b'4001'+('選手'.ljust(8,'　')).encode('cp932')+b'NAME           '+('東京').encode('cp932')+b'A1H010101'
  self.assertEqual(len(prefix),48)
  payload=b'\n'.join(f'{4000+i:04}'.encode()+prefix[4:]+(b'1' if i%2 else b'2')+b'2152050' for i in range(1001))
  result=parse_registry(payload);self.assertEqual(result['4001']['sex'],'male');self.assertEqual(result['4002']['sex'],'female')
 def test_chronological_tuning_and_test_are_disjoint(self):
  cases=[{'date':f'2026-10-{day:02d}','venue':v,'actual':'1-2-3','features':[], 'odds':{'3連単_'+c:120 for c in __import__('boat24_context').COMBOS}} for day in range(20,26) for v in range(1,16)]
  uniform={c:1/120 for c in __import__('boat24_context').COMBOS};m={'samples':[]}
  with patch('boat24_validation.predict',return_value={'probabilities':uniform,'neighbour_evidence':[{'neighbours':10}]*6}):r=validate_chronologically(m,cases)
  self.assertFalse(set(r['tuning_dates'])&set(r['test_dates']));self.assertLess(max(r['tuning_dates']),min(r['test_dates']));self.assertEqual(r['test_races'],45);self.assertEqual(m['market_alpha'],0)
 def test_new_feature_families_can_affect_predictions(self):
  for group in ('race_conditions','opposition','local_support'):
   samples=[]
   for lane in range(1,7):
    for state in (0,10):
     for n in range(12):samples.append({'venue':15,'course':lane,'date':'2026-10-01','code':str(n),'finish':lane if state==0 else 7-lane,'features':{group:{'signal':state}}})
   m={'samples':samples,'scales':scales(samples)};a=[{group:{'signal':0}} for _ in range(6)];b=[{group:{'signal':10}} for _ in range(6)]
   self.assertNotEqual(predict(a,15,'2026-11-03',m)['probabilities'],predict(b,15,'2026-11-03',m)['probabilities'])
 def test_model_digest_changes_snapshot_fingerprint(self):
  from boat24_context import fingerprint
  self.assertNotEqual(fingerprint([],{}, {'model_id':'a'}),fingerprint([],{}, {'model_id':'b'}))
 def test_final_test_cannot_reselect_weights_when_it_disagrees(self):
  from boat24_context import COMBOS
  cases=[{'date':f'2026-10-{day:02d}','venue':v,'actual':'1-2-3' if day<23 else '6-5-4','features':[],'odds':{'3連単_'+c:120 for c in COMBOS}} for day in range(20,26) for v in range(1,16)]
  m={'samples':[]};evidence=[{'neighbours':10,'mean_finish_estimate':i} for i in range(1,7)]
  with patch('boat24_validation.predict',return_value={'neighbour_evidence':evidence}):r=validate_chronologically(m,cases)
  self.assertEqual(m['market_alpha'],0);self.assertEqual(m['temperature'],2);self.assertFalse(r['context_beats_market_on_test'])
 def test_no_invented_rider_adjustment_from_win_rate(self):
  c,d,h,m=fixture()
  for profiles in h.profiles.values():
   for p in profiles:p.pop('expected_finish',None)
  f=race_features(CODE,c,d,h,NOW,m['previous_motor_rows'])['features'][0]
  self.assertNotIn('過去3節選手補正',f['motor_history']);self.assertIn('過去3節平均着順',f['motor_history'])
 def test_grade_roman_numeral_is_normalized(self):
  c,d,h,m=fixture();d['title'][CODE]['グレード']='ＧⅠ';f=race_features(CODE,c,d,h,NOW,m['previous_motor_rows'])['features'][0]
  self.assertEqual(f['race_conditions']['グレード_G1'],1)
 def test_missing_only_new_family_does_not_change_neighbour_weights(self):
  samples=[]
  for lane in range(1,7):
   for n in range(20):samples.append({'venue':15,'course':lane,'date':'2026-10-01','code':str(n),'finish':1+n%6,'features':{'ability':{'signal':n}}})
  m={'samples':samples,'scales':scales(samples)};a=[{'ability':{'signal':i}} for i in range(6)];b=copy.deepcopy(a)
  for f in b:f['comments']={'never_seen':1}
  self.assertEqual(predict(a,15,'2026-11-03',m)['probabilities'],predict(b,15,'2026-11-03',m)['probabilities'])
