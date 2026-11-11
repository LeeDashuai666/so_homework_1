"""Frozen V6 statistics; exact paired-median confidence intervals."""
import json
import math
import statistics
from pathlib import Path

CASES = ['low95', 'high95', 'low80', 'uniform', 'sorted', 'shift', 'long-recovery',
         'fast-shift', 'short-uniform1', 'short-uniform4', 'short-uniform16',
         'short-low95', 'short-uniform63', 'threshold64', 'threshold65', 'fast-shift1',
         'low50', 'hot-prefix', 'hot-suffix', 'shift-high', 'striped',
         'threshold511', 'threshold512', 'threshold513', 'early-shift', 'calibration-alias']

BATCHES = {'short-uniform1': 1, 'short-uniform4': 4, 'short-uniform16': 16,
           'short-low95': 16, 'short-uniform63': 63, 'threshold64': 64,
           'threshold65': 65, 'fast-shift': 256, 'fast-shift1': 64,
           'threshold511': 511}

def write(p, x): Path(p).write_text(json.dumps(x, indent=2)+'\n')

def median_ci(values, alpha=.05):
    """Exact, distribution-free order-statistic CI for the population median.

    Discreteness makes achieved coverage at least 1-alpha under independent
    continuous block ratios. Does not bound individual runs or future inputs.
    """
    x=sorted(values); n=len(x); k=0
    for candidate in range(1, (n+1)//2+1):
        tail=sum(math.comb(n,j) for j in range(candidate)) / 2**n
        if tail <= alpha/2: k=candidate
    return {'low': x[k-1] if k else 0, 'high': x[n-k] if k else math.inf,
            'order_index': k, 'confidence_at_least': 1-alpha}

def analyze(out):
    protocol=json.loads((out/'protocol.json').read_text())
    records=[json.loads(s) for s in (out/'raw.jsonl').read_text().splitlines()]
    cells=len(protocol['sizes'])*len(protocol['cases'])
    results=[]
    for n in protocol['sizes']:
        for case in protocol['cases']:
            row={'size': n, 'case': case}
            for kind in ('pair','null'):
                chosen=[r for r in records if (r['size'],r['case'],r['kind'])==(n,case,kind)]
                ratios=[sum(x['elapsed_ns'] for x in r['runs'] if x['label']=='A') /
                        sum(x['elapsed_ns'] for x in r['runs'] if x['label']=='B') for r in chosen]
                point=median_ci(ratios)
                # Simultaneous family includes every candidate and null cell.
                family=median_ci(ratios, .05/(2*cells))
                row[kind]={'blocks': len(ratios), 'median_speedup': statistics.median(ratios),
                           'ci95': point, 'simultaneous_ci95': family,
                           'ratios': ratios}
            lo=1/1.01; hi=1.01
            row['positive_target']=case in protocol['acceptance']['positive_cases']
            row['pointwise_noninferiority']=row['pair']['ci95']['low'] >= lo
            row['simultaneous_noninferiority']=row['pair']['simultaneous_ci95']['low'] >= lo
            row['null_precision_passed']=(row['null']['ci95']['low'] >= lo and row['null']['ci95']['high'] <= hi)
            row['simultaneous_null_precision_passed']=(row['null']['simultaneous_ci95']['low'] >= lo and row['null']['simultaneous_ci95']['high'] <= hi)
            row['positive_effect_passed']=not row['positive_target'] or row['pair']['ci95']['low']>=1.02
            guarded=[x for r in records if (r['size'],r['case'],r['kind'])==(n,case,'pair') for x in r['runs'] if x['variant']=='guarded']
            row['entered_calls']=sum(x['entered'] for x in guarded)
            row['trial_batches']=sum(x['trial_batches'] for x in guarded)
            row['active_batches']=sum(x['active_batches'] for x in guarded)
            results.append(row)
    write(out/'summary.json',results)
    decision={'prototype_only':True, 'cells':cells, 'functional_measured_executions':len(records)*4,
              'pointwise_noninferiority_passed':sum(r['pointwise_noninferiority'] for r in results),
              'simultaneous_noninferiority_passed':sum(r['simultaneous_noninferiority'] for r in results),
              'null_precision_passed':sum(r['null_precision_passed'] for r in results),
              'simultaneous_null_precision_passed':sum(r['simultaneous_null_precision_passed'] for r in results),
              'positive_targets_passed':sum(r['positive_effect_passed'] for r in results if r['positive_target']),
              'integration_gate_passed':False,
              'empirical_gate_passed':all(r['simultaneous_noninferiority'] and r['simultaneous_null_precision_passed'] and r['positive_effect_passed'] for r in results),
              'universal_no_regression_proven':False}
    write(out/'decision.json',decision)
    for r in results:
        c=r['pair']; null=r['null']
        print(f"{r['size']} {r['case']:20} {c['median_speedup']:.4f} [{c['ci95']['low']:.4f},{c['ci95']['high']:.4f}] null [{null['ci95']['low']:.4f},{null['ci95']['high']:.4f}] enter={r['entered_calls']}",flush=True)
    print(json.dumps(decision),flush=True)
