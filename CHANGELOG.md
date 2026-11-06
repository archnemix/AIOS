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
