"""Pure asset filename, final-PNG envelope and delivery byte contracts."""
from __future__ import annotations

from pathlib import Path
from typing import Any
import struct
import re
from urllib.parse import urlparse
import zlib

# Shared delivery/HTTP ceiling for a single generated asset.
MAX_ASSET_RESPONSE_BYTES = 8 * 1024 * 1024

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_MAX_PNG_BYTES = 32 * 1024 * 1024
# Final gameplay/sync PNG ceiling matches GeneratedAssetSyncService in C#.
# Raw provider canvases are processed independently and do not use this gate.
_MAX_PNG_DIMENSION = 512


def _png_expected_scanline_bytes(width: int, height: int, bits_per_pixel: int, interlace: int) -> tuple[int, list[tuple[int, int]]]:
    if interlace == 0:
        row_bytes = (width * bits_per_pixel + 7) // 8
        return height * (1 + row_bytes), [(height, row_bytes)]
    passes: list[tuple[int, int]] = []
    total = 0
    for x0, y0, dx, dy in ((0, 0, 8, 8), (4, 0, 8, 8), (0, 4, 4, 8), (2, 0, 4, 4), (0, 2, 2, 4), (1, 0, 2, 2), (0, 1, 1, 2)):
        pass_width = 0 if width <= x0 else (width - x0 + dx - 1) // dx
        pass_height = 0 if height <= y0 else (height - y0 + dy - 1) // dy
        if pass_width == 0 or pass_height == 0:
            continue
        row_bytes = (pass_width * bits_per_pixel + 7) // 8
        passes.append((pass_height, row_bytes))
        total += pass_height * (1 + row_bytes)
    return total, passes


def is_complete_png_file(path: Path | str) -> bool:
    """Validate the complete gameplay PNG envelope before delivery or sync."""

    try:
        # Enforce the ceiling during I/O, before allocating a complete file.
        # Read one extra byte to detect growth/overflow without trusting stat().
        with Path(path).open("rb") as stream:
            raw = stream.read(_MAX_PNG_BYTES + 1)
        if len(raw) > _MAX_PNG_BYTES or not raw.startswith(_PNG_SIGNATURE):
            return False
        offset = len(_PNG_SIGNATURE)
        seen_ihdr = seen_plte = seen_idat = False
        idat_ended = False
        width = height = bit_depth = color_type = interlace = 0
        compressed = bytearray()
        while offset <= len(raw) - 12:
            length = struct.unpack_from(">I", raw, offset)[0]
            if length > _MAX_PNG_BYTES:
                return False
            chunk_type = raw[offset + 4:offset + 8]
            data_offset = offset + 8
            crc_offset = data_offset + length
            if crc_offset + 4 > len(raw):
                return False
            chunk_data = raw[data_offset:crc_offset]
            stored_crc = struct.unpack_from(">I", raw, crc_offset)[0]
            if stored_crc != (zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF):
                return False
            offset = crc_offset + 4
            if chunk_type == b"IHDR":
                if seen_ihdr or seen_idat or length != 13:
                    return False
                width, height, bit_depth, color_type, compression, filtering, interlace = struct.unpack(">IIBBBBB", chunk_data)
                valid_depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
                if not (0 < width <= _MAX_PNG_DIMENSION and 0 < height <= _MAX_PNG_DIMENSION):
                    return False
                if bit_depth not in valid_depths.get(color_type, set()) or compression != 0 or filtering != 0 or interlace not in {0, 1}:
                    return False
                seen_ihdr = True
            elif chunk_type == b"PLTE":
                if not seen_ihdr or seen_idat or seen_plte or length == 0 or length % 3 or length > 768:
                    return False
                seen_plte = True
            elif chunk_type == b"IDAT":
                if not seen_ihdr or idat_ended or length == 0 or len(compressed) + length > _MAX_PNG_BYTES:
                    return False
                compressed.extend(chunk_data)
                seen_idat = True
            elif chunk_type == b"IEND":
                if not seen_ihdr or not seen_idat or length != 0 or offset != len(raw) or (color_type == 3 and not seen_plte):
                    return False
                channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color_type, 0)
                expected, passes = _png_expected_scanline_bytes(width, height, channels * bit_depth, interlace)
                if expected <= 0 or expected > _MAX_PNG_BYTES:
                    return False
                inflater = zlib.decompressobj()
                scanlines = inflater.decompress(bytes(compressed), expected + 1)
                if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail or len(scanlines) != expected:
                    return False
                scan_offset = 0
                for pass_height, row_bytes in passes:
                    for _ in range(pass_height):
                        if scanlines[scan_offset] > 4:
                            return False
                        scan_offset += 1 + row_bytes
                return scan_offset == len(scanlines)
            else:
                if not seen_ihdr or (chunk_type[0] & 0x20) == 0:
                    return False
                if seen_idat:
                    idat_ended = True
        return False
    except Exception:
        return False


# AGENT MAP: final asset filename contract shared with C# asset sync. Only safe
# basename `.png`/`.json` files are exposed; raw generation intermediates and
# arbitrary paths/URLs are deliberately stripped. C# downloads these by `/get_asset`.
def asset_filename_from_path(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = urlparse(raw)
        if parsed.scheme in {"http", "https"}:
            raw = parsed.path
    except Exception:
        pass
    name = Path(raw.replace("\\", "/")).name
    if not name or name in {".", ".."}:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9._@+\-]{1,160}", name):
        return ""
    if not name.lower().endswith((".png", ".json")):
        return ""
    return name
