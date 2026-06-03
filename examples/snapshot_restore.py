import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import crackerVM


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(PROJECT_ROOT / "examples/rootfs/longrun/rootfs.ext4")
SNAPSHOT_DIR = Path("/tmp/cracker-sdk-examples/snapshot")
SNAPSHOT_PATH = SNAPSHOT_DIR / "snapshot.json"
MEM_FILE_PATH = SNAPSHOT_DIR / "memory.mem"


def boot_vm(vm: crackerVM) -> None:
    vm.start()
    vm.wait_until_ready()
    vm.configure_logger(log_path=str(Path(vm.log_path).resolve()))
    vm.machine(vcpu_count=1, mem_size_mib=256)
    vm.boot_source(kernel_image_path=KERNEL_PATH, boot_args=BOOT_ARGS)
    vm.root_drive(path=ROOTFS_PATH)
    vm.boot()


def main() -> None:
    source = crackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-snapshot-source.sock",
        log_path="/tmp/cracker-sdk-examples/snapshot/source.firecracker.log",
    )
    restored = crackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-snapshot-restored.sock",
        log_path="/tmp/cracker-sdk-examples/snapshot/restored.firecracker.log",
    )
    print("Source Firecracker log:", source.log_path)
    print("Restored Firecracker log:", restored.log_path)

    try:
        boot_vm(source)
        time.sleep(0.5)
        print("source:", source.status())

        print("paused:", source.pause(strict=True))
        snapshot = source.create_snapshot(
            snapshot_path=str(SNAPSHOT_PATH),
            mem_file_path=str(MEM_FILE_PATH),
            overwrite=True,
        )
        print("snapshot:", snapshot)

        source.stop()
        restore = restored.load_snapshot(
            snapshot_path=snapshot.snapshot_path,
            mem_file_path=snapshot.mem_file_path,
            resume=True,
        )
        print("restore:", restore)
        print("restored:", restored.status())
    finally:
        source.stop()
        restored.stop()


if __name__ == "__main__":
    main()
