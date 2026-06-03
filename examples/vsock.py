import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import VsockClient, crackerVM


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(PROJECT_ROOT / "examples/rootfs/vsock/rootfs.ext4")
VSOCK_PATH = "/tmp/cracker-sdk-examples/vsock/vm.vsock"
LOG_PATH = "/tmp/cracker-sdk-examples/vsock/firecracker.log"


def main() -> None:
    vm = crackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-vsock.sock",
        log_path=LOG_PATH,
    )
    print("Firecracker log:", LOG_PATH)

    try:
        vm.start()
        vm.wait_until_ready()
        vm.configure_logger(log_path=str(Path(vm.log_path).resolve()))
        vm.machine(vcpu_count=1, mem_size_mib=256)
        vm.boot_source(kernel_image_path=KERNEL_PATH, boot_args=BOOT_ARGS)
        vm.root_drive(path=ROOTFS_PATH)
        print("vsock:", vm.vsock(guest_cid=3, uds_path=VSOCK_PATH))
        vm.boot()
        time.sleep(0.5)

        # Requires the example guest listener on vsock port 5000.
        print("response:", VsockClient(VSOCK_PATH).request(port=5000, data=b"ping"))
    finally:
        vm.stop()


if __name__ == "__main__":
    main()
