# Exec Sandboxing

This is the merged low-level sandbox example for both command execution and file
transfer. It uses one C guest agent over Firecracker vsock and only existing SDK
primitives:

- `CrackerVM`
- `vm.vsock(...)`
- `VsockClient`
- `start`, `wait_until_ready`, `machine`, `boot_source`, `root_drive`, `boot`, `stop`

No SDK APIs are added. The request framing and higher-level protocol are local
to this example.

## Protocol

The guest C agent listens on AF_VSOCK port `5000`.

Requests are one per connection:

```txt
HEALTH
EXEC bash|python|js|go|c <timeout_seconds> <script_size>
UPLOAD /workspace/path <size>
DOWNLOAD /workspace/path
```

Every response starts with:

```txt
OK <size>
```

or:

```txt
ERR <size>
```

The response body is exactly `<size>` bytes.

`UPLOAD` and `DOWNLOAD` require absolute guest paths under `/workspace`, and
paths containing `..` are rejected.

## Build the rootfs

The rootfs is built from Docker on Alpine Linux so the guest has Bash, Python 3,
QuickJS, Go, and a C compiler. The C agent is compiled into `/init`.

```bash
sudo examples/real_world/exec_sandboxing/rootfs/build.sh
```

Rerun this command whenever you edit `rootfs/agent.c` or `rootfs/Dockerfile`;
otherwise the VM will keep booting the old `rootfs.ext4`.

The agent tees script stdout and stderr to `/dev/console`, so after rebuilding
the rootfs the same script output returned over vsock also appears in
`/tmp/cracker-sdk-exec-sandboxing.log`.

## Run it

Edit the top-level constants in `main.py` if your Firecracker binary or kernel
live somewhere else, then run:

```bash
python3 examples/real_world/exec_sandboxing/main.py
```

The default run:

- uploads this README into `/workspace/uploads/README.copy.md`
- executes Bash, Python, JavaScript, Go, and C snippets
- downloads `/workspace/results/all-runtimes.txt` back to the host

The `js` runtime uses QuickJS (`qjs`) instead of Node.js. That keeps this
low-level microVM example small and avoids Node's entropy-sensitive startup
behavior in minimal `/init` guests.

## Inspect the rootfs

After the VM has stopped, you can mount the rootfs and check whether files exist
inside it:

```bash
sudo mkdir -p /tmp/cracker-sdk-rootfs-check
sudo mount -o loop examples/real_world/exec_sandboxing/rootfs/rootfs.ext4 /tmp/cracker-sdk-rootfs-check
sudo ls -la /tmp/cracker-sdk-rootfs-check/workspace
sudo find /tmp/cracker-sdk-rootfs-check/workspace -maxdepth 3 -type f -print
sudo umount /tmp/cracker-sdk-rootfs-check
```

If the VM is running, stop it before mounting the image.
