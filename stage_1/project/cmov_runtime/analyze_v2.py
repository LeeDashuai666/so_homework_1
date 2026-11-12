#!/usr/bin/env python3
"""Offline replay of paired old/new/off/null measurements; no new timing."""
import argparse,gzip,json,math,statistics
from pathlib import Path

def median_ci(values,alpha=.05):
 x=sorted(values);n=len(x);k=0
 for c in range(1,(n+1)//2+1):
  if sum(math.comb(n,j) for j in range(c))/2**n<=alpha/2:k=c
 return {'low':x[k-1] if k else 0,'high':x[n-k] if k else None,'order_index':k,'confidence_at_least':1-alpha}

def analyze(source,target):
 p=json.loads((source/'protocol.json').read_text());rawfile=source/'raw.jsonl';opener=open
 if not rawfile.exists():rawfile=source/'raw.jsonl.gz';opener=gzip.open
 with opener(rawfile,'rt') as f:raw=[json.loads(x) for x in f]
 assert len(raw)==p['blocks']*len(p['sizes'])*len(p['cases'])
 assert len({(r['block'],r['size'],r['case']) for r in raw})==len(raw)
 for r in raw:
  assert len(r['runs'])==8 and all(sum(x['label']==v for x in r['runs'])==2 for v in ('A','B','C','N'))
  assert len({x['checksum'] for x in r['runs']})==1
 summary=[]
 for n in p['sizes']:
  for case in p['cases']:
   cell={'size':n,'case':case};rows=[r for r in raw if (r['size'],r['case'])==(n,case)]
   for x,y in [('A','B'),('A','C'),('B','C'),('A','N')]:
    ratios=[sum(t['elapsed_ns'] for t in r['runs'] if t['label']==x)/sum(t['elapsed_ns'] for t in r['runs'] if t['label']==y) for r in rows]
    cell[x+'/'+y]={'median':statistics.median(ratios),'ci95':median_ci(ratios),'ratios':ratios}
   for label in ('B','C'):
    runs=[x for r in rows for x in r['runs'] if x['label']==label]
    cell[label]={'entered':sum(x['entered'] for x in runs),'median_active_batches':statistics.median(x['active_batches'] for x in runs),'median_fallback_batches':statistics.median(x['fallback_batches'] for x in runs),'median_clocks':statistics.median(x['clock_reads'] for x in runs)}
   summary.append(cell)
 target.mkdir(parents=True,exist_ok=True)
 (target/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
 def loss(r,k):return (1/r[k]['median']-1)*100
 worst=max(summary,key=lambda r:loss(r,'A/C'));oldworst=max(summary,key=lambda r:loss(r,'A/B'))
 decision={'cells':len(summary),'measured_executions':len(raw)*8,'all_outputs_passed':True,'contemporaneous_old_new_comparison':True,'within_one_percent_new':sum(loss(r,'A/C')<=1 for r in summary),'within_one_percent_old':sum(loss(r,'A/B')<=1 for r in summary),'worst_new_time_increase_percent':loss(worst,'A/C'),'worst_new_cell':[worst['size'],worst['case']],'worst_old_time_increase_percent':loss(oldworst,'A/B'),'positive_new_vs_old_ci_lower_above_one':sum(r['case']=='low95' and r['B/C']['ci95']['low']>1 for r in summary),'universal_input_bound_proven':False}
 (target/'decision.json').write_text(json.dumps(decision,indent=2)+'\n')
 return summary,decision

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();_,d=analyze(a.source,a.output);print(json.dumps(d))
