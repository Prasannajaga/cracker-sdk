from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VMRunResult:
    exit_code: int | None
    timed_out: bool
    firecracker_log: str
    stdout: str
    stderr: str
    error: str | None
