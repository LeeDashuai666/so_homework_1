#!/usr/bin/env python3
"""Final BOLT on a file-backed public-log counting prototype, not production replay."""
from pathlib import Path
import argparse,bisect,csv,datetime,hashlib,importlib.util,json,os,random,shutil,statistics,subprocess,time
H=Path(__file__).resolve().parent;S=H.parents[1]
p_args=argparse.ArgumentParser(description=__doc__);p_args.add_argument('--output',type=Path,default=S/'results/log-time-count-new');p_args.add_argument('--bolt',type=Path,default=S/'build/bin/llvm-bolt');p_args.add_argument('--compiler',default=shutil.which('clang++-18') or str(S/'.tools/root/usr/lib/llvm-18/bin/clang++'));args=p_args.parse_args();O=args.output.resolve();O.mkdir(parents=True,exist_ok=False)
spec=importlib.util.spec_from_file_location('b',S/'project/cmov_runtime/build.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
spec=importlib.util.spec_from_file_location('p',S/'project/cmov_branchify/run.py');p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
sha=lambda x:hashlib.sha256(Path(x).read_bytes()).hexdigest()
def write(name,value):(O/name).write_text(json.dumps(value,indent=2)+'\n')
commands=[]
def cmd(args,name):
 r=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=240)
 (O/(name+'.log')).write_text(r.stdout+r.stderr);commands.append({'argv':list(map(str,args)),'returncode':r.returncode});write('commands.json',commands)
 if r.returncode:raise RuntimeError(name+' failed')
 return r.stdout
os.sched_setaffinity(0,{2});log=H/'data/Linux_2k.log_structured.csv';keys=[]
with log.open() as f:
 for row in csv.DictReader(f):
  t=datetime.datetime.strptime('2000 '+row['Month']+' '+row['Date']+' '+row['Time'],'%Y %b %d %H:%M:%S').replace(tzinfo=datetime.timezone.utc)
  keys.append(int(t.timestamp()))
keys.sort();(O/'data').mkdir();qmeta={}
def generate(name,seed,case,batches):
 rng=random.Random(seed);path=O/'data'/(name+'.txt');expected=0;total=batches*4096
 with path.open('w') as f:
  for i in range(total):
   old=case=='past95' and rng.randrange(100)<95 or case=='shift' and i<total//2
   t=keys[0]-rng.randint(1,86400) if old else rng.randint(keys[0],keys[-1]+1)
   f.write(str(t)+'\n');expected+=bisect.bisect_left(keys,t)
 qmeta[name]={'seed':seed,'case':case,'queries':total,'expected':expected,'sha256':sha(path)}
 return path
train=generate('training',123071,'past95',16)
cal=generate('calibration',124083,'past95',512)
tests={c:generate('test-'+c,125049,c,512) for c in ('past95','uniform','shift')}
write('data.json',{'source':'https://github.com/logpai/loghub','dataset':'Linux/Linux_2k.log_structured.csv',
 'repository_commit':'dd61d0952749ee7963bde24220d1be5ede023033','csv_sha256':sha(log),'rows':len(keys),
 'timestamp_normalization':'CSV has no year; assign year 2000 UTC consistently, retain month/day/time and all rows.',
 'query_scope':'Synthetic workload queries; 95% outside retained range, uniform, or phase change. Not production query traces.',
 'queries':qmeta})
compiler=args.compiler;bolt=args.bolt.resolve();objs=[]
for name in ('kernel','plain','entry'):
 src=S/'project/cmov_runtime'/(name+'.cpp');obj=O/(name+'.o');objs.append(obj)
 cmd([compiler,'-O3','-g','-std=c++17','-I',S/'project/cmov_runtime','-c',src,'-o',obj],name)
cmd([compiler,'-O3','-g','-std=c++17','-I',S/'project/cmov_runtime','-c',H/'app.cpp','-o',O/'app.o'],'app')
cmd([compiler,'-Wl,--emit-relocs',*objs,O/'app.o','-o',O/'input'],'link')
def execute(binary,q):
 start=time.perf_counter_ns();r=subprocess.run([str(binary),str(log),str(q)],capture_output=True,text=True,check=True,timeout=90);wall=time.perf_counter_ns()-start
 d=json.loads(r.stdout);d['process_ns']=wall
 assert d['checksum']==qmeta[q.stem]['expected']
 return d
for kind in ('normal','probe'):
 flags=[] if kind=='normal' else ['-cmov-branchify-probe','-cmov-branchify-sites='+str(O/'sites.json')]
 cmd([bolt,O/'input','-instrument','-instrumentation-file='+str(O/(kind+'.fdata')),*flags,'-o',O/(kind+'.inst')],kind+'-instrument')
 execute(O/(kind+'.inst'),train)
profile=p.predicate_profile(json.loads((O/'sites.json').read_text()),O/'probe.fdata')
profile['sites']=[s for s in profile['sites'] if s['function']=='cmov_kernel_v1'];assert len(profile['sites'])==1
write('candidate-profile.json',profile);base=['-data='+str(O/'normal.fdata'),*p.COMMON]
cmd([bolt,O/'input',*base,'-o',O/'off'],'off')
cmd([bolt,O/'input',*base,'-cmov-branchify-candidate','-cmov-branchify-profile='+str(O/'candidate-profile.json'),'-o',O/'candidate'],'candidate')
rng=random.Random(126071);calraw=[]
for block in range(9):
 order=['off','candidate'];rng.shuffle(order);order+=order[::-1];runs=[]
 for v in order:runs.append({'variant':v,**execute(O/v,cal)})
 ratio=sum(x['compute_ns'] for x in runs if x['variant']=='off')/sum(x['compute_ns'] for x in runs if x['variant']=='candidate')
 calraw.append({'block':block,'ratio':ratio,'runs':runs})
ci=b.median_ci([r['ratio'] for r in calraw]);approved=ci['low']>=1.02
write('calibration.json',{'approved':approved,'scope':'complete batch computation, file loading excluded','ci95':ci,'raw':calraw})
for site in profile['sites']:site.update(validated=approved,validation_speedup_lower=ci['low'])
write('profile.json',profile)
text=cmd([bolt,O/'input',*base,'-cmov-branchify-runtime','-cmov-branchify-profile='+str(O/'profile.json'),'-o',O/'on'],'on')
injected='retained original kernel' in text;assert injected==approved
write('protocol.json',{'scope':'public-data log cumulative-count business prototype; synthetic requests; full process and batch kernel reported separately',
 'bolt_sha256':sha(bolt),'input_sha256':sha(O/'input'),'off_sha256':sha(O/'off'),'on_sha256':sha(O/'on'),
 'independent_training_calibration_test':True,'approved':approved,'injected':injected,'common_options':p.COMMON,'cpu':2,'blocks':9})
raw=[]
for block in range(9):
 cases=list(tests);rng.shuffle(cases)
 for case in cases:
  order=['off','on','null'];rng.shuffle(order);order+=order[::-1];runs=[]
  for v in order:runs.append({'variant':v,**execute(O/('off' if v=='null' else v),tests[case])})
  row={'block':block,'case':case,'runs':runs};raw.append(row)
  with (O/'raw.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
 print('block',block+1,'/9',flush=True)
summary=[]
for case in tests:
 rows=[r for r in raw if r['case']==case];r={'case':case}
 for metric in ('compute_ns','application_ns','process_ns'):
  for v in ('on','null'):
   ratios=[sum(x[metric] for x in row['runs'] if x['variant']=='off')/sum(x[metric] for x in row['runs'] if x['variant']==v) for row in rows]
   r[metric+'-off/'+v]={'median':statistics.median(ratios),'ci95':b.median_ci(ratios)}
 r['entered_calls']=sum(x['entered'] for row in rows for x in row['runs'] if x['variant']=='on')
 summary.append(r)
write('summary.json',summary);print(json.dumps(summary),flush=True)
