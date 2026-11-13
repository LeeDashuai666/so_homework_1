#!/usr/bin/env python3
"""Check WSL guest PMU counters against known code; retain all observations."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import select
import shutil
import statistics as stats
import subprocess
import time

HERE = Path(__file__).resolve().parent
STAGE = HERE.parents[1]
HARDWARE = ('instructions:u', 'cycles:u', 'branches:u', 'branch-misses:u')
EVENTS = '{' + ','.join(HARDWARE) + '},task-clock'


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def topology():
    rows = []
    for cpu in sorted(os.sched_getaffinity(0)):
        row = {'cpu': cpu}
        base = Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        for key in ('core_id', 'physical_package_id', 'thread_siblings_list'):
            path = base / key
            row[key] = path.read_text().strip() if path.exists() else None
        rows.append(row)
    return rows


def median(rows, key):
    return stats.median(row[key] for row in rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--perf', default=os.environ.get('PERF_BIN'))
    parser.add_argument('--compiler', default='gcc')
    parser.add_argument('--cpu', type=int)
    parser.add_argument('--repeats', type=int, default=7)
    args = parser.parse_args()
    if args.repeats < 3:
        parser.error('at least three repeats are required')
    out = args.output.resolve()
    if out.exists():
        parser.error('choose a new output directory')
    perf = args.perf or shutil.which('perf')
    if not perf:
        perf = str(STAGE / '.tools/root/usr/lib/linux-tools-6.8.0-147/perf')
    perf = str(Path(shutil.which(perf) or perf).resolve())
    rows = topology()
    allowed = [row['cpu'] for row in rows]
    cpu = args.cpu if args.cpu is not None else allowed[min(2, len(allowed) - 1)]
    if cpu not in allowed:
        parser.error('CPU is outside the allowed affinity mask')
    selected = next(row for row in rows if row['cpu'] == cpu)
    sibling = next((row['cpu'] for row in rows if row['cpu'] != cpu
                    and row['core_id'] == selected['core_id']
                    and row['physical_package_id'] == selected['physical_package_id']), None)
    representatives = {}
    for row in rows:
        representatives.setdefault((row['physical_package_id'], row['core_id']), row['cpu'])
    other = next((value for value in representatives.values() if value not in (cpu, sibling)
                  and next(r for r in rows if r['cpu'] == value)['core_id'] != selected['core_id']), None)
    out.mkdir(parents=True)
    (out / 'raw').mkdir()
    shutil.copy2(HERE / 'README.md', out / 'criteria.md')
    shutil.copy2(HERE / 'run.py', out / 'run.py')
    commands = []

    def execute(cmd, timeout=60):
        cmd = list(map(str, cmd))
        commands.append(cmd)
        write_json(out / 'commands.json', commands)
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                              env={**os.environ, 'LC_ALL': 'C'})

    metadata = {'started_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'kernel': platform.release(), 'machine': platform.machine(), 'guest_topology': rows,
                'selected_guest_cpu': cpu, 'guest_sibling': sibling, 'guest_other_core': other,
                'guest_affinity_is_not_host_physical_isolation': True, 'repeats': args.repeats,
                'perf_path': perf, 'thresholds_defined_in': str(HERE / 'README.md')}
    for name, cmd in [('lscpu', ['lscpu']), ('perf_version', [perf, '--version']),
                      ('compiler', [args.compiler, '--version'])]:
        result = execute(cmd)
        (out / (name + '.txt')).write_text(result.stdout + result.stderr)
    powershell = shutil.which('powershell.exe')
    if powershell:
        query = ('Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,'
                 'NumberOfLogicalProcessors,ThreadCount | ConvertTo-Json -Compress')
        try:
            result = execute([powershell, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', query], 20)
            (out / 'windows-cpu.txt').write_text(result.stdout + result.stderr)
            if result.returncode == 0:
                metadata['windows_cpu'] = json.loads(result.stdout)
        except (subprocess.TimeoutExpired, json.JSONDecodeError) as error:
            metadata['windows_cpu_query_error'] = str(error)
        settings_query = ('if (Test-Path "$env:USERPROFILE\\.wslconfig") { '
                          'Get-Content "$env:USERPROFILE\\.wslconfig" | '
                          'Select-String -Pattern "^\\s*(processors|memory)\\s*=" | '
                          'ForEach-Object { $_.Line } }')
        try:
            result = execute([powershell, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', settings_query], 20)
            (out / 'wsl-config-cpu-memory.txt').write_text(result.stdout + result.stderr)
        except subprocess.TimeoutExpired as error:
            metadata['wsl_config_query_error'] = str(error)
    write_json(out / 'metadata.json', metadata)
    source = out / 'probe.c'
    shutil.copy2(HERE / 'probe.c', source)
    binary = out / 'probe'
    result = execute([args.compiler, '-O2', '-g', '-std=c11', '-Wall', '-Wextra', '-Werror',
                      '-fno-omit-frame-pointer', '-fno-pie', '-no-pie', source, '-o', binary])
    (out / 'build.log').write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError('compiler failed; see build.log')
    result = execute(['objdump', '-d', '-Mintel', binary])
    (out / 'probe.asm').write_text(result.stdout)
    metadata['probe_sha256'] = hashlib.sha256(binary.read_bytes()).hexdigest()
    rng = random.Random(20261110)
    observations = []

    def measure(phase, mode, n, run_cpu=cpu, trial=0, condition='idle'):
        stem = f'{len(observations):03d}-{phase}-{mode}-{n}-cpu{run_cpu}-{condition}'
        path = out / 'raw' / (stem + '.csv')
        result = execute(['taskset', '-c', run_cpu, perf, 'stat', '--no-big-num', '-x', ';',
                          '-o', path, '-e', EVENTS, '--', binary, mode, n])
        (out / 'raw' / (stem + '.stdout')).write_text(result.stdout)
        (out / 'raw' / (stem + '.stderr')).write_text(result.stderr)
        row = {'phase': phase, 'mode': mode, 'n': n, 'cpu': run_cpu, 'trial': trial,
               'condition': condition, 'returncode': result.returncode, 'raw_csv': path.name}
        for line in result.stdout.splitlines():
            if line.startswith('{'):
                row.update(json.loads(line))
        counters = {}
        if path.exists():
            for line in path.read_text().splitlines():
                fields = [value.strip() for value in line.split(';')]
                if len(fields) < 5 or fields[2] not in HARDWARE + ('task-clock:u', 'task-clock'):
                    continue
                try:
                    counters[fields[2]] = {'value': float(fields[0]), 'unit': fields[1],
                                           'runtime_ns': float(fields[3]), 'running_percent': float(fields[4])}
                except ValueError:
                    counters[fields[2]] = {'error': line}
        row['counters'] = counters
        observations.append(row)
        with (out / 'raw.jsonl').open('a') as stream:
            stream.write(json.dumps(row) + '\n')
        if result.returncode or any(key not in counters or 'value' not in counters[key] for key in HARDWARE):
            raise RuntimeError(f'perf measurement failed; see {stem}')
        if mode in ('count', 'padded') and row.get('checksum') != n:
            raise RuntimeError('loop checksum mismatch')
        if row.get('cpu_before') != run_cpu or row.get('cpu_after') != run_cpu:
            raise RuntimeError('guest affinity mismatch')
        return row

    # Warm up executable and CPU before collecting data; never time compilation.
    execute(['taskset', '-c', cpu, binary, 'count', 100000000])
    tasks = [('hello', 0), ('count', 0), ('sleep', 500)]
    tasks += [(mode, n) for mode in ('count', 'padded') for n in (100000000, 200000000, 400000000)]
    tasks += [(mode, n) for mode in ('branch-fixed', 'branch-random') for n in (20000000, 40000000)]
    for trial in range(args.repeats):
        order = tasks.copy()
        rng.shuffle(order)
        for mode, n in order:
            measure('reference', mode, n, trial=trial)
        print(f'reference repeat {trial + 1}/{args.repeats}', flush=True)

    for trial in range(args.repeats):
        order = list(representatives.values())
        rng.shuffle(order)
        for test_cpu in order:
            measure('cross-cpu', 'count', 200000000, test_cpu, trial)

    for trial in range(args.repeats):
        conditions = [('idle', None)] + ([('guest-sibling', sibling)] if sibling is not None else [])
        conditions += [('guest-other-core', other)] if other is not None else []
        rng.shuffle(conditions)
        for condition, stress_cpu in conditions:
            stress = None
            try:
                if stress_cpu is not None:
                    cmd = ['taskset', '-c', str(stress_cpu), str(binary), 'busy']
                    commands.append(cmd)
                    stress = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                    if not select.select([stress.stdout], [], [], 5)[0] or stress.stdout.readline().strip() != 'ready':
                        raise RuntimeError('interference worker did not start')
                    time.sleep(0.03)
                measure('interference', 'count', 400000000, trial=trial, condition=condition)
            finally:
                if stress is not None:
                    stress.terminate()
                    try:
                        stress.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        stress.kill()
                        stress.wait()
        print(f'interference repeat {trial + 1}/{args.repeats}', flush=True)

    sample = execute(['taskset', '-c', cpu, perf, 'record', '-q', '-e', 'cycles:u', '-F', '997',
                      '-o', out / 'perf.data', '--', binary, 'count', 1600000000])
    (out / 'perf-record.stdout').write_text(sample.stdout)
    (out / 'perf-record.stderr').write_text(sample.stderr)
    sampling = {'record_returncode': sample.returncode}
    if sample.returncode == 0:
        report = execute([perf, 'report', '--stdio', '--no-children', '--percent-limit', '1',
                          '-i', out / 'perf.data'])
        (out / 'perf-report.txt').write_text(report.stdout + report.stderr)
        matches = re.findall(r'([\d.]+)%[^\n]*\bcounted_loop\b', report.stdout)
        sampling.update({'report_returncode': report.returncode,
                         'known_hotspot_percent': max(map(float, matches), default=0)})

    def group(phase, mode=None, n=None, **where):
        return [row for row in observations if row['phase'] == phase
                and (mode is None or row['mode'] == mode) and (n is None or row['n'] == n)
                and all(row.get(key) == value for key, value in where.items())]

    def counter_median(items, key):
        return stats.median(row['counters'][key]['value'] for row in items)

    checks = []

    def check(name, passed, detail):
        checks.append({'check': name, 'passed': bool(passed), 'detail': detail})

    min_running = min(row['counters'][event]['running_percent'] for row in observations for event in HARDWARE)
    check('valid_grouped_counters', min_running >= 99, {'minimum_running_percent': min_running})
    slopes = []
    all_errors = []
    cycle_ratios = []
    for mode, expected_insns in (('count', 3), ('padded', 11)):
        for low, high in ((100000000, 200000000), (200000000, 400000000)):
            before, after = group('reference', mode, low), group('reference', mode, high)
            insns = (counter_median(after, 'instructions:u') - counter_median(before, 'instructions:u')) / (high - low)
            branches = (counter_median(after, 'branches:u') - counter_median(before, 'branches:u')) / (high - low)
            all_errors += [abs(insns / expected_insns - 1), abs(branches - 1)]
            cycles_ratio = counter_median(after, 'cycles:u') / counter_median(before, 'cycles:u')
            cycle_ratios.append(cycles_ratio)
            slopes.append({'mode': mode, 'low_n': low, 'high_n': high,
                           'instructions_per_extra_iteration': insns,
                           'branches_per_extra_iteration': branches, 'cycles_ratio': cycles_ratio})
    check('known_instruction_and_branch_slopes', max(all_errors) <= .01, slopes)
    check('cycles_scale_with_doubled_work', all(1.5 <= ratio <= 2.5 for ratio in cycle_ratios), cycle_ratios)
    differences = []
    for n in (100000000, 200000000, 400000000):
        delta = counter_median(group('reference', 'padded', n), 'instructions:u') - counter_median(group('reference', 'count', n), 'instructions:u')
        differences.append({'n': n, 'extra_instructions_per_iteration': delta / n})
    check('eight_added_nops_count_as_eight', all(abs(row['extra_instructions_per_iteration'] / 8 - 1) <= .01 for row in differences), differences)
    coefficients = []
    for mode in ('count', 'padded'):
        for n in (100000000, 200000000, 400000000):
            values = [row['counters']['instructions:u']['value'] for row in group('reference', mode, n)]
            coefficients.append({'mode': mode, 'n': n, 'instructions_cv': stats.pstdev(values) / stats.mean(values)})
    check('repeatable_instruction_counts', max(row['instructions_cv'] for row in coefficients) <= .01, coefficients)
    branch = {}
    branch_slopes = {}
    for mode in ('branch-fixed', 'branch-random'):
        items = group('reference', mode, 40000000)
        branch[mode] = stats.median(row['counters']['branch-misses:u']['value'] / row['counters']['branches:u']['value'] for row in items)
        branch_slopes[mode] = (counter_median(items, 'branches:u') - counter_median(group('reference', mode, 20000000), 'branches:u')) / 20000000
    check('controlled_branch_misses', branch['branch-random'] - branch['branch-fixed'] >= .05
          and all(abs(slope / 2 - 1) <= .01 for slope in branch_slopes.values()),
          {'branch_miss_fractions': branch, 'branches_per_extra_iteration': branch_slopes})
    sleepers = group('reference', 'sleep', 500)
    sleep_cycles_ratio = counter_median(sleepers, 'cycles:u') / counter_median(group('reference', 'count', 400000000), 'cycles:u')
    check('sleep_is_not_counted_as_busy_execution', median(sleepers, 'thread_cpu_ns') < 25000000 and sleep_cycles_ratio < .05,
          {'sleep_wall_ns': median(sleepers, 'wall_ns'), 'sleep_thread_cpu_ns': median(sleepers, 'thread_cpu_ns'),
           'sleep_cycles_to_long_compute_ratio': sleep_cycles_ratio})
    cross = [{'cpu': run_cpu, 'instructions': counter_median(group('cross-cpu', cpu=run_cpu), 'instructions:u'),
              'wall_ns': median(group('cross-cpu', cpu=run_cpu), 'wall_ns')}
             for run_cpu in representatives.values()]
    reference_count = counter_median(group('reference', 'count', 200000000), 'instructions:u')
    check('counter_consistency_across_guest_cores', all(abs(row['instructions'] / reference_count - 1) <= .01 for row in cross), cross)
    interference = []
    base = group('interference', condition='idle')
    for condition in dict.fromkeys(row['condition'] for row in group('interference')):
        items = group('interference', condition=condition)
        interference.append({'condition': condition, 'instructions': counter_median(items, 'instructions:u'),
                             'cycles': counter_median(items, 'cycles:u'), 'wall_ns': median(items, 'wall_ns'),
                             'wall_ratio_to_idle': median(items, 'wall_ns') / median(base, 'wall_ns'),
                             'thread_cpu_ns': median(items, 'thread_cpu_ns')})
    base_count = counter_median(base, 'instructions:u')
    check('other_process_instructions_not_charged_to_target', all(abs(row['instructions'] / base_count - 1) <= .01 for row in interference), interference)
    checks.append({'check': 'optional_cycles_sampling_known_hotspot',
                   'passed': sampling.get('known_hotspot_percent', 0) >= 80, 'optional': True, 'detail': sampling})
    aggregates = []
    for mode, n in tasks:
        items = group('reference', mode, n)
        aggregates.append({'mode': mode, 'n': n, 'wall_ns': median(items, 'wall_ns'),
                           'thread_cpu_ns': median(items, 'thread_cpu_ns'),
                           **{key: counter_median(items, key) for key in HARDWARE}})
    summary = {'required_checks_passed': all(row['passed'] for row in checks if not row.get('optional')),
               'perf_stat_runs': len(observations), 'checks': checks, 'reference_medians': aggregates,
               'claim_scope': 'listed guest per-process perf stat events on this configuration; not bare-metal equivalence',
               'unvalidated': ['LBR', 'cache events', 'precise call graphs', 'absolute bare-metal counter accuracy']}
    write_json(out / 'summary.json', summary)
    metadata['completed_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    write_json(out / 'metadata.json', metadata)
    write_json(out / 'commands.json', commands)
    for row in checks:
        print(('PASS' if row['passed'] else 'FAIL') + ': ' + row['check'], flush=True)
    print(f'Completed {len(observations)} perf stat runs: {out}', flush=True)
    return 0 if summary['required_checks_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
