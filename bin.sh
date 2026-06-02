#!/usr/bin/env bash
set -euo pipefail

ROOTFS_NAME="${1:-rootfs.ext4}"
SIZE_MB="${2:-512}"

echo "Creating ${ROOTFS_NAME} with size ${SIZE_MB}MB..."

dd if=/dev/zero of="$ROOTFS_NAME" bs=1M count="$SIZE_MB" status=progress

mkfs.ext4 -F "$ROOTFS_NAME"

mkdir -p mnt-rootfs

echo "Done."
echo
echo "Rootfs image: $ROOTFS_NAME"
echo "Mount with:"
echo "  sudo mount -o loop $ROOTFS_NAME mnt-rootfs"
echo
echo "Unmount with:"
echo "  sudo umount mnt-rootfs"