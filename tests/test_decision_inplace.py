"""Regression checks for memory-safe public receipt updates."""
import unittest
from boat24_decisions import update

class DecisionUpdateMemoryTests(unittest.TestCase):
    def test_default_preserves_caller_document(self):
        original = {'records': {'historical': {'race_code': 'historical', 'receipts': {}}}}
        result = update(original, {'catalog': {}}, {}, '2026-11-08T12:00:00+09:00', {})
        self.assertIsNot(result, original)
        self.assertEqual(original, {'records': {'historical': {'race_code': 'historical', 'receipts': {}}}})
        self.assertIn('protocol', result)

    def test_opt_in_inplace_keeps_existing_records(self):
        original = {'records': {'historical': {'race_code': 'historical', 'receipts': {}}}}
        result = update(original, {'catalog': {}}, {}, '2026-11-08T12:00:00+09:00', {}, inplace=True)
        self.assertIs(result, original)
        self.assertIn('historical', result['records'])
        self.assertIn('protocol', result)

if __name__ == '__main__':
    unittest.main()
