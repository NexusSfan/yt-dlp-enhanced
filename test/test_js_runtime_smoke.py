import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from devscripts.js_runtime_smoke import EXPECTED, check_output, run_smoke


class TestJsRuntimeSmoke(unittest.TestCase):
    def test_fixed_output(self):
        check_output(json.dumps({'total': 140, 'message': 'LOSQ', 'sorted': [1, 2, 7]}))
        for output in ('not JSON', '{}', '{"total": 141}',
                       '{"total":140,"message":"LOSQ","sorted":[true,2,7]}',
                       '{"total":0,"total":140,"message":"LOSQ","sorted":[1,2,7]}'):
            with self.assertRaises(ValueError):
                check_output(output)

    def test_rejects_implicit_path(self):
        with self.assertRaises(ValueError):
            run_smoke(Path('bun'))

    def test_explicit_runtime_and_bounded_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bun'
            path.write_bytes(b'fixture executable')
            with patch('devscripts.js_runtime_smoke.run_process') as run:
                run.side_effect = [
                    subprocess.CompletedProcess([], 0, '1.4.5\n', ''),
                    subprocess.CompletedProcess([], 0, json.dumps(EXPECTED), ''),
                ]
                receipt = run_smoke(path, 1)
                self.assertTrue(receipt['fixture_passed'])
                self.assertFalse(receipt['solver_compatibility_verified'])
                self.assertFalse(receipt['runtime_isolation_verified'])
                self.assertEqual(len(receipt['elapsed_ns']), 1)
                self.assertEqual(run.call_count, 2)
                argv = run.call_args.args[0]
                self.assertEqual(argv[0], str(path.resolve()))
                self.assertIn('--no-install', argv)
                self.assertEqual(run.call_args.kwargs['timeout'], 10)

    def test_runtime_failure_is_not_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'bun'
            path.write_bytes(b'fixture executable')
            with patch('devscripts.js_runtime_smoke.run_process',
                       side_effect=subprocess.TimeoutExpired(['bun'], 10)):
                with self.assertRaises(subprocess.TimeoutExpired):
                    run_smoke(path, 1)
