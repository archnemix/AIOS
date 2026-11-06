# Changelog

## Unreleased

- Add an experimental GRUB ISO target with a pinned, quantized 135M model, per-boot key generation, and a GitHub Actions QEMU inference test.

- Add an experimental Buildroot x86-64 OS target with a pinned native CPU inference server, read-only model volume and key validation. Full image boot remains unverified.

- Add a Linux CPU inference appliance prototype with an authenticated llama.cpp API gateway.
- Add CPU affinity reporting, an example systemd unit, tests, and deployment and benchmark documentation.
