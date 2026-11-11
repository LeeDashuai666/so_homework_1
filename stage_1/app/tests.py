#!/usr/bin/env python3
"""Semantic, rejection, and provenance checks for the actual BOLT pass."""
import argparse
import copy
import json
from pathlib import Path
import subprocess

from run import HERE, STAGE, executable_hash


def main():
    p = argparse.ArgumentParser(description=__doc__)
    local_bolt = HERE/'bin/llvm-bolt'
    p.add_argument('--bolt', type=Path, default=local_bolt if local_bolt.exists() else STAGE/'build/bin/llvm-bolt')
    p.add_argument('--workload', type=Path, default=HERE/'workloads/search')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--cc', default='/usr/bin/gcc')
    args = p.parse_args(); out = args.output.resolve(); out.mkdir(parents=True, exist_ok=False)
    bolt = args.bolt.resolve(); workload = args.workload.resolve(); checks = []
    def run(cmd, name, succeeds=True, contains=None):
        r = subprocess.run([str(x) for x in cmd], capture_output=True, text=True, timeout=120)
        (out/(name+'.log')).write_text(r.stdout+r.stderr)
        assert (r.returncode == 0) == succeeds, (name, r.returncode, r.stderr[-1500:])
        if not succeeds:
            assert r.returncode > 0 and 'Stack dump:' not in r.stderr, name
        if contains: assert contains in r.stdout+r.stderr, name
        checks.append({'case': name, 'passed': True})
        return r.stdout
    sites = out/'sites.json'; off = out/'off'
    run([bolt, workload, '-o', out/'enumerated', '-cmov-branchify-sites='+str(sites), '-verify-cfg'], 'enumerate')
    run([bolt, workload, '-o', off, '-lite=0', '-keep-nops=false', '-verify-cfg'], 'disabled-baseline')
    manifest = json.loads(sites.read_text()); assert manifest['sites']
    base = copy.deepcopy(manifest)
    for site in base['sites']:
        site.update(true_count=100000, false_count=0, validated=True, validation_speedup_lower=1.5)
    run([bolt, workload, '-o', out/'bad', '-cmov-branchify'], 'missing-profile', False, 'requires -cmov-branchify-profile')
    run([bolt, workload, '-o', out/'bad', '-cmov-branchify-probe'], 'probe-without-instrument', False, 'requires -instrument')
    variants = []
    for name in ('wrong-hash', 'wrong-cpu', 'negative-count', 'duplicate',
                 'unvalidated', 'unbiased', 'too-few', 'size-mismatch', 'empty'):
        data = copy.deepcopy(base); invalid = name in ('wrong-hash', 'wrong-cpu', 'negative-count', 'duplicate')
        if name == 'wrong-hash': data['binary_sha256'] = '0'*64
        elif name == 'wrong-cpu': data['host_cpu'] = 'unit-incompatible-cpu'
        elif name == 'duplicate': data['sites'].append(copy.deepcopy(data['sites'][0]))
        elif name == 'empty': data['sites'] = []
        else:
            for site in data['sites']:
                if name == 'negative-count': site['true_count'] = -1
                elif name == 'unvalidated': site['validated'] = False
                elif name == 'unbiased': site.update(true_count=50000, false_count=50000)
                elif name == 'too-few': site.update(true_count=3, false_count=0)
                elif name == 'size-mismatch': site['group_size'] = 3 if site['group_size'] == 2 else 2
        profile = out/(name+'.json'); profile.write_text(json.dumps(data)+'\n')
        binary = out/name
        run([bolt, workload, '-o', binary, '-cmov-branchify',
             '-cmov-branchify-profile='+str(profile), '-lite=0', '-keep-nops=false',
             '-verify-cfg'], name, not invalid)
        if not invalid:
            assert executable_hash(binary) == executable_hash(off), name
            variants.append({'case': name, 'executable_code_identical': True})
    semantic = out/'semantic-original'
    run([args.cc, '-O2', '-g', '-Wl,--emit-relocs', HERE/'tests/semantic_driver.c',
         HERE/'tests/semantic_cases.S', '-o', semantic], 'build-semantics')
    expected = json.loads(run([semantic], 'semantic-original'))
    probe = out/'semantic-probe'; manifest_path = out/'semantic-sites.json'
    run([bolt, semantic, '-o', probe, '-instrument', '-cmov-branchify-probe',
         '-cmov-branchify-sites='+str(manifest_path),
         '-instrumentation-file='+str(out/'semantic.fdata')], 'semantic-instrument')
    actual = json.loads(run([probe], 'semantic-probe'))
    assert actual == expected and actual['checks'] == 300000
    names = {s['function'] for s in json.loads(manifest_path.read_text())['sites']}
    assert {'sem_pair', 'sem_chain'} <= names, names
    assert not names & {'sem_width32', 'sem_memory', 'sem_mixed', 'sem_internal_entry', 'sem_external_entry'}, names
    checks.append({'case': '300000 semantic output/flags/dependency checks', 'passed': True})
    checks.append({'case': 'unsupported widths, memory, mixed predicates and internal/external entries rejected', 'passed': True})
    unwind = out/'unwind-original'
    run([args.cc, '-O2', '-g', '-rdynamic', '-Wl,--emit-relocs',
         HERE/'tests/unwind_driver.c', HERE/'tests/unwind_subject.S', '-ldl', '-o', unwind], 'build-unwind')
    original = json.loads(run([unwind], 'unwind-original'))
    unwind_sites = out/'unwind-sites.json'
    run([bolt, unwind, '-o', out/'unwind-dump', '-cmov-branchify-sites='+str(unwind_sites),
         '-lite=0'], 'unwind-enumerate')
    data = json.loads(unwind_sites.read_text())
    assert any(s['function'] == 'unwind_subject' for s in data['sites'])
    for site in data['sites']:
        site.update(true_count=100000, false_count=0, validated=True, validation_speedup_lower=1.5)
    profile = out/'unwind-profile.json'; profile.write_text(json.dumps(data)+'\n')
    run([bolt, unwind, '-o', out/'unwind-on', '-cmov-branchify',
         '-cmov-branchify-profile='+str(profile), '-lite=0', '-verify-cfg',
         '-update-debug-sections'], 'unwind-optimize', contains='1 converted')
    actual_unwind = json.loads(run([out/'unwind-on'], 'unwind-on'))
    assert original == actual_unwind == {'converted_frame_found': 1}
    (out/'result.json').write_text(json.dumps({'checks': checks, 'rejection_code_identity': variants,
                                            'semantic_result': actual}, indent=2)+'\n')
    print(f'{len(checks)} check groups, 300000 semantic cases: PASS')


if __name__ == '__main__': main()
