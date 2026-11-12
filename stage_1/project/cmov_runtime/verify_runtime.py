#!/usr/bin/env python3
"""Independent functional checks of the frozen ELF; no performance approval."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

CASES = ['low95', 'high95', 'low80', 'uniform', 'sorted', 'shift', 'long-recovery',
         'fast-shift', 'short-uniform1', 'short-uniform4', 'short-uniform16',
         'short-low95', 'short-uniform63', 'threshold64', 'threshold65', 'fast-shift1',
         'low50', 'hot-prefix', 'hot-suffix', 'shift-high', 'striped',
         'threshold511', 'threshold512', 'threshold513', 'early-shift', 'calibration-alias']

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seeds',nargs='+',type=int,default=[59879,59880,59881])
    args=p.parse_args()
    if args.output.exists(): p.error('output already exists')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    records=[]
    for n in (4096,8192):
        for case in CASES:
            for seed in args.seeds:
                expected=None
                for mode in ('input','off','on'):
                    r=subprocess.run([str((args.build/mode).resolve()),'guarded',case,str(n),str(seed),'1'],
                                     check=True,capture_output=True,text=True,timeout=90)
                    data=json.loads(r.stdout); row=data['runs'][0]
                    if expected is None: expected=row['checksum']
                    if row['checksum']!=expected: raise RuntimeError('cross-mode checksum mismatch')
                    if mode=='on':
                        if row['trial_batches']>3: raise RuntimeError('multiple admissions')
                        if data['batches']<512 and (not row['short_bypass'] or row['clock_reads'] or row['trial_batches'] or row['active_batches']):
                            raise RuntimeError('short bypass has speculative work')
                    records.append({'size':n,'case':case,'seed':seed,'variant':mode,**data})
            print(f'{n} {case} passed',flush=True)
    result={'functional_only':True,'performance_acceptance_claimed':False,
            'binary_sha256':{n:hashlib.sha256((args.build/n).read_bytes()).hexdigest() for n in ('input','off','on')},
            'allowed_cpus':sorted(os.sched_getaffinity(0)), 'records_passed':len(records),'records':records}
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k!='records'}))

if __name__=='__main__': main()
