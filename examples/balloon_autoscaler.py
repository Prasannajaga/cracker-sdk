import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import BalloonAutoscaler, BalloonPolicy, read_host_memory
from crackersdk import crackerVM


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(PROJECT_ROOT / "examples/rootfs/longrun/rootfs.ext4")
BOOT_SETTLE_SECONDS = 5.0
LOG_PATH = "/tmp/cracker-sdk-examples/balloon/firecracker.log"


def main() -> None:
    vm = crackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-balloon.sock",
        log_path=LOG_PATH,
    )
    print("Firecracker log:", LOG_PATH)

    try:
        vm.start()
        vm.wait_until_ready()
        vm.configure_logger(log_path=str(Path(vm.log_path).resolve()))
        vm.machine(vcpu_count=1, mem_size_mib=1024)
        vm.boot_source(kernel_image_path=KERNEL_PATH, boot_args=BOOT_ARGS)
        vm.root_drive(path=ROOTFS_PATH)
        print(
            "balloon:",
            vm.balloon(amount_mib=64, deflate_on_oom=True, stats_polling_interval_s=1),
        )
        vm.boot()
        time.sleep(BOOT_SETTLE_SECONDS)

        print("host memory:", read_host_memory())
        autoscaler = BalloonAutoscaler(
            vm,
            BalloonPolicy(
                min_balloon_mib=64,
                max_balloon_mib=512,
                step_mib=64,
                low_available_mib=1024,
                high_available_mib=4096,
                cooldown_seconds=5.0,
            ),
        )

        # Manual-tick only: no background thread.
        # Increase reclaims guest memory; decrease gives memory back.
        for _ in range(5):
            print(autoscaler.tick())
            time.sleep(5)
    finally:
        vm.stop()


if __name__ == "__main__":
    main()
