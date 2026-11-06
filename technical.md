# Technical details

## Scope and architecture

This prototype is a Linux userspace appliance, not a kernel or bootable image. A small standard-library Python gateway listens on loopback and forwards a fixed set of OpenAI-compatible routes to a loopback-only llama.cpp `llama-server`. The backend is independently installed and managed. The gateway does not load a model or perform inference itself. It relays streaming responses without buffering the complete output. It requires a bearer token of at least 32 characters; request bodies are capped at 2 MiB. The unauthenticated `/health` endpoint indicates only that the gateway is responding.

Environment: `AIOS_API_TOKEN` (required), `AIOS_HOST` (default `127.0.0.1`), `AIOS_PORT` (8080), `AIOS_BACKEND` (default `http://127.0.0.1:8081`, HTTP loopback IP and explicit port only). Avoid putting tokens in shell history or process arguments. The hardware command reports logical CPUs in the process affinity mask, not physical cores, cgroup CPU quota, cache topology or RAM. It is a starting point, not an optimized setting.

## Security and deployment

The token is the only built-in access control. There is no TLS, rate limiting, concurrency limit, client isolation, audit log, model output filtering, or production-grade denial-of-service protection. Do not bind to a public interface without a hardened TLS proxy, access policy and resource limits. The server uses a thread per connection; a slow or malicious client can exhaust resources. Keep the inference backend on loopback and firewall other services. Run the gateway and backend as unprivileged separate users and keep software and models updated. Treat model prompts and outputs as sensitive. Tunnel providers receive traffic and may log metadata; review their policies.

`deploy/aios.service` is an example gateway unit, not an installer. Create a dedicated `aios` user, put the source at `/opt/aios`, and provide `/etc/aios/gateway.env` owned by root and readable by the service (for example root:aios mode 0640) containing `AIOS_API_TOKEN=<random secret>`. Install and enable the unit with your distribution's systemd tooling. The backend needs its own independently hardened service. Tune settings for your installation, and verify the sandbox on your distribution.

## Benchmark plan

No speedup has been measured or promised. Compare the same machine, model and quantization, engine build, context size, prompt, thread counts, power settings and load on a minimal installation and a conventional Linux installation. Record CPU model, RAM, kernel, engine revision and flags. Warm up, then run multiple repetitions in alternating order; report median and spread for time to first token, prompt processing and generated tokens per second, peak memory and power if available. Measure both idle and competing-workload cases. Sweep physical-core and logical-core thread counts; cache size, NUMA, memory bandwidth and quantization can dominate. A minimal desktop-free system may save memory but does not inherently accelerate an otherwise idle inference process. Do not compare different hosted CI machines as though they were identical hardware.

## Future work

Build and verify a reproducible bootable image, manage the inference engine and models, account for cgroup quotas and memory, add bounded concurrency and robust request timeouts, provide secure tunnel management, and run controlled hardware benchmarks. The later ISO workflow runs its comparison on one runner and records sanitized results; virtualization remains a significant confounder.

## Experimental native OS target

`os/buildroot` is a Buildroot external tree for a QEMU x86-64 kernel and ext2 root filesystem. Buildroot is pinned in the image guide to 2025.02.12 commit `137a566bf5353831d97c068a4c22e6df5b4d07a0`; llama.cpp is pinned to b5046 commit `74d4f5b041ad837153b0e90fc864b8290e01d8d5` and its source and license are SHA-256 checked. The C++ server is built CPU-only, without downloading models, with static project libraries and no web UI at runtime. It is linked against the target toolchain's system libraries. The default cross-build does not use build-host native CPU instructions; this favors portability over maximum performance. No runtime CPU-dispatched tuning, RAM-based model selection or cache-aware policy has been implemented. Thread count defaults to llama.cpp's automatic setting and should be benchmarked.

BusyBox init mounts the external ext4 model volume read-only, validates a single key, and starts the server as unprivileged UID 1000. It uses the native server's authentication, not the Python gateway: in this pinned version `/health`, `/models`, and `/v1/models` are public even when an API key is configured. The native server may log request metadata and the last four key characters. The service has no TLS, firewall, rate limiter, supervisor, storage encryption, secure boot or automatic security updates. `0.0.0.0` exposes it on all guest interfaces, and even QEMU user networking should not be considered a hardened isolation boundary. Place a properly configured TLS proxy and network restrictions in front of it and review the upstream server's security before exposure. Root login and getty are disabled, but anyone with host or physical access can change boot parameters or inspect disks.

Validation so far: Buildroot defconfig resolves and registers the external package; the pinned llama.cpp server compiled natively with GCC 12 and its required flags appeared in `--help`. The shell scripts and key validator have local tests. The full Buildroot image could not be built in this sandbox because build dependencies (starting with `/usr/bin/file`) are missing and upstream download hosts are restricted; boot, inference, and performance remain unverified. These results do not imply a speedup.

## Model-integrated ISO target

`aios_iso_x86_64_defconfig` produces a gzip-compressed initramfs. The ISO script packages it and the kernel with BIOS GRUB using host `grub-mkrescue`. Its post-build hook embeds an explicitly supplied GGUF in `/opt/aios`. The pinned example model is SmolLM2-135M-Instruct Q3_K_M (93,511,232 bytes; SHA-256 `61c69fc5ce91982e26c625d43be5c3c7f0f774da22f4fa4e45c37a80a22ddad4`), from revision `32db44d69cedb731dc0fc96f60e01a86c6f5919d`. It is a 135M model, not exactly 125M. See its model card and license before redistributing it.

In embedded mode the C key generator uses blocking Linux `getrandom`, creates a mode-0600 key owned by UID 1000, and refuses to overwrite an existing file. Init prints the ephemeral key to the console and starts llama-server. This is convenient for a local appliance, but console access reveals the token. The default GRUB entry binds the server to guest loopback; the separate network entry opts into all-interface unencrypted HTTP. The implementation does not discover or display a usable external address. Use isolated networking and an external authenticated TLS proxy; there is no built-in tunnel.

The GitHub Actions workflow builds one image and runs QEMU with a test-only GRUB default selecting networking, then tests health, token rejection and real text generation. It records a sanitized report and, only after success, split ISO files in the branch. This intentionally stores a large binary in Git to make it accessible without workflow artifacts; it increases repository size. Logs do not include the serial console, which contains the boot token. CI results must be checked before claiming success. No comparison with another OS or CPU performance measurement is made.

## Comparison and context procedure

The automated comparison runs the same Buildroot-built binary with the same target glibc libraries and model on the GitHub-hosted Linux runner and inside the AIOS guest, pinned to the same two host logical CPUs with two inference threads and one slot. It selects KVM if accessible, otherwise records TCG emulation. The 1 GiB guest and larger host have different resource envelopes; virtualization, host load and any CPU feature differences remain confounders. Results are descriptive, not a controlled bare-metal OS speedup.

The ISO default is now `AIOS_CONTEXT=8192` with one upstream default parallel slot. This setting covers prompt plus generation, not 8,192 input tokens plus arbitrary output; concurrent slots would divide the total context. SmolLM2's model metadata reports an 8,192-token training context. An initial 8,000-token check timed out, leaving the maximum unverified. The current CI script checks 2,048 input tokens on both servers; this shorter test must also succeed before being claimed. The optimum memory and context limit for other models and hardware remain unmeasured.

GitHub run 42202660692 produced an ISO of 113,848,320 bytes, but its QEMU readiness check timed out; that image is not confirmed bootable. The test did not capture boot diagnostics. A subsequent change uses Buildroot's `/init` rather than bypassing its devtmpfs setup, enables virtio RNG, and records filtered startup diagnostics on failure. The change has not yet been validated by that earlier run.

GitHub run 42208527000 booted the corrected test ISO using KVM, rejected an invalid token, and generated text from the embedded model. The delivered ISO differs from the test copy in GRUB's default selection and the two-thread test override. The subsequent 8,000-token context request timed out; no throughput or full-context result was recorded in that run.

## Measured result: GitHub run 42208503255

The QEMU test copy booted with KVM, refused an invalid key and generated text. The delivered ISO uses the same kernel, rootfs and model but defaults to the local-only GRUB entry; the test copy selected the network entry and fixed two threads. The ISO is 113,948,672 bytes with SHA-256 `f86a7ec1f3865742a9ffeae20a38c4acf0be0c564b4659b16582d38f6d37dddd`. BIOS QEMU boot was tested; UEFI and physical machines were not.

On one GitHub runner (AMD EPYC 9V45, two pinned logical CPUs), three alternating samples after warmup produced these medians with the identical model, engine binary, target libraries, one sequence, two threads and 8,192 context:

| Metric | GitHub Linux host | AIOS KVM guest |
| --- | ---: | ---: |
| Output tokens/second | 17.67 | 17.77 |
| Prompt tokens/second | 23.65 | 23.52 |
| Time to first text | 1.693 s | 1.703 s |
| Total completion time | 3.504 s | 3.506 s |

The 0.57% output-rate difference is too small and the experiment too confounded to claim an OS speedup. The host server process used 328,868 KiB RSS; the QEMU process, including the guest, used 517,264 KiB RSS. These are not directly comparable measures of OS memory consumption. The guest had 1 GiB allocated; host total memory was approximately 15.6 GiB. Each 8,000-token input was evaluated without truncation: host 866.0 s, guest 905.7 s. These long-prefill results show a practical latency limitation even though both tests fit. They do not establish that all 8,192 tokens can be used as input in addition to generated tokens. Raw samples and metadata are in `results/benchmarks/42208503255.json`.

A second independent run, 42213051304, used an AMD EPYC 7763 and the same two-thread KVM-versus-host setup. Median output throughput was 12.08 tokens/s on the host and 11.90 on AIOS; time to first text was 2.967 s and 2.993 s respectively. Both processed 2,048 input tokens untruncated, taking 219.4 s and 226.3 s. This reinforces that results vary across runners and does not establish an OS speedup. The raw data is `results/benchmarks/42213051304.json`; do not compare the absolute speeds of the two runs as if their CPUs were identical.

## Adaptive CPU backend (experimental)

The image now builds two variants of the pinned llama.cpp server: a baseline x86-64 fallback and an AVX2/FMA/F16C/BMI2 variant. Upstream b5046 enables SSE4.2 for non-native GCC builds even when AVX is disabled; an AIOS build-time patch removes that assumption for the fallback. The boot selector checks the kernel-reported `sse4_2`, `avx`, `avx2`, `fma`, `f16c` and `bmi2` flags on **every** listed CPU; it selects the AVX2 binary only when all are present, otherwise the portable binary. Linux reports AVX only if the OS supports its register state. Feature masking, hotplug, heterogeneous CPUs and hypervisor migration need further validation; selection happens only at startup.

`aios-hardware` reports cache sizes on the first CPU in the affinity mask, available host memory, logical CPUs and distinct physical-core topology. With `AIOS_THREADS=auto`, it starts with one thread per detected physical core within the affinity mask, capped by the whole-core cgroup-v2 quota when readable at `/sys/fs/cgroup/cpu.max`; if topology is missing, it uses affinity count. This quota check does not resolve nested cgroups or cgroup v1, and `MemAvailable` is host memory, not a cgroup limit. This is a conservative starting point, **not** a proven optimum. The probe does not yet tune context, cache allocation or model selection based on RAM or cache size; blind heuristics can reduce performance or cause out-of-memory failures. Set an explicit thread count in `server.conf` and benchmark your workload. The ISO host comparison chooses the same binary variant on both sides.

### CPU kernel experiment

GitHub run `42222865664` used the same pinned SmolLM2 Q3_K_M model and two x86 builds of llama-bench, pinned to CPUs 0–1 on one AMD EPYC 7763 host. It measured three repetitions, 128-token prompt processing and 32-token generation. The baseline is the earlier SSE4.2 build (not the newer SSE2 fallback); the AVX2 build additionally enables AVX2, FMA, F16C and BMI2. With two threads, prompt throughput was 17.81 versus 256.53 tokens/s (14.4x), and generation was 16.13 versus 106.95 tokens/s (6.6x). With one thread, generation was 15.87 versus 100.46 tokens/s. This is an engine-kernel comparison on a single runner, not an OS comparison, an end-to-end API measurement, or a guarantee on other models or hardware. The binaries were measured in fixed order rather than alternating; raw samples and environment are in `results/cpu/42222865664/results.json`.

The adaptive image and boot selection require a fresh ISO build and QEMU test. Do not infer successful integration from the standalone kernel benchmark. An AVX-512 variant, runtime autotuning, RAM-aware model admission, cgroup-v1/nested limits and a bare-metal comparison remain future work.

### Adaptive ISO verification

GitHub run `42223692593` built and booted the new image under QEMU/KVM. The guest selected `avx2`, rejected an invalid token, generated text, and evaluated 2,048 input tokens without truncation. On an AMD EPYC 7763 runner with two fixed inference threads, the guest's median generation speed was 94.77 tokens/s and prompt throughput was 218.23 tokens/s; the same AVX2 binary on the host measured 94.34 and 215.55 respectively. The guest processed the 2,048-token context in 19.27 seconds. These host/VM results are not an OS-only speedup claim. The test copy selected the network GRUB entry and fixed two threads; the distributed ISO defaults to loopback and automatic threading.

The 116,885,504-byte ISO has SHA-256 `f0c936e97a8ecf368c6fb7b2539757884314fdf1f7b1af0e843162a5ecc3b572`; its split files are preserved at Git commit `b63178b`. The integrated AVX2 build's full 8,192-token context and real hardware boot have not been verified. Its 2,048-token check should not be confused with the earlier baseline's 8,000-token check. A separate CI comparison boots two instances of this exact ISO with normal and masked CPU features to exercise both backend selections.
