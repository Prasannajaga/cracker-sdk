#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOTFS="${SCRIPT_DIR}/rootfs.ext4"
ROOTFS_SIZE_MB="${ROOTFS_SIZE_MB:-64}"
MOUNT_DIR="$(mktemp -d)"

cleanup() {
    if mountpoint -q "${MOUNT_DIR}"; then
        sudo umount "${MOUNT_DIR}"
    fi
    rm -rf "${MOUNT_DIR}"
}
trap cleanup EXIT

gcc -static -Os -s -o "${SCRIPT_DIR}/init" "${SCRIPT_DIR}/init.c"
rm -f "${ROOTFS}"
dd if=/dev/zero of="${ROOTFS}" bs=1M count="${ROOTFS_SIZE_MB}" status=none
mkfs.ext4 -q -F "${ROOTFS}"

sudo mount "${ROOTFS}" "${MOUNT_DIR}"
sudo cp "${SCRIPT_DIR}/init" "${MOUNT_DIR}/init"
sudo chmod +x "${MOUNT_DIR}/init"
sync
sudo umount "${MOUNT_DIR}"

echo "${ROOTFS}"
