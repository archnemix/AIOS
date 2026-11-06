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
