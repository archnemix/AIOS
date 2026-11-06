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
