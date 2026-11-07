#!/usr/bin/env python3
"""Compare previous and optimized ISO profiles at several context lengths."""
import importlib.util
import json
import os
import platform
import statistics
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adaptive = load('adaptive_iso', SCRIPTS / 'test-adaptive-iso.py')
compiler = load('compiler_iso', SCRIPTS / 'test-compiler-iso.py')
long_compare = load('long_compare', Path(__file__).with_name('long_compare.py'))


def main():
    if len(sys.argv) != 3 or not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('usage: evolution.py OLD.iso NEW.iso (KVM required)')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two available CPUs required')
    cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                if line.startswith('model name')), 'unknown')
    profiles = [('old_O2', Path(sys.argv[1]), ''), ('new_O3', Path(sys.argv[2]), ''),
                ('new_O3_ub128', Path(sys.argv[2]), 'aios.ubatch=128')]
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        processes, clients = [], []
        try:
            for i, (_, source, args) in enumerate(profiles):
                image = tmp / f'guest{i}.iso'
                compiler.test_image(source.resolve(), image, tmp / f'tree{i}', args)
                process, client = adaptive.start_guest(image, tmp / f'guest{i}.log',
                                                       ','.join(map(str, cpus)), 18082 + i, 'host', 'avx2')
                processes.append(process)
                clients.append(client)
            tokens = clients[0].request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
            if len(tokens) < 2:
                raise RuntimeError('tokenizer returned too few tokens')
            report = {'cpu': cpu, 'kernel': platform.release(), 'acceleration': 'KVM',
                      'host_affinity': cpus, 'threads': 2, 'guest_ram_mib': 1024,
                      'profiles': [p[0] for p in profiles], 'results': {},
                      'limitations': 'Fixed boot order, one CPU and model, synthetic inputs and 32 output '
                      'tokens; old and new images also differ in packaging/kernel configuration. No bare-metal '
                      'OS comparison. Only two long-prompt samples; results are not general guarantees.'}
            warm = (tokens[:2] * 128)[:256]
            for client in clients:
                long_compare.completion(client, warm)
            for length in (256, 2048, 8000):
                prompt = (tokens[:2] * ((length + 1) // 2))[:length]
                samples = {name: [] for name, _, _ in profiles}
                orders = ((0, 1, 2), (2, 1, 0), (1, 2, 0)) if length != 8000 else ((0, 1, 2), (2, 1, 0))
                for order in orders:
                    for index in order:
                        name = profiles[index][0]
                        result = long_compare.completion(clients[index], prompt)
                        samples[name].append(result)
                        print('Measurement: ' + json.dumps({'profile': name, **result}), flush=True)
                metrics = ('prompt_tokens_per_second', 'generation_tokens_per_second', 'wall_seconds')
                medians = {name: {key: statistics.median(x[key] for x in values) for key in metrics}
                           for name, values in samples.items()}
                report['results'][str(length)] = {'samples': samples, 'medians': medians}
            print('REPORT_JSON=' + json.dumps(report), flush=True)
        finally:
            for process in reversed(processes):
                adaptive.stop(process)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
