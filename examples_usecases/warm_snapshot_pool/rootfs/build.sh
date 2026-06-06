#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="warm-snapshot-pool-rootfs"
DOCKERFILE="${SCRIPT_DIR}/dockerfile"
ROOTFS="${SCRIPT_DIR}/rootfs.ext4"
ROOTFS_TAR="${SCRIPT_DIR}/rootfs.tar"
ROOTFS_SIZE_MB="${ROOTFS_SIZE_MB:-1024}"
MOUNT_DIR="$(mktemp -d)"
CONTAINER_ID=""

cleanup() {
    if mountpoint -q "${MOUNT_DIR}"; then
        sudo umount "${MOUNT_DIR}"
    fi
    if [ -n "${CONTAINER_ID}" ]; then
        docker rm "${CONTAINER_ID}" >/dev/null 2>&1 || true
    fi
    rm -rf "${MOUNT_DIR}"
    rm -f "${ROOTFS_TAR}"
}
trap cleanup EXIT

docker build -f "${DOCKERFILE}" -t "${IMAGE_NAME}" "${SCRIPT_DIR}"
CONTAINER_ID="$(docker create "${IMAGE_NAME}")"
docker export "${CONTAINER_ID}" -o "${ROOTFS_TAR}"
docker rm "${CONTAINER_ID}" >/dev/null
CONTAINER_ID=""

rm -f "${ROOTFS}"
dd if=/dev/zero of="${ROOTFS}" bs=1M count="${ROOTFS_SIZE_MB}" status=none
mkfs.ext4 -q -F "${ROOTFS}"

sudo mount "${ROOTFS}" "${MOUNT_DIR}"
sudo tar -xf "${ROOTFS_TAR}" -C "${MOUNT_DIR}"
sudo chmod +x "${MOUNT_DIR}/init"
sync
sudo umount "${MOUNT_DIR}"

echo "${ROOTFS}"
