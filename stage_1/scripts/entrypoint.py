#!/usr/bin/env python3
"""One command for real functional checks and separate performance acceptance."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['smoke','functional','full'],nargs='?',default='smoke')
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    checks=[]
    def run(name,argv):
        print(f'== {name} ==',flush=True)
        with (out/(name+'.log')).open('w') as log:
            result=subprocess.run(list(map(str,argv)),stdout=log,stderr=subprocess.STDOUT)
        checks.append({'name':name,'exit_code':result.returncode,'log':name+'.log'})
        print(f'{name}: '+('PASS' if not result.returncode else f'FAILED ({result.returncode})'),flush=True)
        return result.returncode
    py=sys.executable
    run('default-off-identity',[py,ROOT/'scripts/check_identity.py','--output',out/'default-off-identity'])
    run('static-functional',[py,ROOT/'app/tests.py','--output',out/'static-functional'])
    run('controller-safety',[ROOT/'controller-tests'])
    run('controller-functional',[py,ROOT/'scripts/verify_runtime.py','--binary',ROOT/'runtime-build/dual.bolt','--output',out/'controller-functional.json'])
    functional_passed=all(c['exit_code']==0 for c in checks)
    if args.mode=='smoke' and functional_passed:
        run('static-smoke',[py,ROOT/'app/run.py','--output',out/'static-smoke','--quick','--families','low95','uniform'])
    elif args.mode=='full' and functional_passed:
        run('static-performance',[py,ROOT/'app/run.py','--output',out/'static-performance'])
        run('controller-performance',[py,ROOT/'scripts/benchmark.py','--binary',ROOT/'runtime-build/dual.bolt','--output',out/'controller-performance'])
    shutil.copy2(ROOT/'BASELINE.json',out/'BASELINE.json')
    shutil.copy2(ROOT/'runtime-build/build.json',out/'runtime-build.json')
    result={'mode':args.mode,'checks':checks,'functional_only_or_smoke':args.mode!='full',
            'performance_acceptance_claimed':args.mode=='full' and all(c['exit_code']==0 for c in checks),
            'adaptive_bolt_integration_completed':False,
            'completed_at':datetime.now(timezone.utc).isoformat()}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    return 0 if all(c['exit_code']==0 for c in checks) else 2
if __name__=='__main__': raise SystemExit(main())
