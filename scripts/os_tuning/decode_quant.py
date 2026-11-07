#!/usr/bin/env python3
"""Screen Q2 vs embedded Q3 model on two CPUs, without changing the ISO."""
import json
import os
import platform
import secrets
import signal
import statistics
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from iso_benchmark.client import Client
from os_tuning import decode_cache, long_compare


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: decode_quant.py AIOS.iso Q2_MODEL')
    iso, q2 = map(lambda p: Path(p).resolve(), sys.argv[1:])
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two CPUs required')
    cpu = next((s.split(':', 1)[1].strip() for s in Path('/proc/cpuinfo').read_text().splitlines()
                if s.startswith('model name')), 'unknown')
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        target = long_compare.extract_target(iso, tmp)
        key = tmp / 'key'
        key.write_text(secrets.token_hex(32) + '\n')
        key.chmod(0o600)
        loader = next((target / 'lib').glob('ld-linux-x86-64.so.*'))
        models = [('q3', target / 'opt/aios/model.gguf'), ('q2', q2)]
        processes, clients = [], []
        try:
            for i, (_, model) in enumerate(models):
                cmd = ['taskset', '-c', ','.join(map(str, cpus)), str(loader), '--library-path',
                       f'{target / "lib"}:{target / "usr/lib"}', str(target / 'usr/bin/llama-server-avx2'),
                       '-m', str(model), '--api-key-file', str(key), '--host', '127.0.0.1', '--port', str(18200+i),
                       '--threads', '2', '--ctx-size', '8192', '--ubatch-size', '128', '--no-context-shift', '--no-webui']
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processes.append(proc)
                client = Client(18200+i, key.read_text().strip())
                long_compare.iso_test.wait_for_health(client, proc, 300)
                clients.append(client)
            pairs = [client.request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
                     for client in clients]
            if len(pairs[0]) < 2 or pairs[0] != pairs[1]:
                raise RuntimeError('models do not use the expected identical token IDs')
            pair = pairs[0]
            for client in clients:
                decode_cache.completion(client, pair[:2] * 128)
            quality = {}
            for (name, _), client in zip(models, clients):
                replies = []
                for prompt in decode_cache.PROMPTS:
                    result = client.request('/v1/chat/completions', {'messages': [{'role': 'user', 'content': prompt}],
                                            'max_tokens': 32, 'temperature': 0}, timeout=180)
                    replies.append(result['choices'][0]['message']['content'])
                quality[name] = replies
            report = {'cpu': cpu, 'kernel': platform.release(), 'cpu_affinity': cpus, 'threads': 2,
                      'environment': 'native Linux, exact ISO server and libraries', 'quality_spot_responses': quality,
                      'models': {name: {'bytes': model.stat().st_size} for name, model in models}, 'results': {},
                      'limitations': 'Q2 is a different lossy quantization of the same model family; token '
                      'predictions and quality may differ. Five short response comparisons are not a quality '
                      'benchmark. Two interleaved samples per length, fixed startup order, synthetic inputs, '
                      'shared CI hosts. Process CPU seconds include prefill and generation. No default changed; '
                      'native screening is not booted-ISO performance.'}
            for process in processes:
                os.kill(process.pid, signal.SIGSTOP)
            for n in (256, 2048, 8000):
                prompt = (pair[:2] * ((n + 1) // 2))[:n]
                samples = {name: [] for name, _ in models}
                for order in ((0, 1), (1, 0)):
                    for i in order:
                        os.kill(processes[i].pid, signal.SIGCONT)
                        try:
                            before = decode_cache.cpu_seconds(processes[i].pid)
                            sample = decode_cache.completion(clients[i], prompt)
                            sample['cpu_seconds'] = decode_cache.cpu_seconds(processes[i].pid) - before
                            sample['peak_rss_kib'] = decode_cache.rss_kib(processes[i].pid)
                        finally:
                            os.kill(processes[i].pid, signal.SIGSTOP)
                        samples[models[i][0]].append(sample)
                        print('Measurement: ' + json.dumps({'profile': models[i][0], **sample}), flush=True)
                fields = ('prompt_tokens_per_second', 'generation_tokens_per_second', 'wall_seconds', 'cpu_seconds', 'peak_rss_kib')
                medians = {name: {field: statistics.median(s[field] for s in values) for field in fields}
                           for name, values in samples.items()}
                report['results'][str(n)] = {'samples': samples, 'medians': medians}
                print('PARTIAL_JSON=' + json.dumps({'input_tokens': n, 'medians': medians}), flush=True)
            print('REPORT_JSON=' + json.dumps(report), flush=True)
        finally:
            for proc in reversed(processes):
                if proc.poll() is None:
                    os.kill(proc.pid, signal.SIGCONT)
                long_compare.adaptive.stop(proc)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
