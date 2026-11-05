import copy,unittest
from boat24_boat_comparison import build
class SixBoatComparisonTests(unittest.TestCase):
 def snapshot(self):
  return {'id':'s','race_code':'202611050407','created_at':'2026-11-05T13:30:00+09:00','boat_identities':[{'lane':i,'name':'選手'+str(i),'racer':str(4000+i),'motor':str(20+i)} for i in range(1,7)],'input_snapshot':{'features':[{'ability':{'全国平均ST':.13},'start':{'展示進入':4 if i==3 else 3 if i==4 else i},'motor':{'モーター2連対率':40.,'モーター3連対率':55.},'course':{'勝率得点':6.2,'平均ST':.14},'style':{'差し勝ち率':.1}} for i in range(1,7)]},'race_reasoning':{'support':[{'lane':i,'races':10,'wins':2} for i in range(1,7)]}}
 def previous(self,code='202611050401',stamp='2026-11-05T11:00:00+09:00',flag='0',st=.12):
  return {'race_code':code,'revisions':{'s':self.snapshot()},'result':{'settled_at':stamp,'result_source':{'4コース_艇番':'1','4コース_スタートタイミング':st,'4コース_F':flag}}}
 def test_six_columns_names_motor_raw_average_and_course_join(self):
  s=self.snapshot();before=copy.deepcopy(s);x=build(s);self.assertEqual(s,before);self.assertEqual([b['lane'] for b in x['boats']],list(range(1,7)));self.assertEqual(x['boats'][2]['course'],4);self.assertEqual(x['boats'][0]['motor'],'21');self.assertEqual(x['boats'][0]['average_st'],.13);self.assertEqual(x['boats'][0]['course_win_rate'],.2);self.assertEqual(x['boats'][0]['methods']['差し'],.1)
 def test_confirmed_actual_course_maps_to_boat_and_zero_flag_is_normal(self):
  x=build(self.snapshot(),{'old':self.previous()});b=x['boats'][0];self.assertEqual(b['series_st'],.12);self.assertEqual(b['series_normal_count'],1);self.assertIsNone(x['boats'][3]['series_st'])
 def test_future_other_day_other_venue_and_current_race_are_excluded(self):
  rows=[self.previous(stamp='2026-11-05T14:00:00+09:00'),self.previous(code='202611040401'),self.previous(code='202611050501'),self.previous(code='202611050407')]
  for r in rows:self.assertIsNone(build(self.snapshot(),{'r':r})['boats'][0]['series_st'])
 def test_race_f_is_shown_but_not_in_average(self):
  b=build(self.snapshot(),{'old':self.previous(flag='1',st=-.02)})['boats'][0];self.assertIsNone(b['series_st']);self.assertTrue(b['series_starts'][0]['f']);self.assertEqual(b['series_normal_count'],0)
 def test_missing_is_none_not_zero_or_exhibition_substitute(self):
  x=build({'id':'s','input_snapshot':{'features':[{'start':{'展示ST符号付':.01}}]*6}});self.assertEqual(len(x['boats']),6);self.assertIsNone(x['boats'][0]['average_st']);self.assertIsNone(x['boats'][0]['series_st']);self.assertIsNone(x['boats'][0]['methods']['逃げ'])
 def test_compact_view_carries_table_with_exact_snapshot(self):
  from boat24_history_io import compact_day
  s=self.snapshot();s.update(evaluation_eligible=True,cutoff='2026-11-05T13:41:00+09:00',phase='preview',probabilities={'1-2-3':1})
  x=compact_day({'records':{'202611050407':{'race_code':'202611050407','revisions':{'s':s}}}})
  self.assertEqual(x['records']['202611050407']['boat_comparison']['snapshot_id'],'s')
