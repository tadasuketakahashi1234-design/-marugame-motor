import copy
import datetime as dt
import itertools
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import boat24_daily as daily
from boat24_integrity import JST, atomic_write, eligible, merge_ledgers, summarize

CODE = '202611031501'
COMBOS = ['-'.join(map(str, c)) for c in itertools.permutations(range(1, 7), 3)]


def record(code=CODE):
    return {'race_code': code, 'date': '2026-11-03', 'venue': 15, 'race': 1,
            'created_at': '2026-11-03T08:00:00+09:00',
            'cutoff': '2026-11-03T15:00:00+09:00', 'evaluation_eligible': True,
            'cutoff_verified_at': '2026-11-03T08:00:00+09:00',
            'selection': {str(n): COMBOS[:n] for n in (12, 18)},
            'probabilities': dict.fromkeys(COMBOS, 1/120), 'input_snapshot': {'cards': {}},
            'result': None}


def sources(code=CODE, combo='1-2-3', money='2,500'):
    res = {'レースコード': code, **{f'{i}着_艇番': v for i, v in enumerate(combo.split('-'), 1)}}
    pay = {'レースコード': code, '3連単_組番': combo, '3連単_払戻金': money}
    return res, pay


class LedgerTests(unittest.TestCase):
    def test_deadline_uses_race_day_and_title_column(self):
        r = {'レースコード': '202611021501', '電話投票締切予定': '15:00'}
        self.assertEqual(daily.deadline(r).isoformat(), '2026-11-02T15:00:00+09:00')
        self.assertIsNone(daily.deadline({**r, '電話投票締切予定': '確定'}))

    def test_settlement_is_idempotent(self):
        r = record()
        self.assertTrue(daily.settlement(r, *sources()))
        before = copy.deepcopy(r)
        self.assertFalse(daily.settlement(r, *sources(money='9999')))
        self.assertEqual(r, before)
        self.assertEqual(r['result']['paper']['12'], {'hit': True, 'stake': 1200, 'return': 2500})

    def test_invalid_payout_or_result_remains_pending(self):
        for money in ['NaN', 'inf', '-100', '0', '', '100.5']:
            r = record()
            self.assertFalse(daily.settlement(r, *sources(money=money)))
            self.assertIsNone(r['result'])
        for combo in ['1-1-2', '1-2-F', '1-2-7']:
            self.assertFalse(daily.settlement(record(), *sources(combo=combo)))
        res, pay = sources()
        self.assertFalse(daily.settlement(record(), res, {**pay, '3連単_組番': '1-3-2'}))
        self.assertFalse(daily.settlement(record(), res, {**pay, 'レースコード': '202611031502'}))

    def test_summary_excludes_unverified_and_pending(self):
        hit, miss, unknown, late, pending = [record() for _ in range(5)]
        daily.settlement(hit, *sources())
        daily.settlement(miss, *sources(combo='6-5-4'))
        daily.settlement(unknown, *sources())
        unknown['evaluation_eligible'] = False
        late['created_at'] = late['cutoff']
        out = summarize(dict(enumerate([hit, miss, unknown, late, pending])))
        self.assertEqual((out['eligible'], out['excluded'], out['pending']), (3, 2, 1))
        self.assertEqual(out['12']['races'], 2)
        self.assertEqual(out['12']['hit_rate'], .5)
        self.assertAlmostEqual(out['12']['roi'], 2500/2400)

    def test_legacy_without_flag_requires_valid_timestamps(self):
        r = record();r.pop('evaluation_eligible')
        self.assertTrue(eligible(r))
        r['cutoff'] = None
        self.assertFalse(eligible(r))

    def test_final_is_separate_and_past_final_is_excluded(self):
        r = record()
        r['final_snapshot'] = {'created_at': '2026-11-03T14:50:00+09:00',
                               'selection': {str(n): COMBOS[-n:] for n in (12, 18)}}
        daily.settlement(r, *sources())
        self.assertFalse(r['result']['paper_final']['12']['hit'])
        self.assertEqual(summarize({'x': r}, True)['12']['return'], 0)
        r['final_snapshot']['created_at'] = r['cutoff']
        self.assertFalse(eligible(r, True))

    def test_merge_preserves_remote_forecast_and_every_record(self):
        remote = {'predictions': {'a': record(), 'remote-only': record()}}
        collected = copy.deepcopy(remote)
        collected['predictions'].pop('remote-only')
        collected['predictions']['local-only'] = record()
        current = collected['predictions']['a']
        current['created_at'] = '2026-11-03T08:01:00+09:00'
        current['selection']['12'] = COMBOS[-12:]
        daily.settlement(current, *sources())
        merged = merge_ledgers(remote, collected)['predictions']
        self.assertEqual(set(merged), {'a', 'remote-only', 'local-only'})
        self.assertEqual(merged['a']['selection'], remote['predictions']['a']['selection'])
        self.assertTrue(merged['a']['result']['paper']['12']['hit'])
        self.assertIsNone(remote['predictions']['a']['result'])

    def test_merge_keeps_new_final_for_verified_record(self):
        remote = {'predictions': {'a': record()}}
        local = copy.deepcopy(remote)
        local['predictions']['a']['final_snapshot'] = {'created_at': '2026-11-03T14:50:00+09:00'}
        merged = merge_ledgers(remote, local)
        self.assertEqual(merged['predictions']['a']['final_snapshot'], local['predictions']['a']['final_snapshot'])

    def test_atomic_write_failure_keeps_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ledger.json';atomic_write(path, {'safe': 1})
            with self.assertRaises(ValueError):
                atomic_write(path, {'bad': float('nan')})
            self.assertEqual(json.loads(path.read_text()), {'safe': 1})

    def test_python_browser_summary_parity(self):
        records = [record(), record(), record()]
        daily.settlement(records[0], *sources())
        daily.settlement(records[1], *sources(combo='6-5-4'))
        records[1]['evaluation_eligible'] = False
        js = "const h=require('./omura/docs/boat24_history.js');let s='';process.stdin.on('data',x=>s+=x);process.stdin.on('end',()=>console.log(JSON.stringify(h.summarize(JSON.parse(s)))));"
        result = subprocess.check_output(['node', '-e', js], input=json.dumps(records), text=True)
        self.assertEqual(json.loads(result), summarize(dict(enumerate(records))))


class CollectionTests(unittest.TestCase):
    def run_collector(self, records, data, clock='2026-11-03T09:00:00+09:00'):
        class Clock(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return dt.datetime.fromisoformat(clock)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ledger.json'
            atomic_write(path, {'predictions': records})
            def load(kind, path=None):
                return data.get((kind, path), data.get(kind, []))
            with patch.object(daily, 'OUT', path), patch.object(daily, 'load', side_effect=load), patch.object(daily.dt, 'datetime', Clock):
                daily.main()
            return json.loads(path.read_text())

    def test_title_enriches_unknown_forecasts_without_changing_picks(self):
        r=record();r['cutoff']=None;r['evaluation_eligible']=False;r.pop('cutoff_verified_at')
        data={'cards':[{'レースコード':CODE}], 'title':[{'レースコード':CODE,'電話投票締切予定':'15:00'}]}
        out=self.run_collector({CODE:r},data)['predictions'][CODE]
        self.assertTrue(eligible(out))
        for k in ('created_at','selection','probabilities','input_snapshot'):
            self.assertEqual(out[k],r[k])

    def test_no_retroactive_verification(self):
        r=record();r['cutoff']=None;r['evaluation_eligible']=False;r.pop('cutoff_verified_at')
        data={'cards':[{'レースコード':CODE}], 'title':[{'レースコード':CODE,'電話投票締切予定':'08:59'}]}
        out=self.run_collector({CODE:r},data)['predictions'][CODE]
        self.assertFalse(eligible(out))

    def test_missing_or_passed_cutoff_never_creates_forecast(self):
        for value in [None,'09:00','09:01','確定']:
            title={'レースコード':CODE,'電話投票締切予定':value}
            data={'cards':[{'レースコード':CODE}],'title':[title]}
            self.assertEqual(self.run_collector({},data)['predictions'],{})

    def test_new_forecast_dedup_and_final_snapshot(self):
        data={'cards':[{'レースコード':CODE}], 'title':[{'レースコード':CODE,'電話投票締切予定':'09:10'}],
              'odds':[{'レースコード':CODE,'締切時刻':'09:10','取得日時':'2026-11-03T08:59:00+09:00'}]}
        one=self.run_collector({},data)['predictions']
        self.assertEqual(len(one),1)
        self.assertTrue(eligible(one[CODE], True))
        two=self.run_collector(one,data)['predictions']
        self.assertEqual(one,two)

    def test_today_settles_without_card(self):
        res,pay=sources()
        out=self.run_collector({CODE:record()},{'results':[res],'payouts':[pay]})
        self.assertEqual(out['predictions'][CODE]['result']['payout_100yen'],2500)

    def test_previous_day_settles_final_too(self):
        code='202611021501';r=record(code);r['date']='2026-11-02'
        r['created_at']='2026-11-02T14:00:00+09:00';r['cutoff']='2026-11-02T15:00:00+09:00'
        r['final_snapshot']={'created_at':'2026-11-02T14:50:00+09:00','selection':r['selection']}
        res,pay=sources(code)
        out=self.run_collector({code:r},{'cards':[{'レースコード':CODE}],('results','2026/11/02'):[res],('payouts','2026/11/02'):[pay]})
        self.assertTrue(out['predictions'][code]['result']['paper_final']['12']['hit'])

    def test_total_source_failure_preserves_file(self):
        with self.assertRaisesRegex(RuntimeError,'All sources'):
            self.run_collector({CODE:record()},{})

    def test_backfill_rotates_more_than_14_days(self):
        records={}
        for i in range(18):
            d=dt.date(2026,10,1)+dt.timedelta(days=i);code=d.strftime('%Y%m%d')+'1501'
            r=record(code);r['date']=d.isoformat();records[code]=r
        data={'cards':[{'レースコード':CODE}]}
        out=self.run_collector(records,data)
        self.assertEqual(len(out['diagnostics']['backfill_dates_checked']),14)
        # Simulate the second run with the saved cursor.
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'ledger.json';atomic_write(path,out)
            with patch.object(daily,'OUT',path),patch.object(daily,'load',side_effect=lambda k,path=None: data.get(k,[])):
                daily.main()
            checked=json.loads(path.read_text())['diagnostics']['backfill_dates_checked']
        self.assertIn('2026-10-18',checked)


if __name__=='__main__':
    unittest.main()
