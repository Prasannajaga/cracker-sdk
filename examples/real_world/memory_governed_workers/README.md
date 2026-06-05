# Memory Governed Workers

This example demonstrates a realistic memory pressure management pattern:

- start multiple long-running microVM workers
- configure each worker's balloon device before boot
- tick a host-side autoscaler policy
- reclaim or return memory based on host memory pressure

Increasing balloon amount reclaims memory from a guest. Decreasing balloon
amount gives memory back to the guest. The autoscaler here is manual-tick by
design; a production orchestrator such as SparkVM can own scheduling and policy
loops centrally.

## Build Rootfs

```bash
cd examples/real_world/memory_governed_workers/rootfs
chmod +x build.sh
./build.sh
```

## Run

```bash
sudo -E uv run python examples/real_world/memory_governed_workers/main.py
```

Optional environment variables:

- `FC_BINARY`
- `FC_KERNEL_PATH`
- `ROOTFS_PATH`
- `WORKER_COUNT`
