# AIOS

AIOS is an early CPU-only inference appliance. Its first OS target is a minimal x86-64 Linux image built with Buildroot and a native C/C++ llama.cpp server. It has no desktop and disables the server's web UI. A Linux filesystem is still necessary, and AIOS is not a new kernel. The image is **experimental**; its BIOS ISO has been boot- and inference-tested in QEMU/KVM, not on physical hardware.

## Build and try the OS

Follow [the image guide](docs/image.md) to build the kernel and root filesystem, create a separate model/key volume, and boot under QEMU. You need a Linux build machine, the Buildroot prerequisites, a compatible GGUF model, and sufficient disk, RAM and time. The image defaults to a local-only API; the guide explains how to expose it to a host for a QEMU test.

Once the API is reachable, use the private key stored on the model volume:

```sh
curl http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer $AIOS_API_TOKEN" -H 'Content-Type: application/json' \
  -d '{"model":"local","messages":[{"role":"user","content":"Hello"}]}'
```

The service prints its configured listening URL on the console, but this is not a tunnel URL and does not prove the model loaded. The native server has no TLS. Do not expose it directly to the internet: use a hardened HTTPS proxy and access controls. A separately installed Cloudflare Quick Tunnel, ngrok, or another HTTPS tunnel can point to the host-side proxy; their printed URL is temporary unless configured otherwise. AIOS does not install or manage tunnels yet.

## Prototype gateway

The earlier Python gateway remains available for experiments on an existing Linux installation; it is **not part of the OS image**. See [technical.md](technical.md). The native engine does inference in both setups; changing the gateway language alone would not make model computation faster.

Run repository tests with `python3 -m unittest discover -s tests -v`. See [technical.md](technical.md) for architecture, limitations and benchmarking, [thinking.md](thinking.md) for the engineering journal, and [CHANGELOG.md](CHANGELOG.md) for changes.

## Model-integrated ISO

An experimental BIOS ISO build embeds the 135M-parameter SmolLM2 model and boots the server without a separate model disk. See [docs/iso.md](docs/iso.md) for building, security, and the GitHub Actions QEMU test. The tested adaptive ISO and its checksum are documented in the image guide.

## Experimental CPU adaptation

The image build now includes a portable server and an AVX2 server, selecting the latter only when the processor and Linux expose the required features. It also reports CPU topology, cache and available host memory and chooses a conservative starting thread count. A standalone same-machine kernel test showed a large improvement on one AMD runner; the integrated image has also passed a QEMU/KVM boot and inference test. See [technical.md](technical.md) for results and limitations.

## Choosing a boot profile

The normal local-only entry uses the model's 8,192-token context. For longer prompts within that limit, the experimental **prompt microbatch 128** entry was faster in several measured CPU tests; it may not be faster on every machine. A separate experimental **16k context** entry lets the server accept longer input using position scaling. It has booted and processed a 9,000-token input with 2 GiB of guest RAM, but the embedded model was trained for 8,192 tokens and may not reliably use information beyond that length. Input and output share the configured context. Network entries expose unencrypted HTTP and should only be used behind appropriate protections. Details and measured results are in [the ISO guide](docs/iso.md).

The ISO selects the measured 128-token prompt batch by default **only** for the embedded model with AVX2 and two inference threads; other configurations retain their previous default. This aims to improve input processing on small CI-style CPUs; the booted comparison measured faster input but somewhat slower answer generation. It can be overridden with `aios.ubatch=auto` on the kernel command line. The new default passed the ISO boot test; see the engineering notes for results and limitations.

For higher output speed on GitHub Actions, allocate four vCPUs when available. AIOS normally chooses threads from the CPU topology, and advanced users can set generation and prompt threads separately at boot. In one four-vCPU test, four generation threads produced about 160 tokens/sec versus 143 with two for a 256-token input, using more CPU time. Results depend on the runner and prompt; see [the ISO guide](docs/iso.md).

The ISO also includes an **experimental Q8 key-cache** boot entry. It can improve generation on long prompts without adding CPU cores, but it changes numerical precision and may change answers. The normal entry retains the original F16 cache. See [the ISO guide](docs/iso.md) before using the experimental entry.
