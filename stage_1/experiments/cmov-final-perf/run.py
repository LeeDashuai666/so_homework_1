#!/usr/bin/env python3
"""PMU comparison of the frozen final ELF pair; no binary rewriting."""
from pathlib import Path
import argparse,shutil,hashlib,importlib.util,json,os,platform,random,statistics,subprocess,sys
S=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--build',type=Path,default=S/'results/cmov-v3-final-build-20261113')
parser.add_argument('--output',type=Path,default=S/'results/cmov-perf-new')
parser.add_argument('--perf',default=shutil.which('perf') or str(S/'.tools/bin/perf'))
parser.add_argument('--validation',type=Path,default=S/'results/wsl-perf-final-check-20261113/summary.json')
parser.add_argument('--analyze-only',action='store_true');args=parser.parse_args()
B=args.build.resolve();O=args.output.resolve();replay=args.analyze_only
O.mkdir(parents=True,exist_ok=replay);(O/'raw').mkdir(exist_ok=replay)
spec=importlib.util.spec_from_file_location('build',S/'project/cmov_runtime/build.py');u=importlib.util.module_from_spec(spec);spec.loader.exec_module(u)
perf=Path(args.perf).resolve();events=['cycles:u','instructions:u','branches:u','branch-misses:u']
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
meta=json.loads((B/'build.json').read_text());assert meta['injected']
for v in ('off','on'):assert sha(B/v)==meta[v+'_sha256']
check=json.loads(args.validation.read_text());assert check['required_checks_passed']
protocol={'blocks':9,'seed':122049,'cpu':2,'kernel':platform.release(),'perf':str(perf),
 'events':events,'sha256':{v:sha(B/v) for v in ('off','on')},'cells':[(n,c,4) for n in (4096,8192) for c in ('low95','uniform','shift')]+[(4096,'short-uniform1',2048)],
 'pmu_scope':'Whole process: includes preparation, reference computation and same-mode warmup plus measured calls. Hardware events are user-only; task-clock and perf elapsed cover process. Not an ROI-only counter measurement.',
 'time_scope':'JSON elapsed_ns is the existing benchmark timed API scope; unchanged published 31-block experiment remains primary.',
 'interpretation':'Miss rate alone is insufficient: the transformed code adds branches. Report absolute misses, cycles and instructions; no unique proof of dependency-chain causation.'}
(O/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');(O/'run.py').write_bytes(Path(__file__).read_bytes())
if not replay:
 os.sched_setaffinity(0,{2});rng=random.Random(122049);records=[]
 for block in range(9):
  cells=protocol['cells'].copy();rng.shuffle(cells)
  for n,case,repeats in cells:
   order=['off','on'];rng.shuffle(order);order+=order[::-1];runs=[]
   for i,v in enumerate(order):
    name=f'{block}-{n}-{case}-{i}-{v}';csv=O/'raw'/(name+'.csv')
    args=[str(perf),'stat','--no-big-num','-x',';','-o',str(csv),'-e','{'+','.join(events)+'},task-clock','--',str(B/v),'guarded',case,str(n),str(122049+block),str(repeats)]
    p=subprocess.run(args,capture_output=True,text=True,check=True,timeout=120,env={**os.environ,'LC_ALL':'C'})
    (O/'raw'/(name+'.stdout')).write_text(p.stdout);(O/'raw'/(name+'.stderr')).write_text(p.stderr)
    data=json.loads(p.stdout)['runs'][0];counters={}
    for line in csv.read_text().splitlines():
     f=[x.strip() for x in line.split(';')]
     if len(f)>4 and f[2] in events+['task-clock','task-clock:u']:
      counters[f[2]]={'value':float(f[0]),'running_percent':float(f[4])}
    assert all(e in counters and counters[e]['running_percent']>=99 for e in events)
    runs.append({**data,'variant':v,'counters':counters,'command':args})
   assert len({r['checksum'] for r in runs})==1
   row={'block':block,'size':n,'case':case,'repeats':repeats,'runs':runs};records.append(row)
   with (O/'raw.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
  print('block',block+1,'/9',flush=True)
else:
 records=[json.loads(line) for line in (O/'raw.jsonl').read_text().splitlines()]
summary=[]
for n,c,k in protocol['cells']:
 rows=[r for r in records if (r['size'],r['case'])==(n,c)];r={'size':n,'case':c,'repeats':k}
 for metric in ['elapsed_ns',*events]:
  get=lambda x:x['elapsed_ns'] if metric=='elapsed_ns' else x['counters'][metric]['value']
  ratios=[sum(get(x) for x in row['runs'] if x['variant']=='off')/sum(get(x) for x in row['runs'] if x['variant']=='on') for row in rows]
  r[metric]={'off_on_median_ratio':statistics.median(ratios),'ci95':u.median_ci(ratios)}
 for v in ('off','on'):
  rr=[x for row in rows for x in row['runs'] if x['variant']==v]
  r[v]={e:statistics.median(x['counters'][e]['value'] for x in rr) for e in events}
  r[v]['miss_percent']=statistics.median(100*x['counters']['branch-misses:u']['value']/x['counters']['branches:u']['value'] for x in rr)
  r[v]['ipc']=statistics.median(x['counters']['instructions:u']['value']/x['counters']['cycles:u']['value'] for x in rr)
 summary.append(r);print(n,c,'time',r['elapsed_ns']['off_on_median_ratio'],'cycles',r['cycles:u']['off_on_median_ratio'],flush=True)
(O/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
if not replay:
 for v in ('off','on'):
  p=subprocess.run([str(perf),'record','-q','-e','cycles:u','-F','997','-o',str(O/(v+'.data')),'--',str(B/v),'guarded','low95','4096','122999','16'],capture_output=True,text=True,check=True)
  (O/(v+'-record.stdout')).write_text(p.stdout);(O/(v+'-record.stderr')).write_text(p.stderr)
  p=subprocess.run([str(perf),'report','--stdio','--no-children','--percent-limit','1','--sort','symbol','-i',str(O/(v+'.data'))],capture_output=True,text=True,check=True)
  (O/(v+'-report.txt')).write_text(p.stdout+p.stderr)
print('Complete:',O,flush=True)
