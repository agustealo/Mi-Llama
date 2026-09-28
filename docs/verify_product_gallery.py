from __future__ import annotations

import struct
import subprocess
import zlib
from dataclasses import dataclass
from pathlib import Path

SCREENSHOT_ROOT = Path("docs/assets/screenshots")
MAX_CHANGED_PIXELS = 64
MAX_CHANNEL_DELTA = 8
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


@dataclass(frozen=True)
class DecodedPng:
    width: int
    height: int
    pixels: bytes


def _paeth(left: int, above: int, upper_left: int) -> int:
    estimate = left + above - upper_left
    left_distance = abs(estimate - left)
    above_distance = abs(estimate - above)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= above_distance and left_distance <= upper_left_distance:
        return left
    if above_distance <= upper_left_distance:
        return above
    return upper_left


def decode_png(data: bytes) -> DecodedPng:
    if not data.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG file")

    offset = len(PNG_SIGNATURE)
    width = height = None
    compressed = bytearray()

    while offset < len(data):
        if offset + 12 > len(data):
            raise ValueError("truncated PNG chunk")
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_type = data[offset + 4 : offset + 8]
        chunk_data_start = offset + 8
        chunk_data_end = chunk_data_start + length
        chunk_end = chunk_data_end + 4
        if chunk_end > len(data):
            raise ValueError("truncated PNG payload")
        chunk_data = data[chunk_data_start:chunk_data_end]

        if chunk_type == b"IHDR":
            (
                width,
                height,
                bit_depth,
                color_type,
                compression,
                filter_method,
                interlace,
            ) = struct.unpack(">IIBBBBB", chunk_data)
            if (bit_depth, color_type, compression, filter_method, interlace) != (
                8,
                2,
                0,
                0,
                0,
            ):
                raise ValueError(
                    "gallery verifier requires non-interlaced 8-bit RGB PNG screenshots"
                )
        elif chunk_type == b"IDAT":
            compressed.extend(chunk_data)
        elif chunk_type == b"IEND":
            break
        offset = chunk_end

    if width is None or height is None or not compressed:
        raise ValueError("PNG is missing IHDR or IDAT data")

    bytes_per_pixel = 3
    stride = width * bytes_per_pixel
    raw = zlib.decompress(bytes(compressed))
    expected = height * (stride + 1)
    if len(raw) != expected:
        raise ValueError(f"unexpected PNG payload length: {len(raw)} != {expected}")

    pixels = bytearray(height * stride)
    previous = bytearray(stride)
    raw_offset = 0

    for row_index in range(height):
        filter_type = raw[raw_offset]
        raw_offset += 1
        scanline = raw[raw_offset : raw_offset + stride]
        raw_offset += stride
        reconstructed = bytearray(stride)

        for index, value in enumerate(scanline):
            left = reconstructed[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
            above = previous[index]
            upper_left = previous[index - bytes_per_pixel] if index >= bytes_per_pixel else 0

            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = above
            elif filter_type == 3:
                predictor = (left + above) // 2
            elif filter_type == 4:
                predictor = _paeth(left, above, upper_left)
            else:
                raise ValueError(f"unsupported PNG filter type: {filter_type}")

            reconstructed[index] = (value + predictor) & 0xFF

        start = row_index * stride
        pixels[start : start + stride] = reconstructed
        previous = reconstructed

    return DecodedPng(width=width, height=height, pixels=bytes(pixels))


def committed_bytes(path: Path) -> bytes:
    result = subprocess.run(
        ["git", "show", f"HEAD:{path.as_posix()}"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout


def compare_png(path: Path) -> tuple[int, int]:
    committed = decode_png(committed_bytes(path))
    generated = decode_png(path.read_bytes())
    if (committed.width, committed.height) != (generated.width, generated.height):
        raise RuntimeError(
            f"{path}: dimensions changed from "
            f"{committed.width}x{committed.height} to {generated.width}x{generated.height}"
        )

    changed_pixels = 0
    max_delta = 0
    for offset in range(0, len(committed.pixels), 3):
        baseline = committed.pixels[offset : offset + 3]
        current = generated.pixels[offset : offset + 3]
        if baseline == current:
            continue
        changed_pixels += 1
        max_delta = max(
            max_delta,
            *(
                abs(int(before) - int(after))
                for before, after in zip(baseline, current, strict=True)
            ),
        )

    return changed_pixels, max_delta


def main() -> None:
    paths = sorted(SCREENSHOT_ROOT.glob("*.png"))
    if len(paths) != 6:
        raise RuntimeError(f"expected 6 governed screenshots, found {len(paths)}")

    failures: list[str] = []
    for path in paths:
        changed_pixels, max_delta = compare_png(path)
        print(f"{path}: changed_pixels={changed_pixels}, max_channel_delta={max_delta}")
        if changed_pixels > MAX_CHANGED_PIXELS or max_delta > MAX_CHANNEL_DELTA:
            failures.append(
                f"{path}: {changed_pixels} pixels changed, max channel delta {max_delta} "
                f"(limits: {MAX_CHANGED_PIXELS} pixels, delta {MAX_CHANNEL_DELTA})"
            )

    if failures:
        detail = "\n".join(failures)
        raise RuntimeError(
            "Product screenshots materially differ from the committed gallery. "
            "Download the generated gallery artifact and review the visual change.\n"
            f"{detail}"
        )


if __name__ == "__main__":
    main()
