#!/usr/bin/env python3
"""Measure KV-cache tradeoffs on one pinned CPU and model; no production defaults."""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 4:
        raise SystemExit('usage: cache.py LLAMA_BENCH MODEL OUTPUT_DIR')
    binary, model, out = map(Path, sys.argv[1:])
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two CPUs required')
    affinity = ','.join(map(str, cpus))
    info = Path('/proc/cpuinfo').read_text()
    cpu = next((line.split(':', 1)[1].strip() for line in info.splitlines()
                if line.startswith('model name')), 'unknown')
    modes = [('f16', 'f16', '0'), ('q8_0', 'f16', '0'),
             ('f16', 'f16', '1'), ('q8_0', 'q8_0', '1')]
    report = {'cpu': cpu, 'kernel': platform.release(), 'cpu_affinity': cpus,
              'model_sha256': '61c69fc5ce91982e26c625d43be5c3c7f0f774da22f4fa4e45c37a80a22ddad4',
              'results': [], 'limitations': 'Native fixed-order synthetic microbenchmarks. '
              'Maximum RSS includes the whole process and changes with context length; '
              'quantized caches may change model outputs and quality. No quality test performed.'}
    for i, (key, value, flash) in enumerate(modes):
        mem = out / f'memory-{i}.txt'
        command = ['/usr/bin/time', '-f', '%M', '-o', str(mem), 'taskset', '-c', affinity, str(binary),
                   '-m', str(model), '-ngl', '0', '-o', 'json', '-t', '2', '-b', '512', '-ub', '128',
                   '-ctk', key, '-ctv', value, '-fa', flash, '-p', '2048', '-n', '64',
                   '-pg', '2048,64', '-r', '2']
        run = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        (out / f'mode-{i}.log').write_text(run.stderr[-30000:])
        if run.returncode:
            raise RuntimeError(f'cache mode {i} failed with {run.returncode}')
        report['results'].append({'key': key, 'value': value, 'flash': flash == '1',
                                  'max_rss_kib': int(mem.read_text().strip()), 'benchmarks': json.loads(run.stdout)})
        (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
