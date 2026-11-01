import unittest
from update import build,ranks,unique_history
class TestScoring(unittest.TestCase):
 def test_finishes(self):self.assertEqual(ranks('１２Ｆ [3] ６'),[1,2,3,6])
 def test_build(self):
  stats=[{'場コード':'15','モーター番号':'18','2連対率':'50','3連対率':'65','出走数':'20'}]
  history=unique_history([{'場コード':'15','モーター番号':'18','使用終了日':'2026-10-30','使用開始日':'2026-10-25','使用者名':'選手A','着順列':'１２３１２'}])
  res=build(stats,history,'2026-11-01')
  self.assertEqual(len(res),1);self.assertEqual(res[0]['uses'][0]['races'],5)
if __name__=='__main__':unittest.main()
