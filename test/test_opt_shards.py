import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from devscripts.opt_shards import assigned_modules, partition, verify_outcome_parity, verify_receipts
from devscripts.strict_json import loads
from devscripts.run_tests import parse_args


def make_receipt(ids, *, outcome='passed', reason=None, xfail=None, digest=None):
    phases = [['setup', 'passed'], ['call', outcome], ['teardown', 'passed']]
    return {'schema': 1, 'collected': ids, 'full_collection': ids, 'exitstatus': 0,
            'source_sha256': digest, 'environment_sha256': 'b' * 64, 'reports': {nodeid: phases for nodeid in ids}, 'subtests': {},
            'outcomes': {nodeid: [['parent', phase, result, reason if phase == 'call' else None,
                                   xfail if phase == 'call' else None, None] for phase, result in phases]
                         for nodeid in ids}}


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

    def test_module_paths(self):
        ids = ['test/b.py::test_one', 'test/a.py::test_two', 'test/b.py::test_three']
        self.assertEqual(assigned_modules(ids, {'test/a.py', 'test/b.py'}), ['test/a.py', 'test/b.py'])
        with self.assertRaises(ValueError):
            assigned_modules(ids, {'test/a.py'})

    def test_scoped_receipts(self):
        first, second = ['test/a.py::test_a'], ['test/b.py::test_b']

        def receipt(ids):
            return make_receipt(ids, digest='a' * 64)

        verify_receipts([first, second], [receipt(first), receipt(second)], source_digest='a' * 64)
        with self.assertRaises(ValueError):
            verify_receipts([first, second], [receipt(first), receipt(second)], source_digest='wrong')
        with self.assertRaises(ValueError):
            verify_receipts([first, first], [receipt(first), receipt(first)])
        broad = dict(receipt(first), full_collection=[*first, *second])
        with self.assertRaises(ValueError):
            verify_receipts([first, second], [broad, receipt(second)], source_digest='source')

    def test_outcome_parity_rejects_same_counts_different_outcomes(self):
        ids = ['test/a.py::test_a', 'test/b.py::test_b']

        def receipt(nodeid, outcome, reason=None, xfail=None):
            return make_receipt([nodeid], outcome=outcome, reason=reason, xfail=xfail)

        first = receipt(ids[0], 'passed')
        second = receipt(ids[1], 'skipped', 'fixture unavailable')
        reference = make_receipt(ids)
        for key in ('reports', 'outcomes'):
            reference[key] = {**first[key], **second[key]}
        digest = verify_outcome_parity(reference, [first, second])
        self.assertEqual(digest, verify_outcome_parity(reference, [second, first]))
        for alternatives in (
                [receipt(ids[0], 'skipped', 'fixture unavailable'), receipt(ids[1], 'passed')],
                [first, receipt(ids[1], 'skipped', 'different reason')],
                [first, receipt(ids[1], 'skipped', 'fixture unavailable', 'expected failure')],
                [first], [first, first, second]):
            with self.assertRaises(ValueError):
                verify_outcome_parity(reference, alternatives)

    def test_cli(self):
        with patch('sys.argv', ['run_tests', '--opt', '--workers', '7', 'core']):
            args = parse_args()
        self.assertTrue(args.opt)
        self.assertEqual(args.workers, 7)
        self.assertEqual(args.test, ['core'])

    def test_serial_cli_defaults(self):
        for argv in [[], ['core'], ['download'], ['--pytest-args', '--reruns 2', 'core']]:
            with self.subTest(argv=argv), patch('sys.argv', ['run_tests', *argv]):
                args = parse_args()
                self.assertFalse(args.opt)
                self.assertEqual(args.workers, 7)

    def test_opt_default_workers(self):
        with patch('sys.argv', ['run_tests', '--opt', 'core']):
            self.assertEqual(parse_args().workers, 7)

    def test_real_pytest_subtest_receipt(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            testfile = tmp / 'test_fixture.py'
            spec = tmp / 'spec.json'
            receipt = tmp / 'receipt.json'
            testfile.write_text(
                'import unittest\n\n'
                'class TestFixture(unittest.TestCase):\n'
                '    def test_subtests(self):\n'
                '        for i in range(3):\n'
                '            with self.subTest(i=i):\n'
                '                self.assertGreaterEqual(i, 0)\n', encoding='utf-8')
            spec.write_text(json.dumps({'assigned': None, 'receipt': str(receipt)}), encoding='utf-8')
            env = dict(os.environ, YTDLP_OPT_SPEC=str(spec), PYTHONPATH=str(root))
            env.pop('PYTEST_ADDOPTS', None)
            env.pop('PYTEST_PLUGINS', None)
            result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'devscripts.opt_shards',
                                     str(testfile)], cwd=tmp, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads(receipt.read_text(encoding='utf-8'))
            self.assertEqual(len(data['collected']), 1)
            verify_receipts([data['collected']], [data])
            # An actual duplicate parent call must still be rejected.
            nodeid = data['collected'][0]
            data['reports'][nodeid].append(['call', 'passed'])
            with self.assertRaises(ValueError):
                verify_receipts([data['collected']], [data])

    def test_exact_module_collection_matches_broad_selection(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            (tmp / 'test_a.py').write_text(
                'def test_keep_a(): pass\ndef test_other(): pass\n', encoding='utf-8')
            (tmp / 'test_b.py').write_text('def test_keep_b(): pass\n', encoding='utf-8')
            spec, receipt = tmp / 'spec.json', tmp / 'receipt.json'
            env = dict(os.environ, YTDLP_OPT_SPEC=str(spec), PYTHONPATH=str(root))
            env.pop('PYTEST_ADDOPTS', None)
            env.pop('PYTEST_PLUGINS', None)

            def invoke(assigned, *extra):
                spec.write_text(json.dumps({'assigned': assigned, 'receipt': str(receipt)}), encoding='utf-8')
                return subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'devscripts.opt_shards',
                                       '-k', 'keep', *extra], cwd=tmp, env=env, capture_output=True, text=True, timeout=60)

            result = invoke(None)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            reference = json.loads(receipt.read_text(encoding='utf-8'))
            baseline = reference['collected']
            shards = partition(baseline, 2)
            receipts = []
            for ids in shards:
                result = invoke(ids, '--', *assigned_modules(ids, {'test_a.py', 'test_b.py'}))
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                receipts.append(json.loads(receipt.read_text(encoding='utf-8')))
            verify_receipts(shards, receipts)
            verify_outcome_parity(reference, receipts)
            # Reject an unexpected selected test before running any of that shard.
            result = invoke(shards[0], '--', 'test_a.py', 'test_b.py')
            self.assertNotEqual(result.returncode, 0)

    def test_invalid_inputs(self):
        for ids, workers in [([], 7), (['a', 'a'], 7), (['a'], 0), (['a'], 33)]:
            with self.assertRaises(ValueError):
                partition(ids, workers)

    def test_receipt_fail_closed(self):
        ids = ['test/a.py::test_a']
        good = make_receipt(ids)
        verify_receipts([ids], [good])
        with self.assertRaises(ValueError):
            verify_receipts([ids], [dict(good, subtests={ids[0]: ['failed']})])
        for receipts in [[], [dict(good, full_collection=[*ids, 'unexpected'])], [dict(good, exitstatus=1)], [dict(good, reports={})], [{'collected': [], 'reports': {}}],
                         [{'collected': ids, 'reports': {}}],
                         [{'collected': ids, 'reports': {ids[0]: [['setup', 'passed']]}}]]:
            with self.assertRaises(ValueError):
                verify_receipts([ids], receipts)

    def test_strict_receipt_and_structured_subtest_identity(self):
        ids = ['test/a.py::test_a']
        nodeid = ids[0]

        def receipt(params):
            data = make_receipt(ids)
            data['subtests'][nodeid] = ['passed']
            data['outcomes'][nodeid].insert(1, ['subtest', 'call', 'passed', None, None, [0, 'None', params]])
            return data

        reference = receipt([['x', '1'], ['y', '2']])
        verify_outcome_parity(reference, [reference])
        with self.assertRaises(ValueError):
            verify_outcome_parity(reference, [receipt([['x=1, y', '2']])])
        for mutation in (dict(reference, exitstatus=False), dict(reference, schema=True),
                         dict(reference, unknown=True)):
            with self.assertRaises(ValueError):
                verify_outcome_parity(mutation, [mutation])
        for records in ([['parent', 'future', 'passed', None, None, None]],
                        [['parent', 'setup', 'passed']], list(reversed(reference['outcomes'][nodeid]))):
            broken = dict(reference, outcomes={nodeid: records})
            with self.assertRaises(ValueError):
                verify_outcome_parity(broken, [broken])
        with self.assertRaises(ValueError):
            loads('{"exitstatus":1,"exitstatus":0}')

    def test_direct_script_opt_import(self):
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run([sys.executable, str(root / 'devscripts/run_tests.py'), '--opt',
                                 '--workers', '0', 'core'], cwd=root, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('OPT workers must be 1..32', result.stderr)

    def test_experimental_weighted_partition(self):
        ids = [f'test/{module}.py::test_{i}' for module, count in [('a', 4), ('b', 3), ('c', 2), ('d', 1)] for i in range(count)]
        weights = {f'test/{module}.py': cost for module, cost in [('a', 1), ('b', 1), ('c', 10), ('d', 9)]}
        shards = partition(ids, 2, module_costs=weights)
        self.assertEqual(shards, partition(list(reversed(ids)), 2, module_costs=weights))
        self.assertEqual(sorted(ids), sorted(nodeid for shard in shards for nodeid in shard))
        self.assertEqual([sum(weights[module] for module in set(nodeid.split('::')[0] for nodeid in shard))
                          for shard in shards], [11, 10])
        with self.assertRaises(ValueError):
            partition(ids, 2, module_costs={})
        receipt = make_receipt([ids[0]])
        with self.assertRaises(ValueError):
            verify_receipts([[ids[0]]], [receipt], environment_digest='c' * 64)
