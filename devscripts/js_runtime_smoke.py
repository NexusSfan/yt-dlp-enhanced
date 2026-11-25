"""Opt-in offline Bun smoke test; not an EJS solver or sandbox."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from devscripts.strict_json import loads


FIXTURE = '''
const values = [1, 2, 3, 4, 5, 6, 7];
const total = values.reduce((a, b) => a + b * b, 0);
const message = Array.from("QSOL").reverse().join("");
console.log(JSON.stringify({total, message, sorted: [7, 2, 1].sort((a, b) => a - b)}));
'''
EXPECTED = {'total': 140, 'message': 'LOSQ', 'sorted': [1, 2, 7]}


def check_output(output):
    actual = loads(output)
    if json.dumps(actual, sort_keys=True) != json.dumps(EXPECTED, sort_keys=True):
        raise ValueError('JavaScript fixture outcome mismatch')


def run_smoke(path, repetitions=3):
    if not path.is_absolute() or not path.is_file() or not 1 <= repetitions <= 10:
        raise ValueError('provide an explicit absolute executable path and 1..10 repetitions')
    path = path.resolve(strict=True)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    # Do not inherit proxy settings, JS package paths, or user credentials.
    # This is environment reduction for a trusted local fixture, not a sandbox.
    env = {key: os.environ[key] for key in ('SYSTEMROOT', 'WINDIR') if key in os.environ}
    env['BUN_RUNTIME_TRANSPILER_CACHE_PATH'] = '0'
    samples = []
    with tempfile.TemporaryDirectory(prefix='yt-dlp-js-smoke-') as directory:
        env.update(HOME=directory, USERPROFILE=directory, TMPDIR=directory, TEMP=directory, TMP=directory)
        version = subprocess.run([str(path), '--version'], cwd=directory, env=env,
                                 capture_output=True, text=True, timeout=10, check=True).stdout.strip()
        for _ in range(repetitions):
            started = time.monotonic_ns()
            result = subprocess.run([str(path), '--bun', 'run', '--no-addons', '--no-install', '--prefer-offline', '-'],
                                    input=FIXTURE, cwd=directory, env=env, capture_output=True,
                                    text=True, timeout=10, check=True)
            elapsed = time.monotonic_ns() - started
            if result.stderr:
                raise ValueError('unexpected runtime diagnostics')
            check_output(result.stdout)
            samples.append(elapsed)
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('runtime changed during experiment')
    try:
        ejs_version = importlib.metadata.version('yt-dlp-ejs')
    except importlib.metadata.PackageNotFoundError:
        ejs_version = None
    return {'runtime': 'bun', 'version': version, 'executable_sha256': digest,
            'fixture_sha256': hashlib.sha256(FIXTURE.encode()).hexdigest(),
            'ejs_distribution_version': ejs_version, 'elapsed_ns': samples,
            'fixture_passed': True, 'solver_compatibility_verified': False,
            'runtime_isolation_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bun', required=True, type=Path, help='Absolute path to a trusted Bun executable')
    parser.add_argument('--repetitions', type=int, default=3)
    args = parser.parse_args()
    try:
        print(json.dumps(run_smoke(args.bun, args.repetitions), sort_keys=True))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f'JS smoke failed: {error}\n')


if __name__ == '__main__':
    main()
