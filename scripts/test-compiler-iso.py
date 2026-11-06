#!/usr/bin/env python3
"""Compare two verified AIOS images on identical KVM CPU settings."""
import importlib.util
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from iso_benchmark.measure import run_comparison

spec = importlib.util.spec_from_file_location('adaptive_iso', Path(__file__).with_name('test-adaptive-iso.py'))
adaptive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adaptive)


def test_image(source, destination, tree, kernel_args=''):
    (tree / 'boot/grub').mkdir(parents=True)
    for name in ('bzImage', 'rootfs.cpio.gz', 'grub/grub.cfg'):
        subprocess.run(['xorriso', '-osirrox', 'on', '-indev', str(source), '-extract',
                        '/boot/' + name, str(tree / 'boot' / name)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    grub = tree / 'boot/grub/grub.cfg'
    grub.chmod(0o644)
    config = grub.read_text()
    if 'set default=0' not in config or 'aios.network=1' not in config:
        raise RuntimeError('expected GRUB entries not found')
    grub.write_text(config.replace('set default=0', 'set default=1', 1).replace(
        'aios.network=1', 'aios.network=1 aios.threads=2 ' + kernel_args, 1))
    subprocess.run(['grub-mkrescue', '-o', str(destination), str(tree)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    if len(sys.argv) != 3:
        raise RuntimeError('usage: test-compiler-iso.py O2.iso O3.iso')
    if not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('KVM required')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two available CPUs required')
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        images = [tmp / 'o2.iso', tmp / 'o3.iso']
        for i in range(2):
            test_image(Path(sys.argv[i + 1]).resolve(), images[i], tmp / f'tree{i}')
        processes = []
        try:
            clients = []
            for i in range(2):
                process, client = adaptive.start_guest(images[i], tmp / f'guest{i}.log',
                                                        ','.join(map(str, cpus)), 18082 + i,
                                                        'host', 'avx2')
                processes.append(process)
                clients.append(client)
            result = run_comparison(*clients)
            for key in ('samples', 'medians'):
                result[key] = {'O2': result[key]['github_linux'], 'O3': result[key]['aios_vm']}
            for key in ('output_tokens_per_second', 'prompt_tokens_per_second'):
                result[key + '_ratio'] = result['medians']['O3'][key] / result['medians']['O2'][key]
            cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                        if line.startswith('model name')), 'unknown')
            print(json.dumps({'cpu': cpu, 'kernel': platform.release(), 'acceleration': 'KVM',
                              'cpu_affinity': cpus, 'threads': 2, 'guest_ram_mib': 1024,
                              'results': result, 'limitations': 'Same runner and CPU features; image '
                              'builds also differ in the optional thread-tuner packaging. Both guests '
                              'are forced to two threads. Fixed boot order; not an OS-only comparison.'}, indent=2))
        finally:
            for process in reversed(processes):
                adaptive.stop(process)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
