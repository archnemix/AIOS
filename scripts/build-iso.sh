#!/bin/sh
set -eu
if [ "$#" -ne 2 ]; then echo "Usage: $0 /path/to/buildroot /path/to/verified-model.gguf" >&2; exit 2; fi
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BUILDROOT=$(CDPATH= cd -- "$1" && pwd)
MODEL=$(realpath "$2")
OUTPUT=${AIOS_OUTPUT:-"$ROOT/output/iso"}
mkdir -p "$OUTPUT"
OUTPUT=$(CDPATH= cd -- "$OUTPUT" && pwd)
export AIOS_MODEL_PATH="$MODEL"
make -C "$BUILDROOT" O="$OUTPUT" BR2_EXTERNAL="$ROOT/os/buildroot" aios_iso_x86_64_defconfig
make -C "$BUILDROOT" O="$OUTPUT"
TREE="$OUTPUT/iso-tree"
mkdir -p "$TREE/boot/grub"
cp "$OUTPUT/images/bzImage" "$TREE/boot/bzImage"
cp "$OUTPUT/images/rootfs.cpio.gz" "$TREE/boot/rootfs.cpio.gz"
cp "$ROOT/os/buildroot/board/aios/iso/grub.cfg" "$TREE/boot/grub/grub.cfg"
grub-mkrescue -o "$OUTPUT/aios.iso" "$TREE"
sha256sum "$OUTPUT/aios.iso" > "$OUTPUT/aios.iso.sha256"
echo "ISO: $OUTPUT/aios.iso"
