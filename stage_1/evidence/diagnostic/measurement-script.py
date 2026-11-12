#!/usr/bin/env python3
"""Supplementary same-ELF attribution, not the primary BOLT flag comparison."""
import argparse,hashlib,json,os,random,statistics,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--binary',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--app',type=Path,default=Path('/opt/homework/project/cmov_runtime'));a=p.parse_args()
sys.path.insert(0,str(a.app));from build import median_ci
out=a.output;out.mkdir(parents=True,exist_ok=False);cpus=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpus[min(2,len(cpus)-1)]})
protocol={'blocks':9,'seeds':list(range(81049,81058)),'cells':[[n,c] for n in (4096,8192) for c in ('low95','uniform','shift')],'binary_sha256':hashlib.sha256(a.binary.read_bytes()).hexdigest(),'source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'scope':'same flag-on ELF; ordinary driver vs protected entry; diagnostic attribution only, does not replace separate flag-off/on ELF experiment'}
(out/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');rng=random.Random(81049);raw=[]
for seed in protocol['seeds']:
 cells=[(n,c,k) for n,c in protocol['cells'] for k in ('pair','null')];rng.shuffle(cells)
 for n,c,k in cells:
  r=subprocess.run([str(a.binary),k,c,str(n),str(seed),'1'],capture_output=True,text=True,check=True,timeout=120);v=json.loads(r.stdout)
  assert len({x['checksum'] for x in v['runs']})==1
  raw.append({'size':n,'case':c,'kind':k,'seed':seed,**v})
 print('diagnostic seed',seed,'passed',flush=True)
(out/'raw.json').write_text(json.dumps(raw,indent=2)+'\n');summary=[]
for n,c in protocol['cells']:
 cell={'size':n,'case':c}
 for k in ('pair','null'):
  ratios=[sum(x['elapsed_ns'] for x in r['runs'] if x['label']=='A')/sum(x['elapsed_ns'] for x in r['runs'] if x['label']=='B') for r in raw if (r['size'],r['case'],r['kind'])==(n,c,k)]
  cell[k]={'median_speedup':statistics.median(ratios),'ci95':median_ci(ratios),'ratios':ratios}
 summary.append(cell)
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary,indent=2),flush=True)
