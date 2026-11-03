import itertools
import unittest
import datetime as dt
from boat24_bets import balanced_plan,PURCHASE_POLICY
from boat24_settlement import amounts,settle_record
from boat24_full_update import summary
from boat24_integrity import JST

class BalancedPlanTests(unittest.TestCase):
 def setUp(self):
  self.codes=['-'.join(c) for c in itertools.permutations('123456',3)]
  self.p={c:0. for c in self.codes};self.odds={c:1. for c in self.codes}
 def test_balance_two_unequal_stakes_under_cap(self):
  a,b,c=self.codes[:3];self.p.update({a:.3,b:.3,c:.4});self.odds.update({a:5,b:4})
  plan=balanced_plan(self.p,self.odds)
  self.assertEqual(plan['policy'],PURCHASE_POLICY);self.assertEqual(plan['status'],'ready')
  self.assertEqual(plan['count'],2);self.assertEqual(plan['budget'],1100);self.assertEqual(plan['budget_cap'],1200)
  self.assertEqual({t['combo']:t['stake'] for t in plan['tickets']},{a:800,b:300});self.assertAlmostEqual(plan['estimated_roi'],1560/1100)
  for t in plan['tickets']:
   self.assertGreater(amounts(plan['tickets'],{t['combo']:int(t['odds']*10)*10},[])['profit'],0)
 def test_one_and_three_tickets_possible(self):
  self.p[self.codes[0]]=1.;self.odds[self.codes[0]]=2.
  self.assertEqual(balanced_plan(self.p,self.odds)['count'],1)
  self.p={c:0. for c in self.codes}
  for c in self.codes[:3]:self.p[c]=1/3;self.odds[c]=4.
  self.assertEqual(balanced_plan(self.p,self.odds)['count'],3)
 def test_no_edge_or_invalid_inputs_skip(self):
  self.p={c:1/120 for c in self.codes};self.odds={c:120 for c in self.codes}
  self.assertEqual(balanced_plan(self.p,self.odds)['status'],'no_positive_value')
  self.odds[self.codes[0]]=None;self.assertEqual(balanced_plan(self.p,self.odds)['tickets'],[])
  self.odds[self.codes[0]]=120;self.p[self.codes[0]]=float('nan')
  self.assertEqual(balanced_plan(self.p,self.odds)['status'],'probabilities_invalid')
 def test_matches_exhaustive_small_budget(self):
  a,b,c=self.codes[:3];self.p.update({a:.35,b:.25,c:.4});self.odds.update({a:4.3,b:5.1,c:3.2})
  plan=balanced_plan(self.p,self.odds,budget=400);brute=[]
  for stakes in itertools.product(range(5),repeat=3):
   total=sum(stakes)*100
   if not 0<total<=400:continue
   active=[(k,u) for k,u in zip((a,b,c),stakes) if u]
   if any(int(self.odds[k]*10)*10*u<=total for k,u in active):continue
   hit=sum(self.p[k] for k,u in active);roi=sum(self.p[k]*int(self.odds[k]*10)*10*u for k,u in active)/total
   if roi>1:brute.append(hit*(roi-1))
  self.assertTrue(plan['search_exact']);self.assertAlmostEqual(plan['balance_score'],max(brute))
 def test_settlement_records_current_policy_once(self):
  a,b,c=self.codes[:3];self.p.update({a:.3,b:.3,c:.4});self.odds.update({a:5,b:4})
  plan=balanced_plan(self.p,self.odds)
  snap={'id':'balanced','created_at':'2026-11-03T10:00:00+09:00','cutoff':'2026-11-03T11:00:00+09:00','evaluation_eligible':True,'purchase_plan':plan,'selection':{}}
  rec={'race_code':'202611031901','venue':19,'revisions':{'balanced':snap}}
  res={'レースコード':rec['race_code'],'1着_艇番':'1','2着_艇番':'2','3着_艇番':'3'}
  pay={'レースコード':rec['race_code'],'3連単_組番':a,'3連単_払戻金':'500'};now=dt.datetime(2026,11,3,12,tzinfo=JST)
  self.assertTrue(settle_record(rec,res,pay,snap,now));self.assertEqual(rec['result']['paper']['balanced']['stake'],1100)
  self.assertEqual(rec['result']['paper']['balanced']['return'],4000);self.assertEqual(summary([rec])['no_gami']['races'],1)
  self.assertFalse(settle_record(rec,res,pay,snap,now));self.assertEqual(rec['revisions']['balanced'],snap)
if __name__=='__main__':unittest.main()
