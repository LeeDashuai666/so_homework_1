#!/usr/bin/env python3
"""Verify vanilla and default-off tools produce identical executable sections."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('pipeline',ROOT/'app/run.py')
    pipeline=importlib.util.module_from_spec(spec); spec.loader.exec_module(pipeline)
    records=[]
    for label,bolt in [('vanilla',ROOT/'app/baseline/bin/llvm-bolt'),('disabled',ROOT/'app/bin/llvm-bolt')]:
        binary=out/label
        result=subprocess.run([str(bolt),str(ROOT/'app/workloads/search'),'-o',str(binary),'-lite=0','-keep-nops=false','-verify-cfg'],capture_output=True,text=True,timeout=120)
        (out/(label+'.log')).write_text(result.stdout+result.stderr)
        if result.returncode: raise RuntimeError('BOLT failed: '+label)
        records.append({'tool':label,'executable_section_hash':pipeline.executable_hash(binary)})
    if records[0]['executable_section_hash']!=records[1]['executable_section_hash']:
        raise RuntimeError('default-off output changed executable bytes, addresses or sizes')
    (out/'result.json').write_text(json.dumps({'code_identity_passed':True,'records':records},indent=2)+'\n')
if __name__=='__main__': main()
