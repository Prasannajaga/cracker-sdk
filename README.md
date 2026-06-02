# cracker-sdk

Minimal local Firecracker SDK boilerplate package.

```python
from crackerSDK import crackerVM

vm = crackerVM(
    binary="/home/user/.sparkvm/bin/firecracker",
    socket_path="/tmp/fc.sock",
    log_path="/tmp/firecracker.log",
)

vm.start()
vm.wait_until_ready()

vm.machine(vcpu_count=2, mem_size_mib=2048)
vm.boot_source(kernel_image_path="vmlinux", boot_args="...")
vm.root_drive(path="rootfs.ext4")
vm.drive(drive_id="data", path="execution.ext4")
vm.network(iface_id="eth0", host_dev_name="tap0", guest_mac="AA:FC:00:00:00:01")
vm.entropy()
vm.boot()

exit_code = vm.wait(timeout=60)
```
