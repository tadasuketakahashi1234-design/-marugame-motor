import copy
import datetime as dt
import itertools
import json
from pathlib import Path
import unittest
import os
import subprocess
import tempfile
from unittest.mock import patch
from boat24_integrity import JST
from boat24_quality import prepare,wilson
from boat24_reasoning import build,components,start_duel
from boat24_risk import robust_plan,validate_robust,POLICY,PROTOCOL_ID
from boat24_methods import normalize_method
from boat24_fast_context import refresh,collect
from boat24_course import CourseStats,empty
from boat24_tactics import Tactics,method_reference
from boat24_quote_context import newest_context,reject_obsolete_reprices
from boat24_full_update import latest
from boat24_offers import register_offers,report

CODE='202611041901'
NOW=dt.datetime(2026,11,4,17,38,tzinfo=JST)
def saved():return json.loads(Path('tests/fixtures/shimonoseki1_saved_preview.json').read_text())['snapshot']
def result_row(method):
    row={'取得日時':'2026-11-03T17:00:00+09:00','決まり手':method}
    for i in range(1,7):row.update({f'{i}コース_艇番':str(i),f'{i}着_艇番':str(i),f'{i}コース_スタートタイミング':'.15'})
    return row

class PriorityReasoningTests(unittest.TestCase):
    def test_fresh_http_download_does_not_revive_old_water(self):
        s=saved();fs=copy.deepcopy(s['input_snapshot']['features']);before=copy.deepcopy(s['input_snapshot']['previews'])
        before['weather']['取得日時']=NOW.isoformat()
        q=prepare(fs,before,NOW)
        self.assertEqual(q['weather']['state'],'stale');self.assertTrue(all(not f['weather'] and not f['wind'] for f in fs))
        self.assertEqual(before['weather']['気象観測時刻'],'2026-11-04T16:30:00+09:00')
    def test_unknown_future_and_boundary_observation_times(self):
        for offset,state in [(None,'observation_time_unknown'),(-1,'future_observation'),(600,'fresh'),(601,'stale')]:
            s=saved();p=s['input_snapshot']['previews'];p['weather'].pop('気象観測時刻',None)
            if offset is not None:p['weather']['気象観測時刻']=(NOW-dt.timedelta(seconds=offset)).isoformat()
            self.assertEqual(prepare(s['input_snapshot']['features'],p,NOW)['weather']['state'],state)
    def test_legacy_method_zero_is_not_used_as_a_known_rate(self):
        s=saved();fs=s['input_snapshot']['features'];self.assertIn('逃げ勝ち率',fs[0]['style'])
        q=prepare(fs,s['input_snapshot']['previews'],NOW)
        self.assertNotIn('逃げ勝ち率',fs[0]['style']);self.assertEqual(q['method_label_unverified_lanes'],list(range(1,7)))
        self.assertNotIn('2コースイン逃げ許容率',fs[1]['tactical_detail'])
    def test_method_spaces_and_missing_denominators(self):
        self.assertEqual(normalize_method('逃　げ '),'逃げ');self.assertEqual(normalize_method('まくり 差し'),'まくり差し');self.assertIsNone(normalize_method('不明'))
        stats=CourseStats();card={f'艇{i}_登録番号':str(4000+i) for i in range(1,7)}
        for n,label in enumerate(('不明','逃　げ')):
            stats.add({'cards':{f'20261103190{n+1}':card},'results':{f'20261103190{n+1}':result_row(label)}})
        a=stats.state['racer']['4001-1'];self.assertEqual(a['n'],2);self.assertEqual(a['method_n'],1)
        f,style=stats.features('4001',19,1);self.assertEqual(f['決まり手確認走数'],1);self.assertNotIn('逃げ勝ち率',style)
        old=CourseStats({'racer':{'4001-1':{**empty(),'n':2}},'venue':{'19-1':{**empty(),'n':2}}})
        self.assertNotIn('逃げ勝ち率',old.features('4001',19,1)[1])
    def test_tactical_unknown_is_not_zero_escaped(self):
        card={f'艇{i}_登録番号':str(4000+i) for i in range(1,7)};t=Tactics()
        for n,label in enumerate(('不明','逃 げ')):t.add({'cards':{f'20261103190{n+1}':card},'results':{f'20261103190{n+1}':result_row(label)}})
        fs=[{'start':{'展示進入':i}} for i in range(1,7)];t.attach(fs,card,19,'2026-11-04')
        self.assertEqual(fs[1]['tactical_detail']['実進入確認走数'],2);self.assertEqual(fs[1]['tactical_detail']['決まり手確認走数'],1)
        self.assertNotIn('2コースイン逃げ許容率',fs[1]['tactical_detail'])
    def test_small_course_support_has_wide_historical_interval(self):
        lo,hi=wilson(4,5);self.assertLess(lo,.4);self.assertGreater(hi,.95);self.assertIsNone(wilson(0,0))
    def test_start_comparison_requires_real_sample_and_variance_support(self):
        a={'behavior':{'選手ST標本数':20,'予測本番ST':.1,'ST差標準偏差':.03}}
        b={'behavior':{'選手ST標本数':20,'予測本番ST':.2,'ST差標準偏差':.03}}
        self.assertGreater(start_duel(a,b)['earlier_probability'],.98)
        a['behavior']['選手ST標本数']=3;self.assertNotIn('earlier_probability',start_duel(a,b))
        a['behavior'].update(選手ST標本数=20,ST差標準偏差=0);self.assertEqual(start_duel(a,b)['status'],'distribution_unverified')
    def test_joint_method_reference_maps_courses_to_current_boats_and_rejects_future(self):
        t=Tactics();card={f'艇{i}_登録番号':str(4000+i) for i in range(1,7)}
        for day in (1,2,3):
            for race in range(1,13):
                code=f'202611{day:02d}19{race:02d}';row=result_row('逃　げ');row['取得日時']=f'2026-11-{day:02d}T17:00:00+09:00'
                t.add({'cards':{code:card},'results':{code:row}})
        ref=method_reference(t.state,19,[1,2,4,5,6,3],1,'2026-11-04')
        self.assertEqual(ref['known'],36);self.assertEqual(ref['methods'][0]['pairs'][0]['combo'],'1-2-4')
        self.assertEqual(ref['methods'][0]['pairs'][0]['rate'],1)
        self.assertEqual(method_reference(t.state,19,[1,2,4,5,6,3],1,'2026-11-03')['status'],'future_history_rejected')
        fs=[{'start':{'展示進入':c}} for c in (1,2,6,3,4,5)];t.attach(fs,card,19,'2026-11-04')
        self.assertEqual(fs[0]['tactical_detail']['同場同コース逃げ勝利時_2-3_連動率'],1)
    def test_refund_races_do_not_become_method_training_examples(self):
        t=Tactics();card={f'艇{i}_登録番号':str(4000+i) for i in range(1,7)};row=result_row('逃げ');row['6コース_F']='1'
        t.add({'cards':{'202611031901':card},'results':{'202611031901':row}})
        self.assertFalse(t.state.get('joint_methods'))
    def test_real_market_flip_is_reconstructed_after_inverse_calibration(self):
        s=saved();before=copy.deepcopy(s);c=components(s)
        self.assertGreater(c['context'][3]['first'],c['context'][0]['first'])
        self.assertGreater(c['final'][0]['first'],c['final'][3]['first'])
        self.assertAlmostEqual(c['context'][0]['first'],.306960,places=5);self.assertEqual(s,before)
    def test_opponents_are_conditioned_on_winner_and_fast_boats_are_explained(self):
        r=build(saved());self.assertEqual(r['observed_entry'],[1,2,4,5,6,3]);self.assertEqual(r['axis'],1);self.assertEqual(r['place_axis'],4)
        self.assertAlmostEqual(sum(x['second'] for x in r['axis_opponents']),1);self.assertAlmostEqual(sum(x['third'] for x in r['axis_opponents']),1)
        self.assertIn(5,[b['winner'] for b in r['branches']]);self.assertIn(6,[b['winner'] for b in r['branches']])
        four=next(b for b in r['branches'] if b['winner']==4);self.assertEqual(four['course'],3)
        self.assertTrue(any('展示F' in x for x in four['counter_evidence']));self.assertIsNone(four['method_probability'])
        self.assertTrue(all(c['combo'].startswith('4-') for c in four['combos']))
    def test_fast_context_restores_observed_sixth_course_without_touching_history(self):
        s=saved();original=copy.deepcopy(s);p=copy.deepcopy(s['input_snapshot']['previews'])
        for f in s['input_snapshot']['features']:
            f['start']={};f['exhibition']={};f['entry_detail']={}
        for kind in ('ex','st'):s['input_snapshot']['previews'][kind]={}
        before=copy.deepcopy(s);out=refresh(s,{'previews':{'ex':p['ex'],'st':p['st']}},{},CODE,NOW)
        self.assertEqual(out['input_snapshot']['features'][2]['start']['展示進入'],6)
        self.assertEqual(out['input_snapshot']['features'][3]['start']['展示進入'],3)
        self.assertEqual(s,before);self.assertEqual(out['context_snapshot_at'],NOW.isoformat())
        self.assertEqual(original['input_snapshot']['features'][2]['entry_detail']['展示コース'],6)
    def test_wrong_race_or_future_foot_times_are_rejected(self):
        s=saved();row={**s['input_snapshot']['previews']['original'],'レースコード':'202611041902','取得日時':NOW.isoformat(),'計測項目1':'直線','艇1_値1':'6.0'}
        out=refresh(s,{'original':row},{},CODE,NOW);self.assertEqual(out,s)
        row['レースコード']=CODE;row['取得日時']=(NOW+dt.timedelta(seconds=1)).isoformat()
        self.assertEqual(refresh(s,{'original':row},{},CODE,NOW),s)
    def test_inflight_weather_only_update_cannot_displace_full_exhibition(self):
        fresh=saved();fresh['evaluation_eligible']=True
        weak=copy.deepcopy(fresh);weak.update(id='weak',phase='partial',created_at=NOW.isoformat(),context_snapshot_at=NOW.isoformat(),refresh_kind='official_context_and_odds')
        rec={'revisions':{fresh['id']:fresh,'weak':weak}}
        self.assertEqual(newest_context(rec)['id'],fresh['id']);self.assertEqual(latest(rec)['id'],fresh['id'])
        out=reject_obsolete_reprices({'records':{CODE:{'revisions':{fresh['id']:fresh}}}},{'records':{CODE:{'revisions':{'weak':weak}}}})
        self.assertNotIn('weak',out['records'][CODE]['revisions'])
    def test_full_search_frontier_stays_in_archive_not_initial_view(self):
        from boat24_history_io import compact_day
        s=saved();s['evaluation_eligible']=True;s['purchase_plan']['frontier']=[{'large':'search'}]
        r={'race_code':CODE,'revisions':{s['id']:s}};original=copy.deepcopy(r)
        v=compact_day({'records':{CODE:r}})['records'][CODE]
        self.assertNotIn('frontier',v['revisions'][s['id']]['purchase_plan']);self.assertEqual(r,original)
    def test_live_process_spans_workflow_steps_and_stops_without_deleting_observations(self):
        from boat24_live import start_workflow_worker,stop_workflow_worker
        cwd=Path.cwd()
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            def git(*args):subprocess.run(['git',*args],cwd=root,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            git('init');git('config','user.name','test');git('config','user.email','test@example.com')
            (root/'boat24_live.py').write_text("import sys,time\nfrom pathlib import Path\nwhile not Path(sys.argv[2]).exists():time.sleep(.02)\nPath('retained-observation').write_text('saved')\n")
            git('add','.');git('commit','-m','fixture')
            try:
                os.chdir(root);start_workflow_worker();pid=int((root/'.boat24-live-pid').read_text());stop_workflow_worker()
                try:os.waitpid(pid,0)
                except ChildProcessError:pass
                self.assertTrue((root/'boat24-live-worker/retained-observation').exists())
            finally:os.chdir(cwd)

class RobustAllocationTests(unittest.TestCase):
    def setUp(self):
        self.codes=['-'.join(c) for c in itertools.permutations('123456',3)]
        self.p={c:0. for c in self.codes};self.odds={c:1. for c in self.codes}
        for c in self.codes[:4]:self.p[c]=.25;self.odds[c]=10.
    def test_positive_stress_plan_has_variable_budget_and_limited_concentration(self):
        p=robust_plan(self.p,self.odds)
        self.assertEqual(p['status'],'ready');self.assertTrue(validate_robust(p));self.assertEqual(p['budget'],400)
        self.assertTrue(all(t['stake']<=p['budget']*.25 for t in p['tickets']))
        self.assertTrue(all(t['stress_return']>p['budget'] for t in p['tickets']));self.assertAlmostEqual(p['stress_expected_roi'],1.8)
        self.assertAlmostEqual(p['estimated_roi'],2.5)
    def test_missing_exhibition_waits_and_stress_failure_is_a_price_decision(self):
        self.assertEqual(robust_plan(self.p,self.odds,inputs_ready=False)['status'],'preview_pending')
        for c in self.codes[:4]:self.odds[c]=5.
        self.assertEqual(robust_plan(self.p,self.odds)['status'],'risk_no_positive_value')
    def test_one_longshot_cannot_take_over_the_stake(self):
        self.p={c:0. for c in self.codes};self.p[self.codes[0]]=1.;self.odds[self.codes[0]]=100.
        self.assertNotEqual(robust_plan(self.p,self.odds)['status'],'ready')
        s=saved();odds={c:float(s['input_snapshot']['previews']['odds']['3連単_'+c]) for c in self.codes}
        p=robust_plan(s['probabilities'],odds)
        if p['status']=='ready':self.assertTrue(validate_robust(p));self.assertLessEqual(max(t['stake'] for t in p['tickets']),p['budget']*.25)
    def test_nominal_probability_integrity_is_not_lost_by_haircut(self):
        p=dict(self.p);p[self.codes[0]]=.2;self.assertEqual(robust_plan(p,self.odds)['status'],'probabilities_invalid')
    def test_price_explanations_recompute_the_same_stress_units(self):
        s=saved();s['purchase_plan']=robust_plan(s['probabilities'],{c:float(s['input_snapshot']['previews']['odds']['3連単_'+c]) for c in s['probabilities']})
        rows=build(s)['price_audit'];self.assertTrue(rows)
        self.assertTrue(all(r['stress_unit_expected_roi']<=r['unit_expected_roi'] for r in rows))
        self.assertEqual({r['combo'].split('-')[0] for r in rows},set('123456'))
    def test_save_gate_recomputes_stress_and_rejects_tampering(self):
        p=robust_plan(self.p,self.odds);p.update(odds_observed_at=NOW.isoformat())
        s={'id':'new','created_at':NOW.isoformat(),'computed_at':NOW.isoformat(),'cutoff':(NOW+dt.timedelta(minutes=10)).isoformat(),'evaluation_eligible':True,'purchase_plan':p}
        self.assertEqual(len(register_offers({'revisions':{'new':s}})),1)
        bad=copy.deepcopy(s);bad['purchase_plan']['stress_expected_roi']=999
        self.assertEqual(register_offers({'revisions':{'new':bad}}),[])
        bad=copy.deepcopy(p);bad['risk_controls']['maximum_ticket_share']=.8;self.assertFalse(validate_robust(bad))
    def test_comparison_uses_first_offer_per_protocol_without_best_result_selection(self):
        def offer(sid,protocol,at):return {'snapshot_id':sid,'created_at':at,'protocol_id':protocol,'policy':'balanced-no-gami-v2','model':'m','model_id':'m','phase':'preview'}
        rec={'offers':{'old':offer('old','old','1'),'new':offer('new',PROTOCOL_ID,'2'),'later':offer('later',PROTOCOL_ID,'3')},'result':{'offer_settlements':{'old':{'hit':False,'stake':100,'return':0},'new':{'hit':False,'stake':400,'return':0},'later':{'hit':True,'stake':400,'return':10000}}}}
        rows=report([rec])['protocol_comparison_rows'];new=next(r for r in rows if r['protocol_id']==PROTOCOL_ID)
        self.assertEqual(new['races'],1);self.assertEqual(new['return'],0)

if __name__=='__main__':unittest.main()
