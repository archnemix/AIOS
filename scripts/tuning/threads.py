#!/usr/bin/env python3
"""Sweep generation and prompt thread counts with model and affinity fixed."""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 4:
        raise SystemExit('usage: threads.py BENCH MODEL OUTPUT_DIR')
    binary, model, out = map(Path, sys.argv[1:])
    available = sorted(os.sched_getaffinity(0))
    if not available:
        raise RuntimeError('no allowed CPUs')
    # Keep this focused on the small CI machine and bound runtime.
    cpus = available[:min(8, len(available))]
    choices = sorted({n for n in (1, 2, len(cpus)) if n <= len(cpus)})
    info = Path('/proc/cpuinfo').read_text()
    cpu = next((s.split(':', 1)[1].strip() for s in info.splitlines() if s.startswith('model name')), 'unknown')
    report = {'cpu': cpu, 'kernel': platform.release(), 'cpus': cpus, 'thread_counts': choices,
              'model_sha256': '61c69fc5ce91982e26c625d43be5c3c7f0f774da22f4fa4e45c37a80a22ddad4',
              'results': {}, 'limitations': 'Native fixed-order synthetic benchmark; a given runner may '
              'expose virtual cores and SMT siblings. Prompt and generation may have different optima. '
              'Results are not an OS-only comparison or universal auto-tuning policy.'}
    for microbatch in (128, 512):
        command = ['taskset', '-c', ','.join(map(str, cpus)), str(binary), '-m', str(model), '-ngl', '0',
                   '-o', 'json', '-t', ','.join(map(str, choices)), '-b', '2048', '-ub', str(microbatch),
                   '-p', '256,2048', '-n', '64', '-pg', '2048,64', '-r', '3']
        run = subprocess.run(command, capture_output=True, text=True, timeout=1800)
        (out / f'ubatch-{microbatch}.log').write_text(run.stderr[-30000:])
        if run.returncode:
            raise RuntimeError(f'ubatch {microbatch} failed with {run.returncode}')
        report['results'][str(microbatch)] = json.loads(run.stdout)
        (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
