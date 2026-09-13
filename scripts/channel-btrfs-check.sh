#!/usr/bin/env bash
set -euo pipefail
root="$1"
truncate -s 1G "$root/channel-storage.btrfs"
mkfs.btrfs -f "$root/channel-storage.btrfs"
mkdir -p "$root/channel-storage"
sudo mount -o loop,user_subvol_rm_allowed "$root/channel-storage.btrfs" "$root/channel-storage"
trap 'sudo umount "$root/channel-storage"' EXIT
sudo python3 scripts/ci-mock-agent-smoke.py --bin-dir "$root/standalone/bin" \
  --evidence "$root/btrfs-evidence" --storage "$root/channel-storage" --backend btrfs-subvolume
