#!/usr/bin/env python3
"""Flag admission, rejection identity and actual linked-runtime code audit."""
import argparse,copy,importlib.util,json,re,subprocess
from pathlib import Path
from build import STAGE,sha,write

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
 p.add_argument('--bolt',type=Path,default=STAGE/'build/bin/llvm-bolt')
 p.add_argument('--baseline',type=Path,default=STAGE/'baseline/bin/llvm-bolt')
 a=p.parse_args();b=a.build.resolve();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
 sp=importlib.util.spec_from_file_location('pipeline',STAGE/'project/cmov_branchify/run.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
 base=[str(a.bolt.resolve()),str(b/'input'),'-data='+str(b/'normal.fdata'),*m.COMMON]
 profile=json.loads((b/'validated-profile.json').read_text()); checks=[]
 def run(name,flags,ok=True,tool=None):
  target=o/name;argv=[*(base if tool is None else [str(tool.resolve()),*base[1:]]),*flags,'-o',str(target)]
  r=subprocess.run(argv,capture_output=True,text=True,timeout=90);(o/(name+'.log')).write_text(r.stdout+r.stderr)
  assert (r.returncode==0)==ok,(name,r.returncode,r.stderr[-1000:])
  if not ok:assert r.returncode>0 and 'Stack dump:' not in r.stderr,name
  checks.append({'name':name,'passed':True,'returncode':r.returncode})
  return target
 vanilla=run('vanilla',[],tool=a.baseline);off=run('default-off',[])
 assert m.executable_hash(vanilla)==m.executable_hash(off),'default-off code differs from pinned vanilla'
 checks.append({'name':'default-off executable sections addresses sizes identical to vanilla','passed':True})
 for name in ('empty','unvalidated','insufficient-gain','unbiased','too-few','wrong-group-size','wrong-hash','wrong-cpu','negative-count','duplicate'):
  data=copy.deepcopy(profile)
  if name=='empty':data['sites']=[]
  elif name=='wrong-hash':data['binary_sha256']='0'*64
  elif name=='wrong-cpu':data['host_cpu']='not-this-cpu'
  elif name=='duplicate':data['sites'].append(copy.deepcopy(data['sites'][0]))
  else:
   for s in data['sites']:
    if name=='unvalidated':s['validated']=False
    elif name=='insufficient-gain':s['validation_speedup_lower']=1.019
    elif name=='unbiased':s.update(true_count=50000,false_count=50000)
    elif name=='too-few':s.update(true_count=3,false_count=0)
    elif name=='wrong-group-size':s['group_size']=4
    elif name=='negative-count':s['true_count']=-1
  path=o/(name+'.json');write(path,data)
  valid=name not in ('wrong-hash','wrong-cpu','negative-count','duplicate')
  binary=run(name,['-cmov-branchify-runtime','-cmov-branchify-profile='+str(path)],valid)
  if valid:
   assert m.executable_hash(binary)==m.executable_hash(off),name
   checks.append({'name':name+' executable identity','passed':True})
 for name,symbol in [('missing-entry','-cmov-runtime-entry=absent'),('missing-kernel','-cmov-runtime-kernel=absent'),('wrong-forward-target','-cmov-runtime-plain=cmov_kernel_v1')]:
  binary=run(name,['-cmov-branchify-runtime','-cmov-branchify-profile='+str(b/'validated-profile.json'),symbol])
  assert m.executable_hash(binary)==m.executable_hash(off),name
  checks.append({'name':name+' executable identity','passed':True})
 for name,flags in [('missing-profile',[]),('conflict-static',['-cmov-branchify']),('conflict-candidate',['-cmov-branchify-candidate']),('conflict-instrument',['-instrument'])]:
  run(name,['-cmov-branchify-runtime',*flags,*([] if name=='missing-profile' else ['-cmov-branchify-profile='+str(b/'validated-profile.json')])],False)
 syms={}
 for line in subprocess.check_output(['nm','-S',str(b/'on')],text=True).splitlines():
  f=line.split()
  if len(f)==4:
   try:syms[f[3]]=(int(f[0],16),int(f[1],16))
   except ValueError:pass
 assert int.from_bytes((b/'on').read_bytes()[24:32],'little')==syms['_start'][0],'ELF entry changed to runtime init hook'
 checks.append({'name':'ELF entry remains application _start','passed':True})
 for name,want in [('cmov_kernel_v1',2),('__bolt_cmov_branch_v1',0)]:
  addr,size=syms[name]
  asm=subprocess.check_output(['objdump','-d',f'--start-address={addr}',f'--stop-address={addr+size}',str(b/'on')],text=True)
  (o/(name+'.asm')).write_text(asm)
  assert len(re.findall(r'\s+cmov[a-z]+\s',asm))==want,(name,asm)
 frames=subprocess.check_output(['readelf','--debug-dump=frames',str(b/'on')],text=True)
 addr,size=syms['__bolt_cmov_branch_v1']
 assert any(int(lo,16)<=addr and int(hi,16)>=addr+size for lo,hi in re.findall(r'pc=([0-9a-f]+)\.\.([0-9a-f]+)',frames)),'missing clone FDE'
 checks.append({'name':'exact symbol-sized CMOV counts and clone unwind FDE','passed':True})
 asm=subprocess.check_output(['objdump','-d',str(b/'on')],text=True)
 assert not re.search(r'\b(?:jmp|call)\s+0\s',asm),'unresolved runtime target'
 checks.append({'name':'runtime and thunk relocations resolved','passed':True})
 write(o/'result.json',{'checks':checks,'checks_passed':len(checks),'bolt_sha256':sha(a.bolt),'on_sha256':sha(b/'on'),'performance_claimed':False})
 print(json.dumps({'checks_passed':len(checks)}))
if __name__=='__main__':main()
