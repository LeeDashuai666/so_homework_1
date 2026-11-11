#!/usr/bin/env python3
"""Benchmark a frozen cooperative-ABI prototype without LLVM or a compiler."""
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import random
import subprocess

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--binary',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--blocks',type=int,default=31)
    p.add_argument('--seed',type=int,default=61049)
    args=p.parse_args()
    if args.blocks<31: p.error('at least 31 blocks for simultaneous finite median intervals; use verify_runtime.py for functional smoke')
    out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    binary=args.binary.resolve()
    spec=importlib.util.spec_from_file_location('controller_pipeline',Path(__file__).with_name('analysis.py'))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    cpu=sorted(os.sched_getaffinity(0))[min(2,len(os.sched_getaffinity(0))-1)]
    os.sched_setaffinity(0,{cpu})
    repeats={case:math.ceil(512/count) for case,count in module.BATCHES.items()}
    protocol={'started_at':datetime.now(ZoneInfo('Asia/Hong_Kong')).isoformat(),
              'frozen_prototype_only':True,'new_bolt_option_implemented':False,
              'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),
              'benchmark_driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cpu':cpu,'blocks':args.blocks,'sizes':[4096,8192],'cases':module.CASES,
              'seed':args.seed,'short_repeats':repeats,
              'acceptance':{'positive_cases':['low95'],'positive_lower':1.02,
                            'noninferiority_speedup_lower':1/1.01,'null_equivalence':[1/1.01,1.01]},
              'statistics':'independent seed block, randomized within-process ABBA/BAAB; exact median CI and Bonferroni over candidate/null cells',
              'timed':'complete calls including admission, all queries, shape validation, clocks, telemetry; preparation/checksum reference/startup/JSON excluded equally',
              'code_size_against_single_kernel_measured':False}
    (out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n')
    rng=random.Random(args.seed ^ 0x991203)
    for block in range(args.blocks):
        cells=[(n,c) for n in protocol['sizes'] for c in module.CASES]; rng.shuffle(cells)
        for n,case in cells:
            kinds=['pair','null']; rng.shuffle(kinds)
            for kind in kinds:
                r=subprocess.run([str(binary),kind,case,str(n),str(args.seed+block),str(repeats.get(case,1))],
                                 check=True,capture_output=True,text=True,timeout=120)
                data=json.loads(r.stdout)
                if len({x['checksum'] for x in data['runs']})!=1: raise RuntimeError('cross-mode mismatch')
                row={'block':block,'size':n,'case':case,'kind':kind,'seed':args.seed+block,**data}
                with (out/'raw.jsonl').open('a') as f: f.write(json.dumps(row)+'\n')
        print(f'block {block+1}/{args.blocks} complete',flush=True)
    module.analyze(out)
    decision=json.loads((out/'decision.json').read_text())
    return 0 if decision['empirical_gate_passed'] else 2

if __name__=='__main__': raise SystemExit(main())
