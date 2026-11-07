#!/usr/bin/env python3
"""Compare F16 and experimental Q8 key caches in identical KVM guests."""
import json
import os
import platform
import signal
import statistics
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from os_tuning import combination, decode_cache, generation_compare


def main():
    if len(sys.argv) != 2 or not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('usage: guest_cache_compare.py AIOS.iso (KVM required)')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two available CPUs required')
    cpu = next((s.split(':', 1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines()
                if s.startswith('model name')), 'unknown')
    modes = [('f16', 'aios.k-cache=f16'), ('q8', 'aios.k-cache=q8_0')]
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        processes, clients = [], []
        try:
            for i, (name, args) in enumerate(modes):
                image = tmp / f'{name}.iso'
                combination.compiler.test_image(Path(sys.argv[1]).resolve(), image, tmp / f'tree{i}',
                                                args + ' aios.ubatch=128')
                serial = tmp / f'{name}.log'
                process, client = combination.adaptive.start_guest(image, serial, ','.join(map(str, cpus)),
                                                                    18082+i, 'host', 'avx2', 2048)
                processes.append(process)
                clients.append(client)
                key_type = 'q8_0' if name == 'q8' else 'f16'
                log = serial.read_text(errors='replace')
                if f'AIOS: key cache={key_type}' not in log or 'AIOS: inference backend=avx2 threads=2' not in log:
                    raise RuntimeError(f'{name} guest selected the wrong inference profile')
            token_pair = clients[0].request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
            if len(token_pair) < 2:
                raise RuntimeError('tokenization failed')
            for client in clients:
                decode_cache.completion(client, token_pair[:2] * 128)
            quality = {}
            for (name, _), client in zip(modes, clients):
                answers = []
                for prompt in decode_cache.PROMPTS:
                    result = client.request('/v1/chat/completions', {'messages': [{'role': 'user', 'content': prompt}],
                                            'max_tokens': 32, 'temperature': 0}, timeout=180)
                    answers.append(result['choices'][0]['message']['content'])
                quality[name] = answers
            report = {'cpu': cpu, 'kernel': platform.release(), 'host_affinity': cpus, 'threads': 2,
                      'guest_vcpus': 2, 'guest_ram_mib': 2048, 'ubatch': 128,
                      'quality_spot_responses': quality, 'results': {},
                      'limitations': 'Same ISO/model/CPU allocation, two KVM guests, F16 value cache in both. '
                      'Q8 key cache is lossy and can change responses; five short prompts are not a quality '
                      'benchmark. Synthetic repeated tokens, fixed boot order, three samples at 256/2048 '
                      'and two at 8000. Other guest suspended during measurement. QEMU CPU seconds include '
                      'prefill, output, and virtualization, not energy. Not a Linux/Windows comparison.'}
            for process in processes:
                os.kill(process.pid, signal.SIGSTOP)
            for n in (256, 2048, 8000):
                prompt = (token_pair[:2] * ((n+1)//2))[:n]
                samples = {name: [] for name, _ in modes}
                orders = ((0, 1), (1, 0), (0, 1)) if n != 8000 else ((0, 1), (1, 0))
                for order in orders:
                    for i in order:
                        os.kill(processes[i].pid, signal.SIGCONT)
                        try:
                            before = generation_compare.cpu_seconds(processes[i])
                            result = decode_cache.completion(clients[i], prompt)
                            result['qemu_cpu_seconds'] = generation_compare.cpu_seconds(processes[i]) - before
                            result['qemu_peak_rss_kib'] = decode_cache.rss_kib(processes[i].pid)
                        finally:
                            os.kill(processes[i].pid, signal.SIGSTOP)
                        samples[modes[i][0]].append(result)
                        print('Measurement: ' + json.dumps({'profile': modes[i][0], **result}), flush=True)
                fields = ('prompt_tokens_per_second', 'generation_tokens_per_second', 'wall_seconds',
                          'qemu_cpu_seconds', 'qemu_peak_rss_kib')
                medians = {name: {field: statistics.median(s[field] for s in values) for field in fields}
                           for name, values in samples.items()}
                report['results'][str(n)] = {'samples': samples, 'medians': medians}
                print('PARTIAL_JSON=' + json.dumps({'input_tokens': n, 'medians': medians}), flush=True)
            print('REPORT_JSON=' + json.dumps(report), flush=True)
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    os.kill(process.pid, signal.SIGCONT)
                combination.adaptive.stop(process)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
