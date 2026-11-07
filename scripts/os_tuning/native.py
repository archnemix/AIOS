#!/usr/bin/env python3
"""Factorial benchmark of process THP opt-out and CPU affinity on one Linux host."""
import ctypes
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

PR_SET_THP_DISABLE = 41


def physical_cores(cpus):
    chosen, seen = [], set()
    for cpu in cpus:
        root = Path(f'/sys/devices/system/cpu/cpu{cpu}/topology')
        try:
            identity = ((root / 'physical_package_id').read_text().strip(), (root / 'core_id').read_text().strip())
        except OSError:
            return cpus[:2]
        if identity not in seen:
            seen.add(identity)
            chosen.append(cpu)
            if len(chosen) == 2:
                return chosen
    return cpus[:2]


def setup(affinity, no_thp):
    def configure():
        if affinity is not None:
            os.sched_setaffinity(0, affinity)
        if no_thp and ctypes.CDLL(None, use_errno=True).prctl(PR_SET_THP_DISABLE, 1, 0, 0, 0) != 0:
            os._exit(125)
    return configure


def memory_sample(pid):
    try:
        entries = Path(f'/proc/{pid}/smaps_rollup').read_text().splitlines()
        values = {line.split(':', 1)[0]: int(line.split()[1]) for line in entries
                  if line.startswith(('AnonHugePages:', 'ShmemPmdMapped:', 'FilePmdMapped:', 'Rss:'))}
        return values
    except (OSError, ValueError, IndexError):
        return {}


def main():
    if len(sys.argv) != 4:
        raise SystemExit('usage: native.py BENCH MODEL OUTPUT')
    binary, model, output = map(Path, sys.argv[1:])
    available = sorted(os.sched_getaffinity(0))
    if len(available) < 2:
        raise RuntimeError('at least two logical CPUs are required')
    selected = physical_cores(available)
    kernel_thp = Path('/sys/kernel/mm/transparent_hugepage/enabled')
    policy = kernel_thp.read_text().strip() if kernel_thp.exists() else 'unavailable'
    cpu_info = Path('/proc/cpuinfo').read_text()
    cpu = next((line.split(':', 1)[1].strip() for line in cpu_info.splitlines() if line.startswith('model name')), 'unknown')
    report = {'cpu': cpu, 'kernel': platform.release(), 'available_cpus': available,
              'pinned_cpus': selected, 'thp_policy': policy, 'modes': [],
              'limitations': 'Native shared CI host, fixed mode order, two inference threads; affinity '
              'changes placement eligibility, not thread count. PR_SET_THP_DISABLE changes this process '
              'and descendants only. Huge-page samples may miss transient allocations. '
              'Not an OS comparison; performance and page usage are hardware/workload specific.'}
    modes = [('unrestricted', False), ('unrestricted', True), ('pinned', False), ('pinned', True)]
    for i, (placement, disable) in enumerate(modes):
        command = [str(binary), '-m', str(model), '-ngl', '0', '-o', 'json', '-t', '2', '-b', '512',
                   '-ub', '128', '-p', '256,2048', '-n', '64', '-r', '3']
        log = output / f'mode-{i}.log'
        stdout = output / f'mode-{i}.json'
        with log.open('w') as err, stdout.open('w') as out:
            process = subprocess.Popen(command, stdout=out, stderr=err,
                preexec_fn=setup(selected if placement == 'pinned' else None, disable))
            samples = []
            deadline = time.monotonic() + 1800
            while process.poll() is None:
                if time.monotonic() > deadline:
                    process.kill()
                    process.wait()
                    raise RuntimeError(f'mode {i} exceeded timeout')
                sample = memory_sample(process.pid)
                if sample:
                    samples.append(sample)
                time.sleep(2)
            if process.returncode:
                raise RuntimeError(f'mode {i} failed with {process.returncode}')
        data = json.loads(stdout.read_text())
        report['modes'].append({'placement': placement, 'thp_disabled': disable,
                                'peak_sampled_kib': {key: max((sample.get(key, 0) for sample in samples), default=0)
                                    for key in ('Rss', 'AnonHugePages', 'ShmemPmdMapped', 'FilePmdMapped')},
                                'benchmarks': data})
        (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
