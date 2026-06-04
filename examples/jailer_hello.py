import sys
from pathlib import Path
import time

from crackersdk.vsock import VsockClient
from examples.vsock import VSOCK_PATH

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import CrackerVM, Jailer, JailerConfig

BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
JAILER_BINARY = "/usr/local/bin/jailer"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(PROJECT_ROOT / "examples/rootfs/vsock/rootfs.ext4")
WORKDIR = "/tmp/cracker-jailer-hello"
SOCKET_PATH = "/tmp/cracker-jailer-hello.sock"
JAIL_ID = "hello-demo-3"
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

    # Normal mode starts Firecracker directly with vm.run().
    # Jailed mode starts the same VM through the Firecracker jailer.
    jailed = Jailer(
        vm,
        config=JailerConfig(
            jailer_binary=JAILER_BINARY,
            jail_id=JAIL_ID,
            uid=JAILER_UID,
            gid=JAILER_GID,
            chroot_base_dir=JAILER_CHROOT_BASE,
        ),
    )

    # Only Firecracker, the kernel, and the rootfs are copied into the jail.
    # Kernel/rootfs/log/socket paths are remapped inside the chroot.
    # The caller does not pass kernel/rootfs paths to Jailer.run().
    result = jailed.run(timeout=5)

    time.sleep(0.5)
    # Requires the example guest listener on vsock port 5000.
    print("response:", VsockClient(VSOCK_PATH).request(port=5000, data=b"ping"))

    print("exit_code:", result.exit_code)
    print("timed_out:", result.timed_out)
    print("stdout:")
    print(result.stdout)
    print("stderr:")
    print(result.stderr)
    print("firecracker_log:")
    print(result.firecracker_log)


if __name__ == "__main__":
    # Example:
    # sudo uv run python examples/jailer_hello.py
    main()
