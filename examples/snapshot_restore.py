import os
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from firecracker_sdk import crackerVM


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"

FC_BINARY = os.environ.get("FC_BINARY", "/home/prasanna/.local/bin/firecracker")
KERNEL_PATH = os.environ.get("KERNEL_PATH", "/home/prasanna/.sparkvm/images/vmlinux")
ROOTFS_PATH = os.environ.get(
    "ROOTFS_PATH",
    str(PROJECT_ROOT / "examples/rootfs/longrun/rootfs.ext4"),
)

SNAPSHOT_DIR = Path(os.environ.get("SNAPSHOT_DIR", "/tmp/cracker-sdk-snapshot-demo"))
SNAPSHOT_PATH = SNAPSHOT_DIR / "snapshot.json"
MEM_FILE_PATH = SNAPSHOT_DIR / "memory.mem"


def configure_and_boot(vm: crackerVM) -> None:
    vm.start()
    vm.wait_until_ready()
    vm.machine(vcpu_count=1, mem_size_mib=256)
    vm.boot_source(kernel_image_path=KERNEL_PATH, boot_args=BOOT_ARGS)
    vm.root_drive(path=ROOTFS_PATH)
    vm.boot()


def main() -> None:
    original = crackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-snapshot-source.sock",
    )
    restored = crackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-snapshot-restored.sock",
    )

    try:
        configure_and_boot(original)
        time.sleep(0.5)
        print("original running:", original.status())

        print("original paused:", original.pause(strict=True))
        snapshot = original.create_snapshot(
            snapshot_path=str(SNAPSHOT_PATH),
            mem_file_path=str(MEM_FILE_PATH),
            overwrite=True,
        )
        print("snapshot:", snapshot)
        print("original after snapshot:", original.status())

        original.stop()
        print("original stopped:", original.status())

        restore = restored.load_snapshot(
            snapshot_path=snapshot.snapshot_path,
            mem_file_path=snapshot.mem_file_path,
            resume=True,
        )
        print("restore:", restore)
        print("restored status:", restored.status())
    finally:
        original.stop()
        restored.stop()
        print("final original:", original.status())
        print("final restored:", restored.status())


if __name__ == "__main__":
    main()
