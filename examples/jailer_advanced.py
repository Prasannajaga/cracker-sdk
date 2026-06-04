import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import CrackerVM, Jailer, JailerConfig, VsockClient

BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
JAILER_BINARY = "/usr/local/bin/jailer"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(PROJECT_ROOT / "examples/rootfs/vsock/rootfs.ext4")
WORKDIR = "/tmp/cracker-jailer-advanced"
SOCKET_PATH = "/tmp/cracker-jailer-advanced.sock"
JAIL_ID = "advanced-demo-4"
JAILER_UID = 1000
JAILER_GID = 1000
JAILER_CHROOT_BASE = "/tmp/cracker-jailer"


def main() -> None:
    vm = CrackerVM(
        binary=FC_BINARY,
        socket_path=SOCKET_PATH,
        kernel_path=KERNEL_PATH,
        rootfs_path=ROOTFS_PATH,
        boot_args=BOOT_ARGS,
        workdir=WORKDIR,
    )

    config = JailerConfig(
        jailer_binary=JAILER_BINARY,
        jail_id=JAIL_ID,
        uid=JAILER_UID,
        gid=JAILER_GID,
        chroot_base_dir=JAILER_CHROOT_BASE,
        cleanup_on_exit=True,
    )

    with Jailer(vm, config) as jailer:
        jailer.start()
        jailer.wait_until_ready()
        jailer.machine(vcpu_count=1, mem_size_mib=256)
        jailer.configure_logger(log_path=jailer.log_path)
        jailer.boot_source(kernel_image_path=jailer.kernel_path, boot_args=BOOT_ARGS)
        jailer.root_drive(path=jailer.rootfs_path)
        jailer.entropy()
        jailer.vsock(guest_cid=3)
        jailer.boot()
        print("host_vsock_path:", jailer.host_vsock_path)
        time.sleep(5)
        if jailer.host_vsock_path is None:
            raise RuntimeError("Vsock host path was not configured")
        print("response:", VsockClient(jailer.host_vsock_path).request(port=5000, data=b"ping"))
        print(jailer.status())


if __name__ == "__main__":
    main()
