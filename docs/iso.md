# Model-integrated ISO (experimental)

The ISO target boots an x86-64 Linux kernel into an in-memory Buildroot root filesystem, with no desktop. It includes SmolLM2-135M-Instruct, a **135-million-parameter** model close to the requested 125M size, using the smaller Q3_K_M GGUF quantization (93,511,232 bytes). The model is from [tensorblock's conversion](https://huggingface.co/tensorblock/SmolLM2-135M-Instruct-GGUF), derived from Hugging Face's SmolLM2, under Apache-2.0 according to its model card. The model is embedded in the initramfs; RAM must hold both it and the running engine. Tiny models have limited quality. Review the model's license and intended uses before redistribution.

## Build

You need the Buildroot prerequisites, `grub-mkrescue` (BIOS GRUB modules), `xorriso`, `mtools`, and network access to Buildroot sources and Hugging Face. Use the pinned Buildroot checkout from [image.md](image.md). On Ubuntu, `grub-pc-bin grub-common xorriso mtools` provide the ISO tools.

```sh
mkdir -p output
./scripts/download-model.sh "$PWD/output/model.gguf"
./scripts/build-iso.sh /path/to/buildroot "$PWD/output/model.gguf"
```

The download script verifies the model against the SHA-256 pinned in the repository. `build-iso.sh` accepts any explicitly provided model; verify custom files yourself. Output is `output/iso/aios.iso` and a checksum. This is a BIOS x86-64 boot target; UEFI and physical hardware boot are not yet verified. The ISO is not an installer, and its filesystem and key are not persistent. It is not guaranteed to fit any particular size until measured.

## Boot and use

The default boot menu entry listens only on guest loopback. The second menu entry explicitly enables an HTTP API on all guest interfaces: use only on an isolated, trusted network. It has **no TLS**. A fresh random token is generated after the kernel RNG is ready and printed on the serial console at boot as `AIOS_BOOT_TOKEN=...`; it changes on every boot. Anyone who can see the console can use it. The boot message shows the listening address, which is not necessarily a remotely usable URL. Model loading can take time, and the startup message alone does not indicate readiness.

For example, after selecting the network entry in QEMU's serial boot menu, this forwards only the host's loopback port into the guest:

```sh
qemu-system-x86_64 -m 1024 -smp 2 -nographic \
  -cdrom output/iso/aios.iso -boot d \
  -netdev user,id=n0,hostfwd=tcp:127.0.0.1:8080-:8080 \
  -device virtio-net-pci,netdev=n0
```

Set `AIOS_API_TOKEN` on the host to the displayed token, then use the request in the main README. Do not put the token in public logs, screenshots or shared consoles. `/health`, `/models`, and `/v1/models` are public in the pinned upstream server. Other routes require the token. There is no rate limiting, TLS, watchdog, secure boot, persistent key, update mechanism, or production hardening. To make an external URL, separately configure a hardened TLS reverse proxy and a tunnel such as Cloudflare or ngrok on the host. The ISO itself does not include or automatically configure either service.

## CI output

Changing `ci/run-iso.txt` on the session branch triggers one GitHub Actions job. It builds the ISO, makes a test-only copy whose GRUB default is the network entry, boots that copy in QEMU, checks that an invalid token is rejected, and requests real generated text. Its report is saved at `results/iso/report.txt` on the same branch; on success, the ISO is split into files smaller than GitHub's per-file limit and committed there as well. These large files increase repository history. Reassemble and verify them:

```sh
cat results/iso/aios.iso.part-* > aios.iso
(cd results/iso && cat aios.iso.sha256)
sha256sum aios.iso
```

The hashes must match. The test copy differs from the delivered ISO in its default GRUB entry; the embedded kernel, rootfs and model are the same. QEMU emulation is not a valid speedup benchmark. The workflow does not publish its serial log or boot token.

## Throughput and context comparison

The current test configures one sequence and an 8,192-token context for both servers. It sends 8,000 token IDs and checks the server's evaluated-token count and `truncated` flag on each; this tests one near-limit input, not model quality or every possible prompt. The model's published training context is 8,192 tokens, shared between input and generated output. Larger settings require separate testing and may degrade quality. Available RAM also limits larger models and contexts; the OS alone does not define a universal maximum.

After warmup the test alternates three identical 32-token streaming completions per environment, reporting each run and median prompt processing and generation tokens per second, time to first text, and total latency. It runs the *same* Buildroot-built server binary, target libraries, model, two CPU threads, context setting, and pinned logical CPUs on the GitHub Linux host and in the AIOS VM. It checks invalid-token rejection and records ISO size, CPU and guest acceleration. If KVM is unavailable the AIOS guest uses TCG software emulation: its throughput must **not** be treated as an operating-system speed comparison. Even with KVM, guest virtualization, host load and memory differences confound an OS-only speedup claim; use bare-metal, same-hardware measurements for that. The report is evidence only once the workflow has completed.
