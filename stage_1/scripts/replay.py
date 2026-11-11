#!/usr/bin/env python3
"""Recompute historical results without Docker; matching data is not a pass."""
import argparse
import gzip
import json
from pathlib import Path
import shutil
from analysis import analyze

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    args=p.parse_args(); evidence=args.evidence.resolve(); out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    shutil.copy2(evidence/'protocol.json',out/'protocol.json')
    (out/'raw.jsonl').write_bytes(gzip.decompress((evidence/'raw.jsonl.gz').read_bytes()))
    analyze(out)
    for name in ['summary.json','decision.json']:
        if (out/name).read_bytes()!=(evidence/name).read_bytes():
            raise RuntimeError('recomputed evidence differs: '+name)
    decision=json.loads((out/'decision.json').read_text())
    result={'historical_records_reproduced':True,
            'historical_performance_gate_passed':decision['empirical_gate_passed'],
            'adaptive_bolt_integration_completed':False}
    (out/'replay.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()
