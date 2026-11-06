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
