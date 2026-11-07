# Changelog

## Unreleased

- Add a same-runner native Linux versus AIOS VM inference comparison, streaming latency and 8,000-token context checks; configure 8,192 context tokens.

- Add an experimental GRUB ISO target with a pinned, quantized 135M model, per-boot key generation, and a GitHub Actions QEMU inference test.

- Add an experimental Buildroot x86-64 OS target with a pinned native CPU inference server, read-only model volume and key validation. Full image boot remains unverified.

- Add a Linux CPU inference appliance prototype with an authenticated llama.cpp API gateway.
- Add CPU affinity reporting, an example systemd unit, tests, and deployment and benchmark documentation.
- Restore Buildroot's initramfs `/init`, enable virtio RNG, and add filtered boot diagnostics after an initial QEMU readiness timeout.
- Record a successful KVM boot, inference and 8,000-token context comparison against the same server on GitHub Linux.
- Add experimental runtime AVX2 selection, portable x86-64 fallback, CPU topology reporting and conservative automatic thread selection; record a same-runner kernel benchmark.
- Boot-test the adaptive AVX2 ISO with model inference and a 2,048-token context; add a separate feature-masked portable/AVX2 guest comparison.
- Verify both portable and AVX2 inference paths in feature-masked KVM guests and record the same-runner comparison.
- Add opt-in, bounded model-specific thread calibration with a conservative fallback and a separate tuned-boot smoke test.
- Benchmark `-O2` versus `-O3` and apply `-O3` only to the AVX2 inference engine; ISO-level validation pending.
- Validated the opt-in thread tuner in a KVM boot and recorded initial Intel kernel/flash-attention sweep measurements.
- Reject overlong prompts by default rather than silently dropping context; trusted builds can explicitly enable context shifting. ISO boot validation pending.
- Serialize ISO publishing and add near-limit and prefix-cache benchmarks.
- Boot-tested the AVX2 `-O3` image and compared it with the earlier image on the same runner; short-prompt and generation throughput improved for the tested workload.
- Add experimental 128-token prompt-microbatch boot entries and a same-image prefill comparison; image testing pending.
- Verified an 8,000-token prompt and demonstrated same-slot shared-prefix reuse on the optimized ISO; measured KV precision tradeoffs without changing defaults.
- Verified the default oversized-input rejection in a new booted O3 ISO.
- Boot-tested the experimental microbatch-128 profile and its inference path.
- Measured the opt-in 128-token prompt microbatch against the normal boot profile on the same ISO and runner.
- Add experimental 16k RoPE-scaled boot entries and THP-policy measurement support; image and quality tests pending.
- Benchmarked Linux process affinity and THP opt-out individually and combined; neither is enabled by default based on the inconclusive result.
- Boot-tested the opt-in 16k profile with a 9,000-token input; recorded before/after throughput at 256, 2,048, and 8,000 input tokens.
- Measured guest THP policy and prompt microbatch separately and together; the THP effect remains inconclusive.
- Measured thread tuning and microbatch individually and together; the tuner selected two threads in that test.
- Compared the 16k profile with the same binary on ordinary Linux at five input lengths; recorded the failed synthetic retrieval probe and its limitations.
- Added a chat-formatted retrieval probe at five context lengths and recorded failures rather than treating accepted input as reliable recall.
- Compare optional 0.5B long-context model on Linux and add opt-in external-model 32k ISO profiles; external-volume boot test pending.
- Swept inference thread counts on separate Intel and AMD four-vCPU runners and recorded workload-specific scaling.
- Add opt-in combined thread-calibration and microbatch boot profiles; ISO boot test pending.
- Boot-tested the external-model profile with read-only disk, authentication and inference; Qwen-specific guest checks are separate.
- Added an interleaved two-runner screening benchmark for GitHub Actions CPU inference settings; no default changed pending results and guest confirmation.
- For the next ISO build, select the previously measured 128-token prompt microbatch for the embedded model on two AVX2 threads, with an explicit upstream-default override. Fresh ISO boot validation is pending.
- Completed GitHub Actions native setting screening on two AMD runners: 128-token batching improved synthetic 2,048-token prefill by 8.2–10.7% over 512; booted-server and output-speed results remain separate.
