#!/usr/bin/env python3
"""Measure -O2 and -O3 on the same CPU, model and workload."""
import json
import os
import platform
import sys
from pathlib import Path
from measure import BASE, benchmark, cpu_flags


def main():
    if len(sys.argv) != 4:
        raise SystemExit('usage: measure_optlevel.py BUILD_DIR MODEL OUTPUT_DIR')
    build, model, out = map(Path, sys.argv[1:])
    info = Path('/proc/cpuinfo').read_text()
    if not BASE <= cpu_flags(info):
        raise RuntimeError('AVX2 features not available on every CPU')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two logical CPUs required')
    report = {'cpu': next((s.split(':', 1)[1].strip() for s in info.splitlines() if s.startswith('model name')), 'unknown'),
              'kernel': platform.release(), 'cpu_affinity': cpus, 'model_sha256': '61c69fc5ce91982e26c625d43be5c3c7f0f774da22f4fa4e45c37a80a22ddad4',
              'note': 'Native compiler settings, not an OS comparison. Fixed order; same host and workload.', 'results': {}}
    for level in ('2', '3'):
        binary = build / f'o{level}/bin/llama-bench'
        args = ['-p', '256,2048', '-n', '32', '-t', '2', '-fa', '0', '-b', '2048', '-ub', '512', '-r', '3']
        report['results']['O' + level] = benchmark(binary, model, ','.join(map(str, cpus)), args, out / f'o{level}-bench.log')
        (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print('Compared O2 and O3')


if __name__ == '__main__':
    main()
