import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from devscripts.process_lifecycle import run_process


class TestProcessLifecycle(unittest.TestCase):
    def test_normal_process(self):
        result = run_process([sys.executable, '-c', 'print(42)'], timeout=10,
                             capture_output=True, text=True, check=True)
        self.assertEqual(result.stdout.strip(), '42')

    @unittest.skipUnless(os.name == 'posix', 'requires POSIX process groups')
    def test_timeout_stops_child_in_same_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'marker'
            child = 'import pathlib,sys,time; time.sleep(1.2); pathlib.Path(sys.argv[1]).touch()'
            parent = 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]]); time.sleep(5)'
            with self.assertRaises(subprocess.TimeoutExpired):
                run_process([sys.executable, '-c', parent, child, str(marker)], timeout=0.5)
            time.sleep(1.4)
            self.assertFalse(marker.exists())
