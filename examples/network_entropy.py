import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import crackerVM


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"

FC_BINARY = os.environ.get("FC_BINARY", "/home/prasanna/.local/bin/firecracker")
KERNEL_PATH = os.environ.get("KERNEL_PATH", "/home/prasanna/.sparkvm/images/vmlinux")
ROOTFS_PATH = os.environ.get(
    "ROOTFS_PATH",
    str(PROJECT_ROOT / "examples/rootfs/longrun/rootfs.ext4"),
)
SOCKET_PATH = os.environ.get("FC_SOCKET_PATH", "/tmp/cracker-sdk-network-entropy.sock")


def main() -> None:
    vm = crackerVM(
        binary=FC_BINARY,
        socket_path=SOCKET_PATH,
        kernel_path=KERNEL_PATH,
        rootfs_path=ROOTFS_PATH,
        boot_args=BOOT_ARGS,
    )

    try:
        vm.start()
        vm.wait_until_ready()
        vm.machine(vcpu_count=1, mem_size_mib=256)
        vm.boot_source(kernel_image_path=KERNEL_PATH, boot_args=BOOT_ARGS)
        vm.root_drive(path=ROOTFS_PATH)

        print("entropy:", vm.entropy())

        # tap0 must already exist on the host. The SDK only attaches it to Firecracker.
        print(
            "network:",
            vm.network(
                iface_id="eth0",
                host_dev_name="tap0",
                guest_mac="AA:FC:00:00:00:01",
            ),
        )
        print("configured interfaces:", vm.network_interfaces())
        print("entropy enabled:", vm.has_entropy())
    finally:
        vm.stop()

    # This uses the same pre-existing tap0 contract as the manual API flow above.
    result = crackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-network-entropy-run.sock",
        kernel_path=KERNEL_PATH,
        rootfs_path=ROOTFS_PATH,
        boot_args=BOOT_ARGS,
    ).run(
        vcpu_count=1,
        mem_size_mib=256,
        timeout=10,
        entropy=True,
        network_interfaces=[
            {
                "iface_id": "eth0",
                "host_dev_name": "tap0",
                "guest_mac": "AA:FC:00:00:00:01",
            }
        ],
    )
    print("run result:", result)


if __name__ == "__main__":
    main()
