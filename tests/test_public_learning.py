import copy,datetime as dt,json,tempfile,unittest
from pathlib import Path
from test_frozen_decisions import snapshot,observe,AT,CUT,CODE,plan
from boat24_decisions import attach_arms
from boat24_learning import frozen_cases,training_result
from boat24_portfolio_validation import paired_frozen_report
from boat24_replay import load_observations

def fixture():
    s=snapshot();_,_,quotes=plan();attach_arms(s,quotes,True)
    s['input_snapshot']={'features':[{} for _ in range(6)],'source_times':{'odds':AT.isoformat()},'captured_at':AT.isoformat(),'card':{f'艇{i}_登録番号':str(4000+i) for i in range(1,7)}}
    r={'race_code':CODE,'date':AT.date().isoformat(),'venue':19,'revisions':{s['id']:s}}
    doc=observe({},r,AT+dt.timedelta(seconds=10));doc=observe(doc,r,CUT)
    r['result']={'id':'result1','combo':'1-2-3','payout_100yen':1000,'winning_trifectas':{'1-2-3':1000},'refund_verified':True,'refund_boats':[],
                 'result_source':{'レースコード':CODE,**{f'{i}着_艇番':str(i) for i in range(1,7)}}}
    return r,doc

class PublicLearning(unittest.TestCase):
    def test_fixed_snapshot_not_newer_unpublished_snapshot_is_replayed(self):
        r,d=fixture();s=copy.deepcopy(r['revisions']['buy']);s.update(id='late',created_at=(AT+dt.timedelta(minutes=1)).isoformat());s['input_snapshot']['captured_at']=s['created_at'];r['revisions']['late']=s
        original=copy.deepcopy(r)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'full_history';p.mkdir();(p/(r['date']+'.json')).write_text(json.dumps({'records':{CODE:r}}));(root/'boat24_decisions.json').write_text(json.dumps(d))
            selected,diag=load_observations(AT.date()+dt.timedelta(days=1),directory=p)
        self.assertEqual(selected[(CODE,'preview')]['id'],'buy');self.assertEqual(diag['public_frozen'],1);self.assertEqual(r,original)

    def test_missing_public_receipt_never_falls_back_after_protocol_start(self):
        r,d=fixture();d['records'][CODE]['decision']['receipt']['proof']={}
        cases,a=frozen_cases([r],d);self.assertFalse(cases);self.assertEqual(a['excluded']['publication_proof_missing'],1)
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);p=root/'full_history';p.mkdir();(p/(r['date']+'.json')).write_text(json.dumps({'records':{CODE:r}}));(root/'boat24_decisions.json').write_text(json.dumps(d))
            selected,diag=load_observations(AT.date()+dt.timedelta(days=1),directory=p)
        self.assertFalse(selected)

    def test_correction_changes_case_id_not_frozen_inputs(self):
        r,d=fixture();old=frozen_cases([r],d)[0][0];r['result'].update(id='correction',payout_100yen=900,winning_trifectas={'1-2-3':900});new=frozen_cases([r],d)[0][0]
        self.assertNotEqual(old['provenance']['case_id'],new['provenance']['case_id']);self.assertEqual(old['provenance']['input_digest'],new['provenance']['input_digest'])

    def test_six_finishes_can_arrive_without_daily_csv(self):
        r,d=fixture();case=frozen_cases([r],d)[0][0];self.assertEqual(training_result(case)['6着_艇番'],'6')
        for i in (4,5,6):case['result']['result_source'].pop(f'{i}着_艇番')
        self.assertIsNone(training_result(case));bad={'レースコード':CODE,**{f'{i}着_艇番':str(7-i) for i in range(1,7)}};self.assertIsNone(training_result(case,bad))

    def test_current_variable_stakes_not_twelve_equal_tickets_are_scored(self):
        r,d=fixture();z=paired_frozen_report([r,r],d)['phase_reports'][1]
        self.assertEqual(z['races'],1);self.assertEqual(z['models']['candidate']['purchases'],1)
        expected=sum(t['stake'] for t in d['records'][CODE]['decision']['paired']['arms']['candidate']['plan']['tickets'])
        self.assertEqual(z['models']['candidate']['stake'],expected);self.assertNotEqual(expected,1200)
        self.assertFalse(z['adoption_approved']);self.assertFalse(z['checks']['purchases'])

    def test_after_result_arm_change_is_excluded(self):
        r,d=fixture();r['revisions']['buy']['research']['decision_arms']['arms']['candidate']['plan']['budget']+=100
        z=paired_frozen_report([r],d);self.assertEqual(z['comparison_exclusions']['arms_missing_or_not_frozen'],1)

    def test_refund_unverified_and_future_input_excluded(self):
        r,d=fixture();r['result']['refund_verified']=False;self.assertFalse(frozen_cases([r],d)[0])
        r,d=fixture();r['revisions']['buy']['input_snapshot']['source_times']['odds']=CUT.isoformat();self.assertEqual(frozen_cases([r],d)[1]['excluded']['input_time_unverified'],1)

    def test_historical_twelve_point_comparison_cannot_promote(self):
        from boat24_experiments import prior_forward_evidence
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);z=prior_forward_evidence(AT.date()+dt.timedelta(days=1),directory=p)
        self.assertEqual(z['policy'],'public-frozen-learning-1');self.assertFalse(any(x['adoption_approved'] for x in z['phase_reports']))

    def test_real_official_fixture_preserves_all_six_places(self):
        from boat24_official_results import parse_result
        raw=Path('tests/fixtures/official_shimonoseki4.html').read_text();r=parse_result(raw,'202611041904',CUT.isoformat(),'official')
        self.assertEqual(r['result']['4着_艇番'],'4')
        self.assertEqual(r['result']['official_finish_status'],{'6':'落','2':'妨'})
        self.assertNotIn('5着_艇番',r['result']) # Actual fixture has 落/妨, never invent ranks.
        import re
        normal=re.sub(r'(>\s*)落(\s*<)',r'\g<1>５\g<2>',raw);normal=re.sub(r'(>\s*)妨(\s*<)',r'\g<1>６\g<2>',normal)
        r=parse_result(normal,'202611041904',CUT.isoformat(),'official')
        self.assertEqual(sorted(r['result'][f'{i}着_艇番'] for i in range(1,7)),list('123456'))

    def test_new_lower_place_labels_update_existing_settlement(self):
        from boat24_settlement import settle_record
        r,d=fixture();s=r['revisions']['buy'];res=r['result']['result_source'];pay={'レースコード':CODE,'3連単_組番':'1-2-3','3連単_払戻金':'1000'};r['result']=None
        short={k:v for k,v in res.items() if k not in ('4着_艇番','5着_艇番','6着_艇番')};settle_record(r,short,pay,s,CUT);old=r['result']['id']
        self.assertTrue(settle_record(r,res,pay,s,CUT));self.assertNotEqual(old,r['result']['id']);self.assertIn(old,r['result_history'])

class LearningContinuity(unittest.TestCase):
    def test_public_replay_preserves_prior_race_features(self):
        from boat24_replay import restore_snapshot
        r,d=fixture();s=r['revisions']['buy'];s['input_snapshot']['features'][0]['series_detail']={'前走着順':2,'当日既走数':1}
        case=frozen_cases([r],d)[0][0];saved=case['snapshot'];saved['_learning_case']={k:v for k,v in case.items() if k!='snapshot'}
        out=restore_snapshot(saved,CODE,saved['input_snapshot']['card'])
        self.assertEqual(out['features'],s['input_snapshot']['features'])

    def test_real_training_loop_consumes_fixed_card_and_labels_without_csv(self):
        from unittest.mock import patch,MagicMock
        import boat24_train_context as train
        r,d=fixture();case=frozen_cases([r],d)[0][0];s=case['snapshot'];s['_learning_case']={k:v for k,v in case.items() if k!='snapshot'}
        old=copy.deepcopy(s['input_snapshot']['features']);data={'cards':{},'results':{},'motor_rows':[],'weather':{},'ex':{},'st':{},'original':{}}
        built={'features':copy.deepcopy(old),'previews':{'odds':{}},'cutoff':CUT,'asof':AT};surface=MagicMock()
        with patch('boat24_replay.load_observations',return_value=({(CODE,'preview'):s},{'protocol_started_at':AT.isoformat()})),patch.object(train,'load_registry',return_value={}),patch.object(train,'load_tide_book',return_value=({},{})),patch.object(train,'fetch',return_value=[]),patch.object(train,'calendar_and_history',return_value=({},{})),patch.object(train,'collect_day',return_value=data),patch.object(train,'profiles_and_runs',return_value=([],[])),patch.object(train,'race_features',side_effect=lambda *a,**k:copy.deepcopy(built)),patch.object(train,'CourseStats'),patch.object(train,'BehaviorStats'),patch.object(train,'SurfaceStats',return_value=surface),patch('boat24_tactics.Tactics'):
            with self.assertRaisesRegex(RuntimeError,'Insufficient historical samples'):train.build_model(AT.date()+dt.timedelta(days=1),days=1)
        surface.add.assert_called_once();self.assertEqual(surface.add.call_args.args[2],{str(i):i for i in range(1,7)});self.assertEqual(data['cards'][CODE],s['input_snapshot']['card'])

class LabelIntegrity(unittest.TestCase):
    def test_nonfinish_is_not_replaced_by_six_numeric_csv_ranks(self):
        r,d=fixture();case=frozen_cases([r],d)[0][0];case['result']['result_source']['official_finish_status']={'6':'落'}
        self.assertIsNone(training_result(case,case['result']['result_source']))
