# Engineering journal

## Initial prototype

The repository started with only a title. The goal is a CPU-only inference OS with an API, but a kernel and inference runtime cannot safely be assumed away. We chose a minimal Linux appliance prototype first: a standard-library gateway in front of a separately managed llama.cpp server. This allows local testing without downloading models or claiming an untested boot image.

The gateway is loopback-only by default, requires a long bearer token, restricts forwarded routes and request size, and streams backend responses. It deliberately does not automate tunnel installation or publish secrets. Exposure, DoS protection, process supervision and bootable-image work remain open. CPU affinity is reported as a starting point rather than pretending an unvalidated heuristic is optimal.

Performance improvement remains a hypothesis. A controlled same-hardware benchmark is needed; hosted runner variation and a desktop being idle can obscure results. The benchmark plan records these constraints before claiming any speedup.

## Native image direction

The first prototype did not constitute an OS and put a Python gateway on the request path. The performance-critical work was already intended for native llama.cpp, but the user asked for an actual system. We added a separate Buildroot external tree and a pinned CPU-only C++ server, leaving the old gateway as an optional experiment rather than making it a dependency of the image. Linux and Buildroot are reused instead of claiming a new kernel or writing an untested model implementation.

The initial target is a QEMU x86-64 kernel plus root filesystem, with a separate read-only model volume. We disabled root login and the web UI, and found that llama.cpp treats an empty API key list as no authentication, so boot validates a single nonempty key before starting. Upstream intentionally makes some metadata routes public; this and other security gaps are documented. Thread auto-selection is delegated to the engine; there is no evidence yet for a cache or RAM tuning policy.

We compiled the pinned server natively and checked its command-line options, and checked that Buildroot resolves the configuration and includes the external package. Full image validation stopped at missing host build dependencies; this environment also restricts source download hosts. Consequently there is no boot, inference or benchmark result to report. A full build and QEMU smoke test on a suitably provisioned host is the next gate before optimizing or promising speedups.

## Model-integrated ISO

The next requested milestone is an actual small ISO with an integrated model and an automated boot/inference test. We chose SmolLM2-135M rather than an exact 125M model because an instruct-tuned, llama.cpp-compatible quantization is available with a published checksum. The 93.5 MB quantized model dominates image size; removing a GUI cannot remove the model's storage or runtime memory requirements.

The ISO uses an initramfs and a separate GRUB network opt-in. Embedding a shared API key would make every image insecure, so a small C utility blocks for the kernel RNG and generates a fresh per-boot key, displayed only on the console. This is still not appropriate for public exposure without TLS and additional controls. The QEMU test switches only the GRUB default on a temporary copy so it can reach the guest while the release defaults to loopback.

The workflow writes a compact report and, on successful boot and inference, split ISO files to the branch because CI artifacts are not assumed accessible. It is one job, not a large matrix. Workflow access and a full build remain to be verified; no test result should be inferred merely from the workflow definition.

## Boot, throughput and context comparison

The user requested measured results rather than a build recipe. The prior ISO workflow was still running, so its success was not assumed. We extended the next run to compare the exact same Buildroot server, libraries and 135M model on the host and in the guest, with pinned CPUs, equal inference threads and context, warmed-up alternating samples, and timing and context checks. We increased the image's configured one-slot context from 2,048 to the model's 8,192-token training length, and added an actual 8,000-input-token untruncated test. We retain raw samples as well as medians.

The guest is virtualized while the normal GitHub Linux host is native. Hardware KVM mitigates but does not remove that confounder; TCG makes throughput comparisons particularly misleading. A same-machine bare-metal experiment remains necessary before claiming that the OS alone improves speed. A bootable ISO can be published when the smoke test passes even if a later benchmark fails, with that failure recorded separately.

The first CI image build remained in the compile step for over 35 minutes with a Buildroot-built toolchain. To shorten subsequent iterations we switched the ISO configuration to Buildroot's pinned, hash-checked Bootlin x86-64 glibc toolchain; the separate ext2 configuration still uses the internal toolchain. The same external toolchain and target libraries are used for both sides of the comparison. This change is configuration-validated but requires the queued CI build to validate end to end.

## First ISO build result and boot correction

GitHub run 42202660692 built a 113,848,320-byte ISO and downloaded and verified the model, but QEMU did not become ready within ten minutes. No model or boot success can be claimed from that run. Its test did not save serial diagnostics, so the precise failure was not identified. Reviewing Buildroot's initramfs setup revealed that passing `rdinit=/sbin/init` bypassed its `/init` script, including the required devtmpfs mount; the GRUB entries now allow the standard `/init` to run. We also enabled virtio RNG in the kernel and QEMU to help the blocking per-boot key generator initialize without weakening it. Future failures will save only filtered kernel and AIOS startup messages, never the boot token or inference traffic. These fixes need a fresh test.

A subsequent build using the prebuilt toolchain also created an ISO, and its test reached the point of obtaining the boot token, but the model API never became ready. This distinguishes starting init from successful inference. The test now retains safe error/network diagnostics and emits completed short benchmarks before attempting the longer context checks, so a later timeout does not erase all timing data.

The corrected run 42208527000 booted with KVM and generated text with the embedded model, while the 8,000-token request timed out. The test copy selected the network-enabled menu entry and two threads; the delivered ISO defaults to loopback and automatic threading. The ISO was saved after the boot/inference smoke test, but the benchmark was not printed before the timeout. We changed subsequent tests to preserve short-run metrics immediately and attempt a bounded 2,048-token check on both environments. An 8,192 configuration is not proof of a working 8,192-token input.

Once a boot-tested ISO exists, a later failed run must not discard it. The publication workflow now retains the last known boot-tested parts on failure; reports still describe each run's outcome. Older runs already in progress use the previous workflow definition, so the tested image is also available from its immutable result commit.

## Successful boot and measured comparison

GitHub run 42208503255 completed the boot, authentication, inference and long-context tests. It confirmed 8,000 input tokens without truncation on both the host and guest, but each took roughly 14–15 minutes to process. The first run's timeout was not evidence that the context could not fit. Three short-generation samples produced medians of 17.67 output tokens/s on the native host and 17.77 on the KVM guest; we treat this 0.57% difference as noise, not a demonstrated speedup. The benchmark compares a VM with a host, not two bare-metal OS installations, and the memory figures are not like-for-like. The tested ISO was reconstructed from the report's split files and checksum verified; its GRUB default remains local-only, while testing selected the network entry and fixed two threads.

A second bounded run on a different AMD runner also booted and passed 2,048-token context checks. It measured 12.08 host versus 11.90 guest output tokens/s, the opposite small ordering from the first runner. This reinforces the decision not to claim an OS speedup from these tests.

## Hardware-specific inference experiment

The prior ISO used a generic, non-native llama.cpp build, so removing operating-system services was unlikely to improve the core math. We compared the pinned model on one GitHub runner with the same llama.cpp revision, workload and thread counts, changing only CPU compilation flags. Run 42222865664 showed the SSE4.2 baseline at 16.13 output tokens/s and the AVX2/FMA/F16C/BMI2 build at 106.95 tokens/s with two threads. This is a large kernel-level difference on that particular machine, not proof that the OS itself is faster. Prompt throughput also rose from 17.81 to 256.53 tokens/s. We preserve the full report and CPU/cache information rather than extrapolate to other machines.

We then added a runtime-selected AVX2 server alongside a portable fallback. Reviewing upstream revealed that its supposed generic build unconditionally uses SSE4.2, so the fallback removes that assumption rather than crashing on older x86-64 CPUs. Selection checks all kernel-reported CPUs, not just the first, and requires the entire feature set. An affinity-aware physical-core probe and basic cgroup-v2 cap provide an initial thread count; cache and host available RAM are reported, not fed into invented tuning formulas. Benchmarks should decide future policies. The new image and selector still need a full build, boot and inference test before use.

## First adaptive image boot

Run 42223692593 successfully built and booted the adaptive ISO and confirmed that the AVX2 backend was selected on the KVM runner. It authenticated requests, produced text, and evaluated 2,048 tokens without truncation. The guest measured 94.77 output tokens/s with two threads; a same-runner host using the identical optimized binary measured 94.34. Both are close, reinforcing that the gain in the earlier experiment comes from CPU kernels, not a demonstrated OS advantage. The 2,048-token guest test took 19.27 seconds, compared with 226.3 seconds in a prior run on another EPYC 7763 runner using the old backend; cross-runner time differences are indicative, not a controlled speedup measurement.

The portable selector was tested with simulated `/proc/cpuinfo` and its server built locally, but this did not prove fallback inference in the ISO. We added a separate single-job KVM test that boots two copies of the tested ISO, masking AVX features in one and retaining them in the other, then alternates identical requests. It records safe results without serial logs or tokens. Its success must be checked separately.

The first two feature-masked ISO tests did not complete: one extracted GRUB's configuration with its read-only ISO permissions and failed when trying to change the test-only default; the other stalled during package installation. The test now makes the extracted configuration writable and records bounded package-install diagnostics. Neither failure invalidates the prior AVX2 boot test, but the fallback still requires verification.

The next fallback test was blocked by a runner package-install timeout. Its saved apt log showed a large set of recommended multimedia packages being downloaded along with QEMU, so we narrowed the install to required packages and allowed more time. The earlier GRUB permission failure is fixed in the test script, but fallback inference is still pending.

The fallback-comparison job got past dependency installation but its feature-masked guest did not become ready within five minutes. No console diagnostics were captured by that version of the test, so this is not yet evidence of a working fallback. The test now records only filtered boot/error lines and the presence of (not the value of) the boot credential to distinguish a boot, entropy, network or server failure.

## Fallback and AVX2 verified inside the image

Run 42229907573 completed the two-guest test. The feature-masked guest selected the portable backend and the other selected AVX2; both booted and generated text. With alternating samples on the same runner, medians were 11.56 versus 94.47 output tokens/s, and 12.93 versus 216.13 prompt tokens/s. This validates the dispatch and shows a substantial instruction-set kernel difference for this particular short workload. It does not show an OS-only speedup, validate an actual older physical CPU, or prove the automatic thread choice is optimal. Earlier intermittent package-install and guest-start failures are preserved in the engineering history rather than hidden.

## Per-machine tuning

Choosing physical cores is only a heuristic. To improve on it without assuming that more threads are always better, we added an opt-in boot mode that measures the embedded model's generation throughput at up to four thread counts bounded by affinity and a visible cgroup-v2 quota. It chooses a higher count only if the measured gain exceeds two percent, runs the benchmark as the unprivileged service user, and falls back to the topology default on failure or after a 180-second timeout. The default boot remains unchanged, since calibration adds startup latency and a short generation test is not representative of every workload. The benchmark executes the already-selected portable or AVX2 backend. The ISO test now boots a separate tuning-enabled guest and verifies real inference; a failed tuning test must not replace the last tested ISO. Image-size, tuning effectiveness and end-to-end boot require CI validation.

Separately, two GitHub runners are sweeping thread count, batch and microbatch sizes, flash attention, llamafile kernels and AVX512 where supported, holding the model and engine revision fixed. None of those settings is enabled based on an unmeasured guess.

The initial calibration ISO job stalled during runner dependency setup, before the build. We applied the same bounded, no-recommends package installation that succeeded in the earlier fallback test and added a compact dependency log to the report. A replacement build was started; the original job may still run independently.

## Compiler optimization level

We found Buildroot defaults to `-O2` while the earlier native benchmark used CMake's Release `-O3`. Rather than infer the effect from results on different runners, run 42234637751 compared the flags on one EPYC 9V45 with the same AVX2 engine and model. `-O3` improved 2,048-token prefill from 184.35 to 258.46 tokens/s, and 256-token prefill from 349.76 to 405.22 tokens/s; short generation improved from 107.90 to 115.48 tokens/s, though the O2 generation samples were noisy. The order was fixed, and this was a native benchmark. We therefore changed only the AVX2 inference build to append `-O3`, retaining all other target flags and leaving the rest of the OS at the existing settings. It remains subject to image-level validation and a same-runner old-versus-new ISO comparison.

## Initial tuning results and boot validation

ISO run 42233580477 booted the tuner entry under KVM and completed inference after selecting one thread. Its ordinary boot also passed authentication, inference and the 2,048-input-token context test. The verified ISO SHA-256 is `851dc74c8096650176c2c4637d9643cc2c76bc2b78d04ea567e5c74c3ff760c5`; this image predates the separate O3 change.

The first completed tuning sweep, runner 2 of 42231629326, used an Intel Xeon Platinum 8573C. With two threads, batch 512 and microbatch 128, 256-token prompt throughput was 274.18 tokens/s for AVX2 with llamafile kernels, 197.63 without them, and 328.77 for AVX512; generation was 139.95, 139.30 and 137.26 tokens/s respectively, with flash attention off. For 2,048 prompt tokens with batch/microbatch 512, flash off versus on was 161.02 versus 127.98 tokens/s on AVX2. These fixed-order, single-host microbenchmarks do not justify a universal AVX512 or flash default. The other runner and the O3 ISO tests are pending.

Runner 1 of sweep 42231629326 also completed, on Intel Xeon Platinum 8370C. For the same two-thread 256-token setup, AVX2 with llamafile, AVX2 without it, and AVX512 achieved 221.24, 138.88, and 253.48 prompt tokens/s; 64-token generation was 85.74, 86.32, and 82.73 tokens/s respectively. With AVX2, the 2,048-token prefill fell from 134.98 to 96.74 tokens/s with flash attention enabled. These results reinforce keeping llamafile and leaving flash off for this model. AVX512 improves prefill but slightly regresses generation on both tested Intel CPUs; we have not yet tested an AVX512 ISO or implemented an additional dispatch target.

## Long contexts and publication ordering

The optimized ISO in run 42235774412 passed boot, authentication, inference, 2,048-token host/guest tests, and the optional tuned boot. Its SHA-256 is `f9d2f53463e5c0b25339d6e839ab0042f5837f9f276f6354aff91d1ddcdb8235`, source `05d2a9f`. We prepared 8,000-token and common-prefix measurements to test rather than assume longer-context handling. We also changed the next build to reject oversized input by default, with an explicit trusted opt-in to upstream context shifting, so a too-large prompt cannot silently lose content. The image test now exercises the boundary. This behavior remains pending boot validation.

A slow older ISO job published after a newer one; the optimized ISO later replaced it. Future ISO workflows are serialized and reject stale source commits so old successful builds cannot overwrite newer images. An ISO comparison completed its test step but failed to publish its report after the branch advanced. We suspect the reset to the latest branch left tracked files dirty before rebase; result workflows now restore tracked files before recording their run-specific untracked reports. The comparison needs a rerun, and the actual earlier measurements are not available in the repository.

## Matched ISO compiler comparison

Run 42239159231 compared the prior O2 ISO with the O3 AVX2 ISO on the same AMD EPYC 7763 runner, using KVM guests with two pinned logical CPUs, two inference threads, 1 GiB RAM and the same model. After warmup, three alternating short-completion samples had median prompt throughput 213.62 versus 241.30 tokens/s and generation 91.41 versus 100.50 tokens/s, with median end-to-end latency 0.535 versus 0.487 seconds. This is approximately 13.0% faster prompt processing and 9.9% faster generation for this short test. Both image hashes were verified, but the images also differ in tuner packaging and were booted in fixed order. This is an inference-build comparison, not an OS-only speedup or a guarantee on other workloads.

## Prompt microbatch option

The two Intel sweeps showed better 2,048-token prefill for physical microbatch 128 than 512 at batch 512, while upstream's default microbatch is 512. We added explicit experimental local/network GRUB entries for microbatch 128 and a build-time `AIOS_UBATCH` setting, leaving upstream's default unchanged. The next ISO smoke test must boot the new entry and generate text. A same-ISO KVM comparison script was prepared for a 2,048-token prompt; the optimum may differ on other hardware and models, and the observed native microbenchmarks are not a substitute for testing the actual image.

The first long-context attempt reached the prefix-cache check but failed it: our priming request mistakenly set `cache_prompt: false`, which makes the pinned server skip storing the prompt in its reusable cache. The test was corrected to prime with caching enabled and now records the 8,000-token result before running the separate cache measurement. This was a benchmark setup error, not evidence that prefix caching is unavailable; it needs a fresh run.

## Near-limit context, prefix reuse and cache precision

Run 42240488102 booted the verified O3 ISO on an AMD EPYC 9V74 KVM runner, two pinned CPUs/threads and 1 GiB guest memory. An 8,000-token synthetic input evaluated all 8,000 tokens without truncation and generated one token in 88.45 seconds. A separate 4,112-token prompt took 30.71 seconds cold; with the first 4,096 tokens already cached in the same slot, only 16 tokens were processed and the request took 0.206 seconds. The ~149x wall-time ratio is a single synthetic prefix-reuse case, not a general tokens/s or OS speedup; concurrent clients, cache misses, model quality and output length were not tested.

Run 42239899213 measured KV precision on an EPYC 9V45, two threads, native pinned O3 AVX2 llama-bench. F16 K/V without flash used 218,480 KiB peak process RSS and processed 2,048 prompt tokens at 274.70 tokens/s; Q8_0 K/F16 V without flash used 207,196 KiB and 279.89 tokens/s, with short generation 110.38 versus 116.86 tokens/s. Q8_0 K/V required flash and used 186,000 KiB, but 2,048-token prefill fell to 150.24 tokens/s. These are fixed-order short native tests, peak RSS covers the process rather than only KV, and no output-quality evaluation was performed. Keep the existing F16 default; do not silently trade accuracy or prompt speed for memory.

Run 42239159203 successfully booted the context-safe O3 ISO, rejected the 8,192-token prompt with HTTP 400, and passed the ordinary inference, 2,048-token context and tuned-boot tests. Its SHA-256 is `aceabc551dab245edf4f1539b74ca2af9b2a7a78c9a12288d3fac6a895476394`. The separate 8,000-token test was on the immediately preceding O3 ISO, not this image. The later microbatch-profile build is still in progress.
