from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from typing import Any

from .errors import FirecrackerAPIError


@dataclass
class UnixSocketHTTPClient:
    socket_path: str
    timeout: float = 2.0

    def get(self, path: str) -> dict[str, Any] | None:
        return self._request("GET", path)

    def put(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self._request("PUT", path, payload)

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self._request("PATCH", path, payload)

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any] | None:
        body = b""
        headers = ["Host: localhost", "Connection: close"]
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers.extend(
                ["Content-Type: application/json", f"Content-Length: {len(body)}"]
            )
        request = (
            f"{method} {path} HTTP/1.1\r\n" + "\r\n".join(headers) + "\r\n\r\n"
        ).encode("utf-8") + body

        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout)
            try:
                sock.connect(self.socket_path)
                sock.sendall(request)
                raw = b""
                header_end = -1
                expected_total: int | None = None
                while True:
                    chunk = sock.recv(65536)
                    if not chunk:
                        break
                    raw += chunk
                    if header_end == -1 and b"\r\n\r\n" in raw:
                        header_end = raw.find(b"\r\n\r\n") + 4
                        header_blob = raw[: header_end - 4]
                        content_length = 0
                        for line in header_blob.split(b"\r\n")[1:]:
                            if line.lower().startswith(b"content-length:"):
                                try:
                                    content_length = int(line.split(b":", 1)[1].strip())
                                except ValueError:
                                    content_length = 0
                                break
                        expected_total = header_end + content_length

                    if expected_total is not None and len(raw) >= expected_total:
                        break
            except OSError as exc:
                raise FirecrackerAPIError(f"Socket request failed: {exc}") from exc

        try:
            header_blob, body_blob = raw.split(b"\r\n\r\n", 1)
        except ValueError as exc:
            raise FirecrackerAPIError("Malformed HTTP response from Firecracker") from exc

        status_line = header_blob.split(b"\r\n", 1)[0].decode("utf-8", errors="replace")
        parts = status_line.split()
        code = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        text = body_blob.decode("utf-8", errors="replace").strip()
        parsed = json.loads(text) if text else None

        if code >= 400:
            raise FirecrackerAPIError(f"HTTP {code}: {text or 'request failed'}")
        return parsed
