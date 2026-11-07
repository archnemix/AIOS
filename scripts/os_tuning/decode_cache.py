#!/usr/bin/env python3
"""Screen CPU attention/cache options with the tested ISO server on Linux."""
import hashlib
import json
import os
import platform
import secrets
import shutil
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from iso_benchmark.client import Client
from os_tuning import long_compare

MODES = [('baseline', []), ('q8-key', ['--cache-type-k', 'q8_0']),
         ('flash-f16', ['--flash-attn']),
         ('flash-q8', ['--flash-attn', '--cache-type-k', 'q8_0', '--cache-type-v', 'q8_0'])]
PROMPTS = ['What is two plus two?', 'Write one sentence about the ocean.',
           'What is the capital of France?', 'Name one color of the sky.',
           'Explain what a computer does in one sentence.']


def cpu_seconds(pid):
    fields = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()
    return (int(fields[11]) + int(fields[12])) / os.sysconf('SC_CLK_TCK')


def rss_kib(pid):
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
        if line.startswith('VmHWM:'):
            return int(line.split()[1])
    return None


def completion(client, prompt):
    start = time.monotonic()
    result = client.request('/completion', {'prompt': prompt, 'n_predict': 64, 'temperature': 0,
                            'ignore_eos': True, 'cache_prompt': False}, timeout=1200)
    if result.get('tokens_evaluated') != len(prompt) or result.get('tokens_predicted') != 64 or result.get('truncated') is not False:
        raise RuntimeError('incomplete benchmark completion')
    timing = result['timings']
    return {'input_tokens': len(prompt), 'generated_tokens': 64, 'truncated': False,
            'prompt_tokens_per_second': timing['prompt_per_second'],
            'generation_tokens_per_second': timing['predicted_per_second'],
            'wall_seconds': time.monotonic() - start,
            'output_sha256': hashlib.sha256(result.get('content', '').encode()).hexdigest()}


def perf_probe(pid, client, prompt, out):
    perf = shutil.which('perf')
    if not perf:
        return {'available': False, 'reason': 'perf executable unavailable'}
    statfile = out / 'perf-stat.csv'
    cmd = [perf, 'stat', '-x,', '-e', 'cycles,instructions,cache-references,cache-misses',
           '-p', str(pid), '-o', str(statfile), '--', 'sleep', '30']
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        time.sleep(1)
        if proc.poll() is not None:
            _, err = proc.communicate(timeout=5)
            return {'available': False, 'reason': err[-1500:],
                    'stat': statfile.read_text()[-1500:] if statfile.exists() else ''}
        completion(client, prompt)
        _, err = proc.communicate(timeout=45)
        return {'available': proc.returncode == 0, 'exit_code': proc.returncode,
                'stat': statfile.read_text()[-6000:] if statfile.exists() else '', 'stderr': err[-1500:],
                'note': 'Counters cover an entire request plus idle interval; they do not isolate decode kernels.'}
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.communicate()


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: decode_cache.py AIOS.iso OUTPUT_DIR')
    iso, output = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
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
        processes, clients = [], []
        try:
            for i, (name, args) in enumerate(MODES):
                cmd = ['taskset', '-c', ','.join(map(str, cpus)), str(loader), '--library-path',
                       f'{target / "lib"}:{target / "usr/lib"}', str(target / 'usr/bin/llama-server-avx2'),
                       '-m', str(target / 'opt/aios/model.gguf'), '--api-key-file', str(key),
                       '--host', '127.0.0.1', '--port', str(18100 + i), '--threads', '2',
                       '--ctx-size', '8192', '--ubatch-size', '128', '--no-context-shift', '--no-webui', *args]
                proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                processes.append(proc)
                client = Client(18100 + i, key.read_text().strip())
                long_compare.iso_test.wait_for_health(client, proc, 300)
                clients.append(client)
            pair = clients[0].request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
            if len(pair) < 2:
                raise RuntimeError('tokenization failed')
            warm = pair[:2] * 128
            for client in clients:
                completion(client, warm)
            quality = {}
            for (name, _), client in zip(MODES, clients):
                replies = []
                for prompt in PROMPTS:
                    response = client.request('/v1/chat/completions', {'messages': [{'role': 'user', 'content': prompt}],
                                              'max_tokens': 32, 'temperature': 0}, timeout=180)
                    replies.append(response['choices'][0]['message']['content'])
                quality[name] = replies
            report = {'cpu': cpu, 'kernel': platform.release(), 'cpu_affinity': cpus, 'threads': 2,
                      'environment': 'native Linux, extracted tested ISO executable/libraries/model',
                      'model_sha256': '61c69fc5ce91982e26c625d43be5c3c7f0f774da22f4fa4e45c37a80a22ddad4',
                      'context': 8192, 'ubatch': 128, 'quality_spot_responses': quality, 'results': {},
                      'limitations': 'Same two pinned CPUs, embedded model and ISO executable; synthetic '
                      'repeated-token prompts, fixed server startup order, two samples per length. Idle '
                      'servers are suspended during measurements. Process CPU seconds include prefill and '
                      'generation, not energy. Five short response comparisons are not a quality benchmark; '
                      'quantized caches can change outputs. Native Linux screening, not guest performance.'}
            perf_prompt = (pair[:2] * 1024)[:2048]
            report['perf'] = perf_probe(processes[0].pid, clients[0], perf_prompt, output)
            for process in processes:
                os.kill(process.pid, signal.SIGSTOP)
            for n in (256, 2048, 8000):
                prompt = (pair[:2] * ((n + 1) // 2))[:n]
                samples = {name: [] for name, _ in MODES}
                for order in (range(len(MODES)), reversed(range(len(MODES)))):
                    for i in order:
                        os.kill(processes[i].pid, signal.SIGCONT)
                        try:
                            before = cpu_seconds(processes[i].pid)
                            sample = completion(clients[i], prompt)
                            sample['cpu_seconds'] = cpu_seconds(processes[i].pid) - before
                            sample['peak_rss_kib'] = rss_kib(processes[i].pid)
                        finally:
                            os.kill(processes[i].pid, signal.SIGSTOP)
                        samples[MODES[i][0]].append(sample)
                        print('Measurement: ' + json.dumps({'profile': MODES[i][0], **sample}), flush=True)
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
