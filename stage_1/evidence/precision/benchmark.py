"""Separate long-call diagnostic; never replaces the 59-cell main matrix."""
from pathlib import Path
import json,os,random,subprocess,sys
S=Path(__file__).resolve().parents[2];sys.path.insert(0,str(S/'project/cmov_runtime'))
from build import sha,write
from compare_zero_work import analyze
B=S/'results/cmov-v3-final-build-20261113';O=S/'results/cmov-v3-precision-20261113'
O.mkdir(parents=True,exist_ok=False);os.sched_setaffinity(0,{2})
P=json.loads((S/'results/cmov-v3-final-formal-20261113/protocol.json').read_text())
P.update(blocks=31,seed=119049,cells=[{'size':n,'case':c,'scope':'regular','repeats':4}
         for n,c in [(4096,'low95'),(8192,'low95'),(4096,'threshold512'),(4096,'threshold513')]],
         source_sha256=sha(Path(__file__)),supplementary_only='Long-call diagnostic of main positives and near-one-percent threshold cells; original 59-cell matrix remains the primary evidence.')
write(O/'protocol.json',P);rng=random.Random(P['seed']^0x9871)
for block in range(P['blocks']):
 cells=P['cells'].copy();rng.shuffle(cells)
 for cell in cells:
  order=list(P['variants']);rng.shuffle(order);order+=order[::-1];runs=[]
  for label in order:
   binary=Path(P['variants'][label]);assert sha(binary)==P['sha256'][label]
   argv=[str(binary),'guarded',cell['case'],str(cell['size']),str(P['seed']+block),'4']
   r=subprocess.run(argv,capture_output=True,text=True,check=True,timeout=120)
   d=json.loads(r.stdout);x=d['runs'][0];x['label']=label;runs.append(x)
  assert len({x['checksum'] for x in runs})==1
  with (O/'raw.jsonl').open('a') as f:f.write(json.dumps({'block':block,'seed':P['seed']+block,**cell,'runs':runs})+'\n')
 print(f'block {block+1}/31 complete',flush=True)
analyze(O)
