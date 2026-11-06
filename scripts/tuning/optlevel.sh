#!/bin/bash
# Compare the toolchain's -O2 and -O3 settings on the same AVX2 workload.
set -euo pipefail
if [ "$#" -ne 2 ]; then echo 'usage: optlevel.sh LLAMA_SOURCE OUTPUT_DIRECTORY' >&2; exit 2; fi
src=$(realpath "$1")
out=$(realpath -m "$2")
mkdir -p "$out"
for level in 2 3; do
    cmake -S "$src" -B "$out/o$level" -DCMAKE_BUILD_TYPE=Release \
        "-DCMAKE_C_FLAGS_RELEASE=-O$level -DNDEBUG" "-DCMAKE_CXX_FLAGS_RELEASE=-O$level -DNDEBUG" \
        -DBUILD_SHARED_LIBS=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=ON -DLLAMA_BUILD_SERVER=OFF -DLLAMA_CURL=OFF \
        -DGGML_NATIVE=OFF -DGGML_AVX=ON -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON -DGGML_BMI2=ON \
        -DGGML_AVX512=OFF -DGGML_LLAMAFILE=ON > "$out/configure-o$level.log" 2>&1
    cmake --build "$out/o$level" --target llama-bench -j2 > "$out/build-o$level.log" 2>&1
done
