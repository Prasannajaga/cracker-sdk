from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .launcher import JailerLauncher
from .lifecycle import VMState, VMStatus
from .process import Launcher
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
from .vm import crackerVM
from .constant import (
    ASSET_FIRECRACKER_NAME,
    JAILED_KERNEL_PATH,
    JAILED_LOG_PATH,    
    JAILED_ROOTFS_PATH,
    JAILED_SOCKET_PATH,
    JAILED_VSOCK_PATH,
)


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
        self._original_state: _VMExecutionState | None = None
        self._host_vsock_path: str | None = None

    def __enter__(self) -> Jailer:
        self._ensure_prepared()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        self.stop()
        if self.config.cleanup_on_exit:
            self.cleanup()

    @property
    def state(self) -> VMState:
        return self.vm.state

    @property
    def kernel_path(self) -> str:
        return self._ensure_prepared().jailed_kernel_path

    @property
    def rootfs_path(self) -> str:
        return self._ensure_prepared().jailed_rootfs_path

    @property
    def log_path(self) -> str:
        return self._ensure_prepared().jailed_log_path

    @property
    def socket_path(self) -> str:
        return self._ensure_prepared().jailed_socket_path

    @property
    def host_log_path(self) -> str:
        return self._ensure_prepared().host_log_path

    @property
    def host_socket_path(self) -> str:
        return self._ensure_prepared().host_socket_path

    @property
    def host_vsock_path(self) -> str | None:
        return self._host_vsock_path

    def start(self) -> None:
        self._ensure_prepared()
        return self.vm.start()

    def wait_until_ready(
        self,
        timeout: float = 10.0,
        poll_interval: float = 0.1,
    ) -> None:
        return self.vm.wait_until_ready(timeout=timeout, poll_interval=poll_interval)

    def wait(self, timeout: float | None = None) -> int:
        return self.vm.wait(timeout=timeout)

    def stop(self, timeout: float = 5.0) -> None:
        return self.vm.stop(timeout=timeout)

    def status(self) -> VMStatus:
        return self.vm.status()

    def is_running(self) -> bool:
        return self.vm.is_running()

    def is_paused(self) -> bool:
        return self.vm.is_paused()

    def is_stopped(self) -> bool:
        return self.vm.is_stopped()

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
        self._ensure_prepared()
        if vsock is not None:
            vsock = dict(vsock)
            uds_path = vsock.get("uds_path")
            if uds_path is None:
                vsock["uds_path"] = self._prepare_vsock_path(None)
            elif isinstance(uds_path, str):
                vsock["uds_path"] = self._prepare_vsock_path(uds_path)
        try:
            return self.vm.run(
                vcpu_count=vcpu_count,
                mem_size_mib=mem_size_mib,
                timeout=timeout,
                entropy=entropy,
                network_interfaces=network_interfaces,
                vsock=vsock,
            )
        finally:
            if self.config.cleanup_on_exit:
                self.cleanup()

    def machine(
        self,
        *,
        vcpu_count: int,
        mem_size_mib: int,
        smt: bool | None = None,
    ) -> None:
        return self.vm.machine(vcpu_count=vcpu_count, mem_size_mib=mem_size_mib, smt=smt)

    def machine_config(self) -> dict[str, Any] | None:
        return self.vm.machine_config()

    def boot_source(self, *, kernel_image_path: str, boot_args: str = "") -> None:
        return self.vm.boot_source(kernel_image_path=kernel_image_path, boot_args=boot_args)

    def root_drive(self, *, path: str, is_read_only: bool = False) -> None:
        return self.vm.root_drive(path=path, is_read_only=is_read_only)

    def drive(self, *, drive_id: str, path: str, is_read_only: bool = False) -> None:
        return self.vm.drive(drive_id=drive_id, path=path, is_read_only=is_read_only)

    def patch_drive(self, *, drive_id: str, path: str | None = None) -> None:
        return self.vm.patch_drive(drive_id=drive_id, path=path)

    def boot(self) -> None:
        return self.vm.boot()

    def pause(self, *, strict: bool = False) -> VMStatus:
        return self.vm.pause(strict=strict)

    def resume(self, *, strict: bool = False) -> VMStatus:
        return self.vm.resume(strict=strict)

    def send_ctrl_alt_del(self) -> None:
        return self.vm.send_ctrl_alt_del()

    def network(
        self,
        *,
        iface_id: str,
        host_dev_name: str,
        guest_mac: str,
        strict: bool = True,
    ) -> NetworkInterfaceResult:
        return self.vm.network(
            iface_id=iface_id,
            host_dev_name=host_dev_name,
            guest_mac=guest_mac,
            strict=strict,
        )

    def network_interfaces(self) -> dict[str, NetworkInterfaceResult]:
        return self.vm.network_interfaces()

    def entropy(self, *, strict: bool = False) -> EntropyResult:
        return self.vm.entropy(strict=strict)

    def has_entropy(self) -> bool:
        return self.vm.has_entropy()

    def vsock(
        self,
        *,
        guest_cid: int,
        uds_path: str | None = None,
        strict: bool = True,
    ) -> VsockResult:
        uds_path = self._prepare_vsock_path(uds_path)
        return self.vm.vsock(guest_cid=guest_cid, uds_path=uds_path, strict=strict)

    def vsock_config(self) -> VsockResult | None:
        return self.vm.vsock_config()

    def balloon(
        self,
        *,
        amount_mib: int,
        deflate_on_oom: bool,
        stats_polling_interval_s: int = 0,
        strict: bool = True,
    ) -> BalloonResult:
        return self.vm.balloon(
            amount_mib=amount_mib,
            deflate_on_oom=deflate_on_oom,
            stats_polling_interval_s=stats_polling_interval_s,
            strict=strict,
        )

    def balloon_config(self) -> BalloonResult | None:
        return self.vm.balloon_config()

    def update_balloon(
        self,
        *,
        amount_mib: int,
        stats_polling_interval_s: int | None = None,
    ) -> BalloonResult:
        return self.vm.update_balloon(
            amount_mib=amount_mib,
            stats_polling_interval_s=stats_polling_interval_s,
        )

    def balloon_stats(self) -> BalloonStatsResult:
        return self.vm.balloon_stats()

    def snapshot(
        self,
        snapshot_path: str,
        mem_file_path: str,
        *,
        pause: bool = True,
        overwrite: bool = False,
    ) -> SnapshotResult:
        return self.vm.snapshot(
            snapshot_path=snapshot_path,
            mem_file_path=mem_file_path,
            pause=pause,
            overwrite=overwrite,
        )

    def create_snapshot(
        self,
        snapshot_path: str,
        mem_file_path: str,
        *,
        overwrite: bool = False,
    ) -> SnapshotResult:
        return self.vm.create_snapshot(
            snapshot_path=snapshot_path,
            mem_file_path=mem_file_path,
            overwrite=overwrite,
        )

    def restore(
        self,
        snapshot_path: str,
        mem_file_path: str,
        *,
        resume: bool = True,
    ) -> RestoreResult:
        return self.vm.restore(
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
        return self.vm.load_snapshot(
            snapshot_path=snapshot_path,
            mem_file_path=mem_file_path,
            resume=resume,
        )

    def configure_logger(self, log_path: str, level: str = "Info") -> None:
        return self.vm.configure_logger(log_path=log_path, level=level)

    def cleanup(self) -> None:
        if self._context is None:
            return
        shutil.rmtree(Path(self._context.root_dir).parent, ignore_errors=True)
        if self._original_state is not None:
            self._restore_vm_execution_state(self._original_state)
            self._original_state = None
        self._context = None
        self._host_vsock_path = None

    def __getattr__(self, name: str):
        return getattr(self.vm, name)

    def _ensure_prepared(self) -> JailerRunContext:
        if self._context is None:
            context = self._prepare_jail()
            self._original_state = self._capture_vm_execution_state()
            self._apply_jail_context(context)
        return self._context

    def _apply_jail_context(self, context: JailerRunContext) -> None:
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

    def _prepare_vsock_path(self, uds_path: str | None) -> str:
        context = self._ensure_prepared()
        jailed_path = uds_path or JAILED_VSOCK_PATH
        if Path(jailed_path).is_absolute():
            host_vsock = Path(context.root_dir) / jailed_path.removeprefix("/")
            host_vsock.parent.mkdir(parents=True, exist_ok=True)
            _set_owner(host_vsock.parent, self.config.uid, self.config.gid)
            try:
                host_vsock.unlink()
            except FileNotFoundError:
                pass
            self._host_vsock_path = str(host_vsock)
        return jailed_path

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
