"""Run long-lived workers under a manual balloon autoscaling loop."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import BalloonPolicy, CrackerVM


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = os.environ.get("FC_BINARY", "/home/prasanna/.local/bin/firecracker")
KERNEL_PATH = os.environ.get("FC_KERNEL_PATH", "/home/prasanna/.sparkvm/images/vmlinux")
ROOTFS_PATH = os.environ.get("ROOTFS_PATH", str(EXAMPLE_DIR / "rootfs/rootfs.ext4"))
WORKER_COUNT =  10


def create_worker(index: int, policy: BalloonPolicy) -> CrackerVM:
    return CrackerVM(
        binary=FC_BINARY,
        socket_path=f"/tmp/cracker-sdk-memory-worker-{index}.sock",
        log_path=f"/tmp/cracker-sdk-memory-worker-{index}.log",
        kernel_path=KERNEL_PATH,
        rootfs_path=ROOTFS_PATH,
        boot_args=BOOT_ARGS,
        workdir=f"/tmp/cracker-sdk-memory-worker-{index}",
        optimize_memory=True,
        memory_policy=policy,
    )


def start_worker(vm: CrackerVM) -> None:
    vm.start()
    vm.wait_until_ready()
    vm.configure_logger(log_path=str(Path(vm.log_path).resolve()))
    vm.machine(vcpu_count=1, mem_size_mib=1024)
    vm.boot_source(kernel_image_path=KERNEL_PATH, boot_args=BOOT_ARGS)
    vm.root_drive(path=ROOTFS_PATH)
    # optimize_memory=True configures virtio-balloon before boot and starts a
    # background optimizer after boot. If the guest/kernel does not support
    # virtio-balloon, inspect vm.memory_optimizer_status().
    vm.boot()


def main() -> None:
    policy = BalloonPolicy(
        min_balloon_mib=64,
        max_balloon_mib=768,
        step_mib=128,
        low_available_mib=2048,
        high_available_mib=8192,
        cooldown_seconds=5.0,
    )
    workers = [create_worker(index, policy) for index in range(WORKER_COUNT)]

    try:
        for vm in workers:
            start_worker(vm)

        # Memory optimization runs in the background. The loop only prints
        # status; advanced users can still use BalloonAutoscaler.reconcile()
        # manually when they need direct control.
        for _ in range(5):
            for index, vm in enumerate(workers):
                print(f"worker={index}", vm.memory_optimizer_status())
            time.sleep(5)
    finally:
        for vm in workers:
            vm.stop()


if __name__ == "__main__":
    main()
