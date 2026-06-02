from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from typing import Any

from .errors import FirecrackerProcessError, FirecrackerTimeoutError


@dataclass
class ProcessConfig:
    binary: str
    socket_path: str
    log_path: str | None = None
    namespace_name: str | None = None


class ProcessManager:
    def __init__(self, config: ProcessConfig):
        self._config = config
        self._proc: subprocess.Popen[bytes] | None = None
        self._log_fp: Any = None

    @property
    def process(self) -> subprocess.Popen[bytes] | None:
        return self._proc

    def start(self) -> None:
        if self._proc and self._proc.poll() is None:
            raise FirecrackerProcessError("Firecracker process is already running")

        if os.path.exists(self._config.socket_path):
            os.remove(self._config.socket_path)

        cmd = [self._config.binary, "--api-sock", self._config.socket_path]
        if self._config.namespace_name:
            cmd = [
                "ip",
                "netns",
                "exec",
                self._config.namespace_name,
                self._config.binary,
                "--api-sock",
                self._config.socket_path,
            ]

        if self._config.log_path:
            self._log_fp = open(self._config.log_path, "ab")
            stdout = self._log_fp
            stderr = subprocess.STDOUT
        else:
            stdout = subprocess.DEVNULL
            stderr = subprocess.DEVNULL

        try:
            self._proc = subprocess.Popen(cmd, stdout=stdout, stderr=stderr)
        except OSError as exc:
            raise FirecrackerProcessError(f"Failed to start Firecracker: {exc}") from exc

    def wait(self, timeout: float | None = None) -> int:
        if not self._proc:
            raise FirecrackerProcessError("Firecracker process is not started")
        try:
            return self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            raise FirecrackerTimeoutError("Timed out waiting for Firecracker process") from exc

    def stop(self, timeout: float = 5.0) -> None:
        if not self._proc:
            return
        if self._proc.poll() is not None:
            return

        self._proc.terminate()
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        finally:
            if self._log_fp:
                self._log_fp.close()
                self._log_fp = None
