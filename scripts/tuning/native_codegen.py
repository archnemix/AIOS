#!/usr/bin/env python3
"""Screen host-specific code generation against the portable AVX2 baseline."""
import json
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 4:
        raise SystemExit('usage: native_codegen.py BUILD_DIR MODEL OUTPUT_DIR')
    build, model, out = map(Path, sys.argv[1:])
    cpus = sorted(os.sched_getaffinity(0))[:4]
    if len(cpus) != 4:
        raise RuntimeError('four available CPUs required')
    info = Path('/proc/cpuinfo').read_text()
    cpu = next((s.split(':', 1)[1].strip() for s in info.splitlines() if s.startswith('model name')), 'unknown')
    flags = next((s.split(':', 1)[1].strip().split() for s in info.splitlines() if s.startswith('flags')), [])
    report = {'cpu': cpu, 'flags': flags, 'kernel': platform.release(), 'affinity': cpus, 'samples': [],
              'limitations': 'Native Linux llama-bench screening, not the ISO server. The native build may '
              'require host-specific instruction sets and must not be distributed to unknown CPUs. '
              'Generation-only timing begins at a near-empty context; 2048/64 combines prompt and generation. '
              'Three interleaved samples, synthetic input, shared CI host, no quality/energy benchmark.'}
    modes = [('avx2', 2), ('native', 2), ('avx2', 4), ('native', 4)]
    for order in (modes, list(reversed(modes)), modes[1:] + modes[:1]):
        for mode, threads in order:
            command = ['taskset', '-c', ','.join(map(str, cpus)), str(build / mode / 'bin/llama-bench'),
                       '-m', str(model), '-ngl', '0', '-o', 'json', '-t', str(threads), '-b', '2048',
                       '-ub', '128', '-p', '0', '-n', '128', '-pg', '2048,64', '-r', '1']
            run = subprocess.run(command, capture_output=True, text=True, timeout=1200)
            (out / f'{mode}-{threads}.log').write_text(run.stderr[-12000:])
            if run.returncode:
                raise RuntimeError(f'{mode}/{threads} failed ({run.returncode})')
            report['samples'].append({'mode': mode, 'threads': threads, 'benchmarks': json.loads(run.stdout)})
            (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    summary = {}
    for mode, threads in modes:
        rows = [s for s in report['samples'] if s['mode'] == mode and s['threads'] == threads]
        keys = {(r['n_prompt'], r['n_gen']) for s in rows for r in s['benchmarks']}
        summary[f'{mode}-{threads}'] = {f'{p}/{g}': statistics.median(r['avg_ts'] for s in rows for r in s['benchmarks']
                                           if (r['n_prompt'], r['n_gen']) == (p, g)) for p, g in sorted(keys)}
    report['median_tokens_per_second'] = summary
    (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'cpu': cpu, 'medians': summary}, indent=2))


if __name__ == '__main__':
    main()
