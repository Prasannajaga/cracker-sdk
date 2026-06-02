from __future__ import annotations

import os
import subprocess
import threading
from dataclasses import dataclass

from .errors import FirecrackerProcessError, FirecrackerTimeoutError


@dataclass
class ProcessConfig:
    binary: str
    socket_path: str
    log_path: str | None = None
    namespace_name: str | None = None
    mirror_output_to_log: bool = True


class ProcessManager:
    def __init__(self, config: ProcessConfig):
        self._config = config
        self._proc: subprocess.Popen[bytes] | None = None
        self._log_fp = None
        self._log_lock = threading.Lock()
        self._reader_threads: list[threading.Thread] = []
        self._stdout_chunks: list[bytes] = []
        self._stderr_chunks: list[bytes] = []

    @property
    def process(self) -> subprocess.Popen[bytes] | None:
        return self._proc

    @property
    def stdout(self) -> str:
        return b"".join(self._stdout_chunks).decode("utf-8", errors="replace")

    @property
    def stderr(self) -> str:
        return b"".join(self._stderr_chunks).decode("utf-8", errors="replace")

    def set_log_path(self, log_path: str | None) -> None:
        self._config.log_path = log_path

    def set_mirror_output_to_log(self, enabled: bool) -> None:
        self._config.mirror_output_to_log = enabled

    def start(self) -> None:
        if self._proc and self._proc.poll() is None:
            raise FirecrackerProcessError("Firecracker process is already running")

        if os.path.exists(self._config.socket_path):
            os.remove(self._config.socket_path)

        self._stdout_chunks = []
        self._stderr_chunks = []
        self._reader_threads = []

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

        if self._config.log_path and self._config.mirror_output_to_log:
            self._log_fp = open(self._config.log_path, "ab")
        else:
            self._log_fp = None

        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except OSError as exc:
            self._close_log()
            raise FirecrackerProcessError(f"Failed to start Firecracker: {exc}") from exc

        self._start_reader(self._proc.stdout, self._stdout_chunks)
        self._start_reader(self._proc.stderr, self._stderr_chunks)

    def wait(self, timeout: float | None = None) -> int:
        if not self._proc:
            raise FirecrackerProcessError("Firecracker process is not started")
        if timeout is not None:
            timeout = float(timeout)
        try:
            exit_code = self._proc.wait(timeout=timeout)
            self._join_readers()
            self._close_log()
            return exit_code
        except subprocess.TimeoutExpired as exc:
            raise FirecrackerTimeoutError("Timed out waiting for Firecracker process") from exc

    def stop(self, timeout: float = 5.0) -> None:
        if not self._proc:
            return
        timeout = float(timeout)
        if self._proc.poll() is not None:
            self._join_readers()
            self._close_log()
            return

        self._proc.terminate()
        try:
            self._proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            self._proc.kill()
            self._proc.wait()
        finally:
            self._join_readers()
            self._close_log()

    def _start_reader(self, stream, chunks: list[bytes]) -> None:
        if stream is None:
            return

        thread = threading.Thread(target=self._read_stream, args=(stream, chunks), daemon=True)
        thread.start()
        self._reader_threads.append(thread)

    def _read_stream(self, stream, chunks: list[bytes]) -> None:
        try:
            for chunk in iter(lambda: stream.read(65536), b""):
                chunks.append(chunk)
                if self._log_fp:
                    with self._log_lock:
                        self._log_fp.write(chunk)
                        self._log_fp.flush()
        finally:
            stream.close()

    def _join_readers(self) -> None:
        for thread in self._reader_threads:
            thread.join(timeout=1.0)

    def _close_log(self) -> None:
        if self._log_fp:
            self._log_fp.close()
            self._log_fp = None
