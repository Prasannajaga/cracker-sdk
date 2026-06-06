# Isolated Python Job Runner

This example demonstrates a real job-runner pattern:

- the host boots a microVM
- the guest starts a Python agent
- the host sends a job over Firecracker vsock
- the guest writes files into `/workspace`
- the guest runs the requested command
- the guest returns structured stdout, stderr, and exit code

The SDK only provides low-level vsock primitives. The tunnel protocol in
`main.py` is intentionally example-local; a production tunnel or job protocol
belongs in a higher-level project such as SparkVM.

## Build Rootfs

```bash
cd examples/real_world/isolated_python_job_runner/rootfs
chmod +x build.sh
./build.sh
```

The rootfs uses Docker to build a Python-capable filesystem.

## Run

```bash
sudo -E uv run python examples/real_world/isolated_python_job_runner/main.py
```

Optional environment variables:

- `FC_BINARY`
- `FC_KERNEL_PATH`
- `ROOTFS_PATH`
- `FC_SOCKET_PATH`
- `FIRECRACKER_LOG`
- `VSOCK_PATH`

