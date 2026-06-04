from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .launcher import JailerLauncher
from .process import Launcher
from .result import VMRunResult
from .vm import crackerVM


JAILED_KERNEL_PATH = "/kernel/vmlinux"
JAILED_ROOTFS_PATH = "/drives/rootfs.ext4"
JAILED_LOG_PATH = "/logs/firecracker.log"
JAILED_SOCKET_PATH = "/run/firecracker.socket"
ASSET_FIRECRACKER_NAME = "firecracker"


def _resolve_existing_file(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(path)
    if not resolved.is_file():
        raise ValueError(f"Expected a file: {path}")
    return resolved


def _resolve_executable(path: str) -> Path:
    expanded = Path(path).expanduser()
    if expanded.parent == Path("."):
        executable = shutil.which(path)
        if executable is not None:
            return _resolve_existing_file(executable)
    return _resolve_existing_file(path)


def _sync_shared_asset(source: Path, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    needs_copy = not destination.exists()
    if not needs_copy:
        source_stat = source.stat()
        destination_stat = destination.stat()
        needs_copy = (
            source_stat.st_size != destination_stat.st_size
            or source_stat.st_mtime_ns != destination_stat.st_mtime_ns
        )

    if needs_copy:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        shutil.copy2(source, destination)
    return destination


def _set_owner(path: Path, uid: int, gid: int) -> None:
    os.chown(path, uid, gid)


@dataclass(frozen=True)
class JailerConfig:
    jailer_binary: str
    jail_id: str
    uid: int
    gid: int
    chroot_base_dir: str
    exec_file: str | None = None
    extra_args: tuple[str, ...] = ()
    cleanup_on_exit: bool = False

    def __post_init__(self) -> None:
        if not self.jailer_binary:
            raise ValueError("jailer_binary is required")
        _resolve_executable(self.jailer_binary)
        if not self.jail_id:
            raise ValueError("jail_id is required")
        if self.uid < 0:
            raise ValueError("uid must be >= 0")
        if self.gid < 0:
            raise ValueError("gid must be >= 0")
        if not self.chroot_base_dir:
            raise ValueError("chroot_base_dir is required")
        if self.exec_file is not None:
            if not self.exec_file:
                raise ValueError("exec_file must not be empty")
            _resolve_executable(self.exec_file)


@dataclass(frozen=True)
class JailerRunContext:
    jail_id: str
    root_dir: str
    host_kernel_path: str
    jailed_kernel_path: str
    host_rootfs_path: str
    jailed_rootfs_path: str
    host_firecracker_path: str
    jailed_firecracker_path: str
    host_socket_path: str
    jailed_socket_path: str
    host_log_path: str
    jailed_log_path: str


@dataclass(frozen=True)
class _VMExecutionState:
    kernel_path: str | None
    rootfs_path: str | None
    process_socket_path: str
    api_socket_path: str
    process_log_path: str | None
    host_log_path: str | None
    launcher: Launcher | None


class Jailer:
    def __init__(self, vm: crackerVM, config: JailerConfig):
        self.vm = vm
        self.config = config
        self._context: JailerRunContext | None = None

    def run(self, *, timeout: float | None = None) -> VMRunResult:
        context = self._prepare_jail()
        original_state = self._capture_vm_execution_state()
        launcher = JailerLauncher(
            jailer_binary=str(_resolve_executable(self.config.jailer_binary)),
            exec_file=str(self._shared_firecracker_path(context.root_dir)),
            jail_id=self.config.jail_id,
            uid=self.config.uid,
            gid=self.config.gid,
            chroot_base_dir=str(Path(self.config.chroot_base_dir).expanduser().resolve()),
            socket_path=context.jailed_socket_path,
            extra_args=self.config.extra_args,
        )

        try:
            self.vm.kernel_path = context.jailed_kernel_path
            self.vm.rootfs_path = context.jailed_rootfs_path
            self.vm._set_socket_paths(
                process_socket_path=context.jailed_socket_path,
                api_socket_path=context.host_socket_path,
            )
            self.vm._set_log_paths(
                process_log_path=context.jailed_log_path,
                host_log_path=context.host_log_path,
            )
            self.vm._set_launcher(launcher)

            result = self.vm.run() if timeout is None else self.vm.run(timeout=timeout)
            if result.error is not None or result.timed_out:
                self.vm.stop()
            return result
        except Exception:
            self.vm.stop()
            raise
        finally:
            self._restore_vm_execution_state(original_state)
            if self.config.cleanup_on_exit:
                self.cleanup()

    def cleanup(self) -> None:
        if self._context is None:
            return
        shutil.rmtree(Path(self._context.root_dir).parent, ignore_errors=True)
        self._context = None

    def __getattr__(self, name: str):
        return getattr(self.vm, name)

    def _shared_firecracker_path(self, root_dir: str) -> Path:
        return Path(root_dir).parent.parent / "assets" / ASSET_FIRECRACKER_NAME

    def _prepare_jail(self) -> JailerRunContext:
        if self.vm.kernel_path is None or self.vm.rootfs_path is None:
            raise ValueError(
                "Jailer.run() requires the wrapped CrackerVM to have kernel_path and rootfs_path configured."
            )

        source_firecracker = _resolve_executable(self.config.exec_file or self.vm.binary)
        source_kernel = _resolve_existing_file(self.vm.kernel_path)
        source_rootfs = _resolve_existing_file(self.vm.rootfs_path)

        root_dir = (
            Path(self.config.chroot_base_dir).expanduser().resolve()
            / "firecracker"
            / self.config.jail_id
            / "root"
        )
        jail_dir = root_dir.parent
        if jail_dir.exists():
            raise FileExistsError(f"Jail already exists: {jail_dir}")

        assets_dir = root_dir.parent.parent / "assets"
        _sync_shared_asset(source_firecracker, assets_dir / ASSET_FIRECRACKER_NAME)

        host_firecracker = root_dir / ASSET_FIRECRACKER_NAME
        host_kernel = root_dir / "kernel" / "vmlinux"
        host_rootfs = root_dir / "drives" / "rootfs.ext4"
        host_log = root_dir / "logs" / "firecracker.log"
        host_socket = root_dir / "run" / "firecracker.socket"

        for directory in (
            host_firecracker.parent,
            host_kernel.parent,
            host_rootfs.parent,
            host_log.parent,
            host_socket.parent,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        try:
            host_firecracker.unlink()
        except FileNotFoundError:
            pass
        shutil.copy2(source_kernel, host_kernel)
        shutil.copy2(source_rootfs, host_rootfs)
        host_log.write_text("", encoding="utf-8")
        for path in (
            host_rootfs.parent,
            host_rootfs,
            host_log.parent,
            host_log,
            host_socket.parent,
        ):
            _set_owner(path, self.config.uid, self.config.gid)
        try:
            host_socket.unlink()
        except FileNotFoundError:
            pass

        context = JailerRunContext(
            jail_id=self.config.jail_id,
            root_dir=str(root_dir),
            host_kernel_path=str(host_kernel),
            jailed_kernel_path=JAILED_KERNEL_PATH,
            host_rootfs_path=str(host_rootfs),
            jailed_rootfs_path=JAILED_ROOTFS_PATH,
            host_firecracker_path=str(host_firecracker),
            jailed_firecracker_path=f"/{ASSET_FIRECRACKER_NAME}",
            host_socket_path=str(host_socket),
            jailed_socket_path=JAILED_SOCKET_PATH,
            host_log_path=str(host_log),
            jailed_log_path=JAILED_LOG_PATH,
        )
        self._context = context
        return context

    def _capture_vm_execution_state(self) -> _VMExecutionState:
        return _VMExecutionState(
            kernel_path=self.vm.kernel_path,
            rootfs_path=self.vm.rootfs_path,
            process_socket_path=self.vm.process_socket_path,
            api_socket_path=self.vm.api_socket_path,
            process_log_path=self.vm.process_log_path,
            host_log_path=self.vm.host_log_path,
            launcher=self.vm._proc.launcher,
        )

    def _restore_vm_execution_state(self, state: _VMExecutionState) -> None:
        self.vm.kernel_path = state.kernel_path
        self.vm.rootfs_path = state.rootfs_path
        self.vm._set_socket_paths(
            process_socket_path=state.process_socket_path,
            api_socket_path=state.api_socket_path,
        )
        self.vm._set_log_paths(
            process_log_path=state.process_log_path,
            host_log_path=state.host_log_path,
        )
        self.vm._set_launcher(state.launcher)
