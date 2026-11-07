#!/usr/bin/env python3
"""Measure THP policy and microbatch separately and combined on identical guests."""
import importlib.util
import json
import os
import platform
import re
import statistics
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from iso_benchmark.context import complete


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adaptive = load('adaptive_iso', 'test-adaptive-iso.py')
compiler = load('compiler_iso', 'test-compiler-iso.py')


def main():
    if len(sys.argv) != 2 or not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('usage: image.py AIOS.iso (KVM required)')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two available CPUs required')
    cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                if line.startswith('model name')), 'unknown')
    options = [('never', False), ('always', False), ('never', True), ('always', True)]
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        guests, clients = [], []
        try:
            for i, (policy, ub128) in enumerate(options):
                args = 'transparent_hugepage=' + policy + (' aios.ubatch=128' if ub128 else '')
                image = tmp / f'image{i}.iso'
                compiler.test_image(Path(sys.argv[1]).resolve(), image, tmp / f'tree{i}', args)
                serial = tmp / f'serial{i}.log'
                process, client = adaptive.start_guest(image, serial, ','.join(map(str, cpus)),
                                                        18082 + i, 'host', 'avx2')
                guests.append(process)
                clients.append(client)
                log = serial.read_text(errors='replace')
                line = re.search(r'AIOS: transparent hugepage policy=(.*)', log)
                if not line or f'[{policy}]' not in line.group(1):
                    raise RuntimeError(f'guest THP policy {policy} not applied: {line.group(1) if line else "missing"}')
                expected = '128' if ub128 else 'auto'
                if f'AIOS: prompt microbatch={expected}' not in log:
                    raise RuntimeError('guest did not select the expected microbatch')
            tokens = clients[0].request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
            if len(tokens) < 2:
                raise RuntimeError('tokenizer returned too few tokens')
            prompt = [tokens[0], tokens[-1]] * 1024
            for client in clients:
                complete(client, prompt, False)
            samples = [[] for _ in options]
            for order in (range(4), reversed(range(4)), range(4)):
                for i in order:
                    samples[i].append(complete(clients[i], prompt, False))
            modes = []
            for i, (policy, ub128) in enumerate(options):
                median = statistics.median(item['prompt_ms'] for item in samples[i])
                modes.append({'thp': policy, 'ubatch': 128 if ub128 else 'default',
                              'median_prompt_ms': median, 'prompt_tokens_per_second': 2048000 / median,
                              'samples': samples[i]})
            print(json.dumps({'cpu': cpu, 'kernel': platform.release(), 'acceleration': 'KVM',
                              'host_affinity': cpus, 'threads': 2, 'guest_ram_mib': 1024, 'modes': modes,
                              'limitations': 'Same image, fixed guest boot order and single synthetic prompt. '
                              'Kernel policy verified, actual hugepage backing not measured. A policy of always '
                              'does not prove allocations used huge pages. Three samples; not a bare-metal OS comparison.'}, indent=2))
        finally:
            for process in reversed(guests):
                adaptive.stop(process)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
