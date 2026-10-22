"""Build transparent native registration carriers, never generated item artwork.

Modern tML Body is a 9x4 composite sheet (40x56 cells). Head/Legs and
unused legacy Body/Arms paths retain the 20-row 40x56 native layout.
"""
from pathlib import Path
import argparse
import struct
import zlib

ROOT = Path(__file__).resolve().parents[2]
SIZES = {"Head": (40, 1120), "Body": (360, 224), "Legs": (40, 1120),
         "FemaleBody": (40, 1120), "Arms": (40, 1120)}


def transparent_png(width: int, height: int) -> bytes:
    def chunk(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(bytes((width * 4 + 1) * height), level=9))
            + chunk(b"IEND", b""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for suffix, (width, height) in SIZES.items():
        path = ROOT / "ModSources/InfiniCrafterLocal/Assets" / f"GeneratedItem_{suffix}.png"
        expected = transparent_png(width, height)
        if args.check:
            if not path.is_file() or path.read_bytes() != expected:
                raise SystemExit(f"Stale transparent equipment carrier: {path.relative_to(ROOT)}")
        else:
            path.write_bytes(expected)
    print("[OK] transparent native equipment carriers")


if __name__ == "__main__":
    main()
