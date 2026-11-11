#!/usr/bin/env python3
"""Build the actual BOLT-generated dual kernel and the conservative prototype."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--compiler',default='clang++-18')
    p.add_argument('--bolt',type=Path,default=ROOT/'app/bin/llvm-bolt')
    args=p.parse_args(); out=args.output.resolve(); out.mkdir(parents=True,exist_ok=False)
    compiler=shutil.which(args.compiler)
    if not compiler: raise RuntimeError('compiler not found')
    bolt=args.bolt.resolve(); source=ROOT/'runtime'
    spec=importlib.util.spec_from_file_location('static_pipeline',ROOT/'app/run.py')
    pipeline=importlib.util.module_from_spec(spec); spec.loader.exec_module(pipeline)
    commands=[]
    def command(argv,name):
        argv=list(map(str,argv)); r=subprocess.run(argv,capture_output=True,text=True,timeout=180)
        (out/(name+'.log')).write_text(r.stdout+r.stderr)
        commands.append({'argv':argv,'returncode':r.returncode,'log':name+'.log'})
        (out/'commands.json').write_text(json.dumps(commands,indent=2)+'\n')
        if r.returncode: raise RuntimeError(f'command failed: {name}')
    objects=[]
    for name in ['cmov','branch']:
        obj=out/(name+'.o'); objects.append(obj)
        command([compiler,'-O3','-g','-DLOOKUP_NAME=lookup_'+name,'-c',source/'kernel.cpp','-o',obj],name+'-compile')
    original=out/'dual'
    command([compiler,'-O3','-g','-Wl,--emit-relocs',*[source/n for n in ['bench.cpp','runtime.cpp','plain.cpp','dispatch.cpp','admission.cpp']],*objects,'-o',original],'link')
    manifest=out/'sites.json'
    for kind in ['normal','probe']:
        inst=out/(kind+'.inst')
        extra=['-cmov-branchify-probe','-cmov-branchify-sites='+str(manifest)] if kind=='probe' else []
        command([bolt,original,'-o',inst,'-instrument','-instrumentation-file='+str(out/(kind+'.fdata')),*extra],kind+'-instrument')
        command([inst,'on','train','4096','71','1'],kind+'-training')
    profile=pipeline.predicate_profile(json.loads(manifest.read_text()),out/'probe.fdata')
    profile['sites']=[s for s in profile['sites'] if s['function']=='lookup_branch']
    if len(profile['sites'])!=1: raise RuntimeError('compiler did not emit the supported single CMOV group; no performance claim is made')
    (out/'candidate-profile.json').write_text(json.dumps(profile,indent=2)+'\n')
    binary=out/'dual.bolt'
    command([bolt,original,'-o',binary,'-data='+str(out/'normal.fdata'),*pipeline.COMMON,
             '-cmov-branchify-candidate','-cmov-branchify-profile='+str(out/'candidate-profile.json')],'optimize')
    if not re.search(r'CMOV branchify: \d+ candidates, 1 converted',(out/'optimize.log').read_text()):
        raise RuntimeError('expected exactly one actual BOLT conversion')
    command([shutil.which('objdump'),'--disassemble=run_dispatch',binary],'dispatch-disassembly')
    calls=[s for s in (out/'dispatch-disassembly.log').read_text().splitlines() if re.search(r'\bcallq?\b.*<run_plain>',s)]
    if len(calls)!=1: raise RuntimeError('compiler did not preserve one common plain call site')
    meta={'prototype_only':True,'new_bolt_option_implemented':False,
          'compiler':subprocess.check_output([compiler,'--version'],text=True).splitlines()[0],
          'bolt_sha256':pipeline.sha(bolt),'binary_sha256':pipeline.sha(binary),
          'shared_plain_call_site':calls,'sources':{f.name:pipeline.sha(f) for f in sorted(source.iterdir()) if f.is_file()}}
    (out/'build.json').write_text(json.dumps(meta,indent=2)+'\n')
    print(json.dumps(meta,indent=2))
if __name__=='__main__': main()
