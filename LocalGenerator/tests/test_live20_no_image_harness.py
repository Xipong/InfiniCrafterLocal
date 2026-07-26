from __future__ import annotations

from pathlib import Path
import struct
import zlib

from infini_local.pipelines.visual_delivery_gate import visual_delivery_report
from infini_local.qa.live_no_image_fixture import (
    hydrate_no_image_fixture_assets,
    write_no_image_fixture_png,
)
from infini_local.qa.runtime_program_fixtures import build_runtime_fixture


def test_no_image_fixture_hydrates_real_delivery_paths_without_backend(tmp_path: Path) -> None:
    fixture_path = write_no_image_fixture_png(tmp_path / "qa-fixture.png")
    raw = fixture_path.read_bytes()
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert raw[12:16] == b"IHDR"
    assert struct.unpack(">II", raw[16:24]) == (32, 32)
    offset = 8
    compressed = bytearray()
    while offset < len(raw):
        length = struct.unpack(">I", raw[offset:offset + 4])[0]
        kind = raw[offset + 4:offset + 8]
        payload = raw[offset + 8:offset + 8 + length]
        if kind == b"IDAT":
            compressed.extend(payload)
        offset += 12 + length
    assert len(zlib.decompress(bytes(compressed))) == 32 * (1 + 32 * 4)

    data = build_runtime_fixture("workbench_blade")
    data["visual"] = {}
    non_item = [
        entity
        for entity in data["runtimeProgram"]["entities"]
        if entity["kind"] != "item_body"
    ]
    non_item[0]["visualRole"] = "projectile"
    non_item[0]["visual"] = {"assetMode": "baked_sprite"}
    non_item[1]["visualRole"] = "child"
    non_item[1]["visual"] = {"assetMode": "reuse_item_icon"}

    hydrated = hydrate_no_image_fixture_assets(data, fixture_path)
    report = visual_delivery_report(hydrated, check_backend_config=False)

    assert report["ok"], report
    assert hydrated["visual"]["spriteStatus"] == "qa_no_image_fixture"
    assert non_item[0]["visual"]["spriteStatus"] == "qa_no_image_fixture"
    assert non_item[1]["visual"]["spriteStatus"] == "reused_item_icon"
    assert hydrated["debug"]["noImageQaFixturePath"] == str(fixture_path.resolve())
