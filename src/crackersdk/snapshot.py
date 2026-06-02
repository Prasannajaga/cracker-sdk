from pathlib import Path

from .transport import UnixSocketHTTPClient


class SnapshotAPI:
    def __init__(self, client: UnixSocketHTTPClient):
        self._client = client

    def create_snapshot(self, *, snapshot_path: str, mem_file_path: str) -> None:
        snapshot_path = str(Path(snapshot_path).expanduser().resolve())
        mem_file_path = str(Path(mem_file_path).expanduser().resolve())
        self._client.put(
            "/snapshot/create",
            {
                "snapshot_type": "Full",
                "snapshot_path": snapshot_path,
                "mem_file_path": mem_file_path,
            },
        )

    def load_snapshot(self, *, snapshot_path: str, mem_file_path: str, resume: bool = False) -> None:
        snapshot_path = str(Path(snapshot_path).expanduser().resolve())
        mem_file_path = str(Path(mem_file_path).expanduser().resolve())
        self._client.put(
            "/snapshot/load",
            {
                "snapshot_path": snapshot_path,
                "mem_backend": {"backend_type": "File", "backend_path": mem_file_path},
                "resume_vm": resume,
            },
        )
