#!/usr/bin/env python3
"""Promote a visually reviewed Product Gallery artifact without altering image bytes.

Usage:
    python docs/promote_reviewed_gallery.py /path/to/github-artifact.zip --head-sha SHA --approve

Download the artifact from the exact workflow head first. This program does not
declare screenshots approved: --approve records a review decision by the operator.
"""
from __future__ import annotations

import argparse
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GALLERY = ROOT / "docs" / "assets" / "screenshots"
EXPECTED = (
    "01-overview.png",
    "02-library.png",
    "03-research.png",
    "04-notebook.png",
    "05-manuscript.png",
    "06-intelligence.png",
)
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_HEIGHT = 8192


def git_output(*arguments: str) -> str:
    return subprocess.check_output(
        ["git", *arguments], cwd=ROOT, text=True
    ).strip()


def load_images(archive: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(archive) as zipped:
        records = [item for item in zipped.infolist() if not item.is_dir()]
        names = [Path(item.filename).name for item in records]
        if sorted(names) != sorted(EXPECTED) or len(names) != len(set(names)):
            raise ValueError("Artifact must contain exactly six canonical screenshot PNGs.")
        images = {}
        for item in records:
            if Path(item.filename).is_absolute() or ".." in Path(item.filename).parts:
                raise ValueError("Unsafe artifact path.")
            if item.file_size > MAX_FILE_BYTES:
                raise ValueError(f"Screenshot exceeds size limit: {item.filename}")
            content = zipped.read(item)
            if len(content) < 33 or content[:8] != b"\\x89PNG\\r\\n\\x1a\\n":
                raise ValueError(f"Invalid PNG signature: {item.filename}")
            if content[12:16] != b"IHDR" or struct.unpack(">I", content[8:12])[0] != 13:
                raise ValueError(f"Invalid PNG header: {item.filename}")
            width, height = struct.unpack(">II", content[16:24])
            if width != 1440 or not 960 <= height <= MAX_IMAGE_HEIGHT:
                raise ValueError(f"Unexpected full-page dimensions: {item.filename}")
            images[Path(item.filename).name] = content
        return images


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--head-sha", required=True, help="Exact CI workflow head commit.")
    parser.add_argument("--approve", action="store_true", help="Confirm human visual review.")
    args = parser.parse_args()
    if not args.approve:
        parser.error("Explicit visual acceptance is required: pass --approve.")
    if not args.artifact.is_file():
        parser.error("Artifact ZIP not found.")
    expected_sha = args.head_sha.strip()
    if len(expected_sha) != 40 or any(c not in "0123456789abcdef" for c in expected_sha):
        parser.error("--head-sha must be a 40-character lowercase Git commit SHA.")
    actual_sha = git_output("rev-parse", "HEAD")
    if actual_sha != expected_sha:
        parser.error(f"Wrong checkout: expected {expected_sha}; found {actual_sha}.")
    if git_output("status", "--porcelain", "--", "docs/assets/screenshots"):
        parser.error("Screenshot destination already has uncommitted changes.")
    images = load_images(args.artifact)
    GALLERY.mkdir(parents=True, exist_ok=True)
    for name in EXPECTED:
        (GALLERY / name).write_bytes(images[name])
        print(f"Promoted {name} ({len(images[name])} bytes)")
    print("Run the packaged Product Gallery verifier and Quality Gate before merging.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
