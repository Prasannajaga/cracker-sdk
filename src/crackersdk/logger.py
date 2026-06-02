from __future__ import annotations

from .transport import UnixSocketHTTPClient


class _LoggerAPI:
    def __init__(self, client: UnixSocketHTTPClient):
        self._client = client

    def configure_logger(self, log_path: str, level: str = "Info") -> None:
        self._client.put(
            "/logger",
            {
                "log_path": log_path,
                "level": level,
                "show_level": True,
                "show_log_origin": True,
            },
        )
