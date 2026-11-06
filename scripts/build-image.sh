#!/bin/sh
# Buildroot must be checked out at the version documented in technical.md.
set -eu
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 /path/to/buildroot" >&2
    exit 2
fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BUILDROOT=$(CDPATH= cd -- "$1" && pwd)
OUTPUT=${AIOS_OUTPUT:-"$ROOT/output/aios"}
mkdir -p "$OUTPUT"
OUTPUT=$(CDPATH= cd -- "$OUTPUT" && pwd)
make -C "$BUILDROOT" O="$OUTPUT" BR2_EXTERNAL="$ROOT/os/buildroot" aios_x86_64_defconfig
make -C "$BUILDROOT" O="$OUTPUT"
printf '\nKernel and root filesystem: %s/images\n' "$OUTPUT"
