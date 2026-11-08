"""A complete race with real parsers: acquisition through next-day learning."""
import copy,datetime as dt,gzip,hashlib,json,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
from boat24_integrity import JST
from boat24_fast_context import collect,refresh
from boat24_odds import parse_odds
from boat24_live import reprice
from boat24_history_io import write_history,write_view,read_history
from boat24_decisions import update,report
from boat24_full_update import settle
from boat24_replay import load_observations,restore_snapshot
from boat24_water import SurfaceStats
AT=dt.datetime(2026,11,4,9,10,10,tzinfo=JST);CODE='202611041002';CUT=AT.replace(minute=15,second=0);FREEZE=CUT-dt.timedelta(minutes=2)
def fixture(blank=False):
 card={f'艇{i}_登録番号':str(4000+i) for i in range(1,7)}
 header='<a href="?hd=20261104"></a><li class="is-active2">11月4日</li><tr><td>締切予定時刻</td>'+''.join('<td class="'+('is-activeColor1' if i==2 else '')+'">09:15</td>' for i in range(1,13))+'</tr>'
 bodies=''.join(f'<tbody><tr><td class="is-boatColor{i}">{i}</td><td><a href="?toban={4000+i}"></a></td><td>選手</td><td>52.0kg</td><td>'+('' if blank else str(6.6+i*.01))+'</td><td>-0.5</td><td></td><td></td></tr><tr></tr><tr><td>0.5</td></tr></tbody>' for i in range(1,7))
 st=''.join(f'<div class="table1_boatImage1"><span class="table1_boatImage1Number is-type{i}">{i}</span><span class="table1_boatImage1Time">.12</span></div>' for i in range(1,7))
 return card,header+bodies+st
class PipelineEndToEnd(unittest.TestCase):
 def base(self):
  card,_=fixture();return {'id':'initial','model_id':'fixture','model':'fixture-model','phase':'initial','created_at':AT.replace(hour=8,minute=40).isoformat(),'cutoff':CUT.isoformat(),'evaluation_eligible':True,'input_snapshot':{'card':card,'features':[{'ability':{'全国勝率':4+i}} for i in range(6)],'previews':{}},'research':{}}
 def acquire(self,base,blank=False):
  _,html=fixture(blank)
  class Clock(dt.datetime):
   @classmethod
   def now(cls,tz=None):return AT
  def download(url,*args):
   if 'beforeinfo' in url:return html
   if 'bc_sui' in url:return '0910\t1\t2\t北\t3\t15\t20'
   return 'レースコード,取得日時\n'
  with patch('boat24_fast_context.download',side_effect=download),patch('boat24_fast_context.dt',types.SimpleNamespace(datetime=Clock)):
   rows,errors=collect([(CODE,base)],AT)
  self.assertFalse(errors);return rows[CODE]
 def test_complete_race_public_freeze_settlement_and_next_day_surface_learning(self):
  base=self.base();original=copy.deepcopy(base);bundle=self.acquire(base);self.assertEqual(bundle['source_checks']['before']['state'],'parsed');self.assertTrue(bundle['source_checks']['before']['entry_parsed'])
  model={'model_id':'fixture','trained_through':'2026-11-03','samples':[],'market_alpha':0}
  contextual=refresh(base,bundle,model,CODE,AT)
  html=Path('tests/fixtures/official_odds_mikuni.html').read_text().replace('8:50','9:10');quote=parse_odds(html,CODE,AT);self.assertIsNotNone(quote)
  s=reprice(contextual,quote,model,CODE,AT+dt.timedelta(seconds=1));self.assertIsNotNone(s);self.assertEqual(s['phase'],'preview');self.assertTrue(s['input_quality']['purchase_inputs_ready']);self.assertEqual(base,original)
  self.assertEqual(s['purchase_plan']['status'],'ready');self.assertFalse(s['probability_verified'])
  rec={'race_code':CODE,'date':'2026-11-04','venue':10,'race':2,'revisions':{'initial':base,s['id']:s}}
  catalog={CODE:{'race_code':CODE,'venue':10,'race':2,'cutoff':CUT.isoformat(),'state':'saved'}}
  with tempfile.TemporaryDirectory() as tmp:
   history=Path(tmp)/'full_history';history.mkdir();path=history/'2026-11-04.json';day={'date':'2026-11-04','records':{CODE:rec},'catalog':catalog}
   path=write_history(path,day);view_path=write_view(path,day);raw=view_path.read_bytes();public=json.loads(raw);self.assertEqual(hashlib.sha256(raw).hexdigest(),json.loads(view_path.with_name('2026-11-04.pointer.json').read_text())['sha256'])
   doc=update({},public,{CODE:rec},(AT+dt.timedelta(seconds=20)).isoformat(),{'sha256':hashlib.sha256(raw).hexdigest(),'source_commit':'a'*40})
   doc=update(doc,{'catalog':catalog},{CODE:rec},FREEZE.isoformat(),{});frozen=copy.deepcopy(doc['records'][CODE]['decision']);self.assertEqual(frozen['state'],'buy');self.assertEqual(frozen['snapshot_id'],s['id'])
   combo=s['purchase_plan']['tickets'][0]['combo'];res={'レースコード':CODE,'official_refund_verified':True,'official_refund_boats':[],**{f'{i}着_艇番':boat for i,boat in enumerate(combo.split('-'),1)}};pay={'レースコード':CODE,'3連単_組番':combo,'3連単_払戻金':'9000'}
   self.assertTrue(settle(rec,res,pay,CUT+dt.timedelta(minutes=5)));doc=update(doc,{'catalog':catalog},{CODE:rec},(CUT+dt.timedelta(minutes=5)).isoformat(),{});self.assertEqual(doc['records'][CODE]['decision'],frozen);self.assertTrue(doc['records'][CODE]['settlement']['actual_rule']['hit']);self.assertEqual(report(doc)['model_rows'][0]['races'],1)
   day['records'][CODE]=rec;write_history(path,day);before=copy.deepcopy(rec['revisions']);observed,diag=load_observations(AT.date()+dt.timedelta(days=1),directory=history);self.assertEqual(diag['races'],1)
   replay=restore_snapshot(observed[(CODE,'preview')],CODE,base['input_snapshot']['card']);self.assertEqual(replay['features'][0]['weather']['風速(m)'],3)
   surface=SurfaceStats();surface.add(10,replay['features'],{str(i):i for i in range(1,7)},AT.date().isoformat());self.assertTrue(surface.state['wind']);self.assertEqual(rec['revisions'],before);self.assertEqual(read_history(path)['records'][CODE]['revisions'],before)
 def test_verified_page_without_exhibition_is_not_reported_as_source_publication_fact(self):
  base=self.base();bundle=self.acquire(base,blank=True);check=bundle['source_checks']['before'];self.assertEqual(check['state'],'verified_page_preview_incomplete');self.assertFalse(check['exhibition_parsed']);self.assertNotIn('published_at',check)
 def test_stale_source_and_freeze_overrun_rejections_have_explicit_reasons(self):
  base=self.base();base['model_id']='m';q=parse_odds(Path('tests/fixtures/official_odds_mikuni.html').read_text(),CODE,AT);diagnostic={}
  self.assertIsNone(reprice(base,q,{'model_id':'m','trained_through':'2026-11-03'},CODE,AT,diagnostics=diagnostic));self.assertEqual(diagnostic['rejection'],'source_quote_stale_or_unclocked')
 def test_transport_failure_stays_unconfirmed_without_fabricating_unpublished_state(self):
  base=self.base()
  with patch('boat24_fast_context.download',side_effect=TimeoutError('timeout')):rows,errors=collect([(CODE,base)],AT)
  self.assertIn('before_'+CODE,errors);self.assertEqual(rows[CODE]['source_checks']['before']['state'],'unconfirmed');self.assertNotIn('previews',rows[CODE])
 def test_preview_diagnostics_pinpoint_missing_lane_without_approving_purchase(self):
  from boat24_quality import prepare
  features=[{'start':{'展示進入':i,'展示ST符号付':.12},'exhibition':{'展示タイム相対':0.01}} for i in range(1,7)]
  features[2]['exhibition'].pop('展示タイム相対')
  features[4]['start'].pop('展示ST符号付')
  result=prepare(features,{},AT)
  self.assertFalse(result['purchase_inputs_ready'])
  self.assertEqual(result['missing_preview_lanes']['entry'],[])
  self.assertEqual(result['missing_preview_lanes']['exhibition'],[3])
  self.assertEqual(result['missing_preview_lanes']['start'],[5])
  features[2]['exhibition']['展示タイム相対']=0.01
  features[4]['start']['展示ST符号付']=.12
  self.assertTrue(prepare(features,{},AT)['purchase_inputs_ready'])
 def test_duplicate_entry_courses_fail_closed(self):
  from boat24_quality import prepare
  features=[{'start':{'展示進入':i,'展示ST符号付':.12},'exhibition':{'展示タイム相対':0.01}} for i in range(1,7)]
  features[5]['start']['展示進入']=1
  result=prepare(features,{},AT)
  self.assertFalse(result['purchase_inputs_ready'])
  self.assertEqual(result['missing_preview_lanes']['entry'],list(range(1,7)))
 def test_malformed_original_exhibition_csv_is_reported(self):
  from boat24_fast_context import collect
  with patch('boat24_fast_context.download',return_value='wrong_column,value\nabc,1\n'):
   rows,errors=collect({},AT)
  self.assertEqual(rows,{})
  self.assertIn('original_today',errors)
  self.assertIn('レースコード',errors['original_today'])
 def test_stage_records_failures_without_turning_them_into_success(self):
  from boat24_pipeline import stage
  trace={}
  with patch('boat24_pipeline.time.perf_counter',side_effect=[10,12.5]):
   with self.assertRaises(ValueError):
    with stage(trace,'acquire'):raise ValueError('parse failed')
  self.assertEqual(trace['stages']['acquire']['state'],'failed');self.assertEqual(trace['stages']['acquire']['seconds'],2.5)
