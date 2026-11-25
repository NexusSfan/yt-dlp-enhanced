"""Experimental isolated core-test sharding; no additional runtime dependencies."""
import collections
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from devscripts.opt_source import manifest_digest, materialize_commit, verify_snapshot


def partition(nodeids, workers):
    """Keep each test module together; greedily balance by collected test count."""
    if not 1 <= workers <= 32 or not nodeids or len(set(nodeids)) != len(nodeids):
        raise ValueError('invalid worker count or empty/duplicate collection')
    groups = collections.defaultdict(list)
    for nodeid in sorted(nodeids):
        groups[nodeid.split('::', 1)[0]].append(nodeid)
    shards = [[] for _ in range(min(workers, len(groups)))]
    for _, ids in sorted(groups.items(), key=lambda item: (-len(item[1]), item[0])):
        min(shards, key=len).extend(ids)
    return [sorted(shard) for shard in shards]


def assigned_modules(nodeids, source_paths):
    """Only collect modules present in the immutable source generation."""
    modules = sorted({nodeid.split('::', 1)[0] for nodeid in nodeids})
    if not modules or any(module not in source_paths or not module.endswith('.py') for module in modules):
        raise ValueError('unrecognised test module in assignment')
    return modules


def verify_receipts(expected, receipts, *, source_digest=None):
    if len(expected) != len(receipts):
        raise ValueError('missing or extra shard receipts')
    full = [nodeid for ids in expected for nodeid in ids]
    if not full or len(set(full)) != len(full):
        raise ValueError('empty or overlapping shard assignments')
    for ids, receipt in zip(expected, receipts, strict=True):
        if source_digest is not None and receipt.get('source_sha256') != source_digest:
            raise ValueError('source manifest mismatch')
        if receipt.get('exitstatus') != 0 or sorted(receipt.get('full_collection', [])) != sorted(ids):
            raise ValueError('assigned module collection or exit status mismatch')
        if sorted(receipt['collected']) != sorted(ids):
            raise ValueError('collection mismatch')
        subtests = receipt.get('subtests', {})
        if not set(subtests).issubset(ids):
            raise ValueError('unexpected subtest reports')
        if any(outcome not in {'passed', 'skipped'} for outcomes in subtests.values() for outcome in outcomes):
            raise ValueError('failed subtest')
        reports = receipt['reports']
        if set(reports) != set(ids):
            raise ValueError('missing or unexpected execution reports')
        for nodeid, phases in reports.items():
            if not phases or len({phase for phase, _ in phases}) != len(phases):
                raise ValueError(f'duplicate or absent phases: {nodeid}')
            if any(outcome not in {'passed', 'skipped'} for _, outcome in phases):
                raise ValueError(f'failed test: {nodeid}')
            by_phase = dict(phases)
            if 'setup' not in by_phase or 'teardown' not in by_phase:
                raise ValueError(f'incomplete phases: {nodeid}')
            if by_phase['setup'] == 'passed' and 'call' not in by_phase:
                raise ValueError(f'missing call: {nodeid}')


def outcome_ledger(receipts):
    """Canonical observed pytest outcomes, including skip/xfail and subtest details."""
    ledger = {}
    for receipt in receipts:
        details = receipt['outcomes']
        if set(details) != set(receipt['reports']):
            raise ValueError('missing or unexpected outcome details')
        for nodeid, records in details.items():
            if nodeid in ledger:
                raise ValueError('duplicate outcome identity')
            parents = [record[1:3] for record in records if record[0] == 'parent']
            children = [record[2] for record in records if record[0] == 'subtest']
            if parents != receipt['reports'][nodeid] or children != receipt.get('subtests', {}).get(nodeid, []):
                raise ValueError(f'inconsistent outcome details: {nodeid}')
            ledger[nodeid] = records
    return ledger


def verify_outcome_parity(reference, receipts):
    """Compare observed identities, phases, outcomes, reasons and subtest order."""
    expected = outcome_ledger([reference])
    actual = outcome_ledger(receipts)
    if expected.keys() != actual.keys():
        raise ValueError('serial/parallel outcome identity mismatch')
    mismatches = sorted(nodeid for nodeid in expected if expected[nodeid] != actual[nodeid])
    if mismatches:
        raise ValueError(f'serial/parallel outcome mismatch: {mismatches[:5]}')
    return hashlib.sha256(json.dumps(expected, sort_keys=True, ensure_ascii=True).encode('ascii')).hexdigest()


def run_opt(workers, *, pattern=None, flaky=None, ci=False, verify=False):
    if not 1 <= workers <= 32:
        print('OPT workers must be 1..32', file=sys.stderr)
        return 2
    root = Path.cwd()
    # Cleanliness is an additional precondition, not evidence of source bytes.
    if subprocess.check_output(['git', 'status', '--porcelain'], cwd=root).strip():
        print('OPT requires a clean tracked checkout; commit changes before benchmarking', file=sys.stderr)
        return 2
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, cwd=root).strip()
    args = ['-Werror', '--tb=short', '-m', 'not download', '-p', 'devscripts.opt_shards']
    if ci:
        args.append('--color=yes')
    if pattern:
        args.extend(['-k', pattern])
    if not (flaky or (flaky is None and not ci)):
        args.append('--disallow-flaky')
    started = time.monotonic()
    try:
        with tempfile.TemporaryDirectory(prefix='yt-dlp-opt-') as tmp:
            temp = Path(tmp)

            pristine = temp / 'source'
            manifest = materialize_commit(root, head, pristine)
            source_digest = manifest_digest(manifest)
            source_paths = {entry[0] for entry in manifest}
            verify_snapshot(pristine, manifest)

            def snapshot(name):
                dest = temp / name
                shutil.copytree(pristine, dest, copy_function=shutil.copy)
                verify_snapshot(dest, manifest)
                return dest

            def invoke(name, assigned=None, *, collect_only=False):
                invocation_started = time.monotonic()
                checkout = snapshot(name)
                spec = temp / f'{name}.json'
                result = temp / f'{name}-receipt.json'
                spec.write_text(json.dumps({'assigned': assigned, 'receipt': str(result), 'source_sha256': source_digest}), encoding='utf-8')
                env = dict(os.environ, YTDLP_OPT_SPEC=str(spec))
                # Disable user-supplied pytest overrides; retain the installed pinned plugins.
                env.pop('PYTEST_ADDOPTS', None)
                env.pop('PYTEST_PLUGINS', None)
                env.pop('PYTHONPATH', None)
                command = [sys.executable, '-m', 'pytest', *args]
                if collect_only:
                    command.extend(('--collect-only', '-q'))
                elif assigned is not None:
                    command.extend(['--', *assigned_modules(assigned, source_paths)])
                try:
                    proc = subprocess.run(command, cwd=checkout, env=env, timeout=900)
                    if proc.returncode:
                        raise ValueError(f'{name}: pytest exit {proc.returncode}')
                    receipt = json.loads(result.read_text(encoding='utf-8'))
                finally:
                    shutil.rmtree(checkout)
                receipt['invocation_elapsed_seconds'] = round(time.monotonic() - invocation_started, 3)
                return receipt

            # A full serial oracle already supplies the coordinator's manifest.
            # Do not pay for a separate global collection in verification mode.
            collection = invoke('reference' if verify else 'collection', collect_only=not verify)
            if collection.get('source_sha256') != source_digest or collection.get('exitstatus') != 0:
                raise ValueError('invalid collection receipt')
            baseline = collection['collected']
            shards = partition(baseline, workers)
            if verify:
                verify_receipts([baseline], [collection], source_digest=source_digest)
            parallel_started = time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(shards)) as pool:
                receipts = list(pool.map(lambda pair: invoke(f'shard-{pair[0]}', pair[1]), enumerate(shards)))
            verify_receipts(shards, receipts, source_digest=source_digest)
            parallel_elapsed = round(time.monotonic() - parallel_started, 3)
            outcome_digest = verify_outcome_parity(collection, receipts) if verify else None
            if subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, cwd=root).strip() != head or subprocess.check_output(['git', 'status', '--porcelain'], cwd=root).strip():
                raise ValueError('checkout changed during execution')
            summary = {'head': head, 'source_sha256': source_digest, 'workers': len(shards), 'tests': len(baseline),
                       'collection_sha256': hashlib.sha256(json.dumps(sorted(baseline)).encode()).hexdigest(),
                       'shard_sizes': list(map(len, shards)),
                       'module_counts': [len(assigned_modules(ids, source_paths)) for ids in shards],
                       'outcome_parity_verified': verify, 'outcome_sha256': outcome_digest,
                       'reference_or_collection_seconds': collection['invocation_elapsed_seconds'],
                       'parallel_phase_seconds': parallel_elapsed}
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        print('OPT source/coverage receipt: ' + json.dumps(summary, sort_keys=True), flush=True)
        return 0
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f'OPT failed: {error}', file=sys.stderr)
        return 1


# Pytest plugin hooks. Loaded only via -p in OPT subprocesses.
_spec = None
_reports = collections.defaultdict(list)
_full_collection = []
_subtests = collections.defaultdict(list)
_outcomes = collections.defaultdict(list)


def pytest_configure(config):
    global _spec
    _reports.clear()
    _full_collection.clear()
    _subtests.clear()
    _outcomes.clear()
    _spec = None
    path = os.environ.get('YTDLP_OPT_SPEC')
    if path:
        _spec = json.loads(Path(path).read_text(encoding='utf-8'))


def pytest_collection_finish(session):
    if _spec is None:
        return
    _full_collection.extend(item.nodeid for item in session.items)
    assigned = _spec['assigned']
    if assigned is not None and sorted(_full_collection) != sorted(assigned):
        import pytest

        pytest.exit('OPT assigned module collection differs from coordinator manifest', returncode=2)


def pytest_runtest_logreport(report):
    if _spec is None:
        return
    # pytest 9 emits a separate SubtestReport for each unittest subTest.
    # Keep these outcomes separate from the parent's unique lifecycle phases.
    try:
        from _pytest.subtests import SubtestReport
    except ImportError:
        SubtestReport = ()
    # Skip locations can include private workspace paths. Compare the reason,
    # not the absolute temporary path or elapsed time.
    reason = None
    if report.skipped:
        reason = str(report.longrepr[2] if isinstance(report.longrepr, tuple) else report.longrepr)
    if reason is not None:
        reason = reason.replace(str(Path.cwd()), '<source>')
    xfail = getattr(report, 'wasxfail', None)
    if xfail is not None:
        xfail = str(xfail).replace(str(Path.cwd()), '<source>')
    if isinstance(report, SubtestReport):
        _subtests[report.nodeid].append(report.outcome)
        label = report.head_line.replace(str(Path.cwd()), '<source>')
        _outcomes[report.nodeid].append(['subtest', report.when, report.outcome, reason, xfail, label])
    else:
        _reports[report.nodeid].append([report.when, report.outcome])
        _outcomes[report.nodeid].append(['parent', report.when, report.outcome, reason, xfail, None])


def pytest_sessionfinish(session, exitstatus):
    if _spec is not None:
        Path(_spec['receipt']).write_text(json.dumps({
            'collected': [item.nodeid for item in session.items],
            'full_collection': _full_collection,
            'reports': dict(_reports),
            'subtests': dict(_subtests),
            'outcomes': dict(_outcomes),
            'exitstatus': int(exitstatus),
            'source_sha256': _spec.get('source_sha256'),
        }), encoding='utf-8')
