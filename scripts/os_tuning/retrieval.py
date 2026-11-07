#!/usr/bin/env python3
"""Small chat-formatted retrieval probes, not a comprehensive quality evaluation."""
import importlib.util
import json
import os
import platform
import re
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adaptive = load('adaptive_iso', 'test-adaptive-iso.py')
compiler = load('compiler_iso', 'test-compiler-iso.py')


def tokenize(client, text):
    return client.request('/tokenize', {'content': text, 'add_special': False})['tokens']


def probe(client, length):
    # Use the model's ChatML role tokens, a simple artificial fact, and a
    # harmless repeated sentence as filler. The fact is near the beginning.
    head = tokenize(client, '<|im_start|>system\nYou are a helpful assistant. Answer the user concisely.<|im_end|>\n'
                    '<|im_start|>user\nThe secret word is mango. Remember it.\n')
    filler = tokenize(client, 'A bird sits beside a tree. ')
    tail = tokenize(client, '\nWhat is the secret word? Answer with the word only.<|im_end|>\n<|im_start|>assistant\n')
    count = length - len(head) - len(tail)
    if not filler or count < 0:
        raise RuntimeError('invalid test prompt size')
    prompt = head + (filler * ((count + len(filler) - 1) // len(filler)))[:count] + tail
    start = time.monotonic()
    response = client.request('/completion', {'prompt': prompt, 'n_predict': 16, 'temperature': 0,
                              'ignore_eos': False, 'cache_prompt': False}, timeout=1800)
    content = response.get('content', '')
    result = {'input_tokens': length, 'evaluated': response.get('tokens_evaluated'),
              'truncated': response.get('truncated'), 'answer': content[:300],
              'correct': bool(re.search(r'\bmango\b', content, re.IGNORECASE)),
              'wall_seconds': time.monotonic() - start}
    if result['evaluated'] != length or result['truncated'] is not False:
        raise RuntimeError('retrieval probe did not fully evaluate the requested input')
    return result


def main():
    if len(sys.argv) != 2 or not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('usage: retrieval.py AIOS.iso (KVM required)')
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two CPUs required')
    cpu = next((line.split(':', 1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines()
                if line.startswith('model name')), 'unknown')
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        processes, clients = [], []
        try:
            for i, args in enumerate(('aios.ubatch=128', 'aios.ubatch=128 aios.context=16k')):
                image = tmp / f'guest{i}.iso'
                compiler.test_image(Path(sys.argv[1]).resolve(), image, tmp / f'tree{i}', args)
                process, client = adaptive.start_guest(image, tmp / f'guest{i}.log', ','.join(map(str, cpus)),
                                                       18082 + i, 'host', 'avx2', 2048)
                processes.append(process)
                clients.append(client)
            report = {'cpu': cpu, 'kernel': platform.release(), 'acceleration': 'KVM', 'host_affinity': cpus,
                      'guest_ram_mib': 2048, 'threads': 2, 'microbatch': 128, 'probes': {},
                      'limitations': 'Single deterministic artificial fact, repeated filler, fact near start; '
                      'correct substring is not a general quality score. No multi-position, multi-task, '
                      'prompt-injection, or statistical evaluation. The 16k profile scales RoPE.'}
            for length in (256, 2048, 8000, 12000, 16000):
                report['probes'][str(length)] = {}
                indices = (0, 1) if length <= 8000 else (1,)
                for i in indices:
                    name = ('model_8k', 'linear_scaled_16k')[i]
                    result = probe(clients[i], length)
                    report['probes'][str(length)][name] = result
                    print('Probe: ' + json.dumps({'profile': name, **result}), flush=True)
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
