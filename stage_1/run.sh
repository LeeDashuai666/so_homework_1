#!/usr/bin/env bash
set -euo pipefail
hw_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
hw_mode="${1:-smoke}"
if [[ $# -gt 0 ]]; then shift; fi
case "$hw_mode" in
  smoke|functional|full|build|evidence) ;;
  -h|--help)
    echo 'Usage: ./run.sh [smoke|functional|full|build|evidence] [--output DIRECTORY] [--source] [--jobs N]'
    exit 0 ;;
  *) echo "Unknown mode: $hw_mode" >&2; exit 2 ;;
esac
hw_output="$hw_root/../results/$(date +%Y%m%d-%H%M%S)-$hw_mode"
hw_jobs="${BOLT_BUILD_JOBS:-2}"
hw_source=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --output) hw_output="${2:?--output requires a directory}"; shift 2 ;;
    --jobs) hw_jobs="${2:?--jobs requires a positive integer}"; shift 2 ;;
    --source) hw_source=1; shift ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done
[[ "$hw_jobs" =~ ^[1-9][0-9]*$ ]] || { echo '--jobs must be positive' >&2; exit 2; }
command -v python3 >/dev/null || { echo 'Python 3 is required by the launcher.' >&2; exit 2; }
if [[ "$hw_mode" == evidence ]]; then
  exec env PYTHONDONTWRITEBYTECODE=1 python3 "$hw_root/scripts/replay.py" --evidence "$hw_root/evidence/final" --output "$hw_output"
fi
[[ "$(uname -m)" == x86_64 ]] || { echo 'Native Linux x86-64 is required; emulated performance is not accepted.' >&2; exit 2; }
command -v docker >/dev/null || { echo 'Install Docker Engine or enable Docker Desktop WSL integration first.' >&2; exit 2; }
docker info >/dev/null 2>&1 || { echo 'Docker daemon is unavailable or current user lacks access.' >&2; exit 2; }
hw_fingerprint="$(python3 - "$hw_root" <<'PY'
from pathlib import Path
import hashlib,sys
p=Path(sys.argv[1]); h=hashlib.sha256()
files=[p/'Dockerfile',p/'BASELINE.json']
for d in ['project','runtime','scripts','patches','licenses']:
    files += [f for f in (p/d).rglob('*') if f.is_file() and '__pycache__' not in f.parts]
for f in sorted(files): h.update(str(f.relative_to(p)).encode()); h.update(f.read_bytes())
print(h.hexdigest()[:16])
PY
)"
hw_image="so-homework-1:runtime-$hw_fingerprint"
if [[ "$hw_source" == 0 ]] && ! docker image inspect "$hw_image" >/dev/null 2>&1 && [[ -f "$hw_root/image.json" ]]; then
  python3 "$hw_root/scripts/fetch_image.py" --metadata "$hw_root/image.json" \
    --fingerprint "$hw_fingerprint" --cache "$hw_root/.build"
fi
if [[ "$hw_source" == 1 ]] || ! docker image inspect "$hw_image" >/dev/null 2>&1; then
  echo "Building LLVM/BOLT at 2026-11-02; first build downloads source and compiles it (jobs=$hw_jobs)."
  hw_network=()
  if [[ -n "${BOLT_BUILD_NETWORK:-}" ]]; then
    hw_network=(--network "$BOLT_BUILD_NETWORK")
  elif [[ "${HTTP_PROXY:-${http_proxy:-${HTTPS_PROXY:-${https_proxy:-}}}}" =~ ^https?://(127\.0\.0\.1|localhost): ]]; then
    hw_network=(--network host)
    echo 'Using host network during build for the local proxy.'
  fi
  hw_proxy=()
  for hw_name in HTTP_PROXY HTTPS_PROXY http_proxy https_proxy NO_PROXY no_proxy; do
    if [[ -n "${!hw_name:-}" ]]; then hw_proxy+=(--build-arg "$hw_name"); fi
  done
  docker build --platform linux/amd64 "${hw_network[@]}" \
    "${hw_proxy[@]}" --build-arg APT_DOWNLOAD_MODE="${BOLT_APT_MODE:-auto}" \
    --build-arg GIT_DOWNLOAD_MODE="${BOLT_GIT_MODE:-auto}" \
    --build-arg BUILD_JOBS="$hw_jobs" -t "$hw_image" "$hw_root"
fi
if [[ "$hw_mode" == build ]]; then echo "Image ready: $hw_image"; exit 0; fi
[[ ! -e "$hw_output" ]] || { echo 'Choose a new --output directory; existing results are never overwritten.' >&2; exit 2; }
mkdir -p "$hw_output"
hw_output="$(cd "$hw_output" && pwd)"
echo "Image: $hw_image"
echo "Output: $hw_output"
exec docker run --rm --user "$(id -u):$(id -g)" --network none \
  --mount "type=bind,src=$hw_output,dst=/results" \
  "$hw_image" "$hw_mode" --output /results/run
