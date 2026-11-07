"""Boot with independent generation and batch worker settings."""
import os
import re
import subprocess
import time
import urllib.error

from .client import Client


def test_generation_controls(output, directory, affinity, acceleration):
    tree = directory / 'generation-tree'
    (tree / 'boot/grub').mkdir(parents=True)
    for name in ('bzImage', 'rootfs.cpio.gz'):
        os.link(output / 'iso-tree/boot' / name, tree / 'boot' / name)
    config = (output / 'iso-tree/boot/grub/grub.cfg').read_text()
    if 'set default=0' not in config or 'aios.network=1' not in config:
        raise RuntimeError('network GRUB entry missing')
    config = config.replace('set default=0', 'set default=1', 1).replace(
        'aios.network=1', 'aios.network=1 aios.threads=1 aios.batch-threads=2 aios.poll=100', 1)
    (tree / 'boot/grub/grub.cfg').write_text(config)
    iso = directory / 'generation.iso'
    subprocess.run(['grub-mkrescue', '-o', str(iso), str(tree)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    serial = directory / 'generation.log'
    cmd = affinity + ['qemu-system-x86_64', *acceleration, '-m', '1024', '-smp', '2', '-display', 'none',
                      '-monitor', 'none', '-no-reboot', '-serial', f'file:{serial}', '-cdrom', str(iso),
                      '-boot', 'd', '-netdev', 'user,id=n0,hostfwd=tcp:127.0.0.1:18082-:8080',
                      '-device', 'virtio-net-pci,netdev=n0', '-device', 'virtio-rng-pci']
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 300
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('generation controls guest exited early')
            text = serial.read_text(errors='replace') if serial.exists() else ''
            token = re.search(r'AIOS_BOOT_TOKEN=([0-9a-f]{64})', text)
            if token and re.search(r'AIOS: inference backend=(portable|avx2) threads=1\b', text) and \
                    'AIOS: batch threads=2 generation poll=100' in text:
                client = Client(18082, token.group(1))
                try:
                    if client.request('/health').get('status') == 'ok':
                        result = client.request('/completion', {'prompt': 'Hello', 'n_predict': 4,
                                                'ignore_eos': True, 'temperature': 0}, timeout=120)
                        if not result.get('content'):
                            raise RuntimeError('generation controls returned no output')
                        return {'generation_threads': 1, 'batch_threads': 2, 'poll': 100, 'inference': 'passed'}
                except (OSError, urllib.error.URLError, ValueError):
                    pass
            time.sleep(2)
        raise RuntimeError('generation controls guest did not become ready')
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
