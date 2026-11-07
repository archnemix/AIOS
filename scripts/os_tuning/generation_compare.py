#!/usr/bin/env python3
"""Compare generation thread and polling settings in identical KVM guests."""
import hashlib
import json
import os
import platform
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from os_tuning import combination


def cpu_seconds(process):
    # Linux stat fields 14 and 15: include all QEMU process threads.
    fields = Path(f'/proc/{process.pid}/stat').read_text().rsplit(')', 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK')


def profiles(vcpus):
    return [('one', 1, 50), ('two', 2, 50)] + (
        [('four', 4, 50), ('four-poll0', 4, 0), ('four-poll100', 4, 100)] if vcpus >= 4 else
        [('two-poll0', 2, 0), ('two-poll100', 2, 100)])


def main():
    if len(sys.argv) != 3 or not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('usage: generation_compare.py AIOS.iso VCPUS (KVM required)')
    vcpus = int(sys.argv[2])
    if vcpus not in (2, 4):
        raise RuntimeError('vcpus must be 2 or 4')
    cpus = sorted(os.sched_getaffinity(0))[:vcpus]
    if len(cpus) != vcpus:
        raise RuntimeError(f'{vcpus} available CPUs required')
    cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                if line.startswith('model name')), 'unknown')
    modes = profiles(vcpus)
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        processes, clients = [], []
        try:
            for i, (name, threads, poll) in enumerate(modes):
                image = tmp / f'{name}.iso'
                args = f'aios.threads={threads} aios.batch-threads={vcpus} aios.poll={poll} aios.ubatch=128'
                combination.compiler.test_image(Path(sys.argv[1]).resolve(), image, tmp / f'tree{i}', args)
                serial = tmp / f'{name}.log'
                process, client = combination.adaptive.start_guest(image, serial, ','.join(map(str, cpus)),
                                                                    18082 + i, 'host', 'avx2', 2048, vcpus)
                processes.append(process)
                clients.append(client)
                log = serial.read_text(errors='replace')
                if f'AIOS: inference backend=avx2 threads={threads}' not in log or \
                   f'AIOS: batch threads={vcpus} generation poll={poll}' not in log or \
                   'AIOS: prompt microbatch=128' not in log:
                    raise RuntimeError(f'{name} guest did not select its expected profile')
            tokens = clients[0].request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
            if len(tokens) < 2:
                raise RuntimeError('tokenizer returned too few tokens')
            for client in clients:
                combination.bench.completion(client, tokens[:2] * 128, generated=64)
            # Spot-check deterministic response equality across settings; this is not a quality benchmark.
            digests = {}
            for (name, _, _), client in zip(modes, clients):
                response = client.request('/completion', {'prompt': 'The capital of France is', 'n_predict': 32,
                                          'temperature': 0, 'ignore_eos': True, 'cache_prompt': False}, timeout=120)
                digests[name] = hashlib.sha256(response.get('content', '').encode()).hexdigest()
            report = {'cpu': cpu, 'kernel': platform.release(), 'acceleration': 'KVM', 'host_affinity': cpus,
                      'guest_vcpus': vcpus, 'guest_ram_mib': 2048, 'batch_threads': vcpus,
                      'response_hashes': digests, 'identical_spot_responses': len(set(digests.values())) == 1,
                      'results': {}, 'limitations': 'Same ISO and vCPU allocation within each run; CPU thread '
                      'counts differ and can consume more CPU time. Fixed guest boot order, shared host, '
                      'synthetic repeated-token inputs, 3 samples at 256/2048 and 2 at 8000. CPU seconds '
                      'are QEMU process user+system time for request, not energy. One response equality '
                      'check is not a quality evaluation. Not a bare-metal or OS-only comparison.'}
            for n in (256, 2048, 8000):
                prompt = (tokens[:2] * ((n + 1) // 2))[:n]
                samples = {name: [] for name, _, _ in modes}
                orders = (list(range(len(modes))), list(reversed(range(len(modes)))))
                if n != 8000:
                    orders += (list(range(1, len(modes))) + [0],)
                for order in orders:
                    for i in order:
                        before = cpu_seconds(processes[i])
                        result = combination.bench.completion(clients[i], prompt, generated=64)
                        result['qemu_cpu_seconds'] = cpu_seconds(processes[i]) - before
                        samples[modes[i][0]].append(result)
                        print('Measurement: ' + json.dumps({'profile': modes[i][0], **result}), flush=True)
                fields = ('prompt_tokens_per_second', 'generation_tokens_per_second', 'wall_seconds', 'qemu_cpu_seconds')
                medians = {name: {field: statistics.median(s[field] for s in values) for field in fields}
                           for name, values in samples.items()}
                report['results'][str(n)] = {'samples': samples, 'medians': medians}
                print('PARTIAL_JSON=' + json.dumps({'input_tokens': n, 'medians': medians}), flush=True)
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
