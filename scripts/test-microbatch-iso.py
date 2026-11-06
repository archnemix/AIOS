#!/usr/bin/env python3
"""Compare two prompt microbatch settings using the same booted image."""
import importlib.util
import json
import os
import platform
import statistics
import sys
import tempfile
from pathlib import Path

from iso_benchmark.context import complete


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adaptive = load('adaptive_iso', 'test-adaptive-iso.py')
compiler = load('compiler_iso', 'test-compiler-iso.py')


def main():
    if len(sys.argv) != 2 or not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('usage: test-microbatch-iso.py AIOS.iso (KVM required)')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two available CPUs required')
    cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                if line.startswith('model name')), 'unknown')
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        images = [tmp / 'default.iso', tmp / 'ub128.iso']
        for i, args in enumerate(('', 'aios.ubatch=128')):
            compiler.test_image(Path(sys.argv[1]).resolve(), images[i], tmp / f'tree{i}', args)
        processes, clients = [], []
        try:
            for i in range(2):
                serial = tmp / f'guest{i}.log'
                process, client = adaptive.start_guest(images[i], serial, ','.join(map(str, cpus)),
                                                        18082 + i, 'host', 'avx2')
                processes.append(process)
                clients.append(client)
                expected = '128' if i else 'auto'
                if f'AIOS: prompt microbatch={expected}' not in serial.read_text(errors='replace'):
                    raise RuntimeError('guest did not select the expected microbatch')
            tokens = clients[0].request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
            if len(tokens) < 2:
                raise RuntimeError('tokenizer returned too few tokens')
            prompt = [tokens[0], tokens[-1]] * 1024
            for client in clients:
                complete(client, prompt, False)
            samples = {'default': [], 'ubatch128': []}
            for order in ((0, 1), (1, 0), (0, 1)):
                for i in order:
                    samples[('default', 'ubatch128')[i]].append(complete(clients[i], prompt, False))
            median_ms = {key: statistics.median(item['prompt_ms'] for item in values)
                         for key, values in samples.items()}
            print(json.dumps({'cpu': cpu, 'kernel': platform.release(), 'acceleration': 'KVM',
                              'cpu_affinity': cpus, 'threads': 2, 'guest_ram_mib': 1024,
                              'samples': samples, 'median_prompt_ms': median_ms,
                              'ubatch128_speedup': median_ms['default'] / median_ms['ubatch128'],
                              'limitations': 'Identical ISO and workload, fixed boot order, one model and '
                              'synthetic repeated-token input. Three samples; not an OS-only comparison '
                              'or a guarantee on other hardware or prompts.'}, indent=2))
        finally:
            for process in reversed(processes):
                adaptive.stop(process)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
