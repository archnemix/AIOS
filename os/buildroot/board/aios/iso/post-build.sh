#!/bin/sh
set -eu
: "${AIOS_MODEL_PATH:?Set AIOS_MODEL_PATH to the verified GGUF model}"
test -f "$AIOS_MODEL_PATH"
install -D -m 0644 "$AIOS_MODEL_PATH" "$1/opt/aios/model.gguf"
# The ISO runs entirely from its initramfs, with an ephemeral key each boot.
sed -i 's/^AIOS_MODEL_MODE=.*/AIOS_MODEL_MODE=embedded/' "$1/etc/aios/server.conf"
# Use a measured inference profile only for the embedded two-thread AVX2 case.
sed -i 's/^AIOS_UBATCH=.*/AIOS_UBATCH=ci-auto/' "$1/etc/aios/server.conf"
