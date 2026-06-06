# SSH Sandbox

This example boots a Firecracker microVM with a TAP interface and connects with
OpenSSH. The SDK still only attaches the TAP device via `vm.network(...)`; TAP
setup and the `ssh` command are local to this example.

The guest uses:

- static IP `172.16.0.2/24`
- root SSH login with public-key auth only
- OpenSSH server from the rootfs image
- a small guest entropy bootstrap before OpenSSH starts

## Add your public key

Replace the placeholder in:

```txt
examples/real_world/ssh_sandbox/rootfs/authorized_keys.example
```

Use the public key that matches `SSH_PRIVATE_KEY_PATH` in `main.py`.

The split is:

- `rootfs/authorized_keys.example` is copied into the guest image as
  `/root/.ssh/authorized_keys`; it must contain your public key.
- `SSH_PRIVATE_KEY_PATH` is used only on the host by the `ssh -i ...` command;
  it must point at the matching private key, not the `.pub` file.

After changing `authorized_keys.example`, rebuild `rootfs.ext4`.

## Build the rootfs

This rootfs builder uses Docker to assemble Alpine Linux with OpenSSH:

```bash
sudo examples/real_world/ssh_sandbox/rootfs/build.sh
```

## Run it

The run script creates `tap-cracker-ssh`, assigns `172.16.0.1/24` on the host,
boots the VM, waits for TCP port 22, and runs one SSH command.

```bash
sudo python examples/real_world/ssh_sandbox/main.py
```

Edit the top-level constants in `main.py` for your local Firecracker binary,
kernel, private key, or command.

If output stops after the `network:` line, the script is waiting for TCP port
22. The guest runs `/usr/local/sbin/seed-entropy` before starting OpenSSH so
minimal Firecracker kernels do not leave `sshd` blocked in early boot randomness
setup. Check `/tmp/cracker-sdk-ssh-sandbox.log` for `seed-entropy: credited`
followed by `sshd is listening on port 22`. If the port becomes reachable but
SSH auth fails, the command will exit quickly because the example uses
`BatchMode=yes`.
