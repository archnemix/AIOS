#!/usr/bin/env python3
"""Test near-limit input and shared-prefix reuse in the actual KVM appliance."""
import importlib.util
import json
import os
import platform
import sys
import tempfile
from pathlib import Path

from iso_benchmark.context import complete, shared_prefix


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(file))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adaptive = load('adaptive_iso', 'test-adaptive-iso.py')
compiler = load('compiler_iso', 'test-compiler-iso.py')


def main():
    if len(sys.argv) != 2:
        raise RuntimeError('usage: test-long-context-iso.py AIOS.iso')
    if not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('KVM required for this measurement')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two available CPUs required')
    cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                if line.startswith('model name')), 'unknown')
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        image = tmp / 'test.iso'
        compiler.test_image(Path(sys.argv[1]).resolve(), image, tmp / 'tree')
        process, client = adaptive.start_guest(image, tmp / 'serial.log', ','.join(map(str, cpus)),
                                                18082, 'host', 'avx2')
        try:
            tokens = client.request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
            if len(tokens) < 2:
                raise RuntimeError('tokenizer returned too few tokens')
            long_prompt = [tokens[0], tokens[-1]] * 4000
            long_result = complete(client, long_prompt, False)
            print('8000-token check: ' + json.dumps(long_result), flush=True)
            cache_result = shared_prefix(client)
            print(json.dumps({'cpu': cpu, 'kernel': platform.release(), 'acceleration': 'KVM',
                              'cpu_affinity': cpus, 'threads': 2, 'guest_ram_mib': 1024,
                              'context_configured': 8192, 'long_context': long_result,
                              'shared_prefix': cache_result,
                              'limitations': 'Synthetic repeated-token prompts, one output token, one '
                              'measurement each; not a model-quality test. Prompt caching requires a '
                              'matching prefix in the same slot and is not guaranteed under concurrent use. '
                              'KVM is not a bare-metal OS comparison.'}, indent=2))
        finally:
            adaptive.stop(process)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
