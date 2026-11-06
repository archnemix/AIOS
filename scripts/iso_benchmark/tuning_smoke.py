"""Exercise the optional boot-time tuner in a separate QEMU guest."""
import os
import re
import subprocess
import time
import urllib.error
from pathlib import Path

from .client import Client


def test_tuning_boot(output, directory, affinity, acceleration):
    tree = directory / 'tuning-tree'
    (tree / 'boot/grub').mkdir(parents=True)
    for name in ('bzImage', 'rootfs.cpio.gz'):
        os.link(output / 'iso-tree/boot' / name, tree / 'boot' / name)
    grub = (output / 'iso-tree/boot/grub/grub.cfg').read_text()
    if 'set default=0' not in grub or 'aios.network=1 aios.autotune=1' not in grub:
        raise RuntimeError('tuning GRUB entry missing')
    (tree / 'boot/grub/grub.cfg').write_text(grub.replace('set default=0', 'set default=3', 1))
    iso = directory / 'tuning.iso'
    subprocess.run(['grub-mkrescue', '-o', str(iso), str(tree)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    serial = directory / 'tuning.log'
    command = affinity + ['qemu-system-x86_64', *acceleration, '-m', '1024', '-smp', '2',
                          '-display', 'none', '-monitor', 'none', '-no-reboot', '-serial', f'file:{serial}',
                          '-cdrom', str(iso), '-boot', 'd', '-netdev',
                          'user,id=n0,hostfwd=tcp:127.0.0.1:18082-:8080',
                          '-device', 'virtio-net-pci,netdev=n0', '-device', 'virtio-rng-pci']
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 420
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('tuning QEMU guest exited before becoming ready')
            text = serial.read_text(errors='replace') if serial.exists() else ''
            token = re.search(r'AIOS_BOOT_TOKEN=([0-9a-f]{64})', text)
            selection = re.search(r'AIOS: tuning selected ([0-9]+) threads', text)
            if 'AIOS: tuning failed or timed out' in text:
                raise RuntimeError('guest tuning benchmark failed; fallback was used')
            if token and selection:
                client = Client(18082, token.group(1))
                try:
                    if client.request('/health').get('status') == 'ok':
                        result = client.request('/completion', {'prompt': 'Hello', 'n_predict': 4, 'ignore_eos': True, 'temperature': 0}, timeout=120)
                        if not result.get('content'):
                            raise RuntimeError('tuned guest returned no model output')
                        return {'selected_threads': int(selection.group(1)), 'model_inference': 'passed'}
                except (OSError, urllib.error.URLError, ValueError):
                    pass
            time.sleep(2)
        raise RuntimeError('tuned guest did not become ready in 420 seconds')
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def test_ubatch_boot(output, directory, affinity, acceleration):
    tree = directory / 'ubatch-tree'
    (tree / 'boot/grub').mkdir(parents=True)
    for name in ('bzImage', 'rootfs.cpio.gz'):
        os.link(output / 'iso-tree/boot' / name, tree / 'boot' / name)
    grub = (output / 'iso-tree/boot/grub/grub.cfg').read_text()
    if 'set default=0' not in grub or 'aios.network=1 aios.ubatch=128' not in grub:
        raise RuntimeError('microbatch GRUB entry missing')
    (tree / 'boot/grub/grub.cfg').write_text(grub.replace('set default=0', 'set default=5', 1))
    iso = directory / 'ubatch.iso'
    subprocess.run(['grub-mkrescue', '-o', str(iso), str(tree)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    serial = directory / 'ubatch.log'
    command = affinity + ['qemu-system-x86_64', *acceleration, '-m', '1024', '-smp', '2',
                          '-display', 'none', '-monitor', 'none', '-no-reboot', '-serial', f'file:{serial}',
                          '-cdrom', str(iso), '-boot', 'd', '-netdev',
                          'user,id=n0,hostfwd=tcp:127.0.0.1:18082-:8080',
                          '-device', 'virtio-net-pci,netdev=n0', '-device', 'virtio-rng-pci']
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('microbatch guest exited before becoming ready')
            text = serial.read_text(errors='replace') if serial.exists() else ''
            token = re.search(r'AIOS_BOOT_TOKEN=([0-9a-f]{64})', text)
            if token and 'AIOS: prompt microbatch=128' in text:
                client = Client(18082, token.group(1))
                try:
                    if client.request('/health').get('status') == 'ok':
                        result = client.request('/completion', {'prompt': 'Hello', 'n_predict': 4,
                                                'ignore_eos': True, 'temperature': 0}, timeout=120)
                        if not result.get('content'):
                            raise RuntimeError('microbatch guest returned no model output')
                        return {'microbatch': 128, 'model_inference': 'passed'}
                except (OSError, urllib.error.URLError, ValueError):
                    pass
            time.sleep(2)
        raise RuntimeError('microbatch guest did not become ready in 300 seconds')
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
