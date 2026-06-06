"""Boot a Firecracker VM with TAP networking and connect with OpenSSH."""

from __future__ import annotations

import socket
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import CrackerVM


BOOT_ARGS = (
    "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init "
    "random.trust_cpu=on"
)
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(EXAMPLE_DIR / "rootfs/rootfs.ext4")
SOCKET_PATH = "/tmp/cracker-sdk-ssh-sandbox.sock"
LOG_PATH = "/tmp/cracker-sdk-ssh-sandbox.log"
WORKDIR = "/tmp/cracker-sdk-ssh-sandbox"

TAP_DEV = "tap-cracker-ssh"
HOST_TAP_CIDR = "172.16.0.1/24"
GUEST_IP = "172.16.0.2"
GUEST_MAC = "AA:FC:00:00:00:02"
SSH_PRIVATE_KEY_PATH = "/home/prasanna/.ssh/id_ed25519"
SSH_PUBLIC_KEY_PATH = "/home/prasanna/.ssh/id_ed25519.pub"
SSH_USER = "root"
SSH_COMMAND = "uname -a && echo connected over ssh"
SSH_READY_TIMEOUT_SECONDS = 90


def run_command(args: list[str]) -> None:
    print("$", " ".join(args))
    subprocess.run(args, check=True)


def check_ssh_key_files() -> None:
    private_key = Path(SSH_PRIVATE_KEY_PATH)
    public_key = Path(SSH_PUBLIC_KEY_PATH)
    if not private_key.exists():
        raise FileNotFoundError(f"SSH private key does not exist: {private_key}")
    if not public_key.exists():
        raise FileNotFoundError(f"SSH public key does not exist: {public_key}")
    if private_key.name.endswith(".pub"):
        raise ValueError("SSH_PRIVATE_KEY_PATH must point to the private key, not the .pub file")


def tap_exists() -> bool:
    result = subprocess.run(
        ["ip", "link", "show", TAP_DEV],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def configure_tap() -> bool:
    created = False
    if not tap_exists():
        run_command(["ip", "tuntap", "add", "dev", TAP_DEV, "mode", "tap"])
        created = True
    run_command(["ip", "addr", "replace", HOST_TAP_CIDR, "dev", TAP_DEV])
    run_command(["ip", "link", "set", TAP_DEV, "up"])
    return created


def delete_tap_if_created(created: bool) -> None:
    if created:
        subprocess.run(["ip", "link", "delete", TAP_DEV], check=False)


def create_vm() -> CrackerVM:
    return CrackerVM(
        binary=FC_BINARY,
        socket_path=SOCKET_PATH,
        log_path=LOG_PATH,
        workdir=WORKDIR,
    )


def boot_vm(vm: CrackerVM) -> None:
    vm.start()
    vm.wait_until_ready()
    vm.configure_logger(log_path=str(Path(vm.log_path).resolve()))
    vm.machine(vcpu_count=1, mem_size_mib=512)
    vm.boot_source(kernel_image_path=KERNEL_PATH, boot_args=BOOT_ARGS)
    vm.root_drive(path=ROOTFS_PATH)
    print(
        "network:",
        vm.network(iface_id="eth0", host_dev_name=TAP_DEV, guest_mac=GUEST_MAC),
    )
    vm.entropy()
    vm.boot()


def wait_for_ssh() -> None:
    deadline = time.monotonic() + SSH_READY_TIMEOUT_SECONDS
    last_error: Exception | None = None
    print(f"waiting up to {SSH_READY_TIMEOUT_SECONDS}s for ssh on {GUEST_IP}:22")
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((GUEST_IP, 22), timeout=1):
                print("ssh port is reachable")
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.5)
    print_host_network_debug()
    print_guest_log_tail()
    raise TimeoutError(f"ssh did not become reachable: {last_error}")


def print_host_network_debug() -> None:
    commands = (
        ["ip", "addr", "show", TAP_DEV],
        ["ip", "route", "get", GUEST_IP],
        ["ip", "neigh", "show", GUEST_IP],
    )
    print("\n--- host network debug ---")
    for args in commands:
        print("$", " ".join(args))
        subprocess.run(args, check=False)
    print("--- end host network debug ---\n")


def print_guest_log_tail(lines: int = 80) -> None:
    log_path = Path(LOG_PATH)
    if not log_path.exists():
        return
    print(f"\n--- last {lines} lines from {LOG_PATH} ---")
    text = log_path.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines()[-lines:]:
        print(line)
    print("--- end guest log ---\n")


def ssh_command() -> list[str]:
    return [
        "ssh",
        "-i",
        SSH_PRIVATE_KEY_PATH,
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=5",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "LogLevel=ERROR",
        "-o",
        "UserKnownHostsFile=/tmp/cracker-sdk-ssh-known-hosts",
        f"{SSH_USER}@{GUEST_IP}",
        SSH_COMMAND,
    ]


def main() -> None:
    check_ssh_key_files()
    created_tap = configure_tap()
    vm = create_vm()
    try:
        boot_vm(vm)
        wait_for_ssh()
        run_command(ssh_command())
    finally:
        vm.stop()
        delete_tap_if_created(created_tap)


if __name__ == "__main__":
    main()
