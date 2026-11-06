#!/usr/bin/env python3
"""Compare AVX2 and portable paths in two KVM guests on one runner."""
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

from iso_benchmark.client import Client
from iso_benchmark.measure import run_comparison


def stop(process):
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def start_guest(iso, serial, cpus, port, cpu, expected):
    cmd = ["taskset", "-c", cpus, "qemu-system-x86_64", "-machine", "accel=kvm", "-cpu", cpu,
           "-m", "1024", "-smp", "2", "-display", "none", "-monitor", "none", "-no-reboot",
           "-serial", f"file:{serial}", "-cdrom", str(iso), "-boot", "d", "-netdev",
           f"user,id=n0,hostfwd=tcp:127.0.0.1:{port}-:8080",
           "-device", "virtio-net-pci,netdev=n0", "-device", "virtio-rng-pci"]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError(f"{expected} QEMU exited ({process.returncode})")
            text = serial.read_text(errors="replace") if serial.exists() else ""
            backend = re.search(r"AIOS: inference backend=(portable|avx2)", text)
            match = re.search(r"AIOS_BOOT_TOKEN=([0-9a-f]{64})", text)
            if backend and backend.group(1) != expected:
                raise RuntimeError(f"expected {expected} backend; guest selected {backend.group(1)}")
            if backend and match:
                client = Client(port, match.group(1))
                try:
                    if client.request('/health').get('status') == 'ok':
                        return process, client
                except (OSError, urllib.error.URLError, ValueError):
                    pass
            time.sleep(2)
        raise RuntimeError(f"{expected} guest not ready in 300 seconds")
    except Exception:
        stop(process)
        raise


def main():
    if len(sys.argv) != 2:
        raise RuntimeError('usage: test-adaptive-iso.py AIOS.iso')
    if not os.access('/dev/kvm', os.R_OK | os.W_OK):
        raise RuntimeError('KVM unavailable; cannot make the intended same-runner comparison')
    iso = Path(sys.argv[1]).resolve()
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError('two available CPUs required')
    cpu_affinity = ','.join(map(str, cpus))
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        tree = temp / 'tree'
        (tree / 'boot/grub').mkdir(parents=True)
        for name in ('bzImage', 'rootfs.cpio.gz', 'grub/grub.cfg'):
            subprocess.run(['xorriso', '-osirrox', 'on', '-indev', str(iso), '-extract',
                            '/boot/' + name, str(tree / 'boot' / name)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        grub = tree / 'boot/grub/grub.cfg'
        grub.chmod(0o644)
        config = grub.read_text()
        if 'set default=0' not in config or 'aios.network=1' not in config:
            raise RuntimeError('expected GRUB entries not found')
        grub.write_text(config.replace('set default=0', 'set default=1', 1).replace(
            'aios.network=1', 'aios.network=1 aios.threads=2', 1))
        test_iso = temp / 'test.iso'
        subprocess.run(['grub-mkrescue', '-o', str(test_iso), str(tree)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        processes = []
        try:
            portable, portable_client = start_guest(test_iso, temp / 'portable.log', cpu_affinity, 18082,
                                                     'host,-avx,-avx2,-fma,-f16c,-bmi2', 'portable')
            processes.append(portable)
            optimized, optimized_client = start_guest(test_iso, temp / 'avx2.log', cpu_affinity, 18083,
                                                       'host', 'avx2')
            processes.append(optimized)
            measured = run_comparison(portable_client, optimized_client)
            # The generic helper names the two inputs after the host/guest test.
            for key in ('samples', 'medians'):
                measured[key] = {'portable': measured[key]['github_linux'],
                                 'avx2': measured[key]['aios_vm']}
            slow = measured['medians']['portable']['output_tokens_per_second']
            measured['generation_speedup'] = measured['medians']['avx2']['output_tokens_per_second'] / slow
            slow = measured['medians']['portable']['prompt_tokens_per_second']
            measured['prompt_speedup'] = measured['medians']['avx2']['prompt_tokens_per_second'] / slow
            cpu_info = Path('/proc/cpuinfo').read_text()
            cpu_name = next((line.split(':', 1)[1].strip() for line in cpu_info.splitlines()
                             if line.startswith('model name')), 'unknown')
            print(json.dumps({'cpu': cpu_name, 'kernel': platform.release(), 'acceleration': 'KVM',
                              'cpu_affinity': cpus, 'threads': 2, 'guest_ram_mib': 1024,
                              'baseline_cpu': 'host,-avx,-avx2,-fma,-f16c,-bmi2',
                              'optimized_cpu': 'host', 'results': measured,
                              'limitations': 'Same host, two guests, CPU feature masks differ. '
                              'This measures kernel dispatch, not an OS-only speedup.'}, indent=2))
        finally:
            for process in reversed(processes):
                stop(process)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Serial logs contain credentials and are never published.
        print(f'FAIL: {type(error).__name__}: {error}', file=sys.stderr)
        sys.exit(1)
