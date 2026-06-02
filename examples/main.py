import os
from pathlib import Path

from crackersdk import crackerVM


def main() -> None:
    binary = os.environ.get("FC_BINARY", "firecracker")
    socket_path = os.environ.get("FC_SOCKET_PATH", "/tmp/fc.sock")
    log_path = os.environ.get("FC_LOG_PATH", "/tmp/firecracker.log")
    kernel_path = os.environ.get("FC_KERNEL_PATH", "/home/prasanna/.sparkvm/images/vmlinux")
    rootfs_path = os.environ.get(
        "FC_ROOTFS_PATH",
        "rootfs.ext4",
    )
    init_script_guest_path = os.environ.get("FC_INIT_SCRIPT_GUEST_PATH", "/init.sh")

    # Remove a stale socket from previous runs.
    Path(socket_path).unlink(missing_ok=True)

    vm = crackerVM(
        binary=binary,
        socket_path=socket_path,
        log_path=log_path,
    )

    try:
        print(f"Using guest init script: {init_script_guest_path}")
        print("Ensure this file exists inside the guest rootfs image.")
        vm.start()
        vm.wait_until_ready(timeout=30)

        vm.machine(vcpu_count=1, mem_size_mib=256)
        vm.boot_source(
            kernel_image_path=kernel_path,
            boot_args=f"console=ttyS0 reboot=k panic=1 pci=off init={init_script_guest_path}",
        )
        vm.root_drive(path=rootfs_path)
        vm.boot()

        vm.wait(timeout=30)
    except Exception as exc:
        print(f"VM startup failed: {exc}")
        print("Check Firecracker logs for details:")
        print(f"  {log_path}")
        raise
    finally:
        vm.stop()


if __name__ == "__main__":
    main()
