import copy
import unittest
from boat24_quote_context import newest_context,reject_obsolete_reprices

CODE='202611041901'
def snapshot(sid,created,context=None,phase='preview'):
    s={'id':sid,'created_at':'2026-11-04T'+created+'+09:00','cutoff':'2026-11-04T17:41:00+09:00',
       'evaluation_eligible':True,'phase':phase,'input_snapshot':{'features':[{'entry_detail':{'展示コース':i}} for i in (1,2,6,3,4,5)]}}
    if context:s.update(context_snapshot_at='2026-11-04T'+context+'+09:00',refresh_kind='official_odds_reprice')
    return s

class QuoteContextTests(unittest.TestCase):
    def setUp(self):
        self.fresh=snapshot('fresh','17:36:52')
        self.old=snapshot('old','17:37:48','17:12:33','partial')
    def test_latest_quote_clock_cannot_replace_newer_exhibition_context(self):
        r={'revisions':{'fresh':self.fresh,'old':self.old}}
        before=copy.deepcopy(r)
        self.assertIs(newest_context(r),self.fresh)
        self.assertEqual(r,before)
    def test_new_quote_on_same_context_is_preferred(self):
        s=snapshot('repriced','17:38:00','17:36:52')
        self.assertIs(newest_context({'revisions':{'fresh':self.fresh,'repriced':s}}),s)
    def test_inflight_quote_is_rejected_if_main_published_newer_context(self):
        remote={'records':{CODE:{'revisions':{'fresh':self.fresh}}}}
        incoming={'records':{CODE:{'revisions':{'old':self.old},'offers':{'bad':{'snapshot_id':'old'}}}}}
        before=copy.deepcopy(incoming)
        out=reject_obsolete_reprices(remote,incoming)
        self.assertEqual(out['records'][CODE]['revisions'],{})
        self.assertEqual(out['records'][CODE]['offers'],{})
        self.assertEqual(incoming,before)
    def test_previously_published_revisions_are_never_removed(self):
        incoming={'records':{CODE:{'revisions':{'fresh':self.fresh,'old':self.old},'offers':{'saved':{'snapshot_id':'old'}}}}}
        self.assertEqual(reject_obsolete_reprices(incoming,incoming),incoming)
    def test_current_context_quote_is_not_rejected(self):
        s=snapshot('ok','17:38:00','17:36:52')
        incoming={'records':{CODE:{'revisions':{'ok':s}}}}
        remote={'records':{CODE:{'revisions':{'fresh':self.fresh}}}}
        self.assertEqual(reject_obsolete_reprices(remote,incoming),incoming)
    def test_ineligible_or_invalid_context_cannot_be_selected(self):
        bad=snapshot('bad','17:40:00','17:41:00');bad['evaluation_eligible']=False
        self.assertIsNone(newest_context({'revisions':{'bad':bad}}))

if __name__=='__main__':unittest.main()
