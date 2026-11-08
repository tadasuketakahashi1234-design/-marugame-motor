"""Regression tests for bounded official beforeinfo retry."""
import datetime as dt
import unittest
from unittest.mock import patch
import boat24_fast_context as fast
from boat24_integrity import JST

class BeforeinfoRetryTests(unittest.TestCase):
    def setUp(self):
        self.code='202611081101'
        self.now=dt.datetime(2026,11,8,10,10,tzinfo=JST)
        self.snapshot={'input_snapshot':{'card':{}},'boat_identities':[]}
    def _run(self,download):
        with patch.object(fast,'download',side_effect=download),patch.object(fast,'parse_before',return_value={'verified':True}),patch.object(fast,'parse_live_previews',return_value={'st':{'レースコード':self.code}}):
            return fast.collect([(self.code,self.snapshot)],self.now)
    def test_timeout_then_success_keeps_verified_entry(self):
        def response(url,timeout=5):
            if 'beforeinfo' in url:
                if 'retry=1' not in url:raise TimeoutError('temporary timeout')
                return 'valid official html'
            return ''
        rows,errors=self._run(response)
        self.assertNotIn('before_'+self.code,errors)
        self.assertEqual(rows[self.code]['previews']['st']['レースコード'],self.code)
        self.assertEqual(rows[self.code]['source_checks']['before']['state'],'parsed')
    def test_both_timeouts_record_error(self):
        def response(url,timeout=5):
            if 'beforeinfo' in url:raise TimeoutError('official timeout')
            return ''
        rows,errors=self._run(response)
        self.assertIn('before_'+self.code,errors)
        self.assertIn('retry exhausted',errors['before_'+self.code])
        self.assertEqual(rows[self.code]['source_checks']['before']['state'],'unconfirmed')
    def test_identity_failure_is_not_retried(self):
        calls=[]
        def response(url,timeout=5):
            if 'beforeinfo' in url:calls.append(url)
            return 'html'
        with patch.object(fast,'download',side_effect=response),patch.object(fast,'parse_before',return_value={}),patch.object(fast,'parse_live_previews',return_value={}):
            _,errors=fast.collect([(self.code,self.snapshot)],self.now)
        self.assertEqual(len(calls),1)
        self.assertIn('before_'+self.code,errors)
if __name__=='__main__':unittest.main()
