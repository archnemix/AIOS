#!/usr/bin/env python3
"""Compare synthetic retrieval for embedded and optional long-context models on one Linux host."""
import importlib.util
import json
import os
import platform
import secrets
import subprocess
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


long_compare = load('long_compare', Path(__file__).with_name('long_compare.py'))
retrieval = load('retrieval', Path(__file__).with_name('retrieval.py'))
from iso_benchmark.client import Client


def main():
    if len(sys.argv) != 3:
        raise RuntimeError('usage: alternate_model.py AIOS.iso QWEN.gguf')
    iso, qwen = map(lambda value: Path(value).resolve(), sys.argv[1:])
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two CPUs required')
    affinity = ','.join(map(str, cpus))
    info = Path('/proc/cpuinfo').read_text()
    cpu = next((line.split(':', 1)[1].strip() for line in info.splitlines() if line.startswith('model name')), 'unknown')
    with tempfile.TemporaryDirectory() as directory:
        tmp = Path(directory)
        target = long_compare.extract_target(iso, tmp)
        loaders = list((target / 'lib').glob('ld-linux-x86-64.so.*'))
        if not loaders:
            raise RuntimeError('target loader is missing')
        key = tmp / 'host.key'
        key.write_text(secrets.token_hex(32) + '\n')
        key.chmod(0o600)
        modes = [('SmolLM2_135M_Q3_scaled', target / 'opt/aios/model.gguf', ['--rope-scaling', 'linear', '--rope-scale', '2']),
                 ('Qwen2_5_0_5B_Q3_model_rope', qwen, [])]
        processes, clients, logs = [], [], []
        try:
            for i, (name, model, extra) in enumerate(modes):
                log_path = tmp / f'host{i}.log'
                log = log_path.open('w')
                logs.append(log)
                command = ['taskset', '-c', affinity, str(loaders[0]), '--library-path',
                           f'{target / "lib"}:{target / "usr/lib"}', str(target / 'usr/bin/llama-server-avx2'),
                           '-m', str(model), '--api-key-file', str(key), '--host', '127.0.0.1',
                           '--port', str(18081 + i), '--threads', '2', '--ctx-size', '16384',
                           '--ubatch-size', '128', '--no-context-shift', '--no-webui', *extra]
                proc = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
                processes.append(proc)
                client = Client(18081 + i, key.read_text().strip())
                clients.append(client)
                long_compare.iso_test.wait_for_health(client, proc, 600)
            report = {'cpu': cpu, 'kernel': platform.release(), 'affinity': cpus, 'threads': 2,
                      'context': 16384, 'ubatch': 128, 'environment': 'native Ubuntu Linux',
                      'models': [m[0] for m in modes], 'results': {}, 'metadata': {},
                      'limitations': 'One synthetic chat-formatted retrieval probe per length/model; '
                      'not an OS comparison, quality benchmark or general speed comparison. '
                      'Models have different architectures and tokenizers, and SmolLM2 is '
                      'extrapolated beyond its 8192-token training context. Fixed startup order.'}
            for i, (name, _, _) in enumerate(modes):
                logs[i].flush()
                lines = (tmp / f'host{i}.log').read_text(errors='replace').splitlines()
                report['metadata'][name] = [line.strip()[:300] for line in lines
                                           if 'n_ctx_train' in line and 'token' not in line.lower()][:5]
            for length in (256, 2048, 8000, 12000, 16000):
                report['results'][str(length)] = {}
                for i in (0, 1):
                    name = modes[i][0]
                    result = retrieval.probe(clients[i], length)
                    report['results'][str(length)][name] = result
                    print('Probe: ' + json.dumps({'model': name, **result}), flush=True)
            print('REPORT_JSON=' + json.dumps(report), flush=True)
        finally:
            for process in reversed(processes):
                long_compare.adaptive.stop(process)
            for log in logs:
                log.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr, flush=True)
        sys.exit(1)
