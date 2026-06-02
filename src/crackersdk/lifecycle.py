from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class VMState(str, Enum):
    RUNNING = "running"
    PAUSED = "paused"
    EXITED = "exited"


@dataclass(frozen=True)
class VMStatus:
    state: VMState
    process_running: bool
    api_available: bool
    pid: int | None
    exit_code: int | None
    last_error: str | None
