from __future__ import annotations

import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from .boot import BootAPI
from .errors import (
    FirecrackerError,
    FirecrackerProcessError,
    FirecrackerStateError,
    FirecrackerTimeoutError,
)
from .lifecycle import VMState, VMStatus
from .logger import _LoggerAPI
from .networking import NetworkingAPI
from .process import ProcessConfig, ProcessManager
from .result import (
    EntropyResult,
    NetworkInterfaceResult,
    RestoreResult,
    SnapshotResult,
    VMRunResult,
)
from .runtime import RuntimeAPI
from .snapshot import SnapshotAPI
from .transport import UnixSocketHTTPClient


DEFAULT_BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"


class crackerVM:
    def __init__(
        self,
        *,
        binary: str,
        socket_path: str,
        log_path: str | None = None,
        workdir: str | None = None,
        namespace_name: str | None = None,
        kernel_path: str | None = None,
        rootfs_path: str | None = None,
        boot_args: str = DEFAULT_BOOT_ARGS,
        api_timeout: float = 2.0,
    ):
        self.binary = binary
        self.socket_path = socket_path
        self.workdir = workdir
        if workdir is not None:
            os.makedirs(workdir, exist_ok=True)
            if log_path is None:
                log_path = os.path.join(workdir, "firecracker.log")
        self.log_path = log_path
        self.namespace_name = namespace_name
        self.kernel_path = kernel_path
        self.rootfs_path = rootfs_path
        self.boot_args = boot_args

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
        self._logger = _LoggerAPI(self._client)
        self._state = VMState.EXITED
        self._last_error: str | None = None
        self._network_interfaces: dict[str, NetworkInterfaceResult] = {}
        self._entropy_enabled = False

    def __enter__(self) -> crackerVM:
        self.start()
        self.wait_until_ready()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()

    @property
    def state(self) -> VMState:
        self._sync_state_from_process()
        return self._state

    def start(self) -> None:
        try:
            self._proc.start()
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def wait_until_ready(self, timeout: float = 10.0, poll_interval: float = 0.1) -> None:
        timeout = float(timeout)
        deadline = time.monotonic() + timeout
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if self._proc.process and self._proc.process.poll() is not None:
                error = FirecrackerProcessError("Firecracker exited before becoming ready")
                self._state = VMState.EXITED
                self._last_error = str(error)
                raise error

            if os.path.exists(self.socket_path):
                try:
                    self._boot.get_machine_config()
                    self._last_error = None
                    return
                except FirecrackerError as exc:
                    last_error = exc
            time.sleep(poll_interval)

        detail = f": {last_error}" if last_error else ""
        error = FirecrackerTimeoutError(f"Timed out waiting for Firecracker API readiness{detail}")
        self._last_error = str(error)
        raise error

    def wait(self, timeout: float | None = None) -> int:
        try:
            exit_code = self._proc.wait(timeout=timeout)
            self._state = VMState.EXITED
            self._last_error = None
            return exit_code
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def stop(self, timeout: float = 5.0) -> None:
        try:
            self._proc.stop(timeout=timeout)
            self._state = VMState.EXITED
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def is_running(self) -> bool:
        self._sync_state_from_process()
        return self._state == VMState.RUNNING

    def is_paused(self) -> bool:
        self._sync_state_from_process()
        return self._state == VMState.PAUSED

    def is_stopped(self) -> bool:
        self._sync_state_from_process()
        return self._state == VMState.EXITED

    def status(self) -> VMStatus:
        process_running, pid, exit_code = self._process_state()
        api_available = False

        if process_running:
            try:
                self._boot.get_machine_config()
                api_available = True
            except Exception as exc:
                self._last_error = str(exc)
        else:
            self._state = VMState.EXITED

        return VMStatus(
            state=self._state,
            process_running=process_running,
            api_available=api_available,
            pid=pid,
            exit_code=exit_code,
            last_error=self._last_error,
        )

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
        try:
            self._boot.boot()
            self._state = VMState.RUNNING
            self._last_error = None
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def configure_logger(self, log_path: str, level: str = "Info") -> None:
        self._logger.configure_logger(log_path=log_path, level=level)

    def run(
        self,
        *,
        vcpu_count: int = 1,
        mem_size_mib: int = 256,
        timeout: float = 30.0,
        entropy: bool = False,
        network_interfaces: list[dict[str, str]] | None = None,
    ) -> VMRunResult:
        error: str | None = None
        exit_code: int | None = None
        timed_out = False
        timeout = float(timeout)

        try:
            self._ensure_log_path()
            self._prepare_log_file()
            self._proc.set_log_path(self.log_path)
            self._proc.set_mirror_output_to_log(False)

            if self.kernel_path is None:
                raise FirecrackerError("kernel_path is required")
            if self.rootfs_path is None:
                raise FirecrackerError("rootfs_path is required")

            self.start()
            self.wait_until_ready(timeout=30)
            self.configure_logger(log_path=str(Path(self.log_path).resolve()))
            self.machine(vcpu_count=vcpu_count, mem_size_mib=mem_size_mib)
            self.boot_source(kernel_image_path=self.kernel_path, boot_args=self.boot_args)
            self.root_drive(path=self.rootfs_path)
            if entropy:
                entropy_result = self.entropy()
                if not entropy_result.success:
                    raise FirecrackerError(entropy_result.error or "Failed to configure entropy")
            if network_interfaces is not None:
                for interface in network_interfaces:
                    network_result = self.network(**interface)
                    if not network_result.success:
                        raise FirecrackerError(
                            network_result.error or "Failed to configure network interface"
                        )
            self.boot()
            exit_code = self.wait(timeout=timeout)
        except FirecrackerTimeoutError as exc:
            timed_out = True
            error = str(exc)
            self.stop()
        except Exception as exc:
            error = str(exc)
            self.stop()

        if error is not None:
            self._last_error = error

        return self._result(exit_code=exit_code, timed_out=timed_out, error=error)

    def pause(self, *, strict: bool = False) -> VMStatus:
        status = self.status()
        if status.state == VMState.PAUSED and not strict:
            return status
        if status.state != VMState.RUNNING:
            if strict:
                self._raise_state_error("pause", status)
            return status

        try:
            self._runtime.pause()
            self._state = VMState.PAUSED
            self._last_error = None
            return self.status()
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def resume(self, *, strict: bool = False) -> VMStatus:
        status = self.status()
        if status.state == VMState.RUNNING and not strict:
            return status
        if status.state != VMState.PAUSED:
            if strict:
                self._raise_state_error("resume", status)
            return status

        try:
            self._runtime.resume()
            self._state = VMState.RUNNING
            self._last_error = None
            return self.status()
        except Exception as exc:
            self._last_error = str(exc)
            raise

    def send_ctrl_alt_del(self) -> None:
        self._runtime.send_ctrl_alt_del()

    def network_interfaces(self) -> dict[str, NetworkInterfaceResult]:
        return dict(self._network_interfaces)

    def has_entropy(self) -> bool:
        return self._entropy_enabled

    def network(
        self,
        *,
        iface_id: str,
        host_dev_name: str,
        guest_mac: str,
        strict: bool = True,
    ) -> NetworkInterfaceResult:
        status = self.status()
        if status.state in (VMState.RUNNING, VMState.PAUSED):
            self._raise_state_error("configure network", status)

        existing = self._network_interfaces.get(iface_id)
        if existing is not None:
            if strict:
                error = FirecrackerStateError(
                    f"Network interface {iface_id!r} is already configured"
                )
                self._last_error = str(error)
                raise error
            return existing

        try:
            self._net.network(
                iface_id=iface_id,
                host_dev_name=host_dev_name,
                guest_mac=guest_mac,
            )
            result = NetworkInterfaceResult(
                iface_id=iface_id,
                host_dev_name=host_dev_name,
                guest_mac=guest_mac,
                success=True,
                error=None,
            )
            self._network_interfaces[iface_id] = result
            self._last_error = None
            return result
        except ValueError:
            raise
        except Exception as exc:
            self._last_error = str(exc)
            return NetworkInterfaceResult(
                iface_id=iface_id,
                host_dev_name=host_dev_name,
                guest_mac=guest_mac,
                success=False,
                error=str(exc),
            )

    def entropy(self, *, strict: bool = False) -> EntropyResult:
        status = self.status()
        if status.state in (VMState.RUNNING, VMState.PAUSED):
            self._raise_state_error("configure entropy", status)

        if self._entropy_enabled:
            if strict:
                error = FirecrackerStateError("Entropy is already configured")
                self._last_error = str(error)
                raise error
            return EntropyResult(enabled=True, success=True, error=None)

        try:
            self._net.entropy()
            self._entropy_enabled = True
            self._last_error = None
            return EntropyResult(enabled=True, success=True, error=None)
        except Exception as exc:
            self._last_error = str(exc)
            return EntropyResult(enabled=False, success=False, error=str(exc))

    def snapshot(
        self,
        snapshot_path: str,
        mem_file_path: str,
        *,
        pause: bool = True,
        overwrite: bool = False,
    ) -> SnapshotResult:
        status = self.status()
        if status.state == VMState.RUNNING and pause:
            self.pause(strict=True)
        elif status.state == VMState.EXITED:
            self._raise_state_error("snapshot", status)

        return self.create_snapshot(
            snapshot_path=snapshot_path,
            mem_file_path=mem_file_path,
            overwrite=overwrite,
        )

    def create_snapshot(
        self,
        snapshot_path: str,
        mem_file_path: str,
        *,
        overwrite: bool = False,
    ) -> SnapshotResult:
        status = self.status()
        if status.state != VMState.PAUSED:
            self._raise_state_error("create snapshot", status)

        snapshot_file = Path(snapshot_path).expanduser().resolve()
        mem_file = Path(mem_file_path).expanduser().resolve()
        manifest_file = snapshot_file.with_name(f"{snapshot_file.stem}.manifest.json")

        snapshot_file.parent.mkdir(parents=True, exist_ok=True)
        mem_file.parent.mkdir(parents=True, exist_ok=True)
        manifest_file.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_not_exists(snapshot_file, overwrite)
        self._ensure_not_exists(mem_file, overwrite)
        self._ensure_not_exists(manifest_file, overwrite)

        try:
            self._snap.create_snapshot(
                snapshot_path=str(snapshot_file),
                mem_file_path=str(mem_file),
            )
            manifest = {
                "snapshot_path": str(snapshot_file),
                "mem_file_path": str(mem_file),
                "state": self.state.value,
                "snapshot_type": "Full",
                "entropy_enabled": self._entropy_enabled,
                "network_interfaces": [
                    {
                        "iface_id": interface.iface_id,
                        "host_dev_name": interface.host_dev_name,
                        "guest_mac": interface.guest_mac,
                    }
                    for interface in self._network_interfaces.values()
                ],
            }
            self._write_json_atomic(manifest_file, manifest)
            self._last_error = None
            return SnapshotResult(
                snapshot_path=str(snapshot_file),
                mem_file_path=str(mem_file),
                manifest_path=str(manifest_file),
                state=self.state,
                success=True,
                error=None,
            )
        except Exception as exc:
            self._last_error = str(exc)
            return SnapshotResult(
                snapshot_path=str(snapshot_file),
                mem_file_path=str(mem_file),
                manifest_path=None,
                state=self.status().state,
                success=False,
                error=str(exc),
            )

    def restore(
        self,
        snapshot_path: str,
        mem_file_path: str,
        *,
        resume: bool = True,
    ) -> RestoreResult:
        return self.load_snapshot(
            snapshot_path=snapshot_path,
            mem_file_path=mem_file_path,
            resume=resume,
        )

    def load_snapshot(
        self,
        snapshot_path: str,
        mem_file_path: str,
        *,
        resume: bool = True,
    ) -> RestoreResult:
        status = self.status()
        if status.process_running:
            error = FirecrackerStateError("Cannot load snapshot while Firecracker process is running")
            self._last_error = str(error)
            raise error
        if status.state != VMState.EXITED:
            self._raise_state_error("load snapshot", status)

        snapshot_file = Path(snapshot_path).expanduser().resolve()
        mem_file = Path(mem_file_path).expanduser().resolve()
        if not snapshot_file.is_file():
            raise FileNotFoundError(str(snapshot_file))
        if not mem_file.is_file():
            raise FileNotFoundError(str(mem_file))

        try:
            self.start()
            self.wait_until_ready()
            self._snap.load_snapshot(
                snapshot_path=str(snapshot_file),
                mem_file_path=str(mem_file),
                resume=resume,
            )
            self._load_snapshot_metadata(snapshot_file)
            self._state = VMState.RUNNING if resume else VMState.PAUSED
            self._last_error = None
            return RestoreResult(
                snapshot_path=str(snapshot_file),
                mem_file_path=str(mem_file),
                resumed=resume,
                state=self.state,
                success=True,
                error=None,
            )
        except Exception as exc:
            error = str(exc)
            try:
                self.stop()
            finally:
                self._last_error = error
            return RestoreResult(
                snapshot_path=str(snapshot_file),
                mem_file_path=str(mem_file),
                resumed=False,
                state=self.status().state,
                success=False,
                error=error,
            )

    def _read_text_file(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")

    def _load_snapshot_metadata(self, snapshot_file: Path) -> None:
        manifest_file = snapshot_file.with_name(f"{snapshot_file.stem}.manifest.json")
        if not manifest_file.is_file():
            return

        try:
            manifest = json.loads(self._read_text_file(manifest_file))
        except (OSError, json.JSONDecodeError):
            return
        self._entropy_enabled = bool(manifest.get("entropy_enabled", False))
        self._network_interfaces = {}
        # Restoring TAP/network host state is caller responsibility.
        for interface in manifest.get("network_interfaces", []):
            try:
                result = NetworkInterfaceResult(
                    iface_id=str(interface["iface_id"]),
                    host_dev_name=str(interface["host_dev_name"]),
                    guest_mac=str(interface["guest_mac"]),
                    success=True,
                    error=None,
                )
            except KeyError:
                continue
            self._network_interfaces[result.iface_id] = result

    def _write_json_atomic(self, path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as fp:
                temp_path = Path(fp.name)
                json.dump(payload, fp, indent=2, sort_keys=True)
                fp.write("\n")
            temp_path.replace(path)
        except Exception:
            if temp_path is not None:
                try:
                    temp_path.unlink()
                except OSError:
                    pass
            raise

    def _ensure_not_exists(self, path: Path, overwrite: bool) -> None:
        if not path.exists():
            return
        if not overwrite:
            raise FileExistsError(str(path))
        if path.is_dir():
            raise IsADirectoryError(str(path))
        path.unlink()

    def _ensure_log_path(self) -> None:
        if self.log_path is not None:
            return

        if self.workdir is None:
            self.workdir = tempfile.mkdtemp(prefix="cracker-sdk-")
        os.makedirs(self.workdir, exist_ok=True)
        self.log_path = os.path.join(self.workdir, "firecracker.log")

    def _prepare_log_file(self) -> None:
        if self.log_path is None:
            return

        log_path = Path(self.log_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text("", encoding="utf-8")

    def _process_state(self) -> tuple[bool, int | None, int | None]:
        process = self._proc.process
        if process is None:
            return False, None, None

        exit_code = process.poll()
        if exit_code is None:
            return True, process.pid, None

        self._state = VMState.EXITED
        return False, process.pid, exit_code

    def _sync_state_from_process(self) -> None:
        self._process_state()

    def _raise_state_error(self, action: str, status: VMStatus) -> None:
        error = FirecrackerStateError(
            f"Cannot {action} VM while state is {status.state.value}"
        )
        self._last_error = str(error)
        raise error

    def _result(self, *, exit_code: int | None, timed_out: bool, error: str | None) -> VMRunResult:
        stdout, stdout_firecracker_log = self._split_process_output(self._proc.stdout)
        stderr, stderr_firecracker_log = self._split_process_output(self._proc.stderr)
        firecracker_log = (
            stdout_firecracker_log + stderr_firecracker_log + self._read_firecracker_log()
        )

        return VMRunResult(
            exit_code=exit_code,
            timed_out=timed_out,
            firecracker_log=firecracker_log,
            stdout=stdout,
            stderr=stderr,
            error=error,
        )

    def _read_firecracker_log(self) -> str:
        if self.log_path is None:
            return ""
        try:
            return self._read_text_file(Path(self.log_path))
        except OSError:
            return ""

    def _split_process_output(self, output: str) -> tuple[str, str]:
        user_output: list[str] = []
        firecracker_log: list[str] = []
        for line in output.splitlines(keepends=True):
            if self._looks_like_firecracker_log(line):
                firecracker_log.append(line)
            else:
                user_output.append(line)
        return "".join(user_output), "".join(firecracker_log)

    def _looks_like_firecracker_log(self, line: str) -> bool:
        return (
            len(line) > 30
            and line[4:5] == "-"
            and line[7:8] == "-"
            and "T" in line[:32]
            and "[anonymous-instance:" in line
        )
