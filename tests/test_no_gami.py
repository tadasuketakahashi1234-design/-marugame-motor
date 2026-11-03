import itertools
import unittest
from boat24_bets import no_gami_plan
from boat24_settlement import amounts


class NoGamiTests(unittest.TestCase):
    def setUp(self):
        self.codes=['-'.join(c) for c in itertools.permutations('123456',3)]
        self.prob={c:(120-i)/7260 for i,c in enumerate(self.codes)}

    def test_excludes_favorites_below_total_and_break_even(self):
        odds={c:20 for c in self.codes}
        odds.update({self.codes[0]:1.5,self.codes[1]:11.9,self.codes[2]:12,self.codes[3]:12.09})
        plan=no_gami_plan(self.prob,odds)
        self.assertEqual(plan['status'],'ready')
        self.assertEqual([t['combo'] for t in plan['tickets']],self.codes[4:16])
        self.assertEqual(plan['budget'],1200)
        for t in plan['tickets']:
            settled=amounts(plan['tickets'],{t['combo']:int(t['odds']*10)*10},[])
            self.assertGreater(settled['profit'],0)

    def test_low_synthetic_odds_are_allowed(self):
        plan=no_gami_plan(self.prob,{c:12.1 for c in self.codes})
        self.assertEqual(plan['status'],'ready')
        self.assertLess(plan['synthetic_odds'],7)
        self.assertEqual(plan['minimum_hit_profit'],10)

    def test_missing_invalid_or_insufficient_quotes_skip(self):
        for bad in (None,float('nan'),float('inf'),0):
            odds={c:20 for c in self.codes};odds[self.codes[0]]=bad
            self.assertEqual(no_gami_plan(self.prob,odds)['tickets'],[])
        odds={c:12 for c in self.codes}
        for c in self.codes[:11]:odds[c]=20
        self.assertEqual(no_gami_plan(self.prob,odds)['status'],'no_feasible_plan')


if __name__=='__main__':unittest.main()
