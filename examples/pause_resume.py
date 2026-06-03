import sys
import time
from pathlib import Path
from threading import Thread

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import VMState, crackerVM


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(PROJECT_ROOT / "examples/rootfs/python/rootfs.ext4")
RUN_TIMEOUT_SECONDS = 20.0
PAUSE_SECONDS = 2.0
LOG_PATH = "/tmp/cracker-sdk-examples/pause-resume/firecracker.log"


def wait_for_running(vm, timeout: float = 10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = vm.status()
        if status.state == VMState.RUNNING and status.process_running:
            return status
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for VM to run: {vm.status()}")


def main() -> None:
    vm = crackerVM(
        binary=FC_BINARY,
        socket_path="/tmp/cracker-sdk-pause-resume.sock",
        log_path=LOG_PATH,
        kernel_path=KERNEL_PATH,
        rootfs_path=ROOTFS_PATH,
        boot_args=BOOT_ARGS,
    )
    print("Firecracker log:", LOG_PATH)
    result = {}

    def run_vm() -> None:
        result["run"] = vm.run(
            vcpu_count=1,
            mem_size_mib=256,
            timeout=RUN_TIMEOUT_SECONDS,
        )

    worker = Thread(target=run_vm)
    worker.start()

    try:
        print("running:", wait_for_running(vm))
        print("paused:", vm.pause(strict=True))
        time.sleep(PAUSE_SECONDS)
        print("resumed:", vm.resume(strict=True))
    finally:
        worker.join(timeout=RUN_TIMEOUT_SECONDS + 5)
        if worker.is_alive():
            vm.stop()
            worker.join(timeout=5)

    print("final status:", vm.status())
    if "run" in result:
        print("stdout:")
        print(result["run"].stdout)


if __name__ == "__main__":
    main()
