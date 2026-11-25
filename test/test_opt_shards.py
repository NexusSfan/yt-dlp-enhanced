import unittest
from unittest.mock import patch

from devscripts.run_tests import parse_args

from devscripts.opt_shards import partition, verify_receipts


class TestOptShards(unittest.TestCase):
    def test_deterministic_complete_partition(self):
        ids = [f'test/test_{i % 9}.py::test_{i}' for i in range(50)]
        shards = partition(ids, 7)
        self.assertEqual(shards, partition(list(reversed(ids)), 7))
        self.assertEqual(len(shards), 7)
        self.assertEqual(sorted(ids), sorted(item for shard in shards for item in shard))
        owners = {}
        for index, shard in enumerate(shards):
            for item in shard:
                module = item.split('::')[0]
                self.assertEqual(owners.setdefault(module, index), index)

    def test_cli(self):
        with patch('sys.argv', ['run_tests', '--opt', '--workers', '7', 'core']):
            args = parse_args()
        self.assertTrue(args.opt)
        self.assertEqual(args.workers, 7)
        self.assertEqual(args.test, ['core'])

    def test_invalid_inputs(self):
        for ids, workers in [([], 7), (['a', 'a'], 7), (['a'], 0), (['a'], 33)]:
            with self.assertRaises(ValueError):
                partition(ids, workers)

    def test_receipt_fail_closed(self):
        ids = ['test/a.py::test_a']
        good = {'collected': ids, 'full_collection': ids, 'exitstatus': 0, 'reports': {ids[0]: [
            ['setup', 'passed'], ['call', 'passed'], ['teardown', 'passed']]}}
        verify_receipts([ids], [good])
        for receipts in [[], [dict(good, full_collection=ids + ['unexpected'])], [dict(good, exitstatus=1)], [dict(good, reports={})], [{'collected': [], 'reports': {}}],
                         [{'collected': ids, 'reports': {}}],
                         [{'collected': ids, 'reports': {ids[0]: [['setup', 'passed']]}}]]:
            with self.assertRaises(ValueError):
                verify_receipts([ids], receipts)
