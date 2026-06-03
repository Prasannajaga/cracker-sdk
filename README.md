# cracker-sdk

`cracker-sdk` is a small Python wrapper around the Firecracker runtime API that helps you run microVMs efficiently from Python.

You can use this SDK in two ways: simple mode and advanced control mode.

## Simple Implementation

```python
from crackersdk import crackerVM

BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"

vm = crackerVM(
    binary="/home/user/.local/bin/firecracker",
    socket_path="/tmp/cracker-sdk.sock",
    log_path="/tmp/cracker-sdk.log",
    kernel_path="/home/user/images/vmlinux",
    rootfs_path="examples/rootfs/hello/rootfs.ext4",
    boot_args=BOOT_ARGS,
)

result = vm.run(vcpu_count=1, mem_size_mib=256, timeout=30)

print("exit_code:", result.exit_code)
print("timed_out:", result.timed_out)
print("error:", result.error)
print(result.stdout)
```

## Advanced control 

Use the explicit lifecycle methods when you need full control over the boot
sequence or want to configure devices step by step.

```python
from crackersdk import crackerVM

BOOT_ARGS = "console=ttyS0 reboot=k panic=1 pci=off root=/dev/vda rw init=/init"

vm = crackerVM(
    binary="/home/user/.local/bin/firecracker",
    socket_path="/tmp/cracker-sdk-low-level.sock",
    log_path="/tmp/cracker-sdk-low-level.log",
)

try:
    vm.start()
    vm.wait_until_ready()
    vm.configure_logger("/tmp/cracker-sdk-low-level.log")

    vm.machine(vcpu_count=2, mem_size_mib=512)
    vm.boot_source(
        kernel_image_path="/home/user/images/vmlinux",
        boot_args=BOOT_ARGS,
    )
    vm.root_drive(path="examples/rootfs/hello/rootfs.ext4")
    vm.entropy()

    vm.boot()
    exit_code = vm.wait(timeout=30)
    print("exit_code:", exit_code)
finally:
    vm.stop()
```
