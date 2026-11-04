import copy
import datetime as dt
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from boat24_integrity import JST
from boat24_odds import parse_odds,add_market
from boat24_live import reprice
from boat24_commentary import build

NOW=dt.datetime(2026,11,4,8,51,tzinfo=JST)
CODE='202611041002'
class OfficialOddsTests(unittest.TestCase):
 def setUp(self):self.doc=Path('tests/fixtures/official_odds_mikuni.html').read_text()
 def test_real_official_matrix_is_joined_by_boat_not_cell_position_alone(self):
  row=parse_odds(self.doc,CODE,NOW)
  self.assertEqual(len([k for k in row if k.startswith('3連単_')]),120)
  self.assertEqual(row['3連単_1-2-3'],'7.8');self.assertEqual(row['3連単_1-2-4'],'9.0')
  self.assertEqual(row['3連単_2-1-3'],'11.4');self.assertEqual(row['3連単_6-5-4'],'768.7')
  self.assertEqual(row['取得日時'],'2026-11-04T08:50:00+09:00')
 def test_wrong_race_date_venue_partial_matrix_or_missing_clock_rejected(self):
  for code in ('202611041001','202611042002','202611031002','202511041002'):
   self.assertIsNone(parse_odds(self.doc,code,NOW))
  self.assertIsNone(parse_odds(self.doc.replace('>7.8<','>欠場<'),CODE,NOW))
  self.assertIsNone(parse_odds(self.doc.replace('オッズ更新時間','未確認'),CODE,NOW))
  self.assertIsNone(parse_odds(self.doc,CODE,NOW-dt.timedelta(minutes=3)))
 def test_repeated_download_does_not_fabricate_new_official_quote_time(self):
  row=parse_odds(self.doc,CODE,NOW+dt.timedelta(minutes=15))
  self.assertEqual(row['取得日時'],'2026-11-04T08:50:00+09:00')
 def test_reprice_uses_new_market_features_and_preserves_context_and_model(self):
  quotes=parse_odds(self.doc,CODE,NOW);fs=[{'ability':{'全国勝率':4+i},'market_detail':{'市場1着周辺確率':.99}} for i in range(6)]
  s={'id':'base','created_at':'2026-11-04T08:30:00+09:00','cutoff':'2026-11-04T09:15:00+09:00','model_id':'fixed','complete_inputs':False,'input_snapshot':{'features':fs,'previews':{}},'research':{}}
  model={'model_id':'fixed','trained_through':'2026-11-02'}
  outputs={'phase':'preview','probabilities':{k[4:]:1/120 for k in quotes if k.startswith('3連単_')},'selection':{},'complete_inputs':True,'feature_usage':{}}
  before=copy.deepcopy(s)
  with patch('boat24_live.predict',return_value=outputs):
   r=reprice(s,quotes,model,CODE,NOW)
   self.assertIsNotNone(r);self.assertEqual(s,before)
   self.assertNotEqual(r['input_snapshot']['features'][0]['market_detail']['市場1着周辺確率'],.99)
   self.assertEqual(r['context_snapshot_at'],s['created_at']);self.assertEqual(r['input_snapshot']['captured_at'],NOW.isoformat());self.assertFalse(r['complete_inputs'])
   self.assertIsNone(reprice(s,quotes,{**model,'model_id':'other'},CODE,NOW))
   self.assertIsNone(reprice(s,quotes,model,CODE,NOW+dt.timedelta(minutes=6)))
   self.assertIsNone(reprice(s,quotes,model,CODE,NOW,clock=lambda:NOW.replace(hour=9,minute=14)))
 def test_weather_and_missing_inputs_cannot_be_invented_in_commentary(self):
  fs=[{'ability':{'全国勝率':4+i}} for i in range(6)]
  s={'id':'a','phase':'initial','created_at':NOW.isoformat(),'probabilities':{'1-2-3':1},'input_snapshot':{'features':fs},'purchase_plan':{'status':'odds_stale'}}
  c=build(s);self.assertIn('未取得',c['water']);self.assertIn('展示前',c['axis']);self.assertIn('インを確保',c['deployment']);self.assertNotIn('無風。',c['water'])
  self.assertIn('映像',c['notice']);self.assertEqual(len(c['boats']),6)
  s['input_snapshot']['features'][0].update(weather={'風速(m)':6,'波の高さ(cm)':8},start_detail={'展示F':1})
  s['input_snapshot']['previews']={'weather':{'取得日時':'2026-11-04T08:00:00+09:00'}}
  c=build(s);self.assertIn('風速6m',c['water']);self.assertIn('51分経過',c['water']);self.assertTrue(any('正常ST' in x for x in c['risks']))

if __name__=='__main__':unittest.main()
