#!/usr/bin/env python3
"""Contemporaneous off/V2/V3/null comparison, including fast-path boundaries."""
import argparse, json, math, os, random, statistics, subprocess
from pathlib import Path
from build import STAGE, sha, write, median_ci
from run import CASES, SHORT

def analyze(out):
    protocol=json.loads((out/'protocol.json').read_text())
    raw=[json.loads(line) for line in (out/'raw.jsonl').read_text().splitlines()]
    assert len(raw)==protocol['blocks']*len(protocol['cells'])
    summary=[]
    for cell in protocol['cells']:
        n,c=cell['size'],cell['case']
        rows=[r for r in raw if (r['size'],r['case'])==(n,c)]
        result={**cell,'blocks':len(rows)}
        for x,y in [('A','B'),('A','C'),('B','C'),('A','N')]:
            ratios=[sum(t['elapsed_ns'] for t in r['runs'] if t['label']==x)/
                    sum(t['elapsed_ns'] for t in r['runs'] if t['label']==y) for r in rows]
            result[x+'/'+y]={'median':statistics.median(ratios),'ci95':median_ci(ratios),'ratios':ratios}
        result['median_time_increase_percent']=(1/result['A/C']['median']-1)*100
        result['within_one_percent_reference']=result['A/C']['median']>=1/1.01
        for label in ('A','B','C'):
            runs=[x for r in rows for x in r['runs'] if x['label']==label]
            result[label]={'median_ns_per_call':statistics.median(x['elapsed_ns']/cell['repeats'] for x in runs),
                           'entered':sum(x['entered'] for x in runs),
                           'median_active_batches':statistics.median(x['active_batches']/cell['repeats'] for x in runs),
                           'median_clocks':statistics.median(x['clock_reads']/cell['repeats'] for x in runs)}
        summary.append(result)
        print(n,c,'off/V2',round(result['A/B']['median'],4),'off/V3',round(result['A/C']['median'],4),
              'V2/V3',round(result['B/C']['median'],4),'loss',round(result['median_time_increase_percent'],4),flush=True)
    regular=[r for r in summary if r['scope']=='regular']
    decision={'cells':len(summary),'measured_executions':len(raw)*8,'all_outputs_passed':True,
              'regular_cells':len(regular),'regular_medians_within_one_percent':sum(r['within_one_percent_reference'] for r in regular),
              'worst_regular_median_time_increase_percent':max((r['median_time_increase_percent'] for r in regular),default=None),
              'boundary_cells':len(summary)-len(regular),
              'boundary_medians_within_one_percent':sum(r['within_one_percent_reference'] for r in summary if r['scope']=='boundary'),
              'universal_future_input_bound_proven':False}
    write(out/'summary.json',summary);write(out/'decision.json',decision)
    print(json.dumps(decision),flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--blocks',type=int,default=31);p.add_argument('--seed',type=int,default=117049)
    p.add_argument('--boundary-only',action='store_true');p.add_argument('--analyze-only',action='store_true')
    a=p.parse_args();o=a.output.resolve()
    if a.analyze_only:analyze(o);return
    if a.blocks<3:p.error('at least three blocks')
    b=a.build.resolve();bins={'A':b/'off','B':b/'v2-on','C':b/'on','N':b/'off'}
    cells=[] if a.boundary_only else [{'size':n,'case':c,'scope':'regular','repeats':math.ceil(512/SHORT[c]) if c in SHORT else 1}
                                     for n in (4096,8192) for c in CASES]
    cells += [{'size':n,'case':c,'scope':'boundary','repeats':k} for n,c,k in
              [(0,'low95',8192),(0,'uniform',8192),(0,'short-uniform1',8192),
               (1,'low95',8),(1,'uniform',4),(1,'short-uniform1',512),(64,'low95',4)]]
    o.mkdir(parents=True,exist_ok=False)
    cpu=sorted(os.sched_getaffinity(0))[min(2,len(os.sched_getaffinity(0))-1)];os.sched_setaffinity(0,{cpu})
    protocol={'blocks':a.blocks,'seed':a.seed,'cells':cells,'logical_cpu':cpu,'source_sha256':sha(Path(__file__)),
              'variants':{k:str(v) for k,v in bins.items()},'sha256':{k:sha(v) for k,v in bins.items()},
              'input_sha256':sha(b/'input'),'profile_sha256':sha(b/'validated-profile.json'),
              'comparison':'identical O3 input, profile and common BOLT options; A/N off, B frozen V2 tool/runtime, C V3 lifted zero-work entry',
              'timed':'full guarded API wall time; one same-mode warmup per process; independent controller per logical call; mirrored random four-way order',
              'statistics':'paired block median and exact pointwise 95% interval; all samples retained',
              'seeds_independent_from_training_and_calibration':True}
    write(o/'protocol.json',protocol);rng=random.Random(a.seed^0x9871)
    for block in range(a.blocks):
        order_cells=cells.copy();rng.shuffle(order_cells)
        for cell in order_cells:
            order=list(bins);rng.shuffle(order);order+=order[::-1];runs=[]
            for label in order:
                argv=[str(bins[label]),'guarded',cell['case'],str(cell['size']),str(a.seed+block),str(cell['repeats'])]
                r=subprocess.run(argv,capture_output=True,text=True,check=True,timeout=120)
                d=json.loads(r.stdout);x=d['runs'][0];x['label']=label
                assert x['trial_batches']<=3*cell['repeats']
                if label=='C' and cell['size']==0:
                    assert x['short_bypass']==cell['repeats'] and not x['clock_reads'] and not x['trial_batches'] and not x['active_batches']
                if cell['case'] in SHORT and label in ('B','C'):
                    assert x['short_bypass']==cell['repeats'] and not x['clock_reads']
                runs.append(x)
            assert len({x['checksum'] for x in runs})==1
            with (o/'raw.jsonl').open('a') as f:
                f.write(json.dumps({'block':block,'seed':a.seed+block,**cell,'runs':runs})+'\n')
        print(f'block {block+1}/{a.blocks} complete',flush=True)
    analyze(o)

if __name__=='__main__':main()
