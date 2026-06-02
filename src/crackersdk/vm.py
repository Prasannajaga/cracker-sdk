from __future__ import annotations

import os
import time
from typing import Any

from .boot import BootAPI
from .errors import FirecrackerError, FirecrackerProcessError, FirecrackerTimeoutError
from .networking import NetworkingAPI
from .process import ProcessConfig, ProcessManager
from .runtime import RuntimeAPI
from .snapshot import SnapshotAPI
from .transport import UnixSocketHTTPClient


class crackerVM:
    def __init__(
        self,
        *,
        binary: str,
        socket_path: str,
        log_path: str | None = None,
        namespace_name: str | None = None,
        api_timeout: float = 2.0,
    ):
        self.binary = binary
        self.socket_path = socket_path
        self.log_path = log_path
        self.namespace_name = namespace_name

        self._client = UnixSocketHTTPClient(socket_path=socket_path, timeout=api_timeout)
        self._proc = ProcessManager(
            ProcessConfig(
                binary=binary,
                socket_path=socket_path,
                log_path=log_path,
                namespace_name=namespace_name,
            )
        )
        self._boot = BootAPI(self._client)
        self._runtime = RuntimeAPI(self._client)
        self._net = NetworkingAPI(self._client)
        self._snap = SnapshotAPI(self._client)

    def __enter__(self) -> crackerVM:
        self.start()
        self.wait_until_ready()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()

    def start(self) -> None:
        self._proc.start()

    def wait_until_ready(self, timeout: float = 10.0, poll_interval: float = 0.1) -> None:
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self._proc.process and self._proc.process.poll() is not None:
                raise FirecrackerProcessError("Firecracker exited before becoming ready")

            if os.path.exists(self.socket_path):
                try:
                    self._boot.get_machine_config()
                    return
                except FirecrackerError as exc:
                    last_error = exc
            time.sleep(poll_interval)

        detail = f": {last_error}" if last_error else ""
        raise FirecrackerTimeoutError(f"Timed out waiting for Firecracker API readiness{detail}")

    def wait(self, timeout: float | None = None) -> int:
        return self._proc.wait(timeout=timeout)

    def stop(self, timeout: float = 5.0) -> None:
        self._proc.stop(timeout=timeout)

    def machine(self, *, vcpu_count: int, mem_size_mib: int, smt: bool | None = None) -> None:
        self._boot.machine(vcpu_count=vcpu_count, mem_size_mib=mem_size_mib, smt=smt)

    def machine_config(self) -> dict[str, Any] | None:
        return self._boot.get_machine_config()

    def boot_source(self, *, kernel_image_path: str, boot_args: str = "") -> None:
        self._boot.boot_source(kernel_image_path=kernel_image_path, boot_args=boot_args)

    def root_drive(self, *, path: str, is_read_only: bool = False) -> None:
        self._boot.drive(
            drive_id="rootfs",
            path=path,
            is_root_device=True,
            is_read_only=is_read_only,
        )

    def drive(self, *, drive_id: str, path: str, is_read_only: bool = False) -> None:
        self._boot.drive(
            drive_id=drive_id,
            path=path,
            is_root_device=False,
            is_read_only=is_read_only,
        )

    def patch_drive(self, *, drive_id: str, path: str | None = None) -> None:
        self._boot.patch_drive(drive_id=drive_id, path=path)

    def boot(self) -> None:
        self._boot.boot()

    def pause(self) -> None:
        self._runtime.pause()

    def resume(self) -> None:
        self._runtime.resume()

    def send_ctrl_alt_del(self) -> None:
        self._runtime.send_ctrl_alt_del()

    def network(self, *, iface_id: str, host_dev_name: str, guest_mac: str) -> None:
        self._net.network(iface_id=iface_id, host_dev_name=host_dev_name, guest_mac=guest_mac)

    def entropy(self) -> None:
        self._net.entropy()

    def create_snapshot(self, snapshot_path: str, mem_file_path: str) -> None:
        self._snap.create_snapshot(snapshot_path=snapshot_path, mem_file_path=mem_file_path)

    def load_snapshot(self, snapshot_path: str, mem_file_path: str, resume: bool = False) -> None:
        self._snap.load_snapshot(
            snapshot_path=snapshot_path,
            mem_file_path=mem_file_path,
            resume=resume,
        )
