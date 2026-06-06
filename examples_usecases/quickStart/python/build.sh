#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE_NAME="${IMAGE_NAME:-cracker-sdk-python-rootfs:latest}"
ROOTFS="${SCRIPT_DIR}/rootfs.ext4"
ROOTFS_TAR="${SCRIPT_DIR}/rootfs.tar"
MOUNT_DIR="${SCRIPT_DIR}/mnt"
ROOTFS_SIZE_MB="${ROOTFS_SIZE_MB:-2048}"
CONTAINER_ID=""
MOUNTED=0

cleanup() {
    if [[ "${MOUNTED}" -eq 1 ]]; then
        umount "${MOUNT_DIR}" 2>/dev/null || true
    fi
    if [[ -n "${CONTAINER_ID}" ]]; then
        docker rm "${CONTAINER_ID}" >/dev/null 2>&1 || true
    fi
    rm -f "${ROOTFS_TAR}"
}
trap cleanup EXIT

if [[ "${EUID}" -ne 0 ]]; then
    echo "build.sh must run as root because it mounts an ext4 image" >&2
    exit 1
fi

docker build -t "${IMAGE_NAME}" "${SCRIPT_DIR}"
CONTAINER_ID="$(docker create "${IMAGE_NAME}")"
docker export "${CONTAINER_ID}" -o "${ROOTFS_TAR}"

dd if=/dev/zero of="${ROOTFS}" bs=1M count="${ROOTFS_SIZE_MB}" status=none
mkfs.ext4 -q -F "${ROOTFS}"

mkdir -p "${MOUNT_DIR}"
mount "${ROOTFS}" "${MOUNT_DIR}"
MOUNTED=1

tar -xf "${ROOTFS_TAR}" -C "${MOUNT_DIR}"
chmod +x "${MOUNT_DIR}/init"

umount "${MOUNT_DIR}"
MOUNTED=0

rm -f "${ROOTFS_TAR}"

echo "${ROOTFS}"
