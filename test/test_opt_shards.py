import unittest

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

    def test_invalid_inputs(self):
        for ids, workers in [([], 7), (['a', 'a'], 7), (['a'], 0), (['a'], 33)]:
            with self.assertRaises(ValueError):
                partition(ids, workers)

    def test_receipt_fail_closed(self):
        ids = ['test/a.py::test_a']
        good = {'collected': ids, 'reports': {ids[0]: [
            ['setup', 'passed'], ['call', 'passed'], ['teardown', 'passed']]}}
        verify_receipts([ids], [good])
        for receipts in [[], [{'collected': [], 'reports': {}}],
                         [{'collected': ids, 'reports': {}}],
                         [{'collected': ids, 'reports': {ids[0]: [['setup', 'passed']]}}]]:
            with self.assertRaises(ValueError):
                verify_receipts([ids], receipts)
