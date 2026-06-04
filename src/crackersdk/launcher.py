from __future__ import annotations


class FirecrackerLauncher:
    def __init__(
        self,
        *,
        binary: str,
        socket_path: str,
        namespace_name: str | None = None,
    ):
        self.binary = binary
        self.socket_path = socket_path
        self.namespace_name = namespace_name

    def build_command(self) -> list[str]:
        command = [self.binary, "--api-sock", self.socket_path]
        if self.namespace_name is None:
            return command
        return ["ip", "netns", "exec", self.namespace_name, *command]


class JailerLauncher:
    def __init__(
        self,
        *,
        jailer_binary: str,
        exec_file: str,
        jail_id: str,
        uid: int,
        gid: int,
        chroot_base_dir: str,
        socket_path: str,
        extra_args: tuple[str, ...] = (),
    ):
        self.jailer_binary = jailer_binary
        self.exec_file = exec_file
        self.jail_id = jail_id
        self.uid = uid
        self.gid = gid
        self.chroot_base_dir = chroot_base_dir
        self.socket_path = socket_path
        self.extra_args = extra_args

    def build_command(self) -> list[str]:
        return [
            self.jailer_binary,
            "--id",
            self.jail_id,
            "--exec-file",
            self.exec_file,
            "--uid",
            str(self.uid),
            "--gid",
            str(self.gid),
            "--chroot-base-dir",
            self.chroot_base_dir,
            *self.extra_args,
            "--",
            "--api-sock",
            self.socket_path,
        ]
