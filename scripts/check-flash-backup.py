"""Validate a complete device backup and the factory partition boundary before app-only flashing."""
import argparse
import hashlib
import json
from pathlib import Path


def verify(backup: Path, image: Path, partition: Path):
    data = backup.read_bytes()
    metadata = json.loads(backup.with_suffix(".json").read_text(encoding="utf-8-sig"))
    if len(data) != 16777216 or metadata.get("bytes") != len(data):
        raise ValueError("A complete 16MB backup is required")
    digest = hashlib.sha256(data).hexdigest()
    if digest.lower() != metadata.get("sha256", "").lower():
        raise ValueError("Backup SHA256 mismatch")
    table = partition.read_bytes()
    if data[0x8000:0x8000 + len(table)] != table:
        raise ValueError("Device backup partition table differs from the built firmware")
    if image.stat().st_size > 0x4F0000:
        raise ValueError("Firmware exceeds the factory OTA partition")
    print("Full backup SHA256 and installed partition table verified; app write boundary: 0x20000..0x510000")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument("image", type=Path)
    parser.add_argument("partition", type=Path)
    args = parser.parse_args()
    verify(args.backup, args.image, args.partition)
