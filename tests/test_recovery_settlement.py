import copy
import datetime as dt
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from boat24_integrity import JST,result_paper,merge_ledgers
from boat24_official_results import parse_result,merge_cache
from boat24_offers import register_offers,report
PROTOCOL_ID="balanced-no-gami-v2-first-ready-1" # Actual historical protocol, before stress allocation.
from boat24_settlement import settle_record,settle_legacy
from boat24_full_update import merge_day,summary

AT=dt.datetime(2026,11,3,22,tzinfo=JST)
CODE='202611031909'
def snapshot(key='first',at='2026-11-03T21:20:08+09:00',model='a'):
    tickets=[{'combo':'1-2-3','stake':200,'odds':6.6},{'combo':'1-3-4','stake':700,'odds':7.7},{'combo':'1-3-2','stake':200,'odds':7.6},{'combo':'1-4-3','stake':100,'odds':22.3}]
    return {'id':key,'created_at':at,'computed_at':at,'cutoff':'2026-11-03T21:24:00+09:00','evaluation_eligible':True,'model':'context-6','model_id':model,'phase':'preview','selection':{},'purchase_plan':{'policy':'balanced-no-gami-v2','status':'ready','tickets':tickets,'budget':1200,'estimated_roi':1.086,'odds_observed_at':'2026-11-03T21:19:00+09:00','protocol_id':PROTOCOL_ID}}
def sources():
    return {'レースコード':CODE,'1着_艇番':'1','2着_艇番':'3','3着_艇番':'4','official_refund_verified':True,'official_refund_boats':[]},{'レースコード':CODE,'3連単_組番':'1-3-4','3連単_払戻金':'850'}

class RecoveryTests(unittest.TestCase):
    def test_real_absent_boat_explicit_refund_and_identity_guards(self):
        doc=Path('tests/fixtures/official_tsu_refund.html').read_text();r=parse_result(doc,'202611030912',AT.isoformat(),'official')
        self.assertEqual(r['result']['official_refund_boats'],['2']);self.assertEqual(r['payout']['3連単_払戻金'],'780')
        for code in ('202611030911','202611032212','202611020912','202511030912'):
            self.assertIsNone(parse_result(doc,code,AT.isoformat(),'official'))
        self.assertIsNone(parse_result(doc.replace('<th>返還</th>','<th>不明</th>'),'202611030912',AT.isoformat(),'official'))
    def test_absence_refund_and_legacy_upgrade_survive_merge(self):
        import itertools
        picks=['-'.join(c) for c in itertools.permutations('123456',3)]
        winners=[c for c in picks if '2' not in c.split('-')];refundable=[c for c in picks if '2' in c.split('-')]
        rec={'race_code':'202611030912','created_at':'2026-11-03T10:00:00+09:00','selection':{'12':[winners[0]]+winners[1:6]+refundable[:6]},'result':{'combo':winners[0],'payout_100yen':780}}
        before=copy.deepcopy(rec)
        res={'レースコード':rec['race_code'],'1着_艇番':winners[0][0],'2着_艇番':winners[0][2],'3着_艇番':winners[0][4],'official_refund_verified':True,'official_refund_boats':['2']};pay={'レースコード':rec['race_code'],'3連単_組番':winners[0],'3連単_払戻金':'780'}
        self.assertTrue(settle_legacy(rec,res,pay,AT));self.assertEqual(result_paper(rec)['12']['return'],1380)
        self.assertFalse(settle_legacy(rec,res,pay,AT));self.assertEqual(rec['selection'],before['selection'])
        merged=merge_ledgers({'predictions':{rec['race_code']:before}},{'predictions':{rec['race_code']:rec}})
        self.assertEqual(merged['predictions'][rec['race_code']]['result']['paper']['12']['refund'],600)
    def test_first_ready_survives_later_skip_and_many_revisions(self):
        s=snapshot();skip=copy.deepcopy(s);skip.update(id='skip',created_at='2026-11-03T21:21:43+09:00');skip['purchase_plan'].update(status='odds_stale',tickets=[])
        later=snapshot('second','2026-11-03T21:21:00+09:00')
        rec={'race_code':CODE,'venue':19,'revisions':{'first':s,'second':later,'skip':skip}}
        original=copy.deepcopy(rec['revisions']);res,pay=sources()
        self.assertTrue(settle_record(rec,res,pay,skip,AT));self.assertEqual(rec['result']['purchase_snapshot_id'],'first')
        self.assertEqual(rec['result']['paper']['balanced']['return'],5950);self.assertEqual(rec['result']['paper']['balanced']['profit'],4750)
        self.assertEqual(len(rec['result']['offer_settlements']),2);self.assertEqual(summary([rec])['no_gami']['races'],1)
        self.assertFalse(settle_record(rec,res,pay,skip,AT));self.assertEqual(original,rec['revisions'])
        merged=merge_day({'records':{CODE:{'race_code':CODE,'revisions':{'first':s}}}},{'records':{CODE:rec}})
        self.assertEqual(len(merged['records'][CODE]['offers']),2)
        # An outage must not revert official refunds or create another result revision.
        plain={k:v for k,v in res.items() if not k.startswith('official_')}
        self.assertFalse(settle_record(rec,plain,pay,skip,AT))
    def test_ineligible_offers_do_not_enter_report_and_cohorts_are_separate(self):
        for change in ('stale','gami','late','computed_late'):
            s=snapshot()
            if change=='stale':s['purchase_plan']['odds_observed_at']='2026-11-03T21:00:00+09:00'
            if change=='gami':s['purchase_plan']['tickets'][0]['odds']=1.
            if change=='late':s['created_at']='2026-11-03T21:23:00+09:00'
            if change=='computed_late':s['computed_at']='2026-11-03T21:23:00+09:00'
            self.assertEqual(register_offers({'revisions':{'x':s}}),[])
        recs=[]
        for model in ('a','b'):
            s=snapshot(model=model);rec={'race_code':CODE,'revisions':{'first':s}};settle_record(rec,*sources(),s,AT);recs.append(rec)
        rows=report(recs)['rows'];self.assertEqual(len(rows),2);self.assertTrue(all(r['races']==1 for r in rows))
    def test_frozen_model_does_not_wait_for_daily_retraining_or_accept_future_data(self):
        import tempfile
        import os
        from boat24_train_context import ensure_model
        from boat24_context import VERSION
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'model.json.gz'
            from boat24_model_io import write_json
            model={'version':VERSION,'trained_through':'2026-11-01','model_id':'fixed'};write_json(path,model)
            with patch('boat24_train_context.MODEL',path),patch.dict(os.environ,{'BOAT24_FREEZE_MODEL':'1'}),patch('boat24_train_context.build_model') as train:
                self.assertEqual(ensure_model(AT),(model,False));train.assert_not_called()
                model['trained_through']='2026-11-04';write_json(path,model)
                train.return_value={'version':VERSION,'trained_through':'2026-11-02'}
                ensure_model(AT);train.assert_called_once()

    def test_recovery_publishes_small_history_before_official_network(self):
        import tempfile
        import boat24_recover
        events=[]
        with tempfile.TemporaryDirectory() as tmp:
            with patch('boat24_recover.DIRECTORY',Path(tmp)/'full_history'),patch('boat24_recover.day_paths',return_value=[]),patch('boat24_recover.publish',side_effect=lambda *args:events.append('publish')),patch('boat24_recover.collect_results',side_effect=lambda *args,**kwargs:(events.append('official') or ({},{}))):
                boat24_recover.main()
        self.assertEqual(events,['publish','official','publish'])

    def test_past_official_confirmation_is_cached_without_blocking_live_capture(self):
        import tempfile
        from boat24_official_results import collect_results
        code='202611021501';row={'observed_at':(AT-dt.timedelta(hours=8)).isoformat(),'race_code':code}
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'cache.json';path.write_text(json.dumps({'records':{code:row}}))
            with patch('boat24_official_results.get') as fetch:
                rows,_=collect_results([code],AT,path);fetch.assert_not_called();self.assertEqual(rows[code],row)

    def test_official_cache_keeps_newest_verified_observation(self):
        r={'records':{CODE:{'observed_at':'2026-11-03T22:00:00+09:00','result':{'official_refund_boats':['3']}}}}
        l={'records':{CODE:{'observed_at':'2026-11-03T21:00:00+09:00','result':{'official_refund_boats':[]}}}}
        self.assertEqual(merge_cache(r,l)['records'],r['records'])

if __name__=='__main__':unittest.main()
