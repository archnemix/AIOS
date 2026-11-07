#!/usr/bin/env python3
"""Compare the optimized ISO default to its previous setting in KVM guests."""
import json
import os
import platform
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from os_tuning import combination


def main():
    if len(sys.argv) != 2 or not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('usage: ci_default_compare.py AIOS.iso (KVM required)')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two available CPUs required')
    cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                if line.startswith('model name')), 'unknown')
    modes = [('previous', 'aios.ubatch=auto', 'auto'), ('optimized', '', '128')]
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        processes, clients = [], []
        try:
            for i, (name, args, expected) in enumerate(modes):
                image = tmp / f'{name}.iso'
                combination.compiler.test_image(Path(sys.argv[1]).resolve(), image, tmp / f'tree{i}', args)
                serial = tmp / f'{name}.log'
                process, client = combination.adaptive.start_guest(image, serial, ','.join(map(str, cpus)),
                                                                     18082 + i, 'host', 'avx2', 2048)
                processes.append(process)
                clients.append(client)
                log = serial.read_text(errors='replace')
                if f'AIOS: prompt microbatch={expected}' not in log or 'AIOS: inference backend=avx2 threads=2' not in log:
                    raise RuntimeError(f'{name} guest did not select its expected profile')
            tokens = clients[0].request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
            if len(tokens) < 2:
                raise RuntimeError('tokenizer returned too few tokens')
            for client in clients:
                combination.bench.completion(client, tokens[:2] * 128)
            report = {'cpu': cpu, 'kernel': platform.release(), 'acceleration': 'KVM', 'host_affinity': cpus,
                      'guest_ram_mib': 2048, 'threads': 2, 'results': {},
                      'limitations': 'Identical ISO and two-vCPU guests, AVX2 embedded model; old upstream '
                      'microbatch explicitly requested vs new scoped default. Fixed boot order, synthetic '
                      'repeated-token input, three samples at 256/2048 and two at 8000. No Windows or '
                      'bare-metal comparison; settings may behave differently on other CPUs and prompts.'}
            for n in (256, 2048, 8000):
                prompt = (tokens[:2] * ((n + 1) // 2))[:n]
                samples = {name: [] for name, _, _ in modes}
                orders = ((0, 1), (1, 0), (0, 1)) if n != 8000 else ((0, 1), (1, 0))
                for order in orders:
                    for i in order:
                        result = combination.bench.completion(clients[i], prompt)
                        samples[modes[i][0]].append(result)
                        print('Measurement: ' + json.dumps({'profile': modes[i][0], **result}), flush=True)
                fields = ('prompt_tokens_per_second', 'generation_tokens_per_second', 'wall_seconds')
                medians = {name: {field: statistics.median(s[field] for s in values) for field in fields}
                           for name, values in samples.items()}
                report['results'][str(n)] = {'samples': samples, 'medians': medians}
            print('REPORT_JSON=' + json.dumps(report), flush=True)
        finally:
            for process in reversed(processes):
                combination.adaptive.stop(process)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
