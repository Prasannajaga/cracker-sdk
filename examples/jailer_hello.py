import sys
from pathlib import Path
import time
from crackersdk.vsock import VsockClient 

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import CrackerVM, Jailer, JailerConfig

BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
JAILER_BINARY = "/usr/local/bin/jailer"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(PROJECT_ROOT / "examples/rootfs/hello/rootfs.ext4")
WORKDIR = "/tmp/cracker-jailer-hello"
SOCKET_PATH = "/tmp/cracker-jailer-hello.sock"
JAIL_ID = "hello-demo-5"
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
    result = jailed.run(timeout=5)
  

    print("exit_code:", result.exit_code)
    print("timed_out:", result.timed_out)
    print("stdout:")
    print(result.stdout)
    print("stderr:")
    print(result.stderr)
    print("firecracker_log:")
    print(result.firecracker_log)


if __name__ == "__main__": 
    main()
