from __future__ import annotations

import socket
from pathlib import Path
from types import TracebackType

from .result import VsockMessageResult
from .transport import UnixSocketHTTPClient


class VsockAPI:
    def __init__(self, client: UnixSocketHTTPClient):
        self._client = client

    def put_vsock(self, *, guest_cid: int, uds_path: str) -> None:
        if not isinstance(guest_cid, int):
            raise ValueError("guest_cid must be an int")
        if guest_cid <= 2:
            raise ValueError("guest_cid must be > 2")
        if not uds_path or not uds_path.strip():
            raise ValueError("uds_path must be non-empty")

        socket_path = Path(uds_path).expanduser().resolve()
        socket_path.parent.mkdir(parents=True, exist_ok=True)
        if socket_path.exists():
            if socket_path.is_dir():
                raise IsADirectoryError(str(socket_path))
            socket_path.unlink()

        self._client.put(
            "/vsock",
            {
                "guest_cid": guest_cid,
                "uds_path": str(socket_path),
            },
        )


class VsockClient:
    def __init__(self, uds_path: str, timeout: float = 5.0):
        if not uds_path or not uds_path.strip():
            raise ValueError("uds_path must be non-empty")
        self.uds_path = str(Path(uds_path).expanduser().resolve())
        self.timeout = float(timeout)
        self._sock: socket.socket | None = None
        self._port: int | None = None

    def connect(self, *, port: int) -> None:
        if not isinstance(port, int):
            raise ValueError("port must be an int")
        if port <= 0 or port > 65535:
            raise ValueError("port must be between 1 and 65535")
        if self._sock is not None:
            raise RuntimeError("VsockClient is already connected")

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        try:
            sock.connect(self.uds_path)
            # Firecracker host-initiated vsock connections use a small text
            # preface on the configured UDS: CONNECT <guest_port>\n. Once
            # Firecracker replies with OK <host_side_port>\n, this socket is
            # bridged to the guest AF_VSOCK listener and raw payload bytes flow.
            sock.sendall(f"CONNECT {port}\n".encode("ascii"))
            ack = self._recv_handshake(sock)
            if not ack.startswith("OK "):
                raise RuntimeError(f"Firecracker vsock connect failed: {ack!r}")
        except socket.timeout as exc:
            sock.close()
            raise TimeoutError(f"Timed out connecting to vsock port {port}") from exc
        except OSError as exc:
            sock.close()
            raise RuntimeError(f"Vsock socket error: {exc}") from exc
        except Exception:
            sock.close()
            raise

        self._sock = sock
        self._port = port

    def send(self, data: bytes) -> None:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        sock = self._require_socket()
        try:
            sock.sendall(data)
        except socket.timeout as exc:
            raise TimeoutError("Timed out sending vsock data") from exc
        except OSError as exc:
            raise RuntimeError(f"Vsock socket error: {exc}") from exc

    def recv(self, max_bytes: int = 65536) -> bytes:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be > 0")
        sock = self._require_socket()
        try:
            return sock.recv(max_bytes)
        except socket.timeout as exc:
            raise TimeoutError("Timed out receiving vsock data") from exc
        except OSError as exc:
            raise RuntimeError(f"Vsock socket error: {exc}") from exc

    def request(
        self,
        *,
        port: int,
        data: bytes,
        max_bytes: int = 65536,
    ) -> VsockMessageResult:
        bytes_sent = 0
        response = b""
        try:
            self.connect(port=port)
            self.send(data)
            bytes_sent = len(data)
            response = self.recv(max_bytes=max_bytes)
            return VsockMessageResult(
                uds_path=self.uds_path,
                port=port,
                bytes_sent=bytes_sent,
                bytes_received=len(response),
                response=response,
                success=True,
                error=None,
            )
        except Exception as exc:
            return VsockMessageResult(
                uds_path=self.uds_path,
                port=port,
                bytes_sent=bytes_sent,
                bytes_received=len(response),
                response=response,
                success=False,
                error=str(exc),
            )
        finally:
            self.close()

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None
            self._port = None

    def __enter__(self) -> "VsockClient":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def _require_socket(self) -> socket.socket:
        if self._sock is None:
            raise RuntimeError("VsockClient is not connected")
        return self._sock

    def _recv_handshake(self, sock: socket.socket) -> str:
        chunks: list[bytes] = []
        while True:
            chunk = sock.recv(1)
            if not chunk:
                raise RuntimeError("Firecracker closed vsock connection during handshake")
            chunks.append(chunk)
            if chunk == b"\n":
                break
            if len(chunks) > 128:
                raise RuntimeError("Firecracker vsock handshake response is too long")
        return b"".join(chunks).decode("ascii", errors="replace").strip()
