#!/usr/bin/env python3
"""Factorial comparison of automatic threads and the prompt microbatch option."""
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


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adaptive = load('adaptive_iso', SCRIPTS / 'test-adaptive-iso.py')
compiler = load('compiler_iso', SCRIPTS / 'test-compiler-iso.py')
bench = load('long_compare', Path(__file__).with_name('long_compare.py'))


def main():
    if len(sys.argv) != 2 or not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('usage: combination.py AIOS.iso (KVM required)')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two available CPUs required')
    cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                if line.startswith('model name')), 'unknown')
    modes = [('baseline', ''), ('microbatch', 'aios.ubatch=128'),
             ('autotune', 'aios.autotune=1'), ('combined', 'aios.autotune=1 aios.ubatch=128')]
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        processes, clients, threads = [], [], {}
        try:
            for i, (name, args) in enumerate(modes):
                image = tmp / f'guest{i}.iso'
                compiler.test_image(Path(sys.argv[1]).resolve(), image, tmp / f'tree{i}', args)
                serial = tmp / f'guest{i}.log'
                process, client = adaptive.start_guest(image, serial, ','.join(map(str, cpus)), 18082 + i,
                                                       'host', 'avx2')
                processes.append(process)
                clients.append(client)
                log = serial.read_text(errors='replace')
                match = re.search(r'AIOS: inference backend=avx2 threads=(\d+)', log)
                if not match or ('aios.autotune=1' in args and 'AIOS: tuning selected ' not in log):
                    raise RuntimeError(f'{name} did not run its expected thread setting')
                ub = '128' if 'aios.ubatch=128' in args else 'auto'
                if 'AIOS: prompt microbatch=' + ub not in log:
                    raise RuntimeError(f'{name} did not select expected microbatch')
                threads[name] = int(match.group(1))
            tokens = clients[0].request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
            if len(tokens) < 2:
                raise RuntimeError('tokenizer returned too few tokens')
            report = {'cpu': cpu, 'kernel': platform.release(), 'acceleration': 'KVM', 'host_affinity': cpus,
                      'guest_ram_mib': 1024, 'selected_threads': threads, 'results': {},
                      'limitations': 'Same image and model, single fixed guest boot order, synthetic inputs, '
                      'three samples per profile. Baseline is fixed two threads, not another OS; autotune '
                      'selection may change across boots. No universal optimum is implied.'}
            warm = tokens[:2] * 128
            for client in clients:
                bench.completion(client, warm)
            for n in (256, 2048):
                prompt = (tokens[:2] * ((n + 1) // 2))[:n]
                samples = {name: [] for name, _ in modes}
                for order in ((0, 1, 2, 3), (3, 2, 1, 0), (1, 3, 0, 2)):
                    for i in order:
                        name = modes[i][0]
                        measurement = bench.completion(clients[i], prompt)
                        samples[name].append(measurement)
                        print('Measurement: ' + json.dumps({'profile': name, **measurement}), flush=True)
                fields = ('prompt_tokens_per_second', 'generation_tokens_per_second', 'wall_seconds')
                medians = {name: {field: statistics.median(sample[field] for sample in values) for field in fields}
                           for name, values in samples.items()}
                report['results'][str(n)] = {'samples': samples, 'medians': medians}
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
