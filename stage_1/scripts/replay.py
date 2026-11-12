#!/usr/bin/env python3
"""Recompute saved summary; never represent replay as a new measurement."""
import argparse,gzip,shutil,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
with gzip.open(a.evidence/'raw.jsonl.gz','rb') as f,(a.output/'raw.jsonl').open('wb') as t:shutil.copyfileobj(f,t)
shutil.copy2(a.evidence/'protocol.json',a.output/'protocol.json')
root=Path(__file__).resolve().parents[1]
subprocess.run([sys.executable,str(root/'project/cmov_runtime/analyze_v2.py'),'--source',str(a.output),'--output',str(a.output)],check=True)
assert (a.output/'summary.json').read_bytes()==(a.evidence/'summary.json').read_bytes(),'saved summary differs'
assert (a.output/'decision.json').read_bytes()==(a.evidence/'decision.json').read_bytes(),'saved decision differs'
print('Saved evidence replay matches; this is not a new host measurement.')
