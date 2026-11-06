# Experimental x86-64 image

This is a QEMU-oriented kernel and root filesystem, not an installer or a disk image with a bootloader. It has not yet been built end to end or booted; the steps below describe the intended workflow. Do not deploy it on a public network or use sensitive workloads. A normal filesystem, kernel, network stack and model runtime are required. Hardware boot support, GPU support, persistent configuration management and automatic tunnel setup are future work.

## Build

On a Linux machine install the [Buildroot 2025.02.12 prerequisites](https://buildroot.org/downloads/manual/manual.html#requirement) (including `file`, `rsync`, C/C++ compiler, make, cpio, Python and standard build tools). The build downloads toolchain, kernel and other upstream sources; it needs unrestricted access to their download sites and several gigabytes of disk space. Check the upstream Buildroot release and security guidance before using it.

```sh
git clone https://github.com/buildroot/buildroot.git
cd buildroot
git checkout 137a566bf5353831d97c068a4c22e6df5b4d07a0
cd /path/to/AIOS
./scripts/build-image.sh /path/to/buildroot
```

Output is under `output/aios/images/`: `bzImage` and `rootfs.ext2`. `AIOS_OUTPUT` can select a different output directory. The script re-applies the AIOS defconfig each time. To customize the image, edit the tracked defconfig or overlay before running it. The llama.cpp source is pinned and hash-checked; other Buildroot packages use the hashes from the pinned Buildroot tree.

## Prepare a model volume

Obtain a GGUF model compatible with the pinned llama.cpp version. The image expects an ext4 volume at `/dev/vdb` containing `/model.gguf` and `/api.key`. This example uses a loopback image on the host and requires sudo; set the image size large enough for the model. It does not modify your physical disks. **Do not use a real disk path in place of `model-data.img`.**

```sh
truncate -s 8G model-data.img
mkfs.ext4 -F model-data.img
mkdir -p model-mount
sudo mount -o loop model-data.img model-mount
sudo cp /path/to/model.gguf model-mount/model.gguf
umask 077
python3 -c 'import secrets; print(secrets.token_urlsafe(32))' > api.key
sudo cp api.key model-mount/api.key
sudo chown 1000:1000 model-mount/model.gguf model-mount/api.key
sudo chmod 600 model-mount/api.key
sudo chmod 644 model-mount/model.gguf
sudo umount model-mount
export AIOS_API_TOKEN="$(cat api.key)"
```

Keep both `api.key` and the disk image private; anyone who can read the volume can obtain the key. The key must be exactly one line of 32–128 URL-safe characters. Back up the key securely; do not commit it or the model to Git.

## QEMU test

To reach the guest from the host, **before building**, change `AIOS_LISTEN=127.0.0.1` to `AIOS_LISTEN=0.0.0.0` in `os/buildroot/board/aios/rootfs-overlay/etc/aios/server.conf`. This exposes the server to the guest network; only use a trusted isolated VM network. QEMU's host forwarding below binds to the host's loopback interface. Adjust RAM to fit the model and context:

```sh
qemu-system-x86_64 -m 4096 -smp 4 -nographic \
  -kernel output/aios/images/bzImage \
  -append 'root=/dev/vda rw console=ttyS0' \
  -drive file=output/aios/images/rootfs.ext2,format=raw,if=virtio \
  -drive file=model-data.img,format=raw,if=virtio,readonly=on \
  -netdev user,id=net0,hostfwd=tcp:127.0.0.1:8080-:8080 \
  -device virtio-net-pci,netdev=net0
```

Wait for model loading, then send the request from the README on the host. Stop QEMU with its monitor or process controls. The serial console reports startup, not an externally reachable URL. Root login and getty are disabled in the image; changes require rebuilding. This is not a physical-access security boundary.

`AIOS_THREADS=-1` delegates thread selection to llama.cpp. Edit `server.conf` to set a measured thread count, context size, port or model volume device. The model and key volume is mounted read-only with `nosuid,nodev,noexec`, and the server runs as UID 1000. A startup message means the process was launched, not that it is healthy; a missing, unreadable or incompatible model can still cause the process to exit. There is no watchdog or automatic restart yet.
