#!/usr/bin/env python3
"""Build the unchanged library workload with a normal optimized compiler."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--compiler', default=os.environ.get('CXX', 'clang++'))
    p.add_argument('--output', required=True, type=Path)
    args = p.parse_args(); output = args.output.resolve()
    if output.exists(): raise SystemExit('Refusing to overwrite an existing workload')
    output.parent.mkdir(parents=True, exist_ok=True)
    compiler = shutil.which(args.compiler)
    if not compiler: raise SystemExit('Compiler not found; use --compiler /path/to/clang++')
    source = HERE/'workloads/source'
    command = [compiler, '-O3', '-g', '-Wl,--emit-relocs', str(source/'search_workload.cpp'),
               str(source/'search_lookup.cpp'), '-o', str(output)]
    subprocess.run(command, check=True)
    data = {'command': command, 'compiler': subprocess.check_output([compiler, '--version'], text=True).splitlines()[0],
            'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'sources': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in source.iterdir() if p.is_file()}}
    output.with_suffix('.build.json').write_text(json.dumps(data, indent=2)+'\n')
    print(json.dumps(data, indent=2))


if __name__ == '__main__': main()
