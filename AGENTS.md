Dont use env for examples/ only use static variable for that please.

Examples must stay simple and copy-pasteable:
- Do not read configuration from environment variables in examples.
- Do not use `os.environ`, `os.getenv`, or `shutil.which` in examples.
- Prefer explicit top-level constants such as `FC_BINARY`, `JAILER_BINARY`, `KERNEL_PATH`, `ROOTFS_PATH`, `JAILER_UID`, and `JAILER_GID`.
- Do not generate dynamic example IDs from process IDs or timestamps unless the user explicitly asks for it.
