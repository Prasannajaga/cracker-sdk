import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from firecracker_sdk import VMRunResult, crackerVM


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"

# Adjust these paths for your local Firecracker binary, kernel, and rootfs images.
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
DEFAULT_TIMEOUT_SECONDS = 1.0


def run_example(name: str, rootfs_path: str, timeout: float) -> VMRunResult:
    vm = crackerVM(
        binary=FC_BINARY,
        socket_path=f"/tmp/cracker-sdk-{name}.sock",
        kernel_path=KERNEL_PATH,
        rootfs_path=rootfs_path,
        boot_args=BOOT_ARGS,
    )

    return vm.run(
        vcpu_count=1,
        mem_size_mib=256,
        timeout=timeout,
    )


def print_result(name: str, result: VMRunResult) -> None:
    print(f"== {name} ==")
    print("exit_code:", result.exit_code)
    print("timed_out:", result.timed_out)
    print("error:", result.error)
    print("stdout:")
    print(result.stdout)
    print("stderr:")
    print(result.stderr)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run cracker-sdk Firecracker examples.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Seconds to wait for the Firecracker process before timing out. Default: {DEFAULT_TIMEOUT_SECONDS}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    runs = [
        # ("hello", "examples/rootfs/hello/rootfs.ext4"),
        ("python", "examples/rootfs/python/rootfs.ext4"),
    ]

    results = []
    for name, rootfs_path in runs:
        print(f"Running {name} rootfs: {rootfs_path}")
        result = run_example(name, rootfs_path, timeout=args.timeout)
        print_result(name, result)
        results.append(result)

    failed = any(result.error is not None and not result.timed_out for result in results)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
