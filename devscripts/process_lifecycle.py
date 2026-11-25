"""Bounded local subprocess execution for trusted developer diagnostics."""

import contextlib
import os
import signal
import subprocess


def run_process(command, *, timeout, input=None, capture_output=False, check=False, **kwargs):
    """Kill the POSIX process group on failure to complete; Windows is direct-child only."""
    with subprocess.Popen(command, stdin=subprocess.PIPE if input is not None else None,
                          stdout=subprocess.PIPE if capture_output else None,
                          stderr=subprocess.PIPE if capture_output else None,
                          start_new_session=os.name == 'posix', **kwargs) as process:
        try:
            stdout, stderr = process.communicate(input, timeout=timeout)
        except BaseException:
            if os.name == 'posix':
                with contextlib.suppress(ProcessLookupError):
                    os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            # Do not wait for escaped descendants holding inherited pipes.
            for stream in (process.stdin, process.stdout, process.stderr):
                if stream is not None:
                    stream.close()
            process.wait()
            raise
        result = subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
        if check:
            result.check_returncode()
        return result
