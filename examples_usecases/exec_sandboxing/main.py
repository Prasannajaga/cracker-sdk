"""Run code and move files through one Firecracker C vsock sandbox agent."""

from __future__ import annotations

import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
EXAMPLE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from crackersdk import CrackerVM, VsockClient


BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"
FC_BINARY = "/home/prasanna/.local/bin/firecracker"
KERNEL_PATH = "/home/prasanna/.sparkvm/images/vmlinux"
ROOTFS_PATH = str(EXAMPLE_DIR / "rootfs/rootfs.ext4")
SOCKET_PATH = "/tmp/cracker-sdk-exec-sandboxing.sock"
LOG_PATH = "/tmp/cracker-sdk-exec-sandboxing.log"
VSOCK_PATH = "/tmp/cracker-sdk-exec-sandboxing.vsock"
WORKDIR = "/tmp/cracker-sdk-exec-sandboxing"
GUEST_CID = 3
AGENT_PORT = 5000
SCRIPT_TIMEOUT_SECONDS = 30

HOST_UPLOAD_PATH = str(EXAMPLE_DIR / "README.md")
GUEST_UPLOAD_PATH = "/workspace/uploads/README.copy.md"
HOST_DOWNLOAD_PATH = str(EXAMPLE_DIR / "downloaded.README.copy.md")

BASH_SCRIPT = """\
set -eu     
echo "hello from bash" 
"""

PYTHON_SCRIPT = """\
from pathlib import Path

data = Path("/workspace/uploads/README.copy.md").read_text()
print("hello from python")
print("uploaded README lines:", len(data.splitlines()))
with Path("/workspace/results/all-runtimes.txt").open("a") as file:
    file.write("python appended this line\\n")
"""

JS_SCRIPT = """\
const data = std.loadFile("/workspace/uploads/README.copy.md");
console.log("hello from js");
console.log("uploaded README chars:", data.length);
const file = std.open("/workspace/results/all-runtimes.txt", "a");
file.puts("js appended this line\\n");
file.close();
"""

GO_SCRIPT = """\
package main

import (
    "fmt"
    "os"
)

func main() {
    data, err := os.ReadFile("/workspace/uploads/README.copy.md")
    if err != nil {
        panic(err)
    }
    fmt.Println("hello from go")
    fmt.Println("uploaded README bytes:", len(data))
    file, err := os.OpenFile("/workspace/results/all-runtimes.txt", os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0644)
    if err != nil {
        panic(err)
    }
    defer file.Close()
    file.WriteString("go appended this line\\n")
}
"""

C_SCRIPT = """\
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>

int main(void) {
    struct stat st;
    if (stat("/workspace/uploads/README.copy.md", &st) != 0) {
        perror("stat");
        return 1;
    }
    puts("hello from c");
    printf("uploaded README bytes: %lld\\n", (long long)st.st_size);
    FILE *file = fopen("/workspace/results/all-runtimes.txt", "a");
    if (file == NULL) {
        perror("fopen");
        return 1;
    }
    fputs("c appended this line\\n", file);
    fclose(file);
    return 0;
}
"""


class AgentClient:
    def __init__(self, uds_path: str, port: int = AGENT_PORT, timeout: float = 45.0):
        self.uds_path = uds_path
        self.port = port
        self.timeout = timeout

    def health(self) -> str:
        status, body = self.request(b"HEALTH\n")
        if status != "OK":
            raise RuntimeError(body.decode("utf-8", errors="replace"))
        return body.decode("utf-8")

    def exec(self, runtime: str, script: str, timeout_seconds: int) -> str:
        body = script.encode("utf-8")
        header = f"EXEC {runtime} {timeout_seconds} {len(body)}\n".encode("ascii")
        status, response = self.request(header + body)
        text = response.decode("utf-8", errors="replace")
        if status != "OK":
            raise RuntimeError(text)
        return text

    def upload(self, host_path: str, guest_path: str) -> str:
        data = Path(host_path).read_bytes()
        header = f"UPLOAD {guest_path} {len(data)}\n".encode("ascii")
        status, body = self.request(header + data)
        text = body.decode("utf-8", errors="replace")
        if status != "OK":
            raise RuntimeError(text)
        return text

    def download(self, guest_path: str, host_path: str) -> int:
        header = f"DOWNLOAD {guest_path}\n".encode("ascii")
        status, body = self.request(header)
        if status != "OK":
            raise RuntimeError(body.decode("utf-8", errors="replace"))
        Path(host_path).write_bytes(body)
        return len(body)

    def request(self, payload: bytes) -> tuple[str, bytes]:
        with VsockClient(self.uds_path, timeout=self.timeout) as client:
            client.connect(port=self.port)
            client.send(payload)
            header = self._read_header(client)
            status, raw_size = header.split(" ", 1)
            body = self._read_exact(client, int(raw_size))
        return status, body

    def _read_header(self, client: VsockClient) -> str:
        chunks: list[bytes] = []
        while True:
            chunk = client.recv(1)
            if not chunk:
                raise RuntimeError("agent closed before response header")
            if chunk == b"\n":
                return b"".join(chunks).decode("ascii")
            chunks.append(chunk)

    def _read_exact(self, client: VsockClient, size: int) -> bytes:
        chunks: list[bytes] = []
        remaining = size
        while remaining > 0:
            chunk = client.recv(remaining)
            if not chunk:
                raise RuntimeError("agent closed before response body")
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


def create_vm() -> CrackerVM:
    return CrackerVM(
        binary=FC_BINARY,
        socket_path=SOCKET_PATH,
        log_path=LOG_PATH,
        workdir=WORKDIR,
    )


def boot_vm(vm: CrackerVM) -> None:
    vm.start()
    vm.wait_until_ready()
    vm.configure_logger(log_path=str(Path(vm.log_path).resolve()))
    vm.machine(vcpu_count=1, mem_size_mib=512)
    vm.boot_source(kernel_image_path=KERNEL_PATH, boot_args=BOOT_ARGS)
    vm.root_drive(path=ROOTFS_PATH)
    print("entropy:", vm.entropy())
    print("vsock:", vm.vsock(guest_cid=GUEST_CID, uds_path=VSOCK_PATH))
    vm.boot()


def wait_for_agent(client: AgentClient) -> None:
    deadline = time.monotonic() + 15
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if client.health() == "ready\n":
                return
        except Exception as exc:
            last_error = exc
            time.sleep(0.2)
    raise TimeoutError(f"agent did not become ready: {last_error}")


def main() -> None:
    vm = create_vm()
    try:
        boot_vm(vm)
        client = AgentClient(VSOCK_PATH)
        wait_for_agent(client)


        print("Uploading files")

        client.upload(HOST_UPLOAD_PATH, GUEST_UPLOAD_PATH) 

        print("File uploaded to", GUEST_UPLOAD_PATH)



        print("Executing scripts")


        for runtime, script in (
            ("bash", BASH_SCRIPT),
            ("python", PYTHON_SCRIPT),
            ("js", JS_SCRIPT),
            ("go", GO_SCRIPT),
            ("c", C_SCRIPT),
        ):
            print(f"\n === EXEC {runtime} === ")
            results = client.exec(runtime, script, timeout_seconds=SCRIPT_TIMEOUT_SECONDS)
            print(results, end="")

        
        print("\n Script Execution Completed \n Downloading the file", HOST_DOWNLOAD_PATH)

        bytes_downloaded = client.download("/workspace/results/all-runtimes.txt", HOST_DOWNLOAD_PATH)
        print(f"downloaded {bytes_downloaded} bytes to {HOST_DOWNLOAD_PATH}")
    finally:
        vm.stop()


if __name__ == "__main__":
    main()
