import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import crackerVM


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(PROJECT_ROOT / "examples/rootfs/longrun/rootfs.ext4")
NETWORK = {
    "iface_id": "eth0",
    "host_dev_name": "tap0",
    "guest_mac": "AA:FC:00:00:00:01",
}


def configure_boot(vm: crackerVM) -> None:
    vm.machine(vcpu_count=1, mem_size_mib=256)
    vm.boot_source(kernel_image_path=KERNEL_PATH, boot_args=BOOT_ARGS)
    vm.root_drive(path=ROOTFS_PATH)


def manual_setup() -> None:
    vm = crackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-network-entropy.sock",
        log_path="/tmp/cracker-sdk-examples/network-entropy/manual.firecracker.log",
    )
    print("Manual Firecracker log:", vm.log_path)
    try:
        vm.start()
        vm.wait_until_ready()
        vm.configure_logger(log_path=str(Path(vm.log_path).resolve()))
        configure_boot(vm)
        print("entropy:", vm.entropy())
        # tap0 must already exist. The SDK only attaches it to Firecracker.
        print("network:", vm.network(**NETWORK))
        print("interfaces:", vm.network_interfaces())
        print("has_entropy:", vm.has_entropy())
    finally:
        vm.stop()


def run_setup() -> None:
    vm = crackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-network-entropy-run.sock",
        log_path="/tmp/cracker-sdk-examples/network-entropy/run.firecracker.log",
        kernel_path=KERNEL_PATH,
        rootfs_path=ROOTFS_PATH,
        boot_args=BOOT_ARGS,
    )
    print("Run Firecracker log:", vm.log_path)

    result = vm.run(
        vcpu_count=1,
        mem_size_mib=256,
        timeout=10,
        entropy=True,
        network_interfaces=[NETWORK],
    )
    print("run result:", result)


if __name__ == "__main__":
    manual_setup()
    run_setup()
