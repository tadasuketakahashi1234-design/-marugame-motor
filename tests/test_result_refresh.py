import copy,datetime as dt,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from boat24_integrity import JST
from boat24_official_results import collect_results
from boat24_full_update import merge_day,settle
from boat24_validate_saved import validate
NOW=dt.datetime(2026,11,4,20,0,tzinfo=JST)
class ResultRefreshTests(unittest.TestCase):
 def test_actual_shimonoseki4_official_result_and_wrong_race(self):
  from boat24_official_results import parse_result
  doc=Path('tests/fixtures/official_shimonoseki4.html').read_text()
  row=parse_result(doc,'202611041904',NOW.isoformat(),'official')
  self.assertIsNotNone(row);self.assertEqual(row['payout']['3連単_組番'],'1-3-5');self.assertEqual(row['payout']['3連単_払戻金'],'1140');self.assertEqual(row['result']['official_refund_boats'],[])
  self.assertIsNone(parse_result(doc,'202611041905',NOW.isoformat(),'official'))
 def test_due_result_precedes_old_cache_refresh_and_retries_after_one_minute(self):
  code='202611041904';old='202611040101'
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'cache.json';path.write_text(json.dumps({'records':{},'failures':{code:(NOW-dt.timedelta(seconds=70)).isoformat()}}))
   with patch('boat24_official_results.get',return_value='html') as get,patch('boat24_official_results.parse_result',return_value={'observed_at':NOW.isoformat()}):
    rows,errors=collect_results([old,code],NOW,path,limit=1,priority_codes=[code])
   self.assertIn(code,rows);self.assertNotIn(old,rows);self.assertIn('jcd=19&rno=4',get.call_args[0][0])
 def test_result_checks_run_with_no_upcoming_races_or_csv(self):
  from boat24_live import capture
  code='202611041904';s={'id':'s','cutoff':(dt.datetime.now(JST)-dt.timedelta(minutes=20)).isoformat(),'created_at':(dt.datetime.now(JST)-dt.timedelta(minutes=40)).isoformat(),'phase':'preview','evaluation_eligible':True,'input_snapshot':{'features':[{}]*6}}
  ledger={'records':{code:{'revisions':{'s':s}}}}
  with tempfile.TemporaryDirectory() as tmp:
   directory=Path(tmp);path=directory/(dt.datetime.now(JST).date().isoformat()+'.json');path.write_text('{}')
   with patch('boat24_full_update.DIRECTORY',directory),patch('boat24_full_update.INDEX',directory/'index.json'),patch('boat24_full_update.MANIFEST',directory/'manifest.json'),patch('boat24_live.read_history',return_value=ledger),patch('boat24_live.write_history'),patch('boat24_live.write_view'),patch('boat24_live.collect',return_value=({},{})),patch('boat24_fast_context.collect') as context,patch('boat24_official_results.collect_results',return_value=({code:{'result':{},'payout':{}}},{})) as official,patch('boat24_full_update.settle',return_value=True) as settlement,patch('boat24_full_publish.main'):
    self.assertTrue(capture({}));context.assert_not_called();settlement.assert_called_once();self.assertEqual(official.call_args.args[0],[code]);self.assertEqual(ledger['result_health']['settled'],1)
 def test_health_merge_keeps_newer_settlement_clock(self):
  remote={'records':{},'result_health':{'attempt_at':'2026-11-04T20:00:00+09:00'},'settlement_updated_at':'2026-11-04T20:00:00+09:00'}
  local={'records':{},'result_health':{'attempt_at':'2026-11-04T19:00:00+09:00'}}
  merged=merge_day(remote,local);self.assertEqual(merged['result_health'],remote['result_health']);self.assertEqual(merged['settlement_updated_at'],remote['settlement_updated_at'])
 def test_local_integrity_validation_is_independent_of_public_ui_markers(self):
  s={'evaluation_eligible':True,'created_at':'2026-11-04T18:00:00+09:00','cutoff':'2026-11-04T19:03:00+09:00','input_snapshot':{'features':[{}]*6}}
  self.assertEqual(validate({'records':{'a':{'revisions':{'s':s}}}}),1)
  s['created_at']=s['cutoff']
  with self.assertRaises(AssertionError):validate({'records':{'a':{'revisions':{'s':s}}}})
