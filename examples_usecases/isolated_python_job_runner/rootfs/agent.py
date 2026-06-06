from __future__ import annotations

import json
import os
import shutil
import socket
import struct
import subprocess
import time
from pathlib import Path

PORT = 5000
LANGUAGE_SPECS = {
    "python": {
        "filename": "main.py",
        "command": ["/usr/bin/python3", "main.py"],
    },
    "py": {
        "filename": "main.py",
        "command": ["/usr/bin/python3", "main.py"],
    },
    "javascript": {
        "filename": "main.js",
        "command": ["/usr/bin/node", "main.js"],
    },
    "js": {
        "filename": "main.js",
        "command": ["/usr/bin/node", "main.js"],
    },
    "typescript": {
        "filename": "main.ts",
        "command": [
            "/bin/sh",
            "-c",
            "/usr/bin/tsc main.ts --target ES2022 --module commonjs --outDir dist --pretty false && /usr/bin/node dist/main.js",
        ],
    },
    "ts": {
        "filename": "main.ts",
        "command": [
            "/bin/sh",
            "-c",
            "/usr/bin/tsc main.ts --target ES2022 --module commonjs --outDir dist --pretty false && /usr/bin/node dist/main.js",
        ],
    },
    "go": {
        "filename": "main.go",
        "command": [
            "/bin/sh",
            "-c",
            "mkdir -p .cache/go .tmp && HOME=/workspace/code GOCACHE=/workspace/code/.cache/go GOTMPDIR=/workspace/code/.tmp /usr/bin/go run main.go",
        ],
    },
    "golang": {
        "filename": "main.go",
        "command": [
            "/bin/sh",
            "-c",
            "mkdir -p .cache/go .tmp && HOME=/workspace/code GOCACHE=/workspace/code/.cache/go GOTMPDIR=/workspace/code/.tmp /usr/bin/go run main.go",
        ],
    },
    "rust": {
        "filename": "main.rs",
        "command": [
            "/bin/sh",
            "-c",
            "mkdir -p .tmp && TMPDIR=/workspace/code/.tmp /usr/bin/rustc main.rs -o main-rust && ./main-rust",
        ],
    },
    "rs": {
        "filename": "main.rs",
        "command": [
            "/bin/sh",
            "-c",
            "mkdir -p .tmp && TMPDIR=/workspace/code/.tmp /usr/bin/rustc main.rs -o main-rust && ./main-rust",
        ],
    },
}


def console(message: str) -> None:
    try:
        with open("/dev/console", "a", encoding="utf-8") as fp:
            fp.write(message.rstrip() + "\n")
    except OSError:
        pass


def read_exact(conn: socket.socket, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = conn.recv(remaining)
        if not chunk:
            raise RuntimeError("client closed connection")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def read_frame(conn: socket.socket) -> dict[str, object]:
    header = read_exact(conn, 4)
    size = struct.unpack(">I", header)[0]
    body = read_exact(conn, size)
    payload = json.loads(body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("request payload must be a JSON object")
    return payload


def write_frame(conn: socket.socket, payload: dict[str, object]) -> None:
    body = json.dumps(payload).encode("utf-8")
    conn.sendall(struct.pack(">I", len(body)) + body)


def safe_write_files(workdir: Path, files: dict[str, str]) -> None:
    for name, content in files.items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"unsafe file path: {name}")
        target = workdir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def language_spec(language: object) -> dict[str, object]:
    key = str(language or "python").strip().lower()
    spec = LANGUAGE_SPECS.get(key)
    if spec is None:
        supported = ", ".join(("python", "js", "ts", "go", "rust"))
        raise ValueError(f"unsupported language: {language}. supported: {supported}")
    return spec


def run_code(request: dict[str, object]) -> dict[str, object]:
    spec = language_spec(request.get("language"))
    code = request.get("code")
    if not isinstance(code, str):
        raise ValueError("code must be a string")

    filename = str(spec["filename"])
    command = spec["command"]
    if not isinstance(command, list):
        raise ValueError("language command must be a list")

    workdir = Path("/workspace/code")
    shutil.rmtree(workdir, ignore_errors=True)
    request = {
        **request,
        "command": command,
        "files": {filename: code},
        "workdir": str(workdir),
    }
    return run_command(request)


def run_command(request: dict[str, object]) -> dict[str, object]:
    job_id = str(request.get("id", ""))
    command = request.get("command")
    files = request.get("files") or {}
    workdir = Path(str(request.get("workdir", "/workspace")))
    timeout_seconds = int(request.get("timeout_seconds", 30))
    if not isinstance(command, list) or not all(isinstance(part, str) for part in command):
        raise ValueError("command must be a list of strings")
    if not isinstance(files, dict) or not all(
        isinstance(name, str) and isinstance(content, str)
        for name, content in files.items()
    ):
        raise ValueError("files must be an object mapping paths to text")

    workdir.mkdir(parents=True, exist_ok=True)
    safe_write_files(workdir, files)

    started_at = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=str(workdir),
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
    )
    duration_ms = int((time.monotonic() - started_at) * 1000)
    return {
        "id": job_id,
        "type": "command_result",
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "duration_ms": duration_ms,
    }


def handle(request: dict[str, object]) -> dict[str, object]:
    request_type = request.get("type")
    if request_type == "healthcheck":
        return {"type": "ok"}
    if request_type == "run_code":
        return run_code(request)
    if request_type == "run_command":
        return run_command(request)
    return {"type": "error", "error": f"unknown request type: {request_type}"}


def serve() -> None:
    if not hasattr(socket, "AF_VSOCK"):
        console("AF_VSOCK is unavailable in this Python runtime")
        while True:
            time.sleep(60)

    server = socket.socket(socket.AF_VSOCK, socket.SOCK_STREAM)
    try:
        server.bind((socket.VMADDR_CID_ANY, PORT))
        server.listen()
    except OSError as exc:
        console(f"failed to bind/listen on vsock port {PORT}: {exc}")
        while True:
            time.sleep(60)

    console(f"agent listening on vsock port {PORT}")
    while True:
        conn, _ = server.accept()
        with conn:
            try:
                write_frame(conn, handle(read_frame(conn)))
            except Exception as exc:
                write_frame(conn, {"type": "error", "error": str(exc)})


if __name__ == "__main__":
    serve()
