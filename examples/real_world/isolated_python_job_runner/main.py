"""Host-side isolated Python job runner over Firecracker vsock.

This composes existing cracker-sdk primitives into a realistic job-runner flow.
The SDK provides `CrackerVM` and `VsockClient`; the length-prefixed JSON tunnel
helper is deliberately local to this example.
"""

from __future__ import annotations

import ast
import curses
import json
import re
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from crackersdk import CrackerVM, VsockClient


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY =  "/home/prasanna/.local/bin/firecracker"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(EXAMPLE_DIR / "rootfs/rootfs.ext4")
SOCKET_PATH =  "/tmp/cracker-sdk-job-runner.sock"
LOG_PATH =  "/tmp/cracker-sdk-job-runner.log"
VSOCK_PATH =  "/tmp/cracker-sdk-job-runner.vsock"
WORKDIR = "/tmp/cracker-sdk-job-runner"
AGENT_PORT = 5000
AUTO_LANGUAGE = "auto"
DEFAULT_LANGUAGE = AUTO_LANGUAGE
SUPPORTED_LANGUAGES = ("python", "js", "ts", "go", "rust")
LANGUAGE_CHOICES = (AUTO_LANGUAGE, *SUPPORTED_LANGUAGES)
CTRL_ENTER_SEQUENCES = {
    "\x1b[13;5u",
    "\x1b[13;5~",
    "\x1b[27;5;13~",
}


class VsockTunnel:
    def __init__(self, *, uds_path: str, port: int = AGENT_PORT, timeout: float = 30.0):
        self.uds_path = uds_path
        self.port = port
        self.timeout = timeout

    def request(self, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload).encode("utf-8")
        frame = struct.pack(">I", len(body)) + body
        with VsockClient(self.uds_path, timeout=self.timeout) as client:
            client.connect(port=self.port)
            client.send(frame)
            header = self._read_exact(client, 4)
            size = struct.unpack(">I", header)[0]
            response_body = self._read_exact(client, size)

        response = json.loads(response_body.decode("utf-8"))
        if not isinstance(response, dict):
            raise RuntimeError("Agent returned a non-object response")
        return response

    def healthcheck(self) -> bool:
        response = self.request({"type": "healthcheck"})
        return response.get("type") == "ok"

    def run(
        self,
        code: str,
        *,
        language: str = DEFAULT_LANGUAGE,
        timeout_seconds: int = 30,
    ) -> dict[str, object]:
        language = parse_language(language)
        language = detect_language(code) if language == AUTO_LANGUAGE else language
        if language == "python":
            ast.parse(code, filename="main.py", mode="exec")

        return self.request(
            {
                "type": "run_code",
                "id": f"example-{language}-job",
                "language": language,
                "code": code,
                "timeout_seconds": timeout_seconds,
            }
        )

    def _read_exact(self, client: VsockClient, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = client.recv(remaining)
            if not chunk:
                raise RuntimeError("Agent closed the connection")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

class PythonJobRunnerTUI:
    def __init__(self, tunnel: VsockTunnel):
        self.tunnel = tunnel
        self.language = DEFAULT_LANGUAGE
        self.editor_lines = [""]
        self.cy = 0
        self.cx = 0
        self.history: list[tuple[str, str]] = [
            ("system", "Connected to guest vsock agent."),
            ("system", "Use :lang auto|python|js|ts|go|rust. Press Ctrl+Enter (or Ctrl+G / F2) to run, Ctrl+Q to quit."),
            ("system", "")
        ]
        self.history_scroll = 0

    def run(self) -> None:
        curses.wrapper(self._main)

    def _run_code(self) -> None:
        code = "\n".join(self.editor_lines)
        stripped = code.strip()
        if stripped.startswith(":lang"):
            parts = stripped.split()
            if len(parts) != 2:
                self.history.append(("stderr", "usage: :lang auto|python|js|ts|go|rust"))
            else:
                try:
                    self.language = parse_language(parts[1])
                    self.history.append(("system", f"language: {self.language}"))
                except ValueError as exc:
                    self.history.append(("stderr", str(exc)))
            self.editor_lines = [""]
            self.cy = 0
            self.cx = 0
            return

        active_language = detect_language(code) if self.language == AUTO_LANGUAGE else self.language

        # Log the code to history
        for i, line in enumerate(self.editor_lines):
            prompt = f"{active_language}> " if i == 0 else ".... "
            self.history.append(("editor", prompt + line))

        if not code.strip():
            self.editor_lines = [""]
            self.cy = 0
            self.cx = 0
            return

        start_time = time.monotonic()
        try:
            # Local syntax check before sending
            try:
                if active_language == "python":
                    ast.parse(code, filename="main.py", mode="exec")
            except SyntaxError as exc:
                self.history.append(("stderr", f"Syntax Error: {exc}"))
                self.editor_lines = [""]
                self.cy = 0
                self.cx = 0
                return

            response = self.tunnel.run(code, language=active_language)
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            
            if response.get("type") == "error":
                self.history.append(("stderr", f"Agent error: {response.get('error')}"))
                self.editor_lines = [""]
                self.cy = 0
                self.cx = 0
                return

            stdout = response.get("stdout")
            stderr = response.get("stderr")
            exit_code = response.get("exit_code")
            duration_ms = response.get("duration_ms")
            if duration_ms is None:
                duration_ms = elapsed_ms

            if stdout:
                for line in str(stdout).splitlines():
                    self.history.append(("stdout", line))
            if stderr:
                for line in str(stderr).splitlines():
                    self.history.append(("stderr", line))

            if exit_code != 0:
                self.history.append(("stderr", f"Job exited with status {exit_code}"))

            self.history.append(("system", f"executed in {duration_ms}ms"))

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start_time) * 1000)
            self.history.append(("stderr", f"Exception: {exc}"))
            self.history.append(("system", f"executed in {elapsed_ms}ms"))
            
        self.editor_lines = [""]
        self.cy = 0
        self.cx = 0

    def _main(self, stdscr: curses.window) -> None:
        curses.use_default_colors()
        curses.noecho()
        curses.cbreak()
        curses.nonl()  # Distinguish Enter (13) and Ctrl+Enter/Ctrl+J (10)
        stdscr.keypad(True)
        try:
            curses.curs_set(1)
        except curses.error:
            pass

        if curses.has_colors():
            try:
                curses.init_pair(1, curses.COLOR_CYAN, -1)
                curses.init_pair(2, curses.COLOR_GREEN, -1)
                curses.init_pair(3, curses.COLOR_RED, -1)
                curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_CYAN)
                curses.init_pair(5, curses.COLOR_YELLOW, -1)
            except Exception:
                curses.init_pair(1, curses.COLOR_CYAN, curses.COLOR_BLACK)
                curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
                curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)
                curses.init_pair(4, curses.COLOR_BLACK, curses.COLOR_CYAN)
                curses.init_pair(5, curses.COLOR_YELLOW, curses.COLOR_BLACK)

        while True:
            stdscr.clear()
            height, width = stdscr.getmaxyx()

            if height < 4 or width < 20:
                stdscr.addstr(0, 0, "Terminal too small.")
                stdscr.refresh()
                ch = stdscr.getch()
                if ch in (17, ord('q'), ord('Q')):
                    break
                continue

            # Build display lines
            display_lines: list[tuple[str, str]] = []
            for item_type, text in self.history:
                for line in text.splitlines():
                    display_lines.append((item_type, line))

            editor_start_idx = len(display_lines)
            for i, line in enumerate(self.editor_lines):
                prompt = f"{self.language}> " if i == 0 else ".... "
                display_lines.append(("editor", prompt + line))

            # Calculate scroll range
            start_idx = max(0, len(display_lines) - height)
            if self.history_scroll > 0:
                start_idx = max(0, len(display_lines) - height - self.history_scroll)

            visible_lines = display_lines[start_idx:start_idx + height]

            # Render lines
            for row_idx, (item_type, line_text) in enumerate(visible_lines):
                stdscr.move(row_idx, 0)
                stdscr.clrtoeol()

                if item_type == "editor":
                    if line_text.startswith(".... "):
                        prompt = ".... "
                    else:
                        prompt_end = line_text.find("> ")
                        prompt = line_text[:prompt_end + 2] if prompt_end >= 0 else ""
                    if curses.has_colors():
                        stdscr.attron(curses.color_pair(1) | curses.A_BOLD)
                        stdscr.addstr(prompt)
                        stdscr.attroff(curses.color_pair(1) | curses.A_BOLD)
                    else:
                        stdscr.addstr(prompt)
                    stdscr.addstr(line_text[len(prompt):][:width - len(prompt) - 1])
                elif item_type == "stderr":
                    if curses.has_colors():
                        stdscr.attron(curses.color_pair(3))
                    stdscr.addstr(line_text[:width - 1])
                    if curses.has_colors():
                        stdscr.attroff(curses.color_pair(3))
                elif item_type == "stdout":
                    if curses.has_colors():
                        stdscr.attron(curses.color_pair(2))
                    stdscr.addstr(line_text[:width - 1])
                    if curses.has_colors():
                        stdscr.attroff(curses.color_pair(2))
                elif item_type == "system":
                    if curses.has_colors():
                        stdscr.attron(curses.color_pair(5))
                    stdscr.addstr(line_text[:width - 1])
                    if curses.has_colors():
                        stdscr.attroff(curses.color_pair(5))
                elif item_type == "success":
                    if curses.has_colors():
                        stdscr.attron(curses.color_pair(2) | curses.A_BOLD)
                    stdscr.addstr(line_text[:width - 1])
                    if curses.has_colors():
                        stdscr.attroff(curses.color_pair(2) | curses.A_BOLD)
                else:
                    stdscr.addstr(line_text[:width - 1])

            # Position cursor if editor is visible
            cursor_display_idx = editor_start_idx + self.cy
            if start_idx <= cursor_display_idx < start_idx + len(visible_lines):
                cursor_row = cursor_display_idx - start_idx
                prompt_len = len(f"{self.language}> ") if self.cy == 0 else len(".... ")
                cursor_col = prompt_len + self.cx
                cursor_col = min(cursor_col, width - 1)
                stdscr.move(cursor_row, cursor_col)

            stdscr.refresh()

            try:
                ch = self._read_key(stdscr)
            except KeyboardInterrupt:
                break

            # Handle navigation and typing
            if ch == curses.KEY_RESIZE:
                curses.update_lines_cols()
                continue

            # Snap scrollback to 0 for editing actions, but not for scroll keys
            if ch not in (curses.KEY_PPAGE, 339, curses.KEY_NPAGE, 338, curses.KEY_UP, 259, curses.KEY_DOWN, 258):
                self.history_scroll = 0

            if ch in CTRL_ENTER_SEQUENCES:
                self._run_code()
            elif ch in (curses.KEY_PPAGE, 339):  # Page Up
                self.history_scroll = min(max(0, len(display_lines) - height), self.history_scroll + 5)
            elif ch in (curses.KEY_NPAGE, 338):  # Page Down
                self.history_scroll = max(0, self.history_scroll - 5)
            elif ch in (curses.KEY_UP, 259):
                if self.cy > 0:
                    self.cy -= 1
                    self.cx = min(self.cx, len(self.editor_lines[self.cy]))
                else:
                    self.history_scroll = min(max(0, len(display_lines) - height), self.history_scroll + 1)
            elif ch in (curses.KEY_DOWN, 258):
                if self.history_scroll > 0:
                    self.history_scroll = max(0, self.history_scroll - 1)
                elif self.cy < len(self.editor_lines) - 1:
                    self.cy += 1
                    self.cx = min(self.cx, len(self.editor_lines[self.cy]))
            elif ch in (curses.KEY_LEFT, 260):
                if self.cx > 0:
                    self.cx -= 1
                elif self.cy > 0:
                    self.cy -= 1
                    self.cx = len(self.editor_lines[self.cy])
            elif ch in (curses.KEY_RIGHT, 261):
                if self.cx < len(self.editor_lines[self.cy]):
                    self.cx += 1
                elif self.cy < len(self.editor_lines) - 1:
                    self.cy += 1
                    self.cx = 0
            elif ch in (127, 8, 263, curses.KEY_BACKSPACE):
                if self.cx > 0:
                    line = self.editor_lines[self.cy]
                    self.editor_lines[self.cy] = line[:self.cx - 1] + line[self.cx:]
                    self.cx -= 1
                elif self.cy > 0:
                    prev_len = len(self.editor_lines[self.cy - 1])
                    self.editor_lines[self.cy - 1] += self.editor_lines[self.cy]
                    self.editor_lines.pop(self.cy)
                    self.cy -= 1
                    self.cx = prev_len
            elif ch in (curses.KEY_DC, 330):
                line = self.editor_lines[self.cy]
                if self.cx < len(line):
                    self.editor_lines[self.cy] = line[:self.cx] + line[self.cx + 1:]
                elif self.cy < len(self.editor_lines) - 1:
                    self.editor_lines[self.cy] += self.editor_lines[self.cy + 1]
                    self.editor_lines.pop(self.cy + 1)
            elif ch == 13:  # Enter -> New line
                line = self.editor_lines[self.cy]
                self.editor_lines.insert(self.cy + 1, line[self.cx:])
                self.editor_lines[self.cy] = line[:self.cx]
                self.cy += 1
                self.cx = 0
            elif ch == 9:  # Tab
                line = self.editor_lines[self.cy]
                self.editor_lines[self.cy] = line[:self.cx] + "    " + line[self.cx:]
                self.cx += 4
            elif ch in (17, 24):  # Ctrl+Q or Ctrl+X
                break
            elif ch == 12:  # Ctrl+L
                self.editor_lines = [""]
                self.cy = 0
                self.cx = 0
                self.history = []
            elif ch in (10, curses.KEY_F2, 7):  # Ctrl+Enter (10) / F2 / Ctrl+G -> Run
                self._run_code()
            elif ch in (curses.KEY_HOME, 1, 262):  # Ctrl+A
                self.cx = 0
            elif ch in (curses.KEY_END, 5, 360):  # Ctrl+E
                self.cx = len(self.editor_lines[self.cy])
            elif 32 <= ch <= 126:
                line = self.editor_lines[self.cy]
                self.editor_lines[self.cy] = line[:self.cx] + chr(ch) + line[self.cx:]
                self.cx += 1

    def _read_key(self, stdscr: curses.window) -> int | str:
        ch = stdscr.getch()
        if ch != 27:
            return ch

        chars = [chr(ch)]
        stdscr.nodelay(True)
        try:
            while True:
                next_ch = stdscr.getch()
                if next_ch == -1:
                    break
                chars.append(chr(next_ch))
        finally:
            stdscr.nodelay(False)

        sequence = "".join(chars)
        return sequence if sequence in CTRL_ENTER_SEQUENCES else ch


def wait_for_socket(path: str, *, timeout: float = 10.0) -> None:
    socket_path = Path(path)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if socket_path.exists():
            return
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for vsock socket: {path}")


def wait_for_agent(tunnel: VsockTunnel, *, timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if tunnel.healthcheck():
                return
        except Exception as exc:
            last_error = exc
        time.sleep(0.1)

    detail = f": {last_error}" if last_error else ""
    raise TimeoutError(f"Timed out waiting for guest agent{detail}")


def detect_language(code: str) -> str:
    stripped = code.strip()
    lowered = stripped.lower()
    if not stripped:
        return "python"
    if re.search(r"\bfn\s+main\s*\(", lowered) or "println!(" in stripped or "use std::" in lowered:
        return "rust"
    if "package main" in lowered and re.search(r"\bfunc\s+main\s*\(", lowered):
        return "go"
    if (
        re.search(r"\binterface\s+\w+", lowered)
        or re.search(r":\s*(string|number|boolean|unknown|any)\b", lowered)
        or re.search(r"\btype\s+\w+\s*=", lowered)
    ):
        return "ts"
    if (
        "console.log" in lowered
        or lowered.startswith("function ")
        or "=> " in stripped
        or lowered.startswith("const ")
        or lowered.startswith("let ")
    ):
        return "js"
    return "python"


def parse_language(language: str) -> str:
    language = language.strip().lower()
    aliases = {
        "detect": AUTO_LANGUAGE,
        "py": "python",
        "javascript": "js",
        "typescript": "ts",
        "golang": "go",
        "rs": "rust",
    }
    language = aliases.get(language, language)
    if language not in LANGUAGE_CHOICES:
        supported = ", ".join(LANGUAGE_CHOICES)
        raise ValueError(f"unsupported language: {language}. supported: {supported}")
    return language

def log(message: str) -> None:
    timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"[{timestamp}] {message}"
    print(line)
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fp:
            fp.write(line + "\n")
    except OSError:
        pass 


def main() -> None:
    vm = CrackerVM(
        binary=FC_BINARY,
        socket_path=SOCKET_PATH,
        log_path=LOG_PATH,
        kernel_path=KERNEL_PATH,
        rootfs_path=ROOTFS_PATH,
        boot_args=BOOT_ARGS,
        workdir=WORKDIR,
    )

    try:
        # vm booting 
        boot_started_at = time.monotonic()
        vm.start()
        vm.wait_until_ready()
        vm.machine(vcpu_count=1, mem_size_mib=500)
        vm.configure_logger(log_path=str(Path(vm.log_path).resolve()))
        vm.boot_source(kernel_image_path=KERNEL_PATH, boot_args=BOOT_ARGS)
        vm.root_drive(path=ROOTFS_PATH)

        # initializing vsock portal 
        vm.vsock(guest_cid=3, uds_path=VSOCK_PATH)
        vm.boot()
        log(f"VM booted in {time.monotonic() - boot_started_at:.3f}s")


        wait_for_socket(VSOCK_PATH)

        tunnel = VsockTunnel(uds_path=VSOCK_PATH)
        wait_for_agent(tunnel)
        print("healthcheck: True")
        log(f"VM connection established under {time.monotonic() - boot_started_at:.3f}s")

        tui = PythonJobRunnerTUI(tunnel)
        tui.run()
    finally:
        vm.stop()


if __name__ == "__main__":
    main()
