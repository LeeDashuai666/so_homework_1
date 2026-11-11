#!/usr/bin/env bash
set -euxo pipefail
export GIT_TERMINAL_PROMPT=0
hw_commit=3bd152ddbb6df45e0e07d6c9e9eb1573dcfd3dc6
hw_mode="${GIT_DOWNLOAD_MODE:-auto}"
case "$hw_mode" in auto|direct|proxy) ;; *) echo 'GIT_DOWNLOAD_MODE must be auto/direct/proxy' >&2; exit 2;; esac
git init -q /llvm
git -C /llvm remote add origin https://github.com/llvm/llvm-project.git
git -C /llvm config http.version HTTP/1.1
git -C /llvm config http.lowSpeedLimit 1024
git -C /llvm config http.lowSpeedTime 60
git -C /llvm config http.postBuffer 67108864
git -C /llvm config remote.origin.promisor true
git -C /llvm config remote.origin.partialclonefilter blob:none
hw_ok=0
for hw_try in 1 2 3; do
  echo "Fetching fixed LLVM commit (attempt $hw_try/3): $hw_commit"
  if [[ "$hw_mode" == direct || ( "$hw_mode" == auto && "$hw_try" == 1 ) ]]; then
    git -C /llvm config http.proxy ''
  else
    git -C /llvm config --unset http.proxy || true
  fi
  if timeout 120 git -C /llvm fetch --depth=1 --filter=blob:none --progress origin "$hw_commit"; then hw_ok=1; break; fi
done
[[ "$hw_ok" == 1 ]] || { echo 'Cannot download the fixed LLVM commit; check network/proxy settings.' >&2; exit 1; }
git -C /llvm sparse-checkout init --no-cone
git -C /llvm sparse-checkout set --no-cone --stdin <<'PATTERNS'
/*
!/*/
/llvm/
/bolt/
/cmake/
/third-party/
/libc/
!/llvm/test/
!/llvm/unittests/
!/bolt/test/
!/bolt/unittests/
!/libc/test/
!/libc/benchmarks/
PATTERNS
git -C /llvm checkout --progress --detach "$hw_commit"
[[ "$(git -C /llvm rev-parse HEAD)" == "$hw_commit" ]]
