#!/bin/sh
set -eu
if [ "$#" -ne 1 ]; then echo "Usage: $0 OUTPUT.gguf" >&2; exit 2; fi
url='https://huggingface.co/tensorblock/SmolLM2-135M-Instruct-GGUF/resolve/32db44d69cedb731dc0fc96f60e01a86c6f5919d/SmolLM2-135M-Instruct-Q3_K_M.gguf'
expected=61c69fc5ce91982e26c625d43be5c3c7f0f774da22f4fa4e45c37a80a22ddad4
tmp="$1.download"
trap 'rm -f "$tmp"' EXIT HUP INT TERM
curl -fL --retry 3 "$url" -o "$tmp"
printf '%s  %s\n' "$expected" "$tmp" | sha256sum -c -
mv "$tmp" "$1"
