#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INIT_BIN="${SCRIPT_DIR}/init"
ROOTFS="${SCRIPT_DIR}/rootfs.ext4"
MOUNT_DIR="${SCRIPT_DIR}/mnt"
ROOTFS_SIZE_MB="${ROOTFS_SIZE_MB:-16}"
MOUNTED=0

cleanup() {
    if [[ "${MOUNTED}" -eq 1 ]]; then
        umount "${MOUNT_DIR}" 2>/dev/null || true
    fi
}
trap cleanup EXIT

if [[ "${EUID}" -ne 0 ]]; then
    echo "build.sh must run as root because it mounts an ext4 image" >&2
    exit 1
fi

gcc -static -Os -s -o "${INIT_BIN}" "${SCRIPT_DIR}/init.c"
dd if=/dev/zero of="${ROOTFS}" bs=1M count="${ROOTFS_SIZE_MB}" status=none
mkfs.ext4 -q -F "${ROOTFS}"

mkdir -p "${MOUNT_DIR}"
mount "${ROOTFS}" "${MOUNT_DIR}"
MOUNTED=1

dd if="${INIT_BIN}" of="${MOUNT_DIR}/init" status=none
chmod +x "${MOUNT_DIR}/init"

umount "${MOUNT_DIR}"
MOUNTED=0

echo "${ROOTFS}"
