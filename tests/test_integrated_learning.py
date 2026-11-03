import copy
import datetime as dt
import json
from pathlib import Path
import tempfile
import unittest
from boat24_integrity import JST
from boat24_comments import analyze,parse_pitreport,parse_venue_comments
from boat24_details import attach
from boat24_replay import load_observations,restore_snapshot
from boat24_settlement import amounts,settle_record
from boat24_experiments import paired_report,day_interval
from boat24_factors import CATALOG,audit

DAY='2026-11-03';CODE='202611031508';AT=dt.datetime(2026,11,3,18,30,tzinfo=JST);CUT=AT+dt.timedelta(minutes=11)
def card():return {f'艇{i}_登録番号':str(4000+i) for i in range(1,7)}
def preview():
    ex={'取得日時':AT.isoformat()};st={'取得日時':AT.isoformat()}
    for i in range(1,7):
        ex.update({f'艇{i}_展示タイム':str(6.7+i*.01),f'艇{i}_体重(kg)':'52',f'艇{i}_体重調整(kg)':'1'})
        st.update({f'艇{i}_コース':str(i),f'艇{i}_スタート展示':str(-.03 if i==1 else i*.02)})
    return {'ex':ex,'st':st}

class Integrated(unittest.TestCase):
    def test_comment_aspects_do_not_cancel_each_other(self):
        self.assertEqual(analyze('出足は弱いが伸びは良い')['features'],{'出足':-1,'伸び':1})
        self.assertEqual(analyze('出足と伸びが良い')['features'],{'出足':1,'伸び':1})
        for text in ('伸びが欲しい','伸びは良いか分からない','昨日は伸びが良かった'):
            self.assertEqual(analyze(text)['features'],{})
        self.assertEqual(analyze('伸びは良い。伸びは弱い')['conflicting_aspects'],['伸び'])
        self.assertNotIn('伸び',analyze('伸びは良い。伸びは弱い')['features'])

    def test_exhibition_rank_st_f_and_adjacent_course(self):
        f=[{} for _ in range(6)];p=preview();p['st']['艇2_コース']='3';p['st']['艇3_コース']='2'
        d=attach(f,CODE,card(),{},p,CUT,AT)
        self.assertEqual(f[0]['exhibition_detail']['展示順位'],1)
        self.assertEqual(f[0]['exhibition_detail']['体重調整体重合計kg'],53)
        self.assertNotIn('正常展示ST順位',f[0]['start_detail'])
        self.assertAlmostEqual(f[1]['start_detail']['内隣展示ST差秒'],.04-.06)
        self.assertIn('スロー・ダッシュ',d['unmeasured'])

    def test_future_comments_and_results_never_join(self):
        f=[{} for _ in range(6)];future=AT+dt.timedelta(minutes=1)
        official={'observed_at':future.isoformat(),'comments':{'1':{'racer':'4001','comment':'伸びは良い'}}}
        attach(f,CODE,card(),{},preview(),CUT,AT,official)
        self.assertEqual(f[0]['comment_detail'],{})
        official['observed_at']=AT.isoformat();attach(f,CODE,card(),{},preview(),CUT,AT,official)
        self.assertEqual(f[0]['comment_detail']['時点未公表_伸び'],1)

    def test_replay_uses_prior_dates_and_one_snapshot_per_phase(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);s={'id':'a','phase':'preview','created_at':AT.isoformat(),'cutoff':CUT.isoformat(),'evaluation_eligible':True,'input_snapshot':{'captured_at':AT.isoformat(),'features':[{} for _ in range(6)],'source_times':{'ex':AT.isoformat()}}}
            r={'revisions':{'a':s,'b':dict(s,id='b',created_at=(AT+dt.timedelta(minutes=1)).isoformat(),input_snapshot={**s['input_snapshot'],'captured_at':(AT+dt.timedelta(minutes=1)).isoformat()})}}
            (p/(DAY+'.json')).write_text(json.dumps({'records':{CODE:r}}))
            self.assertEqual(load_observations(AT.date(),directory=p)[0],{})
            selected,diag=load_observations(AT.date()+dt.timedelta(days=1),directory=p)
            self.assertEqual(len(selected),1);self.assertEqual(selected[(CODE,'preview')]['id'],'b')
            self.assertEqual(diag['snapshots'],1)
            r['revisions']['a']['input_snapshot']['source_times']['ex']=(AT+dt.timedelta(hours=1)).isoformat()
            (p/(DAY+'.json')).write_text(json.dumps({'records':{CODE:r}}));self.assertGreater(load_observations(AT.date()+dt.timedelta(days=1),directory=p)[1]['rejected'],0)

    def test_refund_and_multiple_winners_ticket_settlement(self):
        bets=[{'combo':'1-2-3','stake':200},{'combo':'1-2-4','stake':100},{'combo':'1-2-5','stake':100}]
        result=amounts(bets,{'1-2-3':500,'1-2-4':600},['5'])
        self.assertEqual((result['stake'],result['refund'],result['return'],result['profit']),(400,100,1700,1300))

    def test_correction_preserves_forecast_and_original_result(self):
        s={'id':'a','selection':{'12':['-'.join(map(str,(a,b,c))) for a in range(1,7) for b in range(1,7) for c in range(1,7) if len({a,b,c})==3][:12]}}
        rec={'race_code':CODE,'revisions':{'a':copy.deepcopy(s)}};res={'レースコード':CODE,**{f'{p}着_艇番':str(p) for p in range(1,7)}}
        pay={'レースコード':CODE,'3連単_組番':'1-2-3','3連単_払戻金':'500'}
        self.assertTrue(settle_record(rec,res,pay,s,AT));old=copy.deepcopy(rec['result'])
        self.assertFalse(settle_record(rec,res,pay,s,AT));pay['3連単_払戻金']='600'
        self.assertTrue(settle_record(rec,res,pay,s,AT+dt.timedelta(minutes=2)))
        self.assertEqual(rec['result_history'][old['id']],old);self.assertEqual(rec['revisions']['a'],s)

    def test_no_promotion_from_tiny_or_duplicate_paired_history(self):
        p={'1-2-3':.8,'1-2-4':.2};x={'phase':'preview','probabilities':p,'selection':{'12':list(p)}}
        s={'id':'a','phase':'preview','created_at':AT.isoformat(),'cutoff':CUT.isoformat(),'evaluation_eligible':True,'research':{'policy':'paired-forward-1','baseline':x,'candidate':x}}
        rec={'race_code':CODE,'date':DAY,'venue':15,'revisions':{'a':s,'b':dict(s,id='b')},'result':{'combo':'1-2-3','payout_100yen':500}}
        report=paired_report([rec,rec]);row=report['phase_reports'][1]
        self.assertEqual(row['races'],1);self.assertFalse(row['adoption_approved']);self.assertIsNone(row['loss_delta_interval95'])

    def test_catalog_never_claims_unmeasured_video_is_learned(self):
        self.assertGreater(len(CATALOG),150)
        self.assertEqual(len({r['id'] for r in CATALOG}),len(CATALOG))
        rows=audit([{} for _ in range(6)],{},{});video=next(r for r in rows if r['label']=='助走距離')
        self.assertEqual(video['state'],'unavailable');self.assertFalse(video['validated_improvement'])

    def test_compiled_family_and_field_ablation_matches_actual_predictor(self):
        from boat24_context import predict,scales
        from boat24_case_engine import compile_case
        samples=[]
        for lane in range(1,7):
            for j in range(16):
                samples.append({'phase':'initial','date':'2026-11-01','code':f'{j:012d}','venue':15,'course':lane,'finish':1+(lane+j)%6,'features':{'ability':{'rating':j*.37+lane},'exhibition_detail':{'rank':j%6+1,'gap':j*.01}}})
        fs=[{'ability':{'rating':i+2.1},'exhibition_detail':{'rank':i,'gap':i*.01}} for i in range(1,7)]
        model={'samples':samples,'scales':scales(samples),'enabled_groups':['ability','exhibition_detail'],'temperature':1,'market_alpha':0}
        case={'features':fs,'date':DAY,'venue':15,'odds':{}};compiled=compile_case(model,case)
        expected=predict(fs,15,DAY,model,{})['probabilities'];actual=compiled(model['enabled_groups'])
        self.assertLess(max(abs(actual[k]-expected[k]) for k in actual),1e-10)
        changed=copy.deepcopy(fs)
        for f in changed:f['exhibition_detail'].pop('gap')
        expected=predict(changed,15,DAY,model,{})['probabilities'];actual=compiled(model['enabled_groups'],('exhibition_detail','gap'))
        self.assertLess(max(abs(actual[k]-expected[k]) for k in actual),1e-10)

    def test_computation_must_finish_before_freeze(self):
        from test_all_input_model import fixture,NOW,CODE as code
        from boat24_full_update import make_snapshot
        from boat24_train_context import History
        card_,d,history,model=fixture();at=NOW
        from boat24_context import deadline
        limit=next(deadline(d.get(k,{}).get(code),at.date().isoformat()) for k in ('odds','ex','st','title') if deadline(d.get(k,{}).get(code),at.date().isoformat()))
        snapshot,reason=make_snapshot(code,card_,d,model,History([],[]),at,clock=lambda:limit-dt.timedelta(minutes=2))
        self.assertIsNone(snapshot);self.assertEqual(reason,'computed_after_freeze')

if __name__=='__main__':unittest.main()
