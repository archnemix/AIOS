#!/bin/bash
# Build otherwise identical CPU variants of the pinned inference engine.
set -euo pipefail
if [ "$#" -ne 2 ]; then echo 'usage: build.sh LLAMA_SOURCE OUTPUT_DIRECTORY' >&2; exit 2; fi
source_dir=$(realpath "$1")
out=$(realpath -m "$2")
mkdir -p "$out"
common=(-DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DLLAMA_BUILD_TESTS=OFF
        -DLLAMA_BUILD_EXAMPLES=ON -DLLAMA_BUILD_SERVER=OFF -DLLAMA_CURL=OFF
        -DGGML_NATIVE=OFF -DGGML_AVX=ON -DGGML_AVX2=ON -DGGML_FMA=ON -DGGML_F16C=ON -DGGML_BMI2=ON
        -DGGML_AVX_VNNI=OFF -DGGML_AVX512_VBMI=OFF -DGGML_AVX512_VNNI=OFF -DGGML_AVX512_BF16=OFF)
for mode in avx2 avx2-no-llamafile avx512; do
    flags=(-DGGML_AVX512=OFF -DGGML_LLAMAFILE=ON)
    case "$mode" in
        avx2-no-llamafile) flags+=(-DGGML_LLAMAFILE=OFF) ;;
        avx512) flags+=(-DGGML_AVX512=ON) ;;
    esac
    cmake -S "$source_dir" -B "$out/build-$mode" "${common[@]}" "${flags[@]}" > "$out/configure-$mode.log" 2>&1
    cmake --build "$out/build-$mode" --target llama-bench -j2 > "$out/build-$mode.log" 2>&1
done
