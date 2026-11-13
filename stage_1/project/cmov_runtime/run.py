#!/usr/bin/env python3
"""Unified final-ELF flag-off/flag-on benchmark with per-load protection checks."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import json
import math
import os
from pathlib import Path
import random
import statistics
import subprocess

from build import sha, write, median_ci

CASES = ['low95','high95','low80','uniform','sorted','shift','long-recovery',
         'fast-shift','short-uniform1','short-uniform4','short-uniform16',
         'short-low95','short-uniform63','threshold64','threshold65','fast-shift1',
         'low50','hot-prefix','hot-suffix','shift-high','striped',
         'threshold511','threshold512','threshold513','early-shift','calibration-alias']
SHORT = {'short-uniform1':1,'short-uniform4':4,'short-uniform16':16,
         'short-low95':16,'short-uniform63':63,'threshold64':64,'threshold65':65,
         'fast-shift':256,'fast-shift1':64,'threshold511':511}
BOUNDARIES = [(0,'low95',8192),(0,'uniform',8192),(0,'short-uniform1',8192),
              (1,'low95',8),(1,'uniform',4),(1,'short-uniform1',512),(64,'low95',4)]


def analyze(out):
    protocol=json.loads((out/'protocol.json').read_text())
    records=[json.loads(s) for s in (out/'raw.jsonl').read_text().splitlines()]
    results=[]
    for size in protocol['sizes']:
        for case in protocol['cases']:
            if protocol.get('cells') and not any(c['size']==size and c['case']==case for c in protocol['cells']):
                continue
            row={'size':size,'case':case}
            for kind in ('pair','null'):
                data=[r for r in records if (r['size'],r['case'],r['kind'])==(size,case,kind)]
                ratios=[sum(x['elapsed_ns'] for x in r['runs'] if x['label']=='A')/
                        sum(x['elapsed_ns'] for x in r['runs'] if x['label']=='B') for r in data]
                row[kind]={'blocks':len(ratios),'median_speedup':statistics.median(ratios),
                           'ci95':median_ci(ratios),'ratios':ratios}
            ratio=row['pair']['median_speedup']
            row['median_runtime_increase_percent']=(1/ratio-1)*100
            row['median_within_one_percent_reference']=ratio>=1/1.01
            row['positive_target']=case=='low95' and size in (4096,8192)
            row['positive_ci_lower_at_least_two_percent']=row['pair']['ci95']['low']>=1.02
            on=[x for r in records if (r['size'],r['case'],r['kind'])==(size,case,'pair')
                for x in r['runs'] if x['variant']=='on']
            row['entered_calls']=sum(x['entered'] for x in on)
            row['active_batches']=sum(x['active_batches'] for x in on)
            results.append(row)
    write(out/'summary.json',results)
    decision={'integrated_bolt_runtime':True,'separate_flag_off_on_elfs':True,
              'cells':len(results),'measured_executions':len(records)*4,
              'all_measured_outputs_passed':True,
              'median_within_one_percent_reference':sum(r['median_within_one_percent_reference'] for r in results),
              'positive_targets_with_ci_at_least_two_percent':sum(r['positive_target'] and r['positive_ci_lower_at_least_two_percent'] for r in results),
              'worst_median_runtime_increase_percent':max(r['median_runtime_increase_percent'] for r in results),
              'universal_future_input_bound_proven':False,
              'teacher_reference_is_approximate_not_all_simultaneous_ci_gate':True}
    write(out/'decision.json',decision)
    for r in results:
        ci=r['pair']['ci95'];hi=f"{ci['high']:.4f}" if ci['high'] is not None else 'unbounded';print(f"{r['size']} {r['case']:20} {r['pair']['median_speedup']:.4f} [{ci['low']:.4f},{hi}] loss={r['median_runtime_increase_percent']:.3f}%",flush=True)
    print(json.dumps(decision),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--blocks',type=int,default=31)
    p.add_argument('--seed',type=int,default=73049)
    p.add_argument('--sizes',type=int,nargs='+',default=[4096,8192])
    p.add_argument('--cases',nargs='+',choices=CASES,default=CASES)
    p.add_argument('--analyze-only',action='store_true')
    p.add_argument('--boundary-suite',action='store_true',help='measure the seven zero/small-work boundary cells')
    p.add_argument('--calls-per-measurement',type=int,
                   help='aggregate 1..8192 independent calls; useful for zero-work paths')
    args=p.parse_args();out=args.output.resolve()
    if args.analyze_only:analyze(out);return
    if args.blocks<3:p.error('at least three blocks')
    if args.calls_per_measurement is not None and not 1<=args.calls_per_measurement<=8192:
        p.error('calls per measurement must be 1..8192')
    build=args.build.resolve();meta=json.loads((build/'build.json').read_text())
    if not meta['injected']:raise RuntimeError('no runtime was injected; do not claim a protected benchmark')
    bins={v:build/v for v in ('off','on')}
    if any(sha(bins[v])!=meta[v+'_sha256'] for v in bins):raise RuntimeError('ELF changed')
    out.mkdir(parents=True,exist_ok=False)
    allowed=sorted(os.sched_getaffinity(0));cpu=allowed[min(2,len(allowed)-1)]
    os.sched_setaffinity(0,{cpu})
    protocol={'started_at':datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat(),
              'build':str(build),'build_metadata':meta,'sizes':args.sizes,'cases':args.cases,
              'blocks':args.blocks,'seed':args.seed,'logical_cpu':cpu,
              'timed':'same guarded API and benchmark harness in separate final flag-off/on ELFs; full batch call including runtime overhead; input preparation/process startup/JSON excluded equally',
              'statistics':'random ABBA/BAAB independent processes per block, off/off null; exact pointwise median 95% CI, exploratory simultaneous coverage not claimed',
              'teacher_tolerance':'approximately one percent; report medians and uncertainty, do not rewrite historical strict gates',
              'source_sha256':sha(Path(__file__)),
              'warmup':'one complete same-mode call per process, excluded symmetrically',
              'minimum_batches':512,'queries_per_batch':4096,'once_per_call_attempt':True}
    protocol['calls_per_measurement_override']=args.calls_per_measurement
    if args.boundary_suite:
        protocol['sizes']=list(dict.fromkeys(n for n,c,k in BOUNDARIES))
        protocol['cases']=list(dict.fromkeys(c for n,c,k in BOUNDARIES))
        protocol['cells']=[{'size':n,'case':c,'repeats':k} for n,c,k in BOUNDARIES]
    write(out/'protocol.json',protocol)
    rng=random.Random(args.seed^0x1ea49)
    def execute(binary,case,size,seed):
        repeats=args.calls_per_measurement or (math.ceil(512/SHORT[case]) if case in SHORT else 1)
        if args.boundary_suite and not args.calls_per_measurement:
            repeats=next(k for n,c,k in BOUNDARIES if n==size and c==case)
        result=subprocess.run([str(binary),'guarded',case,str(size),str(seed),str(repeats)],capture_output=True,text=True,timeout=120)
        if result.returncode:raise RuntimeError(result.stderr[-2000:])
        return json.loads(result.stdout)
    for block in range(args.blocks):
        cells=[(c['size'],c['case']) for c in protocol['cells']] if args.boundary_suite else [(n,c) for n in args.sizes for c in args.cases]
        rng.shuffle(cells)
        for size,case in cells:
            kinds=['pair','null'];rng.shuffle(kinds)
            for kind in kinds:
                order=[('A','off'),('B','on' if kind=='pair' else 'off'),('B','on' if kind=='pair' else 'off'),('A','off')]
                if rng.getrandbits(1):order=[order[1],order[0],order[3],order[2]]
                rows=[]
                for label,variant in order:
                    data=execute(bins[variant],case,size,args.seed+block)
                    run=data['runs'][0];run['label']=label;run['harness_mode']=run['variant'];run['variant']=variant
                    if variant=='off' and (run['clock_reads'] or run['active_batches'] or run['entered']):
                        raise RuntimeError('flag-off contains controller activity')
                    if variant=='on':
                        if size==0 and (run['clock_reads'] or run['trial_batches'] or run['active_batches']):
                            raise RuntimeError('zero work entered the controller')
                        if run['trial_batches']>3*data['repeats']:raise RuntimeError('repeated admission')
                        if data['batches']<512 and (run['clock_reads'] or run['active_batches'] or run['short_bypass']!=data['repeats']):
                            raise RuntimeError('short bypass did not avoid clocks/branch trials')
                    rows.append(run)
                if len({r['checksum'] for r in rows})!=1:raise RuntimeError('output mismatch')
                with (out/'raw.jsonl').open('a') as stream:
                    stream.write(json.dumps({'block':block,'seed':args.seed+block,'size':size,'case':case,'kind':kind,'runs':rows})+'\n')
        print(f'block {block+1}/{args.blocks} complete',flush=True)
    analyze(out)


if __name__=='__main__':main()
