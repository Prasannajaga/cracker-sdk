import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import crackerVM


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(PROJECT_ROOT / "examples/rootfs/python/rootfs.ext4")
LOG_PATH = "/tmp/cracker-sdk-examples/basic/firecracker.log"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the basic cracker-sdk example.")
    parser.add_argument("--timeout", type=float, default=1.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    vm = crackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-basic.sock",
        log_path=LOG_PATH,
        kernel_path=KERNEL_PATH,
        rootfs_path=ROOTFS_PATH,
        boot_args=BOOT_ARGS,
    )
    print("Firecracker log:", LOG_PATH)

    result = vm.run(vcpu_count=1, mem_size_mib=256, timeout=args.timeout)
    print("exit_code:", result.exit_code)
    print("timed_out:", result.timed_out)
    print("error:", result.error)
    print("stdout:")
    print(result.stdout)
    print("stderr:")
    print(result.stderr)


if __name__ == "__main__":
    main()
