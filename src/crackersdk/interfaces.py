from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from .lifecycle import VMState, VMStatus
from .result import (
    BalloonResult,
    BalloonStatsResult,
    EntropyResult,
    NetworkInterfaceResult,
    RestoreResult,
    SnapshotResult,
    VMRunResult,
    VsockResult,
)


class VMLifecycle(Protocol):
    @property
    def state(self) -> VMState:
        ...

    def start(self) -> None:
        ...

    def wait_until_ready(
        self,
        timeout: float = 10.0,
        poll_interval: float = 0.1,
    ) -> None:
        ...

    def wait(self, timeout: float | None = None) -> int:
        ...

    def stop(self, timeout: float = 5.0) -> None:
        ...

    def status(self) -> VMStatus:
        ...

    def is_running(self) -> bool:
        ...

    def is_paused(self) -> bool:
        ...

    def is_stopped(self) -> bool:
        ...

    def run(
        self,
        *,
        vcpu_count: int = 1,
        mem_size_mib: int = 256,
        timeout: float = 30.0,
        entropy: bool = False,
        network_interfaces: list[dict[str, str]] | None = None,
        vsock: dict[str, object] | None = None,
    ) -> VMRunResult:
        ...


class VMBootConfig(Protocol):
    def machine(
        self,
        *,
        vcpu_count: int,
        mem_size_mib: int,
        smt: bool | None = None,
    ) -> None:
        ...

    def machine_config(self) -> dict[str, Any] | None:
        ...

    def boot_source(
        self,
        *,
        kernel_image_path: str,
        boot_args: str = "",
    ) -> None:
        ...

    def root_drive(
        self,
        *,
        path: str,
        is_read_only: bool = False,
    ) -> None:
        ...

    def drive(
        self,
        *,
        drive_id: str,
        path: str,
        is_read_only: bool = False,
    ) -> None:
        ...

    def patch_drive(
        self,
        *,
        drive_id: str,
        path: str | None = None,
    ) -> None:
        ...

    def boot(self) -> None:
        ...


class VMRuntimeControl(Protocol):
    def pause(self, *, strict: bool = False) -> VMStatus:
        ...

    def resume(self, *, strict: bool = False) -> VMStatus:
        ...

    def send_ctrl_alt_del(self) -> None:
        ...


class VMNetworking(Protocol):
    def network(
        self,
        *,
        iface_id: str,
        host_dev_name: str,
        guest_mac: str,
        strict: bool = True,
    ) -> NetworkInterfaceResult:
        ...

    def network_interfaces(self) -> dict[str, NetworkInterfaceResult]:
        ...

    def entropy(self, *, strict: bool = False) -> EntropyResult:
        ...

    def has_entropy(self) -> bool:
        ...


class VMVsock(Protocol):
    def vsock(
        self,
        *,
        guest_cid: int,
        uds_path: str,
        strict: bool = True,
    ) -> VsockResult:
        ...

    def vsock_config(self) -> VsockResult | None:
        ...


class VMBalloon(Protocol):
    def balloon(
        self,
        *,
        amount_mib: int,
        deflate_on_oom: bool,
        stats_polling_interval_s: int = 0,
        strict: bool = True,
    ) -> BalloonResult:
        ...

    def balloon_config(self) -> BalloonResult | None:
        ...

    def update_balloon(
        self,
        *,
        amount_mib: int,
        stats_polling_interval_s: int | None = None,
    ) -> BalloonResult:
        ...

    def balloon_stats(self) -> BalloonStatsResult:
        ...


class VMSnapshot(Protocol):
    def snapshot(
        self,
        snapshot_path: str,
        mem_file_path: str,
        *,
        pause: bool = True,
        overwrite: bool = False,
    ) -> SnapshotResult:
        ...

    def create_snapshot(
        self,
        snapshot_path: str,
        mem_file_path: str,
        *,
        overwrite: bool = False,
    ) -> SnapshotResult:
        ...

    def restore(
        self,
        snapshot_path: str,
        mem_file_path: str,
        *,
        resume: bool = True,
    ) -> RestoreResult:
        ...

    def load_snapshot(
        self,
        snapshot_path: str,
        mem_file_path: str,
        *,
        resume: bool = True,
    ) -> RestoreResult:
        ...


class VMLogging(Protocol):
    def configure_logger(self, log_path: str, level: str = "Info") -> None:
        ...


@runtime_checkable
class VMRuntime(
    VMLifecycle,
    VMBootConfig,
    VMRuntimeControl,
    VMNetworking,
    VMVsock,
    VMBalloon,
    VMSnapshot,
    VMLogging,
    Protocol,
):
    ...
