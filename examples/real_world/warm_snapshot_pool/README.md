# Warm Snapshot Pool

This example demonstrates a warm sandbox pool pattern:

- boot a base microVM
- wait briefly for guest readiness
- pause the VM
- create a full snapshot
- restore a worker VM from that snapshot

The snapshot manifest written by `create_snapshot()` is useful local metadata.
It is not a scalable production registry. Production systems should index
snapshots in SparkVM or external storage. Device paths such as network taps or
vsock UDS files require careful recreation before restoring snapshots.

## Build Rootfs

```bash
cd examples/real_world/warm_snapshot_pool/rootfs
chmod +x build.sh
./build.sh
```

## Run

```bash
sudo -E uv run python examples/real_world/warm_snapshot_pool/main.py
```

Optional environment variables:

- `FC_BINARY`
- `FC_KERNEL_PATH`
- `ROOTFS_PATH`
- `SNAPSHOT_DIR`

