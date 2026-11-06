#!/usr/bin/env python3
"""Benchmark settings with fixed CPU affinity; save raw llama-bench samples."""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

BASE = {'sse4_2', 'avx', 'avx2', 'fma', 'f16c', 'bmi2'}
AVX512 = {'avx512f', 'avx512cd', 'avx512vl', 'avx512dq', 'avx512bw'}


def cpu_flags(text):
    flags = [set(line.split(':', 1)[1].split()) for line in text.splitlines() if line.startswith('flags')]
    return set.intersection(*flags) if flags else set()


def benchmark(binary, model, cpu_arg, args, log):
    command = ['taskset', '-c', cpu_arg, str(binary), '-m', str(model), '-ngl', '0', '-o', 'json'] + args
    run = subprocess.run(command, capture_output=True, text=True, timeout=1800)
    log.write_text(run.stderr[-30000:])
    if run.returncode:
        raise RuntimeError(f'{binary.name} benchmark failed with code {run.returncode}; see {log.name}')
    return json.loads(run.stdout)


def main():
    if len(sys.argv) != 4:
        raise SystemExit('usage: measure.py BUILD_DIR MODEL OUTPUT_DIR')
    build, model, out = map(Path, sys.argv[1:])
    info = Path('/proc/cpuinfo').read_text()
    features = cpu_flags(info)
    if not BASE <= features:
        raise RuntimeError('AVX2 features are not available on every CPU')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two allowed logical CPUs are required')
    cpu_arg = ','.join(map(str, cpus))
    report = {'cpu': next((s.split(':', 1)[1].strip() for s in info.splitlines() if s.startswith('model name')), 'unknown'),
              'kernel': platform.release(), 'cpu_affinity': cpus, 'model_sha256': '61c69fc5ce91982e26c625d43be5c3c7f0f774da22f4fa4e45c37a80a22ddad4',
              'flags': sorted(features), 'results': {},
              'limitations': 'Native runner, not OS comparison; fixed-order runs; benchmarks may not predict real prompts.'}
    modes = ['avx2', 'avx2-no-llamafile']
    if AVX512 <= features:
        modes.append('avx512')
    for mode in modes:
        binary = build / f'build-{mode}/bin/llama-bench'
        args = ['-p', '256', '-n', '64', '-t', '1,2', '-fa', '0,1', '-b', '256,512', '-ub', '128,256', '-r', '3']
        report['results'][mode] = benchmark(binary, model, cpu_arg, args, out / f'{mode}-short.log')
        # Separate prefill sweep avoids mixing decode with long-context timing.
        args = ['-p', '2048', '-n', '0', '-t', '1,2', '-fa', '0,1', '-b', '512', '-ub', '128,512', '-r', '2']
        report['results'][mode + '-long'] = benchmark(binary, model, cpu_arg, args, out / f'{mode}-long.log')
        (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Measured modes: ' + ', '.join(modes))
    print('AVX512 skipped' if 'avx512' not in modes else 'AVX512 measured')


if __name__ == '__main__':
    main()
