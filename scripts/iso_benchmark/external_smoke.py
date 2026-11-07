"""Boot the external-model profile using a test-only read-only model disk."""
import os
import secrets
import shutil
import subprocess
import time
import urllib.error
from pathlib import Path

from .client import Client


def test_external_boot(output, directory, affinity, acceleration):
    tree = directory / 'external-tree'
    (tree / 'boot/grub').mkdir(parents=True)
    for name in ('bzImage', 'rootfs.cpio.gz'):
        os.link(output / 'iso-tree/boot' / name, tree / 'boot' / name)
    grub = (output / 'iso-tree/boot/grub/grub.cfg').read_text()
    entry = 'aios.external=1 aios.context=32k aios.ubatch=128 aios.network=1'
    if 'set default=0' not in grub or entry not in grub:
        raise RuntimeError('external 32k network GRUB entry missing')
    (tree / 'boot/grub/grub.cfg').write_text(grub.replace('set default=0', 'set default=9', 1))
    iso = directory / 'external.iso'
    subprocess.run(['grub-mkrescue', '-o', str(iso), str(tree)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    contents = directory / 'external-disk-contents'
    contents.mkdir()
    shutil.copyfile(output / 'target/opt/aios/model.gguf', contents / 'model.gguf')
    # Test fixture only: world-readable permissions avoid a root-owned image;
    # real user keys must be restricted to UID 1000 as described in docs.
    token = secrets.token_hex(32)
    (contents / 'api.key').write_text(token + '\n')
    (contents / 'api.key').chmod(0o644)
    disk = directory / 'external.ext4'
    with disk.open('wb') as handle:
        handle.truncate(192 * 1024 * 1024)
    subprocess.run(['mkfs.ext4', '-q', '-F', '-d', str(contents), str(disk)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    serial = directory / 'external.log'
    command = affinity + ['qemu-system-x86_64', *acceleration, '-m', '2048', '-smp', '2',
                          '-display', 'none', '-monitor', 'none', '-no-reboot', '-serial', f'file:{serial}',
                          '-cdrom', str(iso), '-boot', 'd', '-drive', f'file={disk},format=raw,if=none,id=data,readonly=on',
                          '-device', 'virtio-blk-pci,drive=data', '-netdev',
                          'user,id=n0,hostfwd=tcp:127.0.0.1:18082-:8080',
                          '-device', 'virtio-net-pci,netdev=n0', '-device', 'virtio-rng-pci']
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 420
        client = Client(18082, token)
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError('external-model guest exited before becoming ready')
            log = serial.read_text(errors='replace') if serial.exists() else ''
            if 'AIOS: unable to mount model volume' in log:
                raise RuntimeError('external model volume did not mount')
            if 'AIOS: context=32768 rope=model model_mode=external' in log:
                try:
                    if client.request('/health').get('status') == 'ok':
                        reply = client.request('/completion', {'prompt': 'Hello', 'n_predict': 4,
                                               'temperature': 0, 'ignore_eos': True}, timeout=180)
                        if not reply.get('content'):
                            raise RuntimeError('external-model guest returned no output')
                        try:
                            Client(18082, 'invalid').request('/completion', {'prompt': 'Hi', 'n_predict': 1})
                        except urllib.error.HTTPError as error:
                            if error.code != 401:
                                raise RuntimeError('unexpected external-model authentication response') from error
                        else:
                            raise RuntimeError('external-model guest accepted an invalid key')
                        return {'context': 32768, 'model_mode': 'external', 'auth': 'passed',
                                'model_inference': 'passed', 'note': 'embedded SmolLM2 copied to test disk'}
                except (OSError, urllib.error.URLError, ValueError):
                    pass
            time.sleep(2)
        raise RuntimeError('external-model guest did not become ready in 420 seconds')
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
