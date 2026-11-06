#!/bin/bash
# Run both binaries on the same host and the same model, without network access.
set -euo pipefail
if [ "$#" != 3 ]; then echo 'usage: run.sh LLAMA_SOURCE MODEL OUTPUT_DIRECTORY' >&2; exit 2; fi
source_dir=$(realpath "$1")
model=$(realpath "$2")
out=$(realpath -m "$3")
mkdir -p "$out"
common=(-DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF -DLLAMA_BUILD_TESTS=OFF
        -DLLAMA_BUILD_EXAMPLES=ON -DLLAMA_BUILD_SERVER=OFF -DLLAMA_CURL=OFF -DGGML_NATIVE=OFF
        -DGGML_AVX512=OFF -DGGML_AVX512_VNNI=OFF -DGGML_AVX512_VBMI=OFF -DGGML_AVX512_BF16=OFF)
features=(GGML_AVX GGML_AVX2 GGML_FMA GGML_F16C GGML_BMI2)
for mode in baseline avx2; do
    flags=()
    for feature in "${features[@]}"; do
        if [ "$mode" = avx2 ]; then flags+=("-D${feature}=ON"); else flags+=("-D${feature}=OFF"); fi
    done
    cmake -S "$source_dir" -B "$out/build-$mode" "${common[@]}" "${flags[@]}" > "$out/configure-$mode.log" 2>&1
    cmake --build "$out/build-$mode" --target llama-bench -j2 > "$out/build-$mode.log" 2>&1
done
python3 "$(dirname "$0")/run.py" "$out/build-baseline/bin/llama-bench" "$out/build-avx2/bin/llama-bench" "$model" "$out"
