from __future__ import annotations

from pathlib import Path

from infini_local.core.runtime_authoring import CAPABILITY_REGISTRY


ROOT = Path(__file__).resolve().parents[2]
CS = ROOT / "ModSources" / "InfiniCrafterLocal"


def _read(path: str) -> str:
    return (CS / path).read_text("utf-8", errors="ignore")


def test_old_child_spec_model_policy_is_deleted() -> None:
    # Unlike the other retired projectile partials, this Common/Models path is
    # not in check_csharp_contracts.py's deleted-architecture file list.
    assert not (CS / "Common/Models/GeneratedChildSpecPolicy.cs").exists()


def test_generated_parent_summary_csharp_dto_matches_v2_delivery_surface() -> None:
    dto = _read("Common/Models/GeneratedItemData.Model.cs")
    start = dto.index("public sealed class GeneratedParentSummarySpec")
    end = dto.index("public sealed class GeneratedBuffSpec", start)
    summary = dto[start:end]
    for token in (
        'CurrentSchema = "infini.generated-parent-summary.v2"',
        "public string Schema", "public string Identity", "public string Description",
        "public string PlayerExperience", "public string[] NotableEffects",
        "public string RuntimePrimaryEntityId", "public string[] RuntimeEntityIds",
    ):
        assert token in summary
    for retired in (
        "Fantasy", "Category", "DamageClass", "Runtime {", "VisualIdentity",
        "BackedByClaims", "ParentComposition",
    ):
        assert retired not in summary

    registry = _read("Common/Services/GeneratedItemRegistryService.cs")
    prefilter = registry.split("private static bool CacheJsonTargetsCurrentWorld", 1)[1].split("private void PersistOne", 1)[0]
    for current_name in ('TryGetProperty("recipeMeta"', 'TryGetProperty("worldScoped"', 'TryGetProperty("worldId"'):
        assert current_name in prefilter
    for retired_name in ('TryGetProperty("RecipeMeta"', 'TryGetProperty("WorldScoped"', 'TryGetProperty("WorldId"'):
        assert retired_name not in prefilter


def test_generated_parent_reference_is_hydrated_or_rejected_at_combine_wire_boundary() -> None:
    client = _read("Common/Services/GeneratorClient.cs")
    start = client.index("private static object ToWireItem")
    end = client.index("private static Item CraftIdentityItem", start)
    wire = client[start:end]
    for token in (
        "GeneratedItemData.IsPlayerSaveReferenceOnly(existing)",
        "string generatedParentId = existing!.Id;",
        "registry.TryGet(generatedParentId, out GeneratedItemData canonical)",
        "GeneratedItemRegistryService.IsCurrentWorldData(canonical)",
        "existing = canonical;",
        'throw new InvalidOperationException($"Generated parent',
    ):
        assert token in wire
    assert wire.index("GeneratedItemData.IsPlayerSaveReferenceOnly(existing)") < wire.index("Item craftItem = CraftIdentityItem(item, existing)")


def test_release_timing_prompt_tokens_match_held_sprite_projection() -> None:
    release = CAPABILITY_REGISTRY["configure_item_use"].params["releaseTiming"]
    assert release.enum == ("", "immediate", "on_release", "after_charge")
    assert "presentation" in release.description
    draw = _read("Common/Players/GeneratedHeldItemDrawLayer.cs")
    assert 'releaseTiming != "immediate"' in draw
    assert 'releaseTiming == "instant"' not in draw
    assert 'releaseTiming == "early"' not in draw


def test_equipment_overlay_uses_only_explicit_equipment_capabilities() -> None:
    overlay = _read("Common/Players/GeneratedEquipOverlayDrawLayer.cs")
    assert "data.Accessory?.Enabled == true" in overlay
    assert "Gameplay?.Kind" not in overlay


def test_enabled_armor_rejects_an_unauthored_slot() -> None:
    model = _read("Common/Models/GeneratedItemData.Model.cs")
    normalize = _read("Common/Models/GeneratedItemData.Normalize.cs")
    assert 'public string Slot { get; set; } = "";' in model
    assert 'if (Armor.Enabled && Armor.Slot is not ("head" or "body" or "legs"))' in normalize
    assert 'Armor.Slot = "body";' not in normalize


def test_vfx_texture_role_reaches_runtime_sprite_cache_and_sprite_renderers() -> None:
    runtime = _read("Common/VFX/InfiniVfxRuntime.cs")
    visuals = _read("Content/Projectiles/GeneratedProjectile.Visuals.cs")
    model = _read("Common/Models/VfxManifestSpec.cs")
    assert "ResolveTexturePath(GeneratedItemData data, string entityId, string textureRole)" in runtime
    assert "InfiniCrafterLocalMod.Sprites.TryGet(texturePath, out float localForwardRadians)" in runtime
    assert "entity.VisualRole" in runtime
    assert "DrawSpriteTrail" in runtime
    assert "InfiniDetachedVfxSystem.Enqueue" in runtime
    assert "OnDetachedEvent" in runtime
    assert "InfiniVfxRuntime.Draw(Projectile, _data, _entity.Id," in visuals
    assert "sprite renderer requires a non-none textureRole" in model
    assert "impactSprite requires textureRole=impact" in model
    assert 'duplicate impactSprite entity' in model
