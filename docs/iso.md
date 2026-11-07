# Model-integrated ISO (experimental)

The ISO target boots an x86-64 Linux kernel into an in-memory Buildroot root filesystem, with no desktop. It includes SmolLM2-135M-Instruct, a **135-million-parameter** model close to the requested 125M size, using the smaller Q3_K_M GGUF quantization (93,511,232 bytes). The model is from [tensorblock's conversion](https://huggingface.co/tensorblock/SmolLM2-135M-Instruct-GGUF), derived from Hugging Face's SmolLM2, under Apache-2.0 according to its model card. The model is embedded in the initramfs; RAM must hold both it and the running engine. Tiny models have limited quality. Review the model's license and intended uses before redistribution.

## Build

You need the Buildroot prerequisites, `grub-mkrescue` (BIOS GRUB modules), `xorriso`, `mtools`, and network access to Buildroot sources and Hugging Face. Use the pinned Buildroot checkout from [image.md](image.md). On Ubuntu, `grub-pc-bin grub-common xorriso mtools` provide the ISO tools.

```sh
mkdir -p output
./scripts/download-model.sh "$PWD/output/model.gguf"
./scripts/build-iso.sh /path/to/buildroot "$PWD/output/model.gguf"
```

The ISO configuration also downloads the Buildroot-pinned Bootlin x86-64 glibc toolchain, avoiding a full compiler build. The download script verifies the model against the SHA-256 pinned in the repository. `build-iso.sh` accepts any explicitly provided model; verify custom files yourself. Output is `output/iso/aios.iso` and a checksum. This is a BIOS x86-64 boot target; UEFI and physical hardware boot are not yet verified. The ISO is not an installer, and its filesystem and key are not persistent. It is not guaranteed to fit any particular size until measured.

## Boot and use

The default boot menu entry listens only on guest loopback. The second menu entry explicitly enables an HTTP API on all guest interfaces: use only on an isolated, trusted network. It has **no TLS**. A fresh random token is generated after the kernel RNG is ready and printed on the serial console at boot as `AIOS_BOOT_TOKEN=...`; it changes on every boot. Anyone who can see the console can use it. The boot message shows the listening address, which is not necessarily a remotely usable URL. Model loading can take time, and the startup message alone does not indicate readiness.

For example, after selecting the network entry in QEMU's serial boot menu, this forwards only the host's loopback port into the guest:

```sh
qemu-system-x86_64 -m 1024 -smp 2 -nographic \
  -cdrom output/iso/aios.iso -boot d \
  -netdev user,id=n0,hostfwd=tcp:127.0.0.1:8080-:8080 \
  -device virtio-net-pci,netdev=n0 -device virtio-rng-pci
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

The current test configures one sequence and an 8,192-token context for both servers. It sends 2,048 token IDs and checks the server's evaluated-token count and `truncated` flag on each; this tests only that length, not the full configured limit or every possible prompt. A separate earlier attempt timed out, but subsequent runs successfully tested 8,000 input tokens; see below. The model's published training context is 8,192 tokens, shared between input and generated output. Larger settings require separate testing and may degrade quality. Available RAM also limits larger models and contexts; the OS alone does not define a universal maximum.

After warmup the test alternates three identical 32-token streaming completions per environment, reporting each run and median prompt processing and generation tokens per second, time to first text, and total latency. It runs the *same* Buildroot-built server binary, target libraries, model, two CPU threads, context setting, and pinned logical CPUs on the GitHub Linux host and in the AIOS VM. It checks invalid-token rejection and records ISO size, CPU and guest acceleration. If KVM is unavailable the AIOS guest uses TCG software emulation: its throughput must **not** be treated as an operating-system speed comparison. Even with KVM, guest virtualization, host load and memory differences confound an OS-only speedup claim; use bare-metal, same-hardware measurements for that. The report is evidence only once the workflow has completed.

## Verified build and measurements

GitHub run `42208503255` booted the network-selected test copy and generated text. Both the AIOS KVM guest and native GitHub Linux processed an 8,000-token input without truncation under an 8,192-token, single-slot configuration. Short-generation medians were 17.77 versus 17.67 tokens/s respectively; the difference is too small and the VM-versus-host comparison too confounded to demonstrate an OS speedup. See [technical.md](../technical.md) and `results/benchmarks/42208503255.json` for the setup, latency, memory caveats and raw samples. Reaching the model's configured limit is not established by the 8,000-token test.

The boot-tested ISO's SHA-256 is `f86a7ec1f3865742a9ffeae20a38c4acf0be0c564b4659b16582d38f6d37dddd`. Its exact split files are preserved at Git commit `6c53ca7c490d39041aff3ecab65ca8f1d3ad2c2e`; a later workflow result can update the branch's `results/iso` directory.

## Adaptive CPU image

The adaptive image was boot- and inference-tested in GitHub run `42223692593`. Its SHA-256 is `f0c936e97a8ecf368c6fb7b2539757884314fdf1f7b1af0e843162a5ecc3b572`; the exact split files are preserved at commit `b63178b`. AVX2-capable CPUs select the optimized server; other x86-64 CPUs use the fallback. Startup reports the selected backend and a physical-core-based thread recommendation. See [technical.md](../technical.md) for CPU features, measured performance and limitations. Automatic tuning from RAM or cache capacity is not yet implemented.

The same adaptive ISO also passed a feature-masked fallback test in run `42229907573`: both portable and AVX2 guests booted and generated text. On that AMD runner, median output speed was 11.56 versus 94.47 tokens/s respectively. This is an instruction-set comparison on one machine, not an OS-only speedup; see [technical.md](../technical.md) for the methodology and caveats.

## Optional thread calibration

The experimental tuned boot menu entries measure several thread counts for short model generation before starting the server. This adds up to 180 seconds of startup time; if tuning fails, AIOS falls back to the topology-based count. The test is limited to the installed model and a short generation workload and may not be optimal for long prompts. The default entries remain unchanged. This option requires an ISO built after the change; check the CI report for the tuned-boot result before relying on it.

The tuner-enabled image was boot- and inference-tested in run `42233580477`, including the experimental tuned boot entry. Its exact split files are preserved at commit `5d2a65c`; SHA-256: `851dc74c8096650176c2c4637d9643cc2c76bc2b78d04ea567e5c74c3ff760c5`. This image predates the newer AVX2 compiler optimization. A later build is being tested separately and is not represented by this checksum.

Current tested images default to rejecting prompts that exceed the configured context instead of silently truncating them; `AIOS_CONTEXT_SHIFT=1` in trusted build-time configuration opts into upstream shifting. Prompt and output share the limit, so leave room for generation. The native `/completion` endpoint can reuse an unchanged prefix with `cache_prompt: true` (its upstream default); use a consistent prefix and check `truncated`. Cache reuse depends on slot availability and is not a privacy isolation mechanism.

The AVX2 `-O3` image was boot-tested in run `42235774412` and compared with the preceding image in run `42239159231`. Its split files are preserved at commit `53a8e9c`; SHA-256: `f9d2f53463e5c0b25339d6e839ab0042f5837f9f276f6354aff91d1ddcdb8235`. This tested image does not yet include the newer oversized-input rejection.

The tested image described below adds separate experimental boot entries using a 128-token prompt microbatch. On two Intel native tests this improved the tested 2,048-token prefill relative to 512, but results depend on CPU, model and workload. The ordinary boot entries keep the upstream default. The entries were boot-tested in the microbatch-profile image described below, but are not in the earlier O3 image.

The O3 image passed an 8,000-input-token KVM test (with one output token) in run `42240488102`. In that same run, a warmed, identical 4,096-token prefix was reused for a follow-up request. This does not validate model quality across the entire context or guarantee cache hits for concurrent users. The configured 8,192-token limit includes generated output.

The context-safe O3 image passed boot, inference, authentication, the 2,048-token host/guest check, and rejection of an 8,192-token input in run `42239159203`. Its split files are preserved at commit `1fb7b09`; SHA-256: `aceabc551dab245edf4f1539b74ca2af9b2a7a78c9a12288d3fac6a895476394`. The 8,000-token test above used the preceding O3 image; it was not repeated on this image. The experimental microbatch entry is not included in this version.

The microbatch-profile image passed boot, authentication, normal inference, oversized-input rejection, the tuned-thread boot, and a separate microbatch-128 boot/inference smoke test in run `42239858115`. Its split files are preserved at commit `6197296`; SHA-256: `cae8324fa57a7c3bb7ee1737e911d0e8b149acbcb5f437f5d122f6f4242cd689`. The microbatch entry remains experimental despite the same-image speed comparison described below.

In same-image KVM run `42243833933` on one AMD EPYC 7763, the microbatch-128 entry improved median processing of a synthetic 2,048-token prompt by about 8.5% versus the normal entry (13.903 versus 12.816 seconds). This is not guaranteed for other CPUs, models or workloads; the normal entry remains the default.

The experimental 16k boot profile offers a 16,384-token configured context using linear RoPE scaling. The embedded model was trained for 8,192 tokens, so capacity beyond that does **not** imply reliable answers. It also needs more memory and is not the default. Its boot and long-input acceptance tests are described below; they do not establish reliable retrieval quality.

The experimental 16k-profile image booted and processed 9,000 input tokens untruncated in run `42321205469` with 2 GiB guest RAM. Its exact parts are preserved at commit `0169623`; SHA-256: `3c5a6a280c9e05ab5cd486b9eba16af39ce462b0e5b8a55d0869906c4914f444`. Input acceptance is not a quality guarantee beyond the original training length; longer and retrieval tests are separate.

A follow-up comparison in run `42323397851` processed **16,000 input tokens plus 32 output tokens** without truncation on both conventional Linux and the KVM guest using the 16k profile and 2 GiB guest RAM. A simple synthetic retrieval probe failed at both 256 and 12,000 tokens, so this is a capacity result, **not proof of reliable 16k understanding**. See [technical.md](../technical.md) for the Linux/guest throughput at five lengths and the limitations.

A separate chat-formatted synthetic recall test (`42325943874`) also failed to retrieve its fact at 2,048 and 8,000 tokens on both profiles and at 12,000 and 16,000 on the scaled profile. The scaled profile succeeded at 256 tokens, while the unscaled one did not. This is a single artificial test, but it reinforces that the longer allocation must not be mistaken for reliable long-context understanding.

An upcoming image adds separate **external model disk, 32k context** entries. Attach an ext4 model disk as the first virtio block device (`/dev/vda`); it must contain `/model.gguf` and a private `/api.key`. The volume is mounted read-only, and the server uses the model's own RoPE parameters. Prepare and protect the volume as in [the model-volume guide](image.md#prepare-a-model-volume); unlike the ext2 image example, the ISO's external profile expects `/dev/vda`. The local entry is loopback-only; the separate network entry is unencrypted HTTP. Use only compatible, independently verified models and sufficient RAM. This feature needs the next tested ISO.

As an optional alternative to the embedded model, the official Qwen2.5-0.5B-Instruct Q3_K_M GGUF was tested natively on Linux: it answered one synthetic secret-word probe correctly through 16,000 tokens, whereas the smaller model did not. It is 432 MB and was slower; this single test is not a general quality guarantee and it is not included in the ISO. Exact model source, hash and results are in [technical.md](../technical.md) and `results/alternate-model/42327069673/`.
