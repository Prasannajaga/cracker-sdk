import re


JAILED_KERNEL_PATH = "/kernel/vmlinux"
JAILED_ROOTFS_PATH = "/drives/rootfs.ext4"
JAILED_LOG_PATH = "/logs/firecracker.log"
JAILED_SOCKET_PATH = "/run/firecracker.socket"
JAILED_VSOCK_PATH = "/run/vm.vsock"
ASSET_FIRECRACKER_NAME = "firecracker"


MAC_ADDRESS_RE = re.compile(r"^[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}$")
    