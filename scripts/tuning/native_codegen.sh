#!/bin/bash
# Screening only: native binary MUST NOT be distributed to unknown CPUs.
set -euo pipefail
if [ "$#" -ne 2 ]; then echo 'usage: native_codegen.sh SOURCE OUTPUT' >&2; exit 2; fi
src=$(realpath "$1")
out=$(realpath -m "$2")
mkdir -p "$out"
common=(-DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DLLAMA_BUILD_TESTS=OFF
        -DLLAMA_BUILD_EXAMPLES=ON -DLLAMA_BUILD_SERVER=OFF -DLLAMA_CURL=OFF
        -DCMAKE_C_FLAGS_RELEASE='-O3 -DNDEBUG' -DCMAKE_CXX_FLAGS_RELEASE='-O3 -DNDEBUG')
cmake -S "$src" -B "$out/avx2" "${common[@]}" -DGGML_NATIVE=OFF -DGGML_AVX=ON \
    -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON -DGGML_BMI2=ON -DGGML_AVX_VNNI=OFF \
    -DGGML_AVX512=OFF -DGGML_AVX512_VBMI=OFF -DGGML_AVX512_VNNI=OFF -DGGML_AVX512_BF16=OFF \
    -DGGML_LLAMAFILE=ON > "$out/configure-avx2.log" 2>&1
cmake -S "$src" -B "$out/native" "${common[@]}" -DGGML_NATIVE=ON -DGGML_LLAMAFILE=ON \
    -DCMAKE_C_FLAGS=-march=native -DCMAKE_CXX_FLAGS=-march=native > "$out/configure-native.log" 2>&1
for mode in avx2 native; do
    cmake --build "$out/$mode" --target llama-bench -j2 > "$out/build-$mode.log" 2>&1
done
