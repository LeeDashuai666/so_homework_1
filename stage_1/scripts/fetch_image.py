#!/usr/bin/env python3
"""Download and verify the public release image, then load it into Docker."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.parse
import urllib.request

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--metadata',required=True,type=Path)
    p.add_argument('--fingerprint',required=True)
    p.add_argument('--cache',required=True,type=Path)
    args=p.parse_args(); meta=json.loads(args.metadata.read_text())
    if meta['code_fingerprint']!=args.fingerprint:
        raise SystemExit('Sources differ from the release image; use --source to rebuild.')
    url=meta['download_url']; parsed=urllib.parse.urlsplit(url)
    if parsed.scheme!='https' or parsed.netloc!='github.com' or not parsed.path.startswith('/LeeDashuai666/so_homework_1/releases/download/'):
        raise SystemExit('Unexpected release asset URL')
    args.cache.mkdir(parents=True,exist_ok=True)
    target=args.cache/'stage1.docker.tar.gz'
    def digest(path):
        h=hashlib.sha256()
        with path.open('rb') as f:
            for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
        return h.hexdigest()
    if not target.exists() or digest(target)!=meta['archive_sha256']:
        partial=target.with_suffix(target.suffix+'.part')
        errors=[]
        for proxy in [False,True]:
            try:
                opener=urllib.request.build_opener() if proxy else urllib.request.build_opener(urllib.request.ProxyHandler({}))
                print('Downloading verified stage-1 Docker image'+(' with configured proxy.' if proxy else ' directly.'),flush=True)
                count=0; milestone=0; h=hashlib.sha256()
                with opener.open(url,timeout=45) as response,partial.open('wb') as stream:
                    while True:
                        data=response.read(1024*1024)
                        if not data:break
                        stream.write(data);h.update(data);count+=len(data)
                        if count//(32*1024*1024)>milestone:
                            milestone=count//(32*1024*1024);print(f'Downloaded {count//(1024*1024)} MiB',flush=True)
                if h.hexdigest()!=meta['archive_sha256']:raise RuntimeError('image SHA256 mismatch')
                partial.replace(target);break
            except Exception as error:
                errors.append(type(error).__name__+': '+str(error))
        else: raise SystemExit('Image download failed. '+ '; '.join(errors)+'; use --source to build locally.')
    subprocess.run(['docker','load','--input',str(target)],check=True)
    actual=json.loads(subprocess.check_output(['docker','image','inspect',meta['image']],text=True))[0]
    if (actual['RootFS']['Layers']!=meta['rootfs_layers'] or actual['Os']!='linux' or actual['Architecture']!='amd64'
        or actual['Config']['Entrypoint']!=meta['entrypoint'] or actual['Config']['Cmd']!=meta['command']):
        raise SystemExit('Loaded Docker image content or entry point mismatch')
    print('Release image verified and loaded: '+actual['Id'],flush=True)

if __name__=='__main__':main()
