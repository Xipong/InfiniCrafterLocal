from __future__ import annotations

import re
from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"


def _read(rel: str) -> str:
    return read_text_with_partial_bundles(MOD / rel)


def test_generated_item_apply_uses_named_none_use_style_ids() -> None:
    generated = _read("Common/Models/GeneratedItemData.cs")
    extractinator = _read("Content/Items/GeneratedExtractinatorMaterial.cs")
    assert "ItemUseStyleID.None" in generated
    assert "ItemUseStyleID.None" in extractinator
    assert not re.search(r"\b(?:item|Item)\.useStyle\s*=\s*0\s*;", generated + "\n" + extractinator)


def test_generator_client_uses_named_terraria_id_sentinels_for_snapshots() -> None:
    source = _read("Common/Services/GeneratorClient.cs")
    for required in [
        "ProjectileID.None",
        "ItemID.None",
        "TileID.Dirt",
        "WallID.None",
        "ItemRarityID.Orange",
    ]:
        assert required in source
    forbidden = [
        r"\.shoot\s*>\s*0",
        r"\.shoot\s*<=\s*0",
        r"projectileType\s*<=\s*0",
        r"projectileType\s*>=\s*0",
        r"\.createTile\s*>=\s*0",
        r"\.createWall\s*>=\s*0",
        r"\.rare\s*>=\s*3",
        r"\b3\s*=>\s*\"Orange\"",
        r"\b3\s*=>\s*\"#FFC896\"",
    ]
    for pattern in forbidden:
        assert not re.search(pattern, source), pattern


def test_dump_tools_use_projectile_id_none_for_projectile_fields() -> None:
    dump_sources = _read("Common/Commands/InfiniDumpCommand.cs") + "\n" + _read("Common/Commands/InfiniDumpPictureCommand.cs")
    assert "ProjectileID.None" in dump_sources
    assert not re.search(r"\.shoot\s*>\s*0", dump_sources)
    assert not re.search(r"projectileType\s*>?=\s*0", dump_sources)
