"""Regression tests for display-only, verified exhibition data."""
import datetime as dt
import unittest
from boat24_live_observation import latest_verified, verified_from_cache
from boat24_integrity import JST

CODE = '202611081101'
CUTOFF = '2026-11-08T11:32:00+09:00'

def attempt(at='2026-11-08T11:28:00+09:00', code=CODE, complete=True):
    st = {'レースコード':code, '取得日時':at}
    ex = {'レースコード':code, '取得日時':at}
    for lane in range(1, 7 if complete else 6):
        st[f'艇{lane}_コース'] = str(lane)
        st[f'艇{lane}_スタート展示'] = str(round(.10+lane*.01,2))
        ex[f'艇{lane}_展示タイム'] = str(round(6.70+lane*.01,2))
    return {'verified_context':{'previews':{'st':st,'ex':ex}}}

class VerifiedExhibitionTests(unittest.TestCase):
    def test_complete_before_cutoff(self):
        observed=latest_verified(CODE,{'collection_attempts':{'a':attempt()}},{'cutoff':CUTOFF})
        self.assertEqual(len(observed['courses']),6)
        self.assertEqual(observed['exhibition_times']['1'],6.71)
        self.assertAlmostEqual(observed['exhibition_starts']['6'],.16)
        self.assertFalse(observed['prediction_used'])
    def test_after_cutoff_is_rejected(self):
        self.assertIsNone(latest_verified(CODE,{'collection_attempts':{'a':attempt('2026-11-08T11:33:00+09:00')}},{'cutoff':CUTOFF}))
    def test_wrong_race_is_rejected(self):
        self.assertIsNone(latest_verified(CODE,{'collection_attempts':{'a':attempt(code='202611080501')}},{'cutoff':CUTOFF}))
    def test_incomplete_course_is_not_fabricated(self):
        self.assertIsNone(latest_verified(CODE,{'collection_attempts':{'a':attempt(complete=False)}},{'cutoff':CUTOFF}))
    def test_latest_verified_wins(self):
        old=attempt('2026-11-08T11:20:00+09:00')
        new=attempt('2026-11-08T11:29:00+09:00')
        new['verified_context']['previews']['ex']['艇1_展示タイム']='6.99'
        observed=latest_verified(CODE,{'collection_attempts':{'a':old,'b':new}},{'cutoff':CUTOFF})
        self.assertEqual(observed['exhibition_times']['1'],6.99)
    def test_cache_preserves_independent_verified_kinds(self):
        from unittest.mock import patch
        import boat24_official
        # Ensure the implementation merges old and new preview kinds rather than
        # replacing the entire verified preview map on partial refresh.
        import inspect
        source=inspect.getsource(boat24_official.collect)
        self.assertIn("merged=dict(old['live_previews'])",source)
        self.assertIn("merged.update(rec.get('live_previews') or {})",source)
    def test_verified_cache_fallback(self):
        previews=attempt()['verified_context']['previews']
        cache={'races':{CODE:{'live_previews':previews}}}
        observed=verified_from_cache(CODE,cache,CUTOFF)
        self.assertEqual(observed['courses']['1'],1)
        self.assertEqual(observed['exhibition_times']['6'],6.76)
        self.assertFalse(observed['prediction_used'])
    def test_cache_rejects_wrong_race_and_late_observation(self):
        previews=attempt()['verified_context']['previews']
        cache={'races':{CODE:{'live_previews':previews}}}
        self.assertIsNone(verified_from_cache('202611081102',cache,CUTOFF))
        self.assertIsNone(verified_from_cache(CODE,cache,'2026-11-08T11:27:00+09:00'))
    def test_unverified_exhibition_is_not_invented(self):
        a=attempt()
        a['verified_context']['previews'].pop('ex')
        observed=latest_verified(CODE,{'collection_attempts':{'a':a}},{'cutoff':CUTOFF})
        self.assertEqual(observed['exhibition_times'],{})
if __name__=='__main__':unittest.main()
