from __future__ import annotations

from pathlib import Path
import struct
from typing import Any
import zlib


def write_no_image_fixture_png(path: Path, *, size: int = 32) -> Path:
    """Write a deterministic technical PNG without calling an image backend."""

    if size < 1 or size > 256:
        raise ValueError("fixture PNG size must be within 1..256")
    path.parent.mkdir(parents=True, exist_ok=True)

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    rows = bytearray()
    for y in range(size):
        rows.append(0)
        for x in range(size):
            if (x // 4 + y // 4) % 2:
                rows.extend((255, 0, 255, 255))
            else:
                rows.extend((24, 24, 24, 255))
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), level=9))
        + chunk(b"IEND", b"")
    )
    return path


def hydrate_no_image_fixture_assets(data: dict[str, Any], fixture_path: Path) -> dict[str, Any]:
    """Hydrate final-delivery paths with a QA-only PNG after backend interception.

    This function never changes an authored asset mode and never calls or mocks an
    image generator. It gives the production delivery gate a real file to inspect
    while the no-image campaign separately proves that every backend is blocked.
    """

    fixture = str(fixture_path.resolve())
    visual = data.setdefault("visual", {})
    visual.update({
        "spriteStatus": "qa_no_image_fixture",
        "spritePath": fixture,
        "spriteRawPath": fixture,
        "spriteUrl": "",
    })
    raw_program = data.get("runtimeProgram")
    program: dict[str, Any] = raw_program if isinstance(raw_program, dict) else {}
    attack = data.setdefault("attack", {})
    for entity in program.get("entities") or []:
        if not isinstance(entity, dict) or entity.get("kind") == "item_body":
            continue
        entity_visual = entity.setdefault("visual", {})
        mode = str(entity_visual.get("assetMode") or "")
        if mode == "baked_sprite":
            entity_visual.update({
                "spriteStatus": "qa_no_image_fixture",
                "spritePath": fixture,
                "spriteUrl": "",
            })
        elif mode == "reuse_item_icon":
            entity_visual.update({
                "spriteStatus": "reused_item_icon",
                "spritePath": fixture,
                "spriteUrl": "",
            })
        elif mode in {"runtime_geometry", "no_asset"}:
            entity_visual.update({
                "spriteStatus": "not_required",
                "spritePath": "",
                "spriteUrl": "",
            })
        role = str(entity.get("visualRole") or "")
        if role in {"projectile", "impact", "child", "field"}:
            attack[f"{role}SpriteStatus"] = str(entity_visual.get("spriteStatus") or "")
            attack[f"{role}SpritePath"] = str(entity_visual.get("spritePath") or "")
            attack[f"{role}SpriteUrl"] = ""
    data.setdefault("debug", {})["noImageQaFixturePath"] = fixture
    return data


__all__ = ["hydrate_no_image_fixture_assets", "write_no_image_fixture_png"]
