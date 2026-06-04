from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .result import MemoryOptimizerStatus
from .lifecycle import VMState

if TYPE_CHECKING:
    from .vm import crackerVM


@dataclass(frozen=True)
class HostMemory:
    total_mib: int
    available_mib: int


@dataclass(frozen=True)
class BalloonPolicy:
    min_balloon_mib: int = 0
    max_balloon_mib: int = 512
    step_mib: int = 64
    low_available_mib: int = 1024
    high_available_mib: int = 4096
    cooldown_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.min_balloon_mib < 0:
            raise ValueError("min_balloon_mib must be >= 0")
        if self.max_balloon_mib < self.min_balloon_mib:
            raise ValueError("max_balloon_mib must be >= min_balloon_mib")
        if self.step_mib <= 0:
            raise ValueError("step_mib must be > 0")
        if self.low_available_mib < 0:
            raise ValueError("low_available_mib must be >= 0")
        if self.high_available_mib < self.low_available_mib:
            raise ValueError("high_available_mib must be >= low_available_mib")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be >= 0")


@dataclass(frozen=True)
class BalloonPolicyResult:
    previous_amount_mib: int
    new_amount_mib: int
    host_available_mib: int
    action: str
    success: bool
    error: str | None

    def __post_init__(self) -> None:
        if self.action not in {"increase", "decrease", "noop", "cooldown", "error"}:
            raise ValueError("action must be increase, decrease, noop, cooldown, or error")


def read_host_memory() -> HostMemory:
    meminfo = Path("/proc/meminfo").read_text(encoding="utf-8")
    values: dict[str, int] = {}

    for line in meminfo.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        fields = value.strip().split()
        if not fields:
            continue
        try:
            values[key] = int(fields[0])
        except ValueError:
            continue

    try:
        total_kib = values["MemTotal"]
        available_kib = values["MemAvailable"]
    except KeyError as exc:
        raise RuntimeError("Missing MemTotal or MemAvailable in /proc/meminfo") from exc

    return HostMemory(
        total_mib=total_kib // 1024,
        available_mib=available_kib // 1024,
    )


class BalloonAutoscaler:
    def __init__(self, vm: crackerVM, policy: BalloonPolicy):
        self.vm = vm
        self.policy = policy
        self._last_change_at: float | None = None

    def reconcile(self) -> BalloonPolicyResult:
        previous_amount = 0
        host_available = 0

        try:
            status = self.vm.status()
            if status.state not in (VMState.RUNNING, VMState.PAUSED):
                return self._error(
                    previous_amount_mib=previous_amount,
                    host_available_mib=host_available,
                    error=f"Balloon autoscaling requires RUNNING or PAUSED VM, got {status.state.value}",
                )

            config = self.vm.balloon_config()
            if config is None:
                return self._error(
                    previous_amount_mib=previous_amount,
                    host_available_mib=host_available,
                    error="Balloon is not configured for this VM",
                )

            previous_amount = self._current_amount_mib(config)
            memory = read_host_memory()
            host_available = memory.available_mib
            desired_amount = self._desired_amount(
                current_amount_mib=previous_amount,
                available_mib=host_available,
            )

            if desired_amount == previous_amount:
                return BalloonPolicyResult(
                    previous_amount_mib=previous_amount,
                    new_amount_mib=previous_amount,
                    host_available_mib=host_available,
                    action="noop",
                    success=True,
                    error=None,
                )

            now = time.monotonic()
            if self._last_change_at is not None:
                elapsed = now - self._last_change_at
                if elapsed < self.policy.cooldown_seconds:
                    return BalloonPolicyResult(
                        previous_amount_mib=previous_amount,
                        new_amount_mib=previous_amount,
                        host_available_mib=host_available,
                        action="cooldown",
                        success=True,
                        error=None,
                    )

            result = self.vm.update_balloon(amount_mib=desired_amount)
            result_success = getattr(result, "success", True)
            if result_success is False:
                error = getattr(result, "error", None) or "Failed to update balloon"
                return self._error(
                    previous_amount_mib=previous_amount,
                    host_available_mib=host_available,
                    error=str(error),
                )

            self._last_change_at = now
            return BalloonPolicyResult(
                previous_amount_mib=previous_amount,
                new_amount_mib=desired_amount,
                host_available_mib=host_available,
                action="increase" if desired_amount > previous_amount else "decrease",
                success=True,
                error=None,
            )
        except Exception as exc:
            return self._error(
                previous_amount_mib=previous_amount,
                host_available_mib=host_available,
                error=str(exc),
            )

    def _desired_amount(self, *, current_amount_mib: int, available_mib: int) -> int:
        desired_amount = current_amount_mib
        if available_mib < self.policy.low_available_mib:
            desired_amount += self.policy.step_mib
        elif available_mib > self.policy.high_available_mib:
            desired_amount -= self.policy.step_mib

        return min(
            self.policy.max_balloon_mib,
            max(self.policy.min_balloon_mib, desired_amount),
        )

    def _current_amount_mib(self, config: Any) -> int:
        if isinstance(config, dict):
            amount = config.get("amount_mib")
        else:
            amount = getattr(config, "amount_mib", None)

        if amount is None:
            raise RuntimeError("Balloon config does not include amount_mib")

        try:
            return int(amount)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Balloon config amount_mib must be an integer") from exc

    def _error(
        self,
        *,
        previous_amount_mib: int,
        host_available_mib: int,
        error: str,
    ) -> BalloonPolicyResult:
            return BalloonPolicyResult(
                previous_amount_mib=previous_amount_mib,
                new_amount_mib=previous_amount_mib,
                host_available_mib=host_available_mib,
                action="error",
                success=False,
                error=error,
            )

    def tick(self) -> BalloonPolicyResult:
        return self.reconcile()


class BalloonMemoryOptimizer:
    def __init__(
        self,
        vm: crackerVM,
        policy: BalloonPolicy,
        *,
        interval_seconds: float = 5.0,
        max_failures: int = 3,
    ):
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        if max_failures <= 0:
            raise ValueError("max_failures must be > 0")
        self.vm = vm
        self.policy = policy
        self.interval_seconds = float(interval_seconds)
        self.max_failures = int(max_failures)
        self._autoscaler = BalloonAutoscaler(vm, policy)
        self._stop_event = threading.Event()
        self._lock = threading.RLock()
        self._thread: threading.Thread | None = None
        self._last_result: BalloonPolicyResult | None = None
        self._last_error: str | None = None
        self._consecutive_failures = 0

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="cracker-sdk-memory-optimizer",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        with self._lock:
            thread = self._thread
            self._stop_event.set()
        if thread is not None:
            thread.join(timeout=float(timeout))

    def status(self) -> MemoryOptimizerStatus:
        with self._lock:
            running = self._thread is not None and self._thread.is_alive()
            return MemoryOptimizerStatus(
                enabled=True,
                running=running,
                interval_seconds=self.interval_seconds,
                last_result=self._last_result,
                last_error=self._last_error,
            )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                status = self.vm.status()
                if status.state == VMState.EXITED:
                    self._stop_event.set()
                    break
                if status.state == VMState.PAUSED:
                    self._stop_event.wait(self.interval_seconds)
                    continue

                result = self._autoscaler.reconcile()
                with self._lock:
                    self._last_result = result
                    self._last_error = result.error
                    if result.success:
                        self._consecutive_failures = 0
                    else:
                        self._consecutive_failures += 1
                        if self._consecutive_failures >= self.max_failures:
                            self._last_error = (
                                result.error
                                or "Memory optimizer stopped after repeated failures"
                            )
                            self._stop_event.set()
                            break
            except Exception as exc:
                with self._lock:
                    self._last_error = str(exc)
                    self._consecutive_failures += 1
                    if self._consecutive_failures >= self.max_failures:
                        self._stop_event.set()
                        break

            self._stop_event.wait(self.interval_seconds)
