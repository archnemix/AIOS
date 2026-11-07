#!/bin/sh
# Optional, larger model for the external-volume profile; never bundled in the ISO.
set -eu
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 OUTPUT.gguf" >&2
    exit 2
fi
url='https://huggingface.co/Qwen/Qwen2.5-0.5B-Instruct-GGUF/resolve/9217f5db79a29953eb74d5343926648285ec7e67/qwen2.5-0.5b-instruct-q3_k_m.gguf'
expected=590d2479d401db206fe12a4562294d2de6211e06338a6e34fbad64b32f1469d0
tmp="$1.download"
trap 'rm -f "$tmp"' EXIT HUP INT TERM
curl -fL --retry 3 "$url" -o "$tmp"
printf '%s  %s\n' "$expected" "$tmp" | sha256sum -c -
mv "$tmp" "$1"
