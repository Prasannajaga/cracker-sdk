"""Create a warm base snapshot and restore a worker VM from it."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import CrackerVM


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = os.environ.get("FC_BINARY", "/home/prasanna/.local/bin/firecracker")
KERNEL_PATH = os.environ.get("FC_KERNEL_PATH", "/home/prasanna/.sparkvm/images/vmlinux")
ROOTFS_PATH = os.environ.get("ROOTFS_PATH", str(EXAMPLE_DIR / "rootfs/rootfs.ext4"))
SNAPSHOT_DIR = Path(os.environ.get("SNAPSHOT_DIR", "/tmp/cracker-sdk-realworld-warm-snapshot"))
SNAPSHOT_PATH = SNAPSHOT_DIR / "snapshot.json"
MEMORY_PATH = SNAPSHOT_DIR / "memory.mem"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a warm VM snapshot.")
    parser.add_argument(
        "--restore",
        action="store_true",
        help="restore a worker VM from the snapshot after creating it",
    )
    return parser.parse_args()


def configure_and_boot(vm: CrackerVM) -> None:
    vm.start()
    vm.wait_until_ready()
    vm.configure_logger(log_path=str(Path(vm.log_path).resolve()))
    vm.machine(vcpu_count=1, mem_size_mib=256)
    vm.boot_source(kernel_image_path=KERNEL_PATH, boot_args=BOOT_ARGS)
    vm.root_drive(path=ROOTFS_PATH)
    vm.boot()


def main() -> None:
    args = parse_args()
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    base_vm = CrackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-warm-snapshot-base.sock",
        log_path="/tmp/cracker-sdk-warm-snapshot-base.log",
        kernel_path=KERNEL_PATH,
        rootfs_path=ROOTFS_PATH,
        boot_args=BOOT_ARGS,
        workdir="/tmp/cracker-sdk-warm-snapshot-base",
    )
    worker: CrackerVM | None = None

    try:

      if not args.restore:
        configure_and_boot(base_vm)
        time.sleep(2.0)
        base_vm.pause(strict=True)
        snapshot = base_vm.create_snapshot(
            snapshot_path=str(SNAPSHOT_PATH),
            mem_file_path=str(MEMORY_PATH),
            overwrite=True,
        )
        print("snapshot:", snapshot)
        base_vm.stop() 
        return
      
      else:
        print("Restoring worker VM from snapshot...")
        time.sleep(1.0)

        worker = CrackerVM(
            binary=FC_BINARY,
            socket_path="/tmp/cracker-sdk-warm-snapshot-worker.sock",
            log_path="/tmp/cracker-sdk-warm-snapshot-worker.log",
            kernel_path=KERNEL_PATH,
            rootfs_path=ROOTFS_PATH,
            boot_args=BOOT_ARGS,
            workdir="/tmp/cracker-sdk-warm-snapshot-worker",
        )
        restore = worker.restore(
            snapshot_path=str(SNAPSHOT_PATH),
            mem_file_path=str(MEMORY_PATH),
            resume=True,
        )

        # worker.resume()
        print("restore:", restore)
        print("worker_status:", worker.status()) 
        time.sleep(10) 
    finally:
        base_vm.stop()
        if worker is not None:
            worker.stop()


if __name__ == "__main__":
    main()
