#!/usr/bin/env bash
set -euo pipefail
hw_apt_mode="${APT_DOWNLOAD_MODE:-auto}"
case "$hw_apt_mode" in auto|direct|proxy) ;; *) echo 'APT_DOWNLOAD_MODE must be auto/direct/proxy' >&2; exit 2;; esac
hw_packages=("$@")
hw_common=(-o Acquire::Retries=1 -o Acquire::http::Timeout=15 -o Acquire::https::Timeout=15)
hw_direct=(-o Acquire::http::Proxy=DIRECT -o Acquire::https::Proxy=DIRECT)
hw_install() {
  apt-get "${hw_common[@]}" "$@" -o APT::Update::Error-Mode=any update &&
  apt-get "${hw_common[@]}" "$@" install -y --no-install-recommends "${hw_packages[@]}"
}
if [[ "$hw_apt_mode" != proxy ]] && hw_install "${hw_direct[@]}"; then
  echo 'Dependencies downloaded directly.'
elif [[ "$hw_apt_mode" == direct ]]; then
  echo 'Direct package download failed.' >&2; exit 1
else
  echo 'Retrying package download with configured proxy settings.'
  hw_install
fi
rm -rf /var/lib/apt/lists/*
