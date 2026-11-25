import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('git') and shutil.which('sh') and os.name != 'nt', 'requires POSIX Git')
class TestUpstreamSync(unittest.TestCase):
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
