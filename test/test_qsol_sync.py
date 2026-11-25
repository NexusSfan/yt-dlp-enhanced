import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('git') and shutil.which('sh') and os.name != 'nt', 'requires POSIX Git')
class TestUpstreamSync(unittest.TestCase):
    def test_failed_preconditions_stop_before_mutation(self):
        script = Path(__file__).resolve().parents[1] / 'devscripts' / 'merge_upstream.sh'
        for failure in ('rev-parse', 'status'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                log = root / 'calls'
                fake = root / 'git'
                fake.write_text(
                    '#!/bin/sh\n'
                    'printf "%s\\n" "$1" >> "$SYNC_LOG"\n'
                    'if [ "$1" = "$SYNC_FAIL" ]; then exit 42; fi\n'
                    'case "$1" in rev-parse) printf "%s\\n" "$SYNC_ROOT";; esac\n',
                    encoding='utf-8')
                fake.chmod(0o700)
                env = dict(os.environ, PATH=f'{root}{os.pathsep}{os.environ["PATH"]}',
                           SYNC_LOG=str(log), SYNC_FAIL=failure, SYNC_ROOT=str(root))
                result = subprocess.run(['sh', str(script)], cwd=root, env=env, capture_output=True, timeout=30)
                self.assertNotEqual(result.returncode, 0)
                expected = ['rev-parse'] if failure == 'rev-parse' else ['rev-parse', 'status']
                self.assertEqual(log.read_text(encoding='utf-8').splitlines(), expected)

    def test_failed_apply_preserves_baseline(self):
        script = Path(__file__).resolve().parents[1] / 'devscripts' / 'merge_upstream.sh'
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            upstream, fork = root / 'upstream', root / 'fork'

            def git(cwd, *args):
                return subprocess.check_output(['git', '-C', str(cwd), *args], text=True, stderr=subprocess.STDOUT).strip()

            def commit(cwd, content):
                (cwd / 'sample.txt').write_text(content, encoding='utf-8')
                git(cwd, 'add', 'sample.txt')
                git(cwd, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'fixture')

            upstream.mkdir()
            git(upstream, 'init', '-b', 'master')
            commit(upstream, 'base\n')
            subprocess.check_call(['git', 'clone', str(upstream), str(fork)])
            git(fork, 'remote', 'rename', 'origin', 'upstream')
            original = git(fork, 'rev-parse', 'HEAD')
            git(fork, 'tag', 'upstream-base', original)
            commit(fork, 'fork conflict\n')
            before = git(fork, 'rev-parse', 'HEAD')
            commit(upstream, 'upstream conflict\n')
            result = subprocess.run(['sh', str(script)], cwd=fork, capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(git(fork, 'rev-parse', 'upstream-base'), original)
            self.assertEqual(git(fork, 'rev-parse', 'HEAD'), before)
            self.assertEqual(git(fork, 'status', '--porcelain'), '')

    def test_rejects_unrelated_branch_before_fetch(self):
        script = Path(__file__).resolve().parents[1] / 'devscripts' / 'merge_upstream.sh'
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.check_call(['git', 'init', '-b', 'unrelated'], cwd=tmp)
            result = subprocess.run(['sh', str(script)], cwd=tmp, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('outside master', result.stderr)
