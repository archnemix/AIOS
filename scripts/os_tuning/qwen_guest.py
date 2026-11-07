#!/usr/bin/env python3
"""Boot the external Qwen model and compare it with native Linux on one runner."""
import importlib.util
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
from iso_benchmark.client import Client


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adaptive = load('adaptive_iso', SCRIPTS / 'test-adaptive-iso.py')
compiler = load('compiler_iso', SCRIPTS / 'test-compiler-iso.py')
long_compare = load('long_compare', Path(__file__).with_name('long_compare.py'))
retrieval = load('retrieval', Path(__file__).with_name('retrieval.py'))


def wait_guest(serial, process, client):
    deadline = time.monotonic() + 600
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('external-model VM exited early')
        text = serial.read_text(errors='replace') if serial.exists() else ''
        if 'AIOS: unable to mount model volume' in text:
            raise RuntimeError('external model disk failed to mount')
        if 'AIOS: context=32768 rope=model model_mode=external' in text and 'AIOS: inference backend=avx2' in text:
            try:
                if client.request('/health').get('status') == 'ok':
                    return
            except (OSError, urllib.error.URLError, ValueError):
                pass
        time.sleep(2)
    raise RuntimeError('external-model VM did not become ready')


def main():
    if len(sys.argv) != 3 or not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('usage: qwen_guest.py AIOS.iso QWEN.gguf (KVM required)')
    iso, model = (Path(arg).resolve() for arg in sys.argv[1:])
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two available CPUs required')
    affinity = ','.join(map(str, cpus))
    info = Path('/proc/cpuinfo').read_text()
    cpu = next((line.split(':', 1)[1].strip() for line in info.splitlines() if line.startswith('model name')), 'unknown')
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        target = long_compare.extract_target(iso, tmp)
        image = tmp / 'network.iso'
        compiler.test_image(iso, image, tmp / 'tree', 'aios.external=1 aios.context=32k aios.ubatch=128')
        contents = tmp / 'disk-files'
        contents.mkdir()
        shutil.copyfile(model, contents / 'model.gguf')
        token = secrets.token_hex(32)
        (contents / 'api.key').write_text(token + '\n')
        (contents / 'api.key').chmod(0o644)  # disposable test-only key
        disk = tmp / 'model.ext4'
        with disk.open('wb') as handle:
            handle.truncate(650 * 1024 * 1024)
        subprocess.run(['mkfs.ext4', '-q', '-F', '-d', str(contents), str(disk)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        serial = tmp / 'serial.log'
        cmd = ['taskset', '-c', affinity, 'qemu-system-x86_64', '-machine', 'accel=kvm', '-cpu', 'host',
               '-m', '3072', '-smp', '2', '-display', 'none', '-monitor', 'none', '-no-reboot',
               '-serial', f'file:{serial}', '-cdrom', str(image), '-boot', 'd',
               '-drive', f'file={disk},format=raw,if=none,id=data,readonly=on', '-device', 'virtio-blk-pci,drive=data',
               '-netdev', 'user,id=n0,hostfwd=tcp:127.0.0.1:18082-:8080', '-device', 'virtio-net-pci,netdev=n0',
               '-device', 'virtio-rng-pci']
        guest = host = None
        try:
            guest = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            guest_client = Client(18082, token)
            wait_guest(serial, guest, guest_client)
            try:
                Client(18082, 'invalid').request('/completion', {'prompt': 'Hi', 'n_predict': 1})
            except urllib.error.HTTPError as error:
                if error.code != 401:
                    raise RuntimeError('unexpected invalid-token response') from error
            else:
                raise RuntimeError('invalid token was accepted')
            key = tmp / 'host.key'
            key.write_text(token + '\n')
            key.chmod(0o600)
            loaders = list((target / 'lib').glob('ld-linux-x86-64.so.*'))
            if not loaders:
                raise RuntimeError('target loader missing')
            cmd = ['taskset', '-c', affinity, str(loaders[0]), '--library-path',
                   f'{target / "lib"}:{target / "usr/lib"}', str(target / 'usr/bin/llama-server-avx2'),
                   '-m', str(model), '--api-key-file', str(key), '--host', '127.0.0.1', '--port', '18081',
                   '--threads', '2', '--ctx-size', '32768', '--ubatch-size', '128', '--no-context-shift', '--no-webui']
            host = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            host_client = Client(18081, token)
            long_compare.iso_test.wait_for_health(host_client, host, 600)
            tokens = guest_client.request('/tokenize', {'content': ' hello world', 'add_special': False})['tokens']
            if len(tokens) < 2:
                raise RuntimeError('tokenizer returned too few tokens')
            report = {'cpu': cpu, 'kernel': platform.release(), 'affinity': cpus, 'threads': 2,
                      'guest_ram_mib': 3072, 'context': 32768, 'model': 'Qwen2.5-0.5B-Instruct Q3_K_M',
                      'model_sha256': '590d2479d401db206fe12a4562294d2de6211e06338a6e34fbad64b32f1469d0',
                      'authentication': 'invalid token rejected', 'measurements': {},
                      'limitations': 'Native Linux versus KVM with different memory environments; one synthetic '
                      'sample per input length, fixed boot order and two pinned logical CPUs. Not a bare-metal '
                      'OS comparison. One retrieval probe cannot establish general quality.'}
            for index, n in enumerate((256, 2048, 8000, 16000)):
                prompt = (tokens[:2] * ((n + 1) // 2))[:n]
                report['measurements'][str(n)] = {}
                ordered = [('host', host_client), ('guest', guest_client)]
                if index % 2:
                    ordered.reverse()
                for name, client in ordered:
                    result = long_compare.completion(client, prompt)
                    report['measurements'][str(n)][name] = result
                    print('Measurement: ' + json.dumps({'environment': name, **result}), flush=True)
            print('Testing 32000 input tokens in guest', flush=True)
            prompt = (tokens[:2] * 16000)[:32000]
            started = time.monotonic()
            reply = guest_client.request('/completion', {'prompt': prompt, 'n_predict': 1,
                                         'temperature': 0, 'cache_prompt': False}, timeout=3000)
            report['guest_32000'] = {'input_tokens': 32000, 'evaluated': reply.get('tokens_evaluated'),
                                     'truncated': reply.get('truncated'), 'generated': reply.get('tokens_predicted'),
                                     'wall_seconds': time.monotonic() - started}
            print('Capacity: ' + json.dumps(report['guest_32000']), flush=True)
            if reply.get('tokens_evaluated') != 32000 or reply.get('truncated') is not False:
                raise RuntimeError('guest did not fully process 32000 input tokens')
            report['retrieval_16000'] = retrieval.probe(guest_client, 16000)
            print('Retrieval: ' + json.dumps(report['retrieval_16000']), flush=True)
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
