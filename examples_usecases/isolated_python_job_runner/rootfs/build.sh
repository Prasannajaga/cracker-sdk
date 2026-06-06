#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="cracker-sdk-isolated-job-runner-rootfs"
ROOTFS="${SCRIPT_DIR}/rootfs.ext4"
ROOTFS_TAR="${SCRIPT_DIR}/rootfs.tar"
ROOTFS_SIZE_MB="4096"
MOUNT_DIR="$(mktemp -d)"

cleanup() {
    if mountpoint -q "${MOUNT_DIR}"; then
        sudo umount "${MOUNT_DIR}"
    fi
    rm -rf "${MOUNT_DIR}"
    rm -f "${ROOTFS_TAR}"
}
trap cleanup EXIT

docker build -t "${IMAGE_NAME}" "${SCRIPT_DIR}"
container_id="$(docker create "${IMAGE_NAME}")"
docker export "${container_id}" -o "${ROOTFS_TAR}"
docker rm "${container_id}" >/dev/null

rm -f "${ROOTFS}"
dd if=/dev/zero of="${ROOTFS}" bs=1M count="${ROOTFS_SIZE_MB}" status=none
mkfs.ext4 -q -F "${ROOTFS}"

sudo mount "${ROOTFS}" "${MOUNT_DIR}"
sudo tar -xf "${ROOTFS_TAR}" -C "${MOUNT_DIR}"
sudo chmod +x "${MOUNT_DIR}/init"
sync
sudo umount "${MOUNT_DIR}"

echo "${ROOTFS}"
