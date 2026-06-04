from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from .lifecycle import VMState

if TYPE_CHECKING:
    from .balloon_policy import BalloonPolicyResult


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


@dataclass(frozen=True)
class VsockResult:
    guest_cid: int
    uds_path: str
    success: bool
    error: str | None


@dataclass(frozen=True)
class VsockMessageResult:
    uds_path: str
    port: int
    bytes_sent: int
    bytes_received: int
    response: bytes
    success: bool
    error: str | None


@dataclass(frozen=True)
class BalloonResult:
    amount_mib: int
    deflate_on_oom: bool
    stats_polling_interval_s: int
    success: bool
    error: str | None


@dataclass(frozen=True)
class BalloonStatsResult:
    stats: dict[str, int]
    success: bool
    error: str | None


@dataclass(frozen=True)
class MemoryOptimizerStatus:
    enabled: bool
    running: bool
    interval_seconds: float
    last_result: BalloonPolicyResult | None
    last_error: str | None
