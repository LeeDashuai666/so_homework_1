#!/usr/bin/env python3
"""Build, calibrate and test the actual BOLT-injected runtime on this host."""
import argparse,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['smoke','functional','full'],nargs='?',default='smoke');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);checks=[];py=sys.executable;app=ROOT/'project/cmov_runtime'
 def run(name,argv):
  print(name,flush=True)
  with (out/(name+'.log')).open('w') as log:r=subprocess.run(list(map(str,argv)),stdout=log,stderr=subprocess.STDOUT)
  checks.append({'name':name,'returncode':r.returncode});print(name+(': PASS' if not r.returncode else ': FAIL'),flush=True)
  (out/'checks.json').write_text(json.dumps(checks,indent=2)+'\n')
  if r.returncode:raise RuntimeError(str(out/(name+'.log')))
 run('controller-safety',[ROOT/'controller-tests'])
 run('static-semantics',[py,ROOT/'project/cmov_branchify/tests.py','--output',out/'static-tests'])
 run('build-and-calibrate',[py,app/'build.py','--compiler','clang++-18','--output',out/'build'])
 meta=json.loads((out/'build/build.json').read_text())
 if meta['injected']:run('flag-rejections-code-audit',[py,app/'tests.py','--build',out/'build','--output',out/'flag-tests'])
 argv=[py,app/'verify_runtime.py','--build',out/'build','--output',out/'functional.json']
 if a.mode=='smoke':argv+=['--seeds','79879']
 run('actual-elf-functional',argv)
 if a.mode!='functional' and meta['injected']:
  argv=[py,app/('compare.py' if a.mode=='full' else 'run.py'),'--build',out/'build','--output',out/'performance']
  if a.mode=='smoke':argv+=['--blocks','3','--cases','low95','uniform','short-uniform1']
  run('final-elf-performance',argv)
 result={'mode':a.mode,'checks':checks,'runtime_injected':meta['injected'],'adaptive_bolt_integration_completed':True,'performance_acceptance_claimed':False,'note':'Read performance/decision.json and uncertainty. Successful execution is not a universal performance guarantee.' if meta['injected'] else 'Independent calibration rejected this host; flag-on preserves original executable code. No protected speedup claimed.'}
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2),flush=True)
if __name__=='__main__':main()
