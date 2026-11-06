#!/usr/bin/env python3
"""Measure baseline versus AVX2 kernels under the same CPU affinity."""
import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def flags_for_all_cpus():
    sections = Path('/proc/cpuinfo').read_text().split('\n\n')
    flags = []
    for section in sections:
        for line in section.splitlines():
            if line.startswith('flags'):
                flags.append(set(line.split(':', 1)[1].split()))
    return set.intersection(*flags) if flags else set()


def main():
    baseline, avx2, model, out = sys.argv[1:]
    required = {'sse4_2', 'avx', 'avx2', 'fma', 'f16c', 'bmi2'}
    if not required <= flags_for_all_cpus():
        raise RuntimeError('CPU/OS does not expose required AVX2 features on every CPU')
    available = sorted(os.sched_getaffinity(0))
    selected = available[:min(2, len(available))]
    if not selected:
        raise RuntimeError('no CPUs available')
    cpu_arg = ','.join(map(str, selected))
    counts = '1,2' if len(selected) >= 2 else '1'
    result = {'kernel': platform.release(), 'cpu_affinity': selected, 'model': Path(model).name,
              'flags_required': sorted(required), 'threads_tested': counts,
              'note': 'Same host and model, portable vs AVX2 build; not an OS comparison.', 'runs': {}}
    cpu_info = Path('/proc/cpuinfo').read_text()
    result['cpu'] = next((line.split(':', 1)[1].strip() for line in cpu_info.splitlines()
                          if line.startswith('model name')), 'unknown')
    result['memory'] = next((line for line in Path('/proc/meminfo').read_text().splitlines()
                             if line.startswith('MemTotal:')), 'unknown')
    cache = Path('/sys/devices/system/cpu') / f'cpu{selected[0]}' / 'cache'
    result['cache'] = []
    for index in sorted(cache.glob('index*')):
        try:
            result['cache'].append({name: (index / name).read_text().strip()
                                    for name in ('level', 'type', 'size', 'shared_cpu_list')})
        except OSError:
            pass
    for name, binary in [('baseline', baseline), ('avx2', avx2)]:
        cmd = ['taskset', '-c', cpu_arg, binary, '-m', model, '-p', '128', '-n', '32',
               '-t', counts, '-r', '3', '-ngl', '0', '-o', 'json']
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1200)
        Path(out, f'{name}-stderr.log').write_text(proc.stderr[-20000:])
        if proc.returncode:
            raise RuntimeError(f'{name} benchmark failed: exit {proc.returncode}')
        result['runs'][name] = json.loads(proc.stdout)
    Path(out, 'results.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
