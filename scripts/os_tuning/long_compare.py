#!/usr/bin/env python3
"""Compare identical long-context server binaries on Linux host and KVM guest."""
import gzip
import importlib.util
import json
import os
import platform
import secrets
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from iso_benchmark.client import Client


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adaptive = load('adaptive_iso', 'test-adaptive-iso.py')
compiler = load('compiler_iso', 'test-compiler-iso.py')
iso_test = load('test_iso', 'test-iso.py')


def extract_target(iso, temp):
    rootfs = temp / 'rootfs.cpio.gz'
    subprocess.run(['xorriso', '-osirrox', 'on', '-indev', str(iso), '-extract',
                    '/boot/rootfs.cpio.gz', str(rootfs)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    target = temp / 'target'
    target.mkdir()
    with gzip.open(rootfs, 'rb') as source:
        # Preserve the image's libraries and loader so the native and guest
        # tests use the same binary and target userspace, not a new build.
        proc = subprocess.Popen(['cpio', '-id', '--quiet', '--no-absolute-filenames',
                                 'lib/*', 'usr/lib/*', 'usr/bin/llama-server-avx2',
                                 'opt/aios/model.gguf'], cwd=target, stdin=subprocess.PIPE,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            while chunk := source.read(1024 * 1024):
                proc.stdin.write(chunk)
            proc.stdin.close()
            stderr = proc.stderr.read().decode(errors='replace')
            if proc.wait() != 0:
                raise RuntimeError('cpio extraction failed: ' + stderr[-2000:])
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()
    return target


def completion(client, prompt, generated=32):
    start = time.monotonic()
    result = client.request('/completion', {'prompt': prompt, 'n_predict': generated,
                            'temperature': 0, 'ignore_eos': True, 'cache_prompt': False}, timeout=1800)
    timing = result.get('timings', {})
    if result.get('tokens_evaluated') != len(prompt) or result.get('truncated') is not False:
        raise RuntimeError(f'input was not fully evaluated: {len(prompt)}')
    if result.get('tokens_predicted') != generated:
        raise RuntimeError('unexpected number of generated tokens')
    return {'input_tokens': len(prompt), 'output_tokens': generated,
            'prompt_tokens_processed': timing.get('prompt_n'), 'prompt_ms': timing.get('prompt_ms'),
            'prompt_tokens_per_second': timing.get('prompt_per_second'),
            'generation_tokens_per_second': timing.get('predicted_per_second'),
            'wall_seconds': time.monotonic() - start, 'truncated': False}


def retrieval(client, filler_token, token_count):
    header = client.request('/tokenize', {'content': 'Remember this fact: the secret word is marble.\n',
                                          'add_special': False})['tokens']
    question = client.request('/tokenize', {'content': '\nQuestion: What is the secret word? Answer with one word.\nAnswer:',
                                            'add_special': False})['tokens']
    filler_count = token_count - len(header) - len(question)
    if filler_count <= 0:
        raise RuntimeError('retrieval context too small')
    prompt = header + [filler_token] * filler_count + question
    started = time.monotonic()
    response = client.request('/completion', {'prompt': prompt, 'n_predict': 16, 'temperature': 0,
                              'ignore_eos': True, 'cache_prompt': False}, timeout=1800)
    content = response.get('content', '')
    return {'input_tokens': token_count, 'evaluated': response.get('tokens_evaluated'),
            'truncated': response.get('truncated'), 'found_word': 'marble' in content.lower(),
            'answer': content[:250], 'wall_seconds': time.monotonic() - started,
            'note': 'Single artificial retrieval probe; not a reliable quality benchmark.'}


def main():
    if len(sys.argv) != 2 or not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('usage: long_compare.py AIOS.iso (KVM required)')
    iso = Path(sys.argv[1]).resolve()
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two available CPUs required')
    affinity = ','.join(map(str, cpus))
    info = Path('/proc/cpuinfo').read_text()
    cpu = next((line.split(':', 1)[1].strip() for line in info.splitlines() if line.startswith('model name')), 'unknown')
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        target = extract_target(iso, tmp)
        image = tmp / 'test.iso'
        compiler.test_image(iso, image, tmp / 'tree', 'aios.context=16k aios.ubatch=128')
        guest = host = None
        try:
            guest, guest_client = adaptive.start_guest(image, tmp / 'serial.log', affinity, 18082, 'host', 'avx2', 2048)
            boot = (tmp / 'serial.log').read_text(errors='replace')
            if 'AIOS: experimental 16k context' not in boot or 'AIOS: prompt microbatch=128' not in boot:
                raise RuntimeError('guest did not select the requested configuration')
            key = tmp / 'host.key'
            key.write_text(secrets.token_hex(32) + '\n')
            key.chmod(0o600)
            loaders = list((target / 'lib').glob('ld-linux-x86-64.so.*'))
            if not loaders:
                raise RuntimeError('Buildroot loader missing in extracted rootfs')
            command = ['taskset', '-c', affinity, str(loaders[0]), '--library-path',
                       f'{target / "lib"}:{target / "usr/lib"}', str(target / 'usr/bin/llama-server-avx2'),
                       '-m', str(target / 'opt/aios/model.gguf'), '--api-key-file', str(key),
                       '--host', '127.0.0.1', '--port', '18081', '--threads', '2', '--ctx-size', '16384',
                       '--ubatch-size', '128', '--rope-scaling', 'linear', '--rope-scale', '2',
                       '--no-context-shift', '--no-webui']
            host = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            host_client = Client(18081, key.read_text().strip())
            iso_test.wait_for_health(host_client, host, 600)
            token_pair = guest_client.request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
            if len(token_pair) < 2:
                raise RuntimeError('tokenizer returned too few tokens')
            report = {'cpu': cpu, 'host_kernel': platform.release(), 'host_affinity': cpus,
                      'guest': 'KVM', 'guest_ram_mib': 2048, 'threads': 2, 'context': 16384,
                      'rope': 'linear scale 2', 'ubatch': 128, 'measurements': {}, 'retrieval': {},
                      'limitations': 'Same image binary, target libraries, model, affinity and flags; '
                      'host native versus a VM is confounded by virtualization and memory. One sample per '
                      'length and synthetic token input. Linear RoPE extrapolates beyond 8192 trained tokens; '
                      'a single retrieval check does not establish long-context quality.'}
            for index, n in enumerate((256, 2048, 8000, 12000, 16000)):
                tokens = (token_pair[:2] * ((n + 1) // 2))[:n]
                report['measurements'][str(n)] = {}
                for name, client in ((('host', host_client), ('guest', guest_client)) if index % 2 == 0
                                     else (('guest', guest_client), ('host', host_client))):
                    result = completion(client, tokens)
                    report['measurements'][str(n)][name] = result
                    print('Measurement: ' + json.dumps({'environment': name, **result}), flush=True)
            for n in (256, 12000):
                report['retrieval'][str(n)] = retrieval(guest_client, token_pair[0], n)
                print('Retrieval: ' + json.dumps(report['retrieval'][str(n)]), flush=True)
            print('REPORT_JSON=' + json.dumps(report), flush=True)
        finally:
            if host is not None:
                adaptive.stop(host)
            if guest is not None:
                adaptive.stop(guest)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
