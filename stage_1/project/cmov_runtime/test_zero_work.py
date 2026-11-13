#!/usr/bin/env python3
"""Check lifted-entry semantics and conservative rejection with actual BOLT."""
import argparse, json, subprocess
from pathlib import Path
from build import HERE, STAGE, sha, write

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--compiler',default='clang++')
    p.add_argument('--bolt',type=Path,default=STAGE/'build/bin/llvm-bolt')
    a=p.parse_args();b=a.build.resolve();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
    checks=[];commands=[]
    def run(argv,name):
        r=subprocess.run(list(map(str,argv)),capture_output=True,text=True,timeout=240)
        (o/(name+'.log')).write_text(r.stdout+r.stderr)
        commands.append({'argv':list(map(str,argv)),'returncode':r.returncode})
        write(o/'commands.json',commands)
        if r.returncode:raise RuntimeError(name+': '+r.stderr[-1200:])
        return r.stdout
    def optimize(inp,tag,enabled):
        return run([a.bolt,inp,'--lite=0','--verify-cfg',
                    *(['--cmov-branchify-runtime','--cmov-branchify-profile='+str(o/(tag+'.json'))] if enabled else []),
                    '-o',o/(tag+('-on' if enabled else '-off'))],tag+('-on' if enabled else '-off'))
    def profile(inp,tag):
        run([a.bolt,inp,'--lite=0','--cmov-branchify-sites='+str(o/(tag+'-sites.json')),
             '-o',o/(tag+'-enum')],tag+'-enumerate')
        data=json.loads((o/(tag+'-sites.json')).read_text())
        data['sites']=[dict(s,true_count=100000,false_count=0,validated=True,validation_speedup_lower=1.1)
                       for s in data['sites'] if s['function']=='cmov_kernel_v1']
        assert len(data['sites'])==1
        write(o/(tag+'.json'),data)
    # Synthetic profiles below exercise legality and semantics; they never
    # approve a performance claim. Production calibration is in build.py.
    obj=o/'driver.o';run([a.compiler,'-O3','-g','-std=c++17','-I',HERE,'-c',HERE/'test_zero_work.cpp','-o',obj],'driver')
    inp=o/'input';run([a.compiler,'-Wl,--emit-relocs',obj,b/'kernel.o',b/'plain.o',b/'entry.o','-o',inp],'link')
    profile(inp,'functional');optimize(inp,'functional',False)
    log=optimize(inp,'functional',True)
    assert 'CMOV runtime: proved zero-work prefix,' in log
    off=json.loads(run([o/'functional-off'],'functional-check-off'))
    on=json.loads(run([o/'functional-on','lifted'],'functional-check-on'))
    assert off==on
    checks.append({'name':'actual lifted ELF, full/empty/mixed queries, null/guard-page unused contexts, null counters',**on})
    # Two context layouts, plus two prefixes that must be left untouched.
    for tag,offset,condition,zero in [('standard',0,'jle','xor %eax,%eax'),
                                      ('offset-context',24,'jle','xor %eax,%eax'),
                                      ('nonzero-return',0,'jle','mov $7,%eax'),
                                      ('different-predicate',0,'je','xor %eax,%eax')]:
        asm=f'''.text
.globl cmov_kernel_v1
.type cmov_kernel_v1,@function
cmov_kernel_v1:
.cfi_startproc
cmp %rdx,%rsi
je .Lzero
mov {offset}(%rdi),%rcx
mov {offset+8}(%rdi),%rdi
sub %rcx,%rdi
sar $3,%rdi
test %rdi,%rdi
{condition} .Lzero
mov $3,%r10d
.Lloop:
cmp %rcx,%rdi
cmovae %rcx,%r8
cmovae %rdx,%r9
dec %r10
jne .Lloop
mov $11,%eax
ret
.Lzero:
{zero}
ret
.cfi_endproc
.size cmov_kernel_v1,.-cmov_kernel_v1
.section .note.GNU-stack,"",@progbits
'''
        src=o/(tag+'.s');src.write_text(asm)
        driver=o/(tag+'.cpp');driver.write_text(f'''#include "runtime.h"
#include <iostream>
int main() {{ uint64_t storage[8]{{}},q[1]{{}},v[1]{{}}; Slice s{{q,q+1}};
storage[{offset//8}]=(uint64_t)v; storage[{offset//8+1}]=(uint64_t)v;
Counters c; std::cout<<cmov_batch_v1(storage,&s,&s+1,&c)<<" ";
storage[{offset//8+1}]=(uint64_t)(v+1);
std::cout<<cmov_batch_v1(storage,&s,&s+1,&c)<<"\\n"; }}''')
        inp=o/(tag+'-input')
        run([a.compiler,'-O3','-I',HERE,'-Wl,--emit-relocs',src,driver,b/'plain.o',b/'entry.o','-o',inp],tag+'-link')
        profile(inp,tag);optimize(inp,tag,False);log=optimize(inp,tag,True)
        proved='CMOV runtime: proved zero-work prefix,' in log
        assert proved==(tag in ('standard','offset-context')),(tag,log)
        off=run([o/(tag+'-off')],tag+'-check-off');on=run([o/(tag+'-on')],tag+'-check-on')
        assert off==on,(tag,off,on)
        if not proved:
            import importlib.util
            spec=importlib.util.spec_from_file_location('pipeline',STAGE/'project/cmov_branchify/run.py')
            m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
            assert m.executable_hash(o/(tag+'-off'))==m.executable_hash(o/(tag+'-on'))
        checks.append({'name':tag,'lifted':proved,'result':on.strip(),'passed':True})
    write(o/'result.json',{'checks':checks,'bolt_sha256':sha(a.bolt),'performance_claimed':False})
    print(json.dumps({'checks':len(checks),'functional_cases':checks[0]['cases']}))

if __name__=='__main__':main()
