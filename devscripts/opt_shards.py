"""Experimental isolated core-test sharding; no additional runtime dependencies."""
import collections
import concurrent.futures
import hashlib
import importlib.metadata
import json
import os
import platform
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from devscripts.process_lifecycle import run_process
from devscripts.strict_json import load_file
from devscripts.opt_source import manifest_digest, materialize_commit, verify_snapshot


def partition(nodeids, workers, *, module_costs=None):
    """Keep each test module together; greedily balance by collected test count."""
    if not 1 <= workers <= 32 or not nodeids or len(set(nodeids)) != len(nodeids):
        raise ValueError('invalid worker count or empty/duplicate collection')
    groups = collections.defaultdict(list)
    for nodeid in sorted(nodeids):
        groups[nodeid.split('::', 1)[0]].append(nodeid)
    if module_costs is None:
        module_costs = {module: len(ids) for module, ids in groups.items()}
    if (set(module_costs) != set(groups) or any(type(cost) is not int or not 1 <= cost <= 10**15 for cost in module_costs.values())):
        raise ValueError('invalid experimental module costs')
    shards = [[] for _ in range(min(workers, len(groups)))]
    loads = [0] * len(shards)
    for module, ids in sorted(groups.items(), key=lambda item: (-module_costs[item[0]], item[0])):
        index = min(range(len(shards)), key=lambda i: (loads[i], i))
        shards[index].extend(ids)
        loads[index] += module_costs[module]
    return [sorted(shard) for shard in shards]


def assigned_modules(nodeids, source_paths):
    """Only collect modules present in the immutable source generation."""
    modules = sorted({nodeid.split('::', 1)[0] for nodeid in nodeids})
    if not modules or any(module not in source_paths or not module.endswith('.py') for module in modules):
        raise ValueError('unrecognised test module in assignment')
    return modules


def validate_receipt(receipt, *, executed=True):
    fields = {'schema', 'collected', 'full_collection', 'exitstatus', 'source_sha256',
              'reports', 'subtests', 'outcomes', 'environment_sha256'}
    if not isinstance(receipt, dict) or set(receipt) != fields or type(receipt['schema']) is not int or receipt['schema'] != 1:
        raise ValueError('invalid receipt schema')
    if type(receipt['exitstatus']) is not int or receipt['exitstatus'] != 0:
        raise ValueError('invalid receipt exit status')
    for field in ('source_sha256', 'environment_sha256'):
        digest = receipt[field]
        if field == 'source_sha256' and digest is None:
            continue
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise ValueError(f'invalid {field}')
    for field in ('collected', 'full_collection'):
        ids = receipt[field]
        if not isinstance(ids, list) or any(not isinstance(nodeid, str) or not nodeid for nodeid in ids) or len(set(ids)) != len(ids):
            raise ValueError('invalid collection identities')
    ids = set(receipt['collected'])
    if not ids or ids != set(receipt['full_collection']):
        raise ValueError('collection mismatch')
    reports, subtests, outcomes = (receipt[key] for key in ('reports', 'subtests', 'outcomes'))
    if any(not isinstance(mapping, dict) for mapping in (reports, subtests, outcomes)):
        raise ValueError('invalid report mappings')
    if not executed:
        if reports or subtests or outcomes:
            raise ValueError('unexpected execution during collection')
        return
    if set(reports) != ids or set(outcomes) != ids or not set(subtests).issubset(ids):
        raise ValueError('missing or unexpected report identities')
    for nodeid in ids:
        phases = reports[nodeid]
        records = outcomes[nodeid]
        children = subtests.get(nodeid, [])
        if not isinstance(phases, list) or not isinstance(records, list) or not isinstance(children, list):
            raise ValueError('invalid report arrays')
        if any(not isinstance(p, list) or len(p) != 2 or p[0] not in ('setup', 'call', 'teardown')
               or p[1] not in ('passed', 'skipped') for p in phases):
            raise ValueError('invalid lifecycle phase')
        if [p[0] for p in phases] != (['setup', 'call', 'teardown'] if phases and phases[0] == ['setup', 'passed']
                                      else ['setup', 'teardown']):
            raise ValueError('invalid lifecycle order')
        if len(phases) == 2 and phases[0] != ['setup', 'skipped']:
            raise ValueError('invalid setup outcome')
        parents, observed_children = [], []
        for record in records:
            if (not isinstance(record, list) or len(record) != 6 or record[0] not in ('parent', 'subtest')
                    or record[1] not in ('setup', 'call', 'teardown') or record[2] not in ('passed', 'skipped')
                    or any(value is not None and not isinstance(value, str) for value in record[3:5])):
                raise ValueError('invalid outcome record')
            kind, phase, outcome, _, _, identity = record
            if kind == 'parent':
                if identity is not None:
                    raise ValueError('unexpected parent identity')
                parents.append([phase, outcome])
            else:
                if (phase != 'call' or not isinstance(identity, list) or len(identity) != 3
                        or type(identity[0]) is not int or identity[0] != len(observed_children)
                        or not isinstance(identity[1], str) or not isinstance(identity[2], list)
                        or any(not isinstance(pair, list) or len(pair) != 2
                               or any(not isinstance(value, str) for value in pair) for pair in identity[2])
                        or len({pair[0] for pair in identity[2]}) != len(identity[2])):
                    raise ValueError('invalid subtest identity')
                if parents != [['setup', 'passed']]:
                    raise ValueError('subtest outside call phase')
                observed_children.append(outcome)
        if parents != phases or observed_children != children:
            raise ValueError(f'inconsistent outcome details: {nodeid}')


def verify_receipts(expected, receipts, *, source_digest=None, environment_digest=None):
    if len(expected) != len(receipts):
        raise ValueError('missing or extra shard receipts')
    full = [nodeid for ids in expected for nodeid in ids]
    if not full or len(set(full)) != len(full):
        raise ValueError('empty or overlapping shard assignments')
    for ids, receipt in zip(expected, receipts, strict=True):
        validate_receipt(receipt)
        if source_digest is not None and receipt['source_sha256'] != source_digest:
            raise ValueError('source manifest mismatch')
        if environment_digest is not None and receipt['environment_sha256'] != environment_digest:
            raise ValueError('execution environment mismatch')
        if sorted(receipt['collected']) != sorted(ids):
            raise ValueError('collection mismatch')


def outcome_ledger(receipts):
    ledger = {}
    for receipt in receipts:
        validate_receipt(receipt)
        for nodeid, records in receipt['outcomes'].items():
            if nodeid in ledger:
                raise ValueError('duplicate outcome identity')
            ledger[nodeid] = records
    return ledger


def verify_outcome_parity(reference, receipts):
    """Compare observed identities, phases, outcomes, reasons and subtest order."""
    if any(receipt['environment_sha256'] != reference['environment_sha256'] for receipt in receipts):
        raise ValueError('serial/parallel environment mismatch')
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
    attempts = []
    attempt_lock = threading.Lock()
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

            def invoke_inner(name, assigned=None, *, collect_only=False):
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
                    proc = run_process(command, cwd=checkout, env=env, timeout=900)
                    if proc.returncode:
                        raise ValueError(f'{name}: pytest exit {proc.returncode}')
                    receipt = load_file(result)
                finally:
                    shutil.rmtree(checkout)
                return receipt

            def invoke(name, assigned=None, *, collect_only=False):
                invocation_started = time.monotonic()
                status = 'failed'
                try:
                    receipt = invoke_inner(name, assigned, collect_only=collect_only)
                    validate_receipt(receipt, executed=not collect_only)
                    status = 'completed'
                    return receipt, round(time.monotonic() - invocation_started, 3)
                except KeyboardInterrupt:
                    status = 'interrupted'
                    raise
                finally:
                    with attempt_lock:
                        attempts.append({'name': name, 'status': status,
                                         'elapsed_seconds': round(time.monotonic() - invocation_started, 3)})

            # A full serial oracle already supplies the coordinator's manifest.
            # Do not pay for a separate global collection in verification mode.
            collection, reference_elapsed = invoke('reference' if verify else 'collection', collect_only=not verify)
            validate_receipt(collection, executed=verify)
            if collection.get('source_sha256') != source_digest or collection.get('exitstatus') != 0:
                raise ValueError('invalid collection receipt')
            baseline = collection['collected']
            shards = partition(baseline, workers)
            if verify:
                verify_receipts([baseline], [collection], source_digest=source_digest)
            parallel_started = time.monotonic()
            with concurrent.futures.ThreadPoolExecutor(max_workers=len(shards)) as pool:
                receipts = [receipt for receipt, _ in pool.map(lambda pair: invoke(f'shard-{pair[0]}', pair[1]), enumerate(shards))]
            verify_receipts(shards, receipts, source_digest=source_digest,
                            environment_digest=collection['environment_sha256'])
            parallel_elapsed = round(time.monotonic() - parallel_started, 3)
            outcome_digest = verify_outcome_parity(collection, receipts) if verify else None
            if subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, cwd=root).strip() != head or subprocess.check_output(['git', 'status', '--porcelain'], cwd=root).strip():
                raise ValueError('checkout changed during execution')
            summary = {'head': head, 'source_sha256': source_digest, 'workers': len(shards), 'tests': len(baseline),
                       'collection_sha256': hashlib.sha256(json.dumps(sorted(baseline)).encode()).hexdigest(),
                       'shard_sizes': list(map(len, shards)),
                       'module_counts': [len(assigned_modules(ids, source_paths)) for ids in shards],
                       'outcome_parity_verified': verify, 'outcome_sha256': outcome_digest,
                       'environment_sha256': collection['environment_sha256'],
                       'attempts': sorted(attempts, key=lambda item: item['name']),
                       'reference_or_collection_seconds': reference_elapsed,
                       'parallel_phase_seconds': parallel_elapsed}
        summary['elapsed_seconds'] = round(time.monotonic() - started, 3)
        print('OPT source/coverage receipt: ' + json.dumps(summary, sort_keys=True), flush=True)
        return 0
    except (KeyboardInterrupt, OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        interrupted = isinstance(error, KeyboardInterrupt)
        print('OPT interrupted' if interrupted else f'OPT failed: {error}', file=sys.stderr)
        print('OPT failure receipt: ' + json.dumps({'head': head, 'outcome_parity_verified': False,
              'status': 'interrupted' if interrupted else 'failed',
                                                    'elapsed_seconds': round(time.monotonic() - started, 3),
                                                    'attempts': sorted(attempts, key=lambda item: item['name'])}, sort_keys=True), file=sys.stderr, flush=True)
        return 130 if interrupted else 1


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
        _spec = load_file(Path(path))


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
        from _pytest._io.saferepr import saferepr

        identity = [len(_subtests[report.nodeid]), saferepr(report.context.msg),
                    [[key, saferepr(value)] for key, value in report.context.kwargs.items()]]
        _subtests[report.nodeid].append(report.outcome)
        _outcomes[report.nodeid].append(['subtest', report.when, report.outcome, reason, xfail, identity])
    else:
        _reports[report.nodeid].append([report.when, report.outcome])
        _outcomes[report.nodeid].append(['parent', report.when, report.outcome, reason, xfail, None])


def environment_digest(config):
    """Observed runtime and package/plugin identities; not dependency-byte attestation."""
    packages = sorted((dist.metadata.get('Name') or '', dist.metadata.get('Version') or '')
                      for dist in importlib.metadata.distributions())
    plugins = sorted((dist.project_name, dist.version) for _, dist in config.pluginmanager.list_plugin_distinfo())
    data = {'python': sys.version, 'implementation': platform.python_implementation(),
            'platform': sys.platform, 'machine': platform.machine(),
            'packages': packages, 'plugins': plugins}
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=True).encode('ascii')).hexdigest()


def pytest_sessionfinish(session, exitstatus):
    if _spec is not None:
        Path(_spec['receipt']).write_text(json.dumps({
            'schema': 1,
            'collected': [item.nodeid for item in session.items],
            'full_collection': _full_collection,
            'reports': dict(_reports),
            'subtests': dict(_subtests),
            'outcomes': dict(_outcomes),
            'exitstatus': int(exitstatus),
            'source_sha256': _spec.get('source_sha256'),
            'environment_sha256': environment_digest(session.config),
        }), encoding='utf-8')
