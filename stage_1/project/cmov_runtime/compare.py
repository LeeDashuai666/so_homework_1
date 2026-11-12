#!/usr/bin/env python3
"""Rebuild the frozen previous runtime and compare old/new/off on this host."""
import argparse,hashlib,importlib.util,json,math,os,random,statistics,subprocess,shutil
from pathlib import Path
from build import median_ci
HERE=Path(__file__).resolve().parent;S=HERE.parents[1]
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
p.add_argument('--blocks',type=int,default=31);p.add_argument('--seed',type=int,default=94049)
p.add_argument('--bolt',type=Path,default=S/'build/bin/llvm-bolt');p.add_argument('--compiler',default='g++')
a=p.parse_args();a.output=a.output.resolve();a.output.mkdir(parents=True,exist_ok=False);B=a.build.resolve()
m=json.loads((B/'build.json').read_text())
if not m['injected']:raise RuntimeError('new runtime was not admitted')
for name in ('off','on'):
 if hashlib.sha256((B/name).read_bytes()).hexdigest()!=m[name+'_sha256']:raise RuntimeError('binary changed')
R=a.output/'reference';R.mkdir();flags=['-O3','-DNDEBUG','-std=c++17','-ffreestanding','-fno-exceptions','-fno-rtti','-fno-stack-protector','-fPIC','-fomit-frame-pointer','-gz=none','-mno-sse','-mgeneral-regs-only']
for name in ('cmov_observe','cmov'):
 subprocess.run([a.compiler,*flags,'-c',str(HERE/'reference_v1'/(name+'.cpp')),'-o',str(R/(name+'.o'))],check=True)
subprocess.run(['ar','rcsD',str(R/'libbolt_rt_cmov.a'),str(R/'cmov_observe.o'),str(R/'cmov.o')],check=True)
spec=importlib.util.spec_from_file_location('pipeline',S/'project/cmov_branchify/run.py');pipe=importlib.util.module_from_spec(spec);spec.loader.exec_module(pipe)
r=subprocess.run([str(a.bolt),str(B/'input'),'-data='+str(B/'normal.fdata'),*pipe.COMMON,'-cmov-branchify-runtime','-cmov-branchify-profile='+str(B/'validated-profile.json'),'-runtime-cmov-lib='+str(R/'libbolt_rt_cmov.a'),'-o',str(R/'on')],capture_output=True,text=True)
(R/'bolt.log').write_text(r.stdout+r.stderr)
if r.returncode:raise RuntimeError(str(R/'bolt.log'))
cases=['low95','high95','low80','uniform','sorted','shift','long-recovery','fast-shift','short-uniform1','short-uniform4','short-uniform16','short-low95','short-uniform63','threshold64','threshold65','fast-shift1','low50','hot-prefix','hot-suffix','shift-high','striped','threshold511','threshold512','threshold513','early-shift','calibration-alias']
short={'short-uniform1':1,'short-uniform4':4,'short-uniform16':16,'short-low95':16,'short-uniform63':63,'threshold64':64,'threshold65':65,'fast-shift':256,'fast-shift1':64,'threshold511':511}
bins={'A':B/'off','B':R/'on','C':B/'on','N':B/'off'}
allowed=sorted(os.sched_getaffinity(0));os.sched_setaffinity(0,{allowed[min(2,len(allowed)-1)]});rng=random.Random(a.seed^0x9871)
protocol={'blocks':a.blocks,'seed':a.seed,'sizes':[4096,8192],'cases':cases,'variants':{k:str(v) for k,v in bins.items()},'sha256':{k:hashlib.sha256(v.read_bytes()).hexdigest() for k,v in bins.items()},'comparison':'random mirrored 4-way block; A/N vanilla BOLT off, B frozen released implementation, C canonical rebuilt robust confirmation plus paired-B timing','candidate_selection':'reproduction of frozen selected candidate; all cells; balanced old/new/off/null; see numeric blocks/seed fields','source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
protocol['logical_cpu']=next(iter(os.sched_getaffinity(0)))
protocol['reference_runtime_compiler']=subprocess.check_output([a.compiler,'--version'],text=True).splitlines()[0]
protocol['reference_runtime_sources']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (HERE/'reference_v1').glob('*.cpp')}
protocol['runtime_sources']={n:hashlib.sha256((S/'runtime'/n).read_bytes()).hexdigest() for n in ('cmov.cpp','cmov_observe.cpp','cmov.h')}
protocol['runtime_archive_sha256']=hashlib.sha256((S/'build/lib/libbolt_rt_cmov.a').read_bytes()).hexdigest()
(a.output/'source').mkdir()
for n in ('cmov.cpp','cmov_observe.cpp','cmov.h'):(a.output/'source'/n).write_bytes((S/'runtime'/n).read_bytes())
shutil.copytree(HERE/'reference_v1',a.output/'source/reference_v1')
(a.output/'source/formal.py').write_bytes(Path(__file__).read_bytes())
(a.output/'protocol.json').write_text(json.dumps(protocol,indent=2)+'\n');raw=[]
for block in range(a.blocks):
 cells=[(n,c) for n in protocol['sizes'] for c in cases];rng.shuffle(cells)
 for n,c in cells:
  order=list(bins);rng.shuffle(order);order+=list(reversed(order));runs=[]
  for label in order:
   repeats=math.ceil(512/short[c]) if c in short else 1
   r=subprocess.run([str(bins[label]),'guarded',c,str(n),str(a.seed+block),str(repeats)],capture_output=True,text=True,timeout=120)
   if r.returncode:raise RuntimeError(r.stderr[-1500:])
   data=json.loads(r.stdout);x=data['runs'][0];x['label']=label
   assert x['trial_batches']<=3*repeats
   if c in short and label not in ('A','N'):assert x['short_bypass']==repeats and x['clock_reads']==0
   runs.append(x)
  assert len({x['checksum'] for x in runs})==1
  row={'block':block,'size':n,'case':c,'seed':a.seed+block,'runs':runs};raw.append(row)
  with (a.output/'raw.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 print(f'block {block+1}/{a.blocks} complete',flush=True)
summary=[]
for n in protocol['sizes']:
 for c in cases:
  cell={'size':n,'case':c};rows=[r for r in raw if (r['size'],r['case'])==(n,c)]
  for x,y in [('A','B'),('A','C'),('B','C'),('A','N')]:
   ratios=[sum(t['elapsed_ns'] for t in r['runs'] if t['label']==x)/sum(t['elapsed_ns'] for t in r['runs'] if t['label']==y) for r in rows]
   cell[x+'/'+y]={'median':statistics.median(ratios),'ci95':median_ci(ratios),'ratios':ratios}
  for label in ('B','C'):
   cells=[x for r in rows for x in r['runs'] if x['label']==label]
   cell[label]={'entered':sum(x['entered'] for x in cells),'median_active_batches':statistics.median(x['active_batches'] for x in cells),'median_fallback_batches':statistics.median(x['fallback_batches'] for x in cells),'median_clocks':statistics.median(x['clock_reads'] for x in cells)}
  summary.append(cell)
  print(n,c,'released',round(cell['A/B']['median'],4),'new',round(cell['A/C']['median'],4),'new/old',round(cell['B/C']['median'],4),flush=True)
(a.output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')

from analyze_v2 import analyze
_,decision=analyze(a.output,a.output)
print(json.dumps(decision),flush=True)
