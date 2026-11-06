#!/usr/bin/env python3
"""Boot a network-enabled copy of the ISO and exercise real model inference."""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def request(url, token, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=90) as response:
        return response.status, json.load(response)


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: test-iso.py BUILD_OUTPUT_DIRECTORY")
    output = Path(sys.argv[1]).resolve()
    # The release image defaults to loopback. Only the test copy selects LAN mode.
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        tree = temp / "tree"
        (tree / "boot/grub").mkdir(parents=True)
        for name in ("bzImage", "rootfs.cpio.gz"):
            os.link(output / "iso-tree/boot" / name, tree / "boot" / name)
        grub = (output / "iso-tree/boot/grub/grub.cfg").read_text()
        if "set default=0" not in grub:
            raise RuntimeError("GRUB default entry not found")
        (tree / "boot/grub/grub.cfg").write_text(grub.replace("set default=0", "set default=1", 1))
        iso = temp / "test.iso"
        subprocess.run(["grub-mkrescue", "-o", str(iso), str(tree)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        serial = temp / "serial.log"
        cmd = ["qemu-system-x86_64", "-machine", "accel=tcg", "-cpu", "max", "-m", "1024",
               "-smp", "2", "-display", "none", "-monitor", "none", "-no-reboot",
               "-serial", f"file:{serial}", "-cdrom", str(iso), "-boot", "d",
               "-netdev", "user,id=n0,hostfwd=tcp:127.0.0.1:18080-:8080",
               "-device", "virtio-net-pci,netdev=n0"]
        start = time.monotonic()
        process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 600
            token = None
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"QEMU exited early ({process.returncode})")
                if serial.exists():
                    match = re.search(r"AIOS_BOOT_TOKEN=([0-9a-f]{64})", serial.read_text(errors="replace"))
                    if match:
                        token = match.group(1)
                if token:
                    try:
                        status, _ = request("http://127.0.0.1:18080/health", token)
                        if status == 200:
                            break
                    except (OSError, urllib.error.URLError, ValueError):
                        pass
                time.sleep(2)
            else:
                raise RuntimeError("guest did not become ready within 600 seconds")
            try:
                request("http://127.0.0.1:18080/v1/chat/completions", "invalid",
                        {"messages": [{"role": "user", "content": "Hi"}], "max_tokens": 4})
            except urllib.error.HTTPError as error:
                if error.code != 401:
                    raise RuntimeError(f"expected 401 for invalid token, got {error.code}") from error
            else:
                raise RuntimeError("invalid token was accepted")
            _, result = request("http://127.0.0.1:18080/v1/chat/completions", token,
                                {"messages": [{"role": "user", "content": "Say hello."}],
                                 "max_tokens": 16, "temperature": 0})
            choices = result.get("choices", [])
            if not choices or not choices[0].get("message", {}).get("content", "").strip():
                raise RuntimeError("inference returned no text")
            print("PASS: QEMU boot, health, authentication, and model text generation")
            print(f"Elapsed: {time.monotonic() - start:.1f} seconds (emulation; not a benchmark)")
            print("Test ISO differs only in selecting the network-enabled GRUB entry by default.")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not print serial logs, API keys, or model output.
        print(f"FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
