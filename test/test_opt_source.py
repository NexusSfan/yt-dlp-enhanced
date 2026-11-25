import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from devscripts.opt_source import manifest_digest, materialize_commit, verify_snapshot


@unittest.skipUnless(shutil.which('git'), 'requires Git')
class TestOptSource(unittest.TestCase):
    def test_committed_bytes_not_hidden_worktree_edits(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / 'repo'
            repo.mkdir()

            def git(*args):
                return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()

            git('init')
            test = repo / 'test_fixture.py'
            test.write_bytes(b'assert False\n')
            (repo / '.gitattributes').write_bytes(b'test_fixture.py export-ignore\n')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'fixture')
            head = git('rev-parse', 'HEAD')
            git('update-index', '--assume-unchanged', 'test_fixture.py')
            test.write_bytes(b'assert True\n')
            self.assertEqual(git('status', '--porcelain'), '')
            generation = root / 'generation'
            manifest = materialize_commit(repo, head, generation)
            self.assertEqual((generation / test.name).read_bytes(), b'assert False\n')
            verify_snapshot(generation, manifest)
            second = root / 'second'
            self.assertEqual(manifest_digest(materialize_commit(repo, head, second)), manifest_digest(manifest))
            (generation / test.name).write_bytes(b'assert True\n')
            with self.assertRaises(ValueError):
                verify_snapshot(generation, manifest)

    def test_opt_rejects_hidden_failing_committed_test(self):
        project = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            scripts = repo / 'devscripts'
            scripts.mkdir()
            for filename in ('opt_source.py', 'opt_shards.py', 'strict_json.py', 'process_lifecycle.py'):
                shutil.copyfile(project / 'devscripts' / filename, scripts / filename)
            (repo / '.gitignore').write_text('__pycache__/\n.pytest_cache/\n', encoding='utf-8')
            test = repo / 'test_fixture.py'
            test.write_bytes(b'def test_fixture(): assert False\n')

            def git(*args):
                return subprocess.check_output(['git', *args], cwd=repo, text=True).strip()

            git('init')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'fixture')
            git('update-index', '--assume-unchanged', test.name)
            test.write_bytes(b'def test_fixture(): assert True\n')
            self.assertEqual(git('status', '--porcelain'), '')
            env = dict(os.environ, PYTEST_DISABLE_PLUGIN_AUTOLOAD='1')
            env.pop('PYTHONPATH', None)
            command = [sys.executable, '-c',
                       'from devscripts.opt_shards import run_opt; raise SystemExit(run_opt(1, flaky=True))']
            result = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertIn('test_fixture.py::test_fixture', result.stdout)
            self.assertIn('assert False', result.stdout)
            self.assertNotIn('OPT source/coverage receipt:', result.stdout)

    @unittest.skipIf(os.name == 'nt', 'POSIX executable bit')
    def test_committed_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / 'repo'
            repo.mkdir()
            subprocess.check_call(['git', 'init'], cwd=repo)
            file = repo / 'script'
            file.write_bytes(b'#!/bin/sh\n')
            file.chmod(0o755)
            subprocess.check_call(['git', 'add', '.'], cwd=repo)
            subprocess.check_call(['git', '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
                                   'commit', '-m', 'fixture'], cwd=repo)
            head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo, text=True).strip()
            dest = root / 'generation'
            manifest = materialize_commit(repo, head, dest)
            verify_snapshot(dest, manifest)
            (dest / 'script').chmod(0o644)
            with self.assertRaises(ValueError):
                verify_snapshot(dest, manifest)
