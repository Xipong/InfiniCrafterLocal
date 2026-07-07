from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"


def test_csharp_warning_cleanup_does_not_use_blanket_suppression() -> None:
    joined = "\n".join(path.read_text(encoding="utf-8") for path in MOD.rglob("*.cs"))
    assert "#pragma warning disable" not in joined
    assert "#nullable disable warnings" not in joined
    assert "<NoWarn>" not in (MOD / "InfiniCrafterLocal.csproj").read_text(encoding="utf-8")


def test_old_phase1_stub_markers_are_removed_from_code() -> None:
    code_roots = [ROOT / "LocalGenerator" / "infini_local", ROOT / "tools", MOD]
    joined_parts: list[str] = []
    for base in code_roots:
        for path in base.rglob("*"):
            if path.suffix.lower() not in {".py", ".cs"}:
                continue
            joined_parts.append(path.read_text(encoding="utf-8", errors="ignore"))
    joined = "\n".join(joined_parts)
    for forbidden in [
        "PartialPhase1",
        "Phase-1 split marker",
        "dry_run_skeleton",
        "debug-only skeleton",
        "TODO: author core identity/stats fragment",
        "TODO: author runtime/VFX fragments",
        "TODO: validate independently before comparison",
        "skeleton only; main generator remains single-pass",
    ]:
        assert forbidden not in joined


def test_terraria_id_sentinels_are_named_in_csharp_sources() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in MOD.rglob("*.cs"))
    assert "InfiniTerrariaSentinels" in source
    assert "ItemUseStyleID.None" in source
    assert "ProjectileID.None" in source
    assert "ItemID.None" in source
    assert "AmmoID.None" in source
    assert "WallID.None" in source
    assert "TileID.Dirt" in source
    assert "ItemRarityID.Orange" in source
    assert "InfiniTerrariaSentinels.NoBuffType" in source
    assert "InfiniTerrariaSentinels.NoPrefix" in source
    assert "BuffNone" not in source
    assert "FirstItemType" not in source
    assert "FirstProjectileType" not in source
    assert "MaxSupportedItemUseStyle = 14" not in source
    assert "writer.Write(item?.type ?? 0);" not in source
    assert "for (int type = 1; type < ItemLoader.ItemCount; type++)" not in source
    assert "for (int type = 1; type < ProjectileLoader.ProjectileCount; type++)" not in source
