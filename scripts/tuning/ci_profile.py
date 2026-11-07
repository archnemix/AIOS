#!/usr/bin/env python3
"""Interleaved inference-setting sweep for two-CPU GitHub runners."""
import json
import os
import platform
import statistics
import subprocess
import sys
from pathlib import Path

# Same F16 KV cache, AVX2 backend, model and CPU allocation throughout.
PROFILES = [('default', 512, 50), ('ub64', 64, 50), ('ub128', 128, 50),
            ('ub256', 256, 50), ('ub128-poll0', 128, 0), ('ub128-poll100', 128, 100)]


def main():
    if len(sys.argv) != 4:
        raise SystemExit('usage: ci_profile.py BENCH MODEL OUTPUT_DIR')
    binary, model, out = map(Path, sys.argv[1:])
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two allowed CPUs required')
    info = Path('/proc/cpuinfo').read_text()
    cpu = next((line.split(':', 1)[1].strip() for line in info.splitlines()
                if line.startswith('model name')), 'unknown')
    report = {'cpu': cpu, 'kernel': platform.release(), 'cpu_affinity': cpus,
              'threads': 2, 'model_sha256': '61c69fc5ce91982e26c625d43be5c3c7f0f774da22f4fa4e45c37a80a22ddad4',
              'samples': [], 'limitations': 'Native llama-bench, not the guest server; synthetic inputs, '
              'two samples in forward and reverse order. Prompt and generation-only tests are separate; '
              'the mixed 2048/64 test includes both. No model quality comparison. Shared CI '
              'host noise and virtual CPUs limit generalization.'}
    for order in (PROFILES, list(reversed(PROFILES))):
        for name, ubatch, poll in order:
            command = ['taskset', '-c', ','.join(map(str, cpus)), str(binary), '-m', str(model),
                       '-ngl', '0', '-o', 'json', '-t', '2', '-b', '2048', '-ub', str(ubatch),
                       '--poll', str(poll), '-p', '256,2048', '-n', '64', '-pg', '2048,64', '-r', '1']
            run = subprocess.run(command, capture_output=True, text=True, timeout=1200)
            (out / f'{name}.log').write_text(run.stderr[-12000:])
            if run.returncode:
                raise RuntimeError(f'{name} benchmark failed ({run.returncode}); see {name}.log')
            data = json.loads(run.stdout)
            report['samples'].append({'profile': name, 'ubatch': ubatch, 'poll': poll, 'benchmarks': data})
            (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    summary = {}
    for name, _, _ in PROFILES:
        rows = [sample for sample in report['samples'] if sample['profile'] == name]
        keys = {(r['n_prompt'], r['n_gen']) for s in rows for r in s['benchmarks']}
        summary[name] = {f'{p}/{g}': statistics.median(r['avg_ts'] for s in rows for r in s['benchmarks']
                                                       if (r['n_prompt'], r['n_gen']) == (p, g))
                         for p, g in sorted(keys)}
    report['median_tokens_per_second'] = summary
    (out / 'results.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
