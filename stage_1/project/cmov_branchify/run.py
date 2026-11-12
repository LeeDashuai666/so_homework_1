#!/usr/bin/env python3
"""Train, independently validate, optimize, and measure the real BOLT pass.

Requires only Python's standard library. Does not patch ELF bytes, require perf,
or change machine settings. Each workload family receives its own predicate
profile. A distribution shift on an already optimized ELF is reported separately.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import statistics
import struct
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
STAGE = HERE.parents[1]
FAMILIES = {
    'low95': (95, 'low'), 'high95': (95, 'high'),
    'uniform': (0, 'low'), 'sorted': (0, 'sorted'), 'low80': (80, 'low'),
}
COMMON = ['-reorder-blocks=ext-tsp', '-reorder-functions=cdsort',
          '-frame-opt=all', '-reg-reassign', '-peepholes=all',
          '-inline-small-functions', '-cmov-conversion', '-verify-cfg']


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def executable_hash(path):
    """Compare complete executable sections, including addresses and sizes."""
    data = Path(path).read_bytes()
    if data[:6] != b'\x7fELF\x02\x01':
        raise ValueError('Only little-endian ELF64 is supported')
    shoff = struct.unpack_from('<Q', data, 40)[0]
    entsize, count, strindex = struct.unpack_from('<HHH', data, 58)
    strings = struct.unpack_from('<IIQQQQIIQQ', data, shoff+entsize*strindex)
    names = data[strings[4]:strings[4]+strings[5]]
    h = hashlib.sha256()
    for i in range(count):
        section = struct.unpack_from('<IIQQQQIIQQ', data, shoff+entsize*i)
        if section[2] & 4:
            name = names[section[0]:].split(b'\0', 1)[0]
            h.update(name)
            h.update(struct.pack('<QQ', section[3], section[5]))
            h.update(data[section[4]:section[4]+section[5]])
    return h.hexdigest()


def summary(records, trials, seed=7381, draws=10000):
    times = {v: {r['trial']: r['elapsed_ns'] for r in records if r['variant'] == v}
             for v in ('off', 'on')}
    ratios = [times['off'][i]/times['on'][i] for i in range(trials)]
    rng = random.Random(seed)
    samples = sorted(statistics.median(rng.choices(ratios, k=trials)) for _ in range(draws))
    return {'median_paired_speedup': statistics.median(ratios),
            'ci95_low': samples[int(draws*.025)],
            'ci95_high': samples[int(draws*.975)-1],
            'off_median_ns': statistics.median(times['off'].values()),
            'on_median_ns': statistics.median(times['on'].values()),
            'trials': trials}


def predicate_profile(manifest, fdata):
    records = []
    edges = [x.split() for x in Path(fdata).read_text().splitlines()]
    def matches(profile_name, name):
        return profile_name == name or profile_name.rsplit('/', 1)[0] == name
    for site in manifest['sites']:
        counts = {True: 0, False: 0}
        for fields in edges:
            if len(fields) != 8 or fields[0] != '1' or fields[3] != '1':
                continue
            if not matches(fields[1], site['function']) or not matches(fields[4], site['function']):
                continue
            if int(fields[2], 16) != site['offset']:
                continue
            dest = int(fields[5], 16)
            if dest == site['true_offset']:
                counts[True] += int(fields[7])
            elif dest == site['false_offset']:
                counts[False] += int(fields[7])
        records.append({**site, 'true_count': counts[True], 'false_count': counts[False],
                        'validated': False, 'validation_speedup_lower': 0})
    return {k: manifest[k] for k in ('schema_version', 'binary_sha256', 'host_cpu')} | {'sites': records}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    local_bolt = HERE/'bin/llvm-bolt'
    local_workload = HERE/'workloads/search'
    parser.add_argument('--bolt', type=Path, default=local_bolt if local_bolt.exists() else STAGE/'build/bin/llvm-bolt')
    parser.add_argument('--workload', type=Path, default=local_workload if local_workload.exists() else STAGE/'results/cmov-feasibility-20261109/search-original')
    parser.add_argument('--output', type=Path, required=True, help='A new output directory')
    parser.add_argument('--trials', type=int, default=15)
    parser.add_argument('--calibration-trials', type=int, default=9)
    parser.add_argument('--families', nargs='+', choices=FAMILIES, default=list(FAMILIES))
    parser.add_argument('--quick', action='store_true', help='Smoke test; does not establish statistical performance acceptance')
    parser.add_argument('--skip-drift', action='store_true')
    args = parser.parse_args()
    if args.trials < 3 or args.calibration_trials < 3:
        parser.error('At least three paired trials are required')
    out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    bolt = args.bolt.resolve(); workload = args.workload.resolve()
    allowed = sorted(os.sched_getaffinity(0)); cpu = allowed[min(2, len(allowed)-1)]
    os.sched_setaffinity(0, {cpu})
    stamp = lambda: datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat()
    metadata = {'started_at': stamp(), 'machine': platform.machine(), 'kernel': platform.release(),
                'logical_cpu': cpu, 'allowed_cpus': allowed, 'quick': args.quick,
                'workload_sha256': sha(workload), 'bolt_sha256': sha(bolt),
                'timed_region': 'internal steady_clock lookup loop; excludes startup, data generation and profiling',
                'statistic': 'median paired ratios, percentile bootstrap 95% interval, exploratory unadjusted',
                'validation_rule': 'independent seed/size calibration, every lower confidence bound >= 1.02',
                'rejection_equivalence_margin': [0.95, 1.05],
                'input_scope': 'one separately trained and validated binary per declared workload family',
                'unseen_input_performance_guaranteed': False}
    cpuinfo = Path('/proc/cpuinfo')
    if cpuinfo.exists():
        metadata['cpu_model'] = next((s.split(':', 1)[1].strip() for s in cpuinfo.read_text().splitlines() if s.startswith('model name')), '')
    (out/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    commands = []; raw = []; results = []; correctness = []; artifacts = {}
    rng = random.Random(730911)
    def command(cmd, log, timeout=120):
        cmd = [str(x) for x in cmd]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        commands.append({'argv': cmd, 'exit_code': r.returncode, 'log': str(log.relative_to(out))})
        log.write_text(r.stdout+r.stderr)
        (out/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
        if r.returncode:
            raise RuntimeError(f'Command failed ({r.returncode}); see {log}: {r.stderr[-1200:]}')
        return r.stdout
    def run(binary, case):
        r = subprocess.run([str(binary), *map(str, case)], capture_output=True, text=True, timeout=60)
        if r.returncode:
            raise RuntimeError(r.stderr[-1500:])
        return json.loads(r.stdout)
    def pairs(family, phase, case_name, case, bins, trials):
        expected = run(workload, case)['checksum']
        for binary in bins.values():
            assert run(binary, case)['checksum'] == expected
        records = []
        for trial in range(trials):
            order = list(bins); rng.shuffle(order)
            for variant in order:
                result = run(bins[variant], case)
                assert result['checksum'] == expected, (family, phase, case_name, trial, variant)
                row = {'family': family, 'phase': phase, 'case': case_name,
                       'arguments': case, 'trial': trial, 'variant': variant, **result}
                records.append(row); raw.append(row)
                with (out/'raw.jsonl').open('a') as stream:
                    stream.write(json.dumps(row)+'\n')
        return summary(records, trials, draws=3000 if phase == 'calibration' else 10000)
    rounds = 200 if args.quick else 1000
    trials = 5 if args.quick else args.trials
    calibration_trials = 5 if args.quick else args.calibration_trials
    for family in args.families:
        hot, mode = FAMILIES[family]
        folder = out/family; folder.mkdir()
        profile = folder/'probe.fdata'; normal = folder/'normal.fdata'; manifest = folder/'sites.json'
        for kind, extra, fdata in [('normal', [], normal), ('probe', ['-cmov-branchify-probe', '-cmov-branchify-sites='+str(manifest)], profile)]:
            binary = folder/(kind+'.inst')
            command([bolt, workload, '-instrument', '-instrumentation-file='+str(fdata),
                     '-o', binary, *extra], folder/(kind+'-instrument.log'))
            training = [4096, 30, hot, 71, mode]
            expected = run(workload, training)['checksum']
            result = run(binary, training)
            assert result['checksum'] == expected
            correctness.append({'family': family, 'kind': kind, 'training_checksum': expected})
        data = predicate_profile(json.loads(manifest.read_text()), profile)
        data['workload_family'] = family
        predicate = folder/'candidate-profile.json'; predicate.write_text(json.dumps(data, indent=2)+'\n')
        off = folder/'off'; candidate = folder/'candidate'; on = folder/'on'
        common = ['-data='+str(normal), *COMMON]
        command([bolt, workload, '-o', off, *common], folder/'off.log')
        command([bolt, workload, '-o', candidate, *common,
                 '-cmov-branchify-candidate', '-cmov-branchify-profile='+str(predicate)], folder/'candidate.log')
        match = re.search(r'CMOV branchify: (\d+) candidates, (\d+) converted', (folder/'candidate.log').read_text())
        assert match
        converted = int(match[2]); calibration = []
        approved = False
        if converted:
            for size, seed in [(4096, 83), (8192, 1009)]:
                case = [size, rounds, hot, seed, mode]
                row = pairs(family, 'calibration', f'{size}-seed{seed}', case,
                            {'off': off, 'on': candidate}, calibration_trials)
                calibration.append(row)
            approved = all(row['ci95_low'] >= 1.02 for row in calibration)
        else:
            assert executable_hash(off) == executable_hash(candidate), family
        lower = min((row['ci95_low'] for row in calibration), default=0)
        for site in data['sites']:
            site['validated'] = approved
            site['validation_speedup_lower'] = lower if approved else 0
        data['validation'] = {'approved': approved, 'cases': calibration,
                              'independent_from_training': True, 'independent_from_final_test': True,
                              'candidate_sha256': sha(candidate)}
        validated = folder/'validated-profile.json'; validated.write_text(json.dumps(data, indent=2)+'\n')
        command([bolt, workload, '-o', on, *common, '-cmov-branchify',
                 '-cmov-branchify-profile='+str(validated)], folder/'on.log')
        identical = executable_hash(off) == executable_hash(on)
        if not approved:
            assert identical, (family, 'Rejected profile changed executable code')
        if approved:
            assert executable_hash(candidate) == executable_hash(on), 'Validated output changed candidate code'
        artifacts[family] = {'off': off, 'on': on, 'approved': approved}
        sizes = ([4096, 8192, 262144] if family == 'low95' else
                 [4096, 8192] if family == 'uniform' else [4096])
        for size in sizes:
            seed = 2029 if size == 8192 else 71
            n = max(100, rounds//2) if size > 8192 else rounds
            row = pairs(family, 'test', str(size), [size, n, hot, seed, mode],
                        {'off': off, 'on': on}, trials)
            row.update(family=family, size=size, approved=approved, executable_code_identical=identical,
                       off_sha256=sha(off), on_sha256=sha(on))
            row['acceptance_pass'] = (row['ci95_low'] >= 1.02 if approved else
                                      .95 <= row['ci95_low'] and row['ci95_high'] <= 1.05)
            results.append(row)
        # Outputs at small/odd sizes and zero rounds; performance profiles never
        # justify removing semantics for unobserved inputs.
        for size in (1, 2, 3, 31, 257, 4095):
            for count in (0, 2):
                case = [size, count, hot, 193, mode]
                expected = run(workload, case)['checksum']
                assert run(off, case)['checksum'] == expected == run(on, case)['checksum']
                correctness.append({'family': family, 'arguments': case, 'checksum': expected})
        print(f'{family}: candidate={converted}, validated={approved}, unchanged={identical}', flush=True)
    drift = None
    if not args.skip_drift and artifacts.get('low95', {}).get('approved'):
        bins = {v: artifacts['low95'][v] for v in ('off', 'on')}
        drift = pairs('low95', 'distribution-shift', 'uniform-new-input',
                      [4096, rounds, 0, 211, 'low'], bins, 3)
        drift['interpretation'] = 'Diagnostic only: an optimized biased-workload ELF can regress on a new uniform distribution.'
    metadata['completed_at'] = stamp()
    (out/'metadata.json').write_text(json.dumps(metadata, indent=2)+'\n')
    (out/'correctness.json').write_text(json.dumps(correctness, indent=2)+'\n')
    (out/'summary.json').write_text(json.dumps(results, indent=2)+'\n')
    (out/'distribution-shift.json').write_text(json.dumps(drift, indent=2)+'\n')
    for row in results:
        print(f"{row['family']:8s} n={row['size']:6d} {row['median_paired_speedup']:.3f}x "
              f"[{row['ci95_low']:.3f}, {row['ci95_high']:.3f}]", flush=True)
    if not args.quick and not all(row['acceptance_pass'] for row in results):
        raise SystemExit('At least one declared performance/equivalence check failed; all results retained.')


if __name__ == '__main__':
    main()
