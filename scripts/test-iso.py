#!/usr/bin/env python3
"""Boot AIOS and compare its inference with GitHub Linux on the same runner."""

import json
import os
import platform
import re
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
from pathlib import Path

from iso_benchmark.client import Client
from iso_benchmark.measure import check_context, run_comparison


def wait_for_health(client, process, seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"server process exited ({process.returncode})")
        try:
            if client.request("/health").get("status") == "ok":
                return
        except (OSError, urllib.error.URLError, ValueError):
            pass
        time.sleep(2)
    raise RuntimeError("server did not become ready")


def stop(process):
    if process is None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def print_boot_diagnostics(serial):
    if not serial.exists():
        print("DIAGNOSTIC: QEMU produced no serial log", flush=True)
        return
    # Never publish the credential or inference request/response logs.
    allowed = []
    for line in serial.read_text(errors="replace").splitlines():
        if any(word in line.lower() for word in ("token", "api_key", "authorization", "prompt")):
            continue
        low = line.lower()
        if (line.startswith("AIOS:") or re.match(r"^\[\s*\d+\.\d+\]", line)
                or any(word in low for word in ("error", "fatal", "failed", "listening", "eth0", "udhcpc"))):
            allowed.append(line[:400])
    print("DIAGNOSTIC: sanitized boot log (kernel and AIOS messages only):", flush=True)
    for line in allowed[-100:]:
        print(line, flush=True)


def resident_memory_kib(process):
    status = Path(f"/proc/{process.pid}/status").read_text()
    match = re.search(r"^VmRSS:\s*(\d+) kB", status, re.MULTILINE)
    return int(match.group(1)) if match else None


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: test-iso.py BUILD_OUTPUT_DIRECTORY")
    output = Path(sys.argv[1]).resolve()
    target = output / "target"
    model = target / "opt/aios/model.gguf"
    cpus = sorted(os.sched_getaffinity(0))[:2]
    if len(cpus) != 2:
        raise RuntimeError("comparison requires two available logical CPUs")
    affinity = ["taskset", "-c", ",".join(map(str, cpus))]
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        tree = temp / "tree"
        (tree / "boot/grub").mkdir(parents=True)
        for name in ("bzImage", "rootfs.cpio.gz"):
            os.link(output / "iso-tree/boot" / name, tree / "boot" / name)
        grub = (output / "iso-tree/boot/grub/grub.cfg").read_text()
        if "set default=0" not in grub or "aios.network=1" not in grub:
            raise RuntimeError("required GRUB entries not found")
        grub = grub.replace("set default=0", "set default=1", 1)
        grub = grub.replace("aios.network=1", "aios.network=1 aios.threads=2", 1)
        (tree / "boot/grub/grub.cfg").write_text(grub)
        iso = temp / "test.iso"
        subprocess.run(["grub-mkrescue", "-o", str(iso), str(tree)], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        serial = temp / "serial.log"
        kvm = os.access("/dev/kvm", os.R_OK | os.W_OK)
        accel = ["-machine", "accel=kvm", "-cpu", "host"] if kvm else ["-machine", "accel=tcg", "-cpu", "max"]
        qemu = affinity + ["qemu-system-x86_64", *accel, "-m", "1024", "-smp", "2",
               "-display", "none", "-monitor", "none", "-no-reboot", "-serial", f"file:{serial}",
               "-cdrom", str(iso), "-boot", "d", "-netdev", "user,id=n0,hostfwd=tcp:127.0.0.1:18080-:8080",
               "-device", "virtio-net-pci,netdev=n0", "-device", "virtio-rng-pci"]
        boot_start = time.monotonic()
        vm = subprocess.Popen(qemu, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        baseline = None
        try:
            token = None
            deadline = time.monotonic() + 600
            while time.monotonic() < deadline:
                if vm.poll() is not None:
                    raise RuntimeError(f"QEMU exited early ({vm.returncode})")
                if serial.exists():
                    match = re.search(r"AIOS_BOOT_TOKEN=([0-9a-f]{64})", serial.read_text(errors="replace"))
                    if match:
                        token = match.group(1)
                        break
                time.sleep(2)
            if token is None:
                raise RuntimeError("guest did not print boot token within 600 seconds")
            guest = Client(18080, token)
            wait_for_health(guest, vm, 600)
            boot_seconds = time.monotonic() - boot_start
            try:
                Client(18080, "invalid").request("/completion", {"prompt": "Hi", "n_predict": 1})
            except urllib.error.HTTPError as error:
                if error.code != 401:
                    raise RuntimeError(f"expected HTTP 401, got {error.code}") from error
            else:
                raise RuntimeError("invalid token was accepted")
            reply = guest.request("/v1/chat/completions", {"messages": [{"role": "user", "content": "Say hello."}],
                                                            "max_tokens": 16, "temperature": 0}, timeout=600)
            if not reply.get("choices") or not reply["choices"][0].get("message", {}).get("content", "").strip():
                raise RuntimeError("guest inference returned no text")
            print("PASS: ISO test copy booted; API rejected an invalid token and generated model text", flush=True)
            print(f"QEMU acceleration: {'KVM' if kvm else 'TCG software emulation'}", flush=True)
            key = temp / "host.key"
            key.write_text(secrets.token_hex(32) + "\n")
            key.chmod(0o600)
            loaders = list((target / "lib").glob("ld-linux-x86-64.so.*"))
            if not loaders:
                raise RuntimeError("Buildroot's glibc loader was not found")
            libraries = f"{target / 'lib'}:{target / 'usr/lib'}"
            # Compare the exact same engine variant as the guest. The boot log
            # states what was selected; do not compare AVX2 against portable.
            boot_log = serial.read_text(errors="replace")
            selected = re.search(r"AIOS: inference backend=(portable|avx2)\b", boot_log)
            if not selected:
                raise RuntimeError("guest did not report its inference backend")
            variant = selected.group(1)
            if variant == "avx2":
                selector = target / "usr/libexec/aios-select-backend"
                if subprocess.check_output([str(selector)], text=True).strip() != "avx2":
                    raise RuntimeError("guest AVX2 backend cannot safely run on the host")
            binary = target / ("usr/bin/llama-server-avx2" if variant == "avx2" else "usr/bin/llama-server")
            cmd = affinity + [str(loaders[0]), "--library-path", libraries, str(binary),
                              "-m", str(model), "--api-key-file", str(key), "--host", "127.0.0.1", "--port", "18081",
                              "--threads", "2", "--ctx-size", "8192", "--no-webui"]
            baseline = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            host = Client(18081, key.read_text().strip())
            wait_for_health(host, baseline, 600)
            cpu_info = Path("/proc/cpuinfo").read_text()
            cpu_match = re.search(r"^model name\s*:\s*(.+)$", cpu_info, re.MULTILINE)
            memory = Path("/proc/meminfo").read_text()
            memory_match = re.search(r"^MemTotal:\s*(\d+) kB", memory, re.MULTILINE)
            result = {"acceleration": "KVM" if kvm else "TCG", "guest_ram_mib": 1024,
                      "inference_backend": variant,
                      "host_cpu": cpu_match.group(1) if cpu_match else "unknown",
                      "host_mem_total_kib": int(memory_match.group(1)) if memory_match else None,
                      "logical_cpus_pinned": cpus, "threads": 2, "context_configured": 8192,
                      "host_kernel": platform.release(), "boot_to_ready_seconds": boot_seconds,
                      "iso_bytes": (output / "aios.iso").stat().st_size,
                      "comparison": run_comparison(host, guest)}
            medians = result["comparison"]["medians"]
            host_rate = medians["github_linux"]["output_tokens_per_second"]
            result["comparison"]["guest_to_host_output_rate_ratio"] = (
                medians["aios_vm"]["output_tokens_per_second"] / host_rate if host_rate else None)
            result["rss_kib_after_short_tests"] = {"host_server": resident_memory_kib(baseline),
                                                    "qemu_process_including_guest": resident_memory_kib(vm)}
            print("Short inference comparison:", flush=True)
            print(json.dumps(result, indent=2), flush=True)
            print("Checking 2,048 input tokens on each environment.", flush=True)
            result["context_checks"] = {}
            for name, client in (("github_linux", host), ("aios_vm", guest)):
                try:
                    result["context_checks"][name] = check_context(client, 2048, timeout=300)
                except (TimeoutError, OSError) as error:
                    result["context_checks"][name] = {"input_tokens": 2048, "passed": False,
                                                       "error": type(error).__name__}
                print(json.dumps({"context": name, "result": result["context_checks"][name]}), flush=True)
            result["limitations"] = ("Same runner, model and executable; host native versus a QEMU VM. "
                                     "KVM still includes virtualization and guest RAM differences. "
                                     "TCG is emulated and is not a fair OS speed comparison. "
                                     "8192 configured is not the same as 8192 validated.")
            print(json.dumps(result, indent=2), flush=True)
            if not all(item["passed"] for item in result["context_checks"].values()):
                raise RuntimeError("2,048-token context check failed or timed out")
        except Exception:
            print_boot_diagnostics(serial)
            raise
        finally:
            stop(baseline)
            stop(vm)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never publish raw serial logs, key files, prompts or model outputs.
        print(f"FAIL: {type(error).__name__}: {error}", file=sys.stderr)
        sys.exit(1)
