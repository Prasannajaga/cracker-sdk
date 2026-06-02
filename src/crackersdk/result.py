from __future__ import annotations

from dataclasses import dataclass

from .lifecycle import VMState


@dataclass(frozen=True)
class VMRunResult:
    exit_code: int | None
    timed_out: bool
    firecracker_log: str
    stdout: str
    stderr: str
    error: str | None


@dataclass(frozen=True)
class SnapshotResult:
    snapshot_path: str
    mem_file_path: str
    manifest_path: str | None
    state: VMState
    success: bool
    error: str | None


@dataclass(frozen=True)
class RestoreResult:
    snapshot_path: str
    mem_file_path: str
    resumed: bool
    state: VMState
    success: bool
    error: str | None


@dataclass(frozen=True)
class NetworkInterfaceResult:
    iface_id: str
    host_dev_name: str
    guest_mac: str
    success: bool
    error: str | None


@dataclass(frozen=True)
class EntropyResult:
    enabled: bool
    success: bool
    error: str | None
