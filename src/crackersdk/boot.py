from __future__ import annotations

from typing import Any

from .transport import UnixSocketHTTPClient


class BootAPI:
    def __init__(self, client: UnixSocketHTTPClient):
        self._client = client

    def get_machine_config(self) -> dict[str, Any] | None:
        return self._client.get("/machine-config")

    def machine(self, *, vcpu_count: int, mem_size_mib: int, smt: bool | None = None) -> None:
        payload: dict[str, Any] = {"vcpu_count": vcpu_count, "mem_size_mib": mem_size_mib}
        if smt is not None:
            payload["smt"] = smt
        self._client.put("/machine-config", payload)

    def boot_source(self, *, kernel_image_path: str, boot_args: str = "") -> None:
        self._client.put(
            "/boot-source",
            {"kernel_image_path": kernel_image_path, "boot_args": boot_args},
        )

    def drive(
        self, *, drive_id: str, path: str, is_root_device: bool = False, is_read_only: bool = False
    ) -> None:
        self._client.put(
            f"/drives/{drive_id}",
            {
                "drive_id": drive_id,
                "path_on_host": path,
                "is_root_device": is_root_device,
                "is_read_only": is_read_only,
            },
        )

    def patch_drive(self, *, drive_id: str, path: str | None = None) -> None:
        payload: dict[str, Any] = {}
        if path is not None:
            payload["path_on_host"] = path
        self._client.patch(f"/drives/{drive_id}", payload)

    def boot(self) -> None:
        self._client.put("/actions", {"action_type": "InstanceStart"})
