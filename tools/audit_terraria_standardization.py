#!/usr/bin/env python3
from __future__ import annotations

"""Machine gate for canonical Terraria/tModLoader integration boundaries."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "LocalGenerator"))

from infini_local.core.runtime_authoring.capability_registry import (  # noqa: E402
    CAPABILITY_REGISTRY,
    INPUT_KINDS,
)
from infini_local.core.runtime_authoring.terraria_vocabulary import (  # noqa: E402
    AMMO_CATEGORY_TMODLOADER_NAMES,
    DAMAGE_CLASS_TMODLOADER_NAMES,
    ITEM_USE_STYLE_TMODLOADER_NAMES,
    DAMAGE_CLASS_TOKEN_PATTERN,
    VANILLA_PROJECTILE_TYPE_ID_MAX,
)

OUTPUT = ROOT / "contracts" / "terraria_standardization_audit.generated.json"


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def report() -> dict[str, Any]:
    issues: list[dict[str, str]] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        if not ok:
            issues.append({"code": name, "message": detail})

    vocabulary = read("ModSources/InfiniCrafterLocal/Common/Models/TerrariaRuntimeVocabulary.cs")
    normalize = read("ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Normalize.cs")
    apply = read("ModSources/InfiniCrafterLocal/Common/Models/GeneratedItemData.Apply.cs")
    dto = read("ModSources/InfiniCrafterLocal/Common/Models/RuntimeProgramSpec.cs")
    projectile = read("ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.cs")
    executors = read("ModSources/InfiniCrafterLocal/Content/Projectiles/GeneratedProjectile.Executors.cs")
    transport = read("LocalGenerator/infini_local/pipelines/llm_transport.py")
    categories = read("LocalGenerator/infini_local/pipelines/result_identity_policy.py")
    image_config = read("LocalGenerator/infini_local/pipelines/pipeline_visual_config.py")
    vfx = read("ModSources/InfiniCrafterLocal/Common/VFX/InfiniVfxRuntime.cs")
    parent_cards = read("LocalGenerator/infini_local/pipelines/parent_context_cards.py")
    parent_constants = read("LocalGenerator/infini_local/pipelines/pipeline_runtime_constants.py")
    generator_client = read("ModSources/InfiniCrafterLocal/Common/Services/GeneratorClient.cs")
    generated_item = read("ModSources/InfiniCrafterLocal/Content/Items/GeneratedItem.cs")
    program_schema = read("LocalGenerator/infini_local/core/runtime_authoring/program_schema.py")

    for token, owner in DAMAGE_CLASS_TMODLOADER_NAMES.items():
        check(f"damage_class:{token}", f'"{token}" => {owner}' in vocabulary, f"{token} must map exactly to {owner}")
    for token, owner in ITEM_USE_STYLE_TMODLOADER_NAMES.items():
        check(f"use_style:{token}", f'"{token}" => {owner}' in vocabulary, f"{token} must map exactly to {owner}")
    for token, owner in AMMO_CATEGORY_TMODLOADER_NAMES.items():
        check(f"ammo_category:{token}", f'"{token}" => {owner}' in vocabulary, f"{token} must map exactly to {owner}")

    forbidden_loose_lookup = any(x in vocabulary + normalize for x in ("ResolveModded", '"rogue"', "?? DamageClass.Generic"))
    check("exact_damage_class_vocabulary", not forbidden_loose_lookup, "DamageClass mapping must use canonical built-ins or exact ModType.FullName without fallback")
    check("exact_modded_damage_class_lookup", "ModContent.TryFind<DamageClass>(exact" in vocabulary and "Unknown exact damageClass" in vocabulary, "modded DamageClass must use exact registered ModName/ClassName and fail closed")
    check("modded_damage_class_pattern", "CalamityMod/RogueDamageClass" and re.fullmatch(DAMAGE_CLASS_TOKEN_PATTERN, "CalamityMod/RogueDamageClass") is not None and re.fullmatch(DAMAGE_CLASS_TOKEN_PATTERN, "rogue") is None, "schema pattern must accept exact tModLoader FullName and reject loose aliases")
    check("old_damage_policy_deleted", not (ROOT / "ModSources/InfiniCrafterLocal/Common/Models/GeneratedDamageClassPolicy.cs").exists(), "open-ended legacy damage policy must stay deleted")
    check("old_effect_archetype_catalog_deleted", not (ROOT / "LocalGenerator/infini_local/core/effect_catalog.py").exists() and not (ROOT / "LocalGenerator/data/effect_archetypes.json").exists() and "ATTACK_PATTERN" not in read("LocalGenerator/infini_local/web/server.py"), "retired whole-weapon/effect aliases must not remain as a discoverable fallback architecture")
    check("canonical_damage_class_reverse_mapping", "CanonicalDamageClassToken" in vocabulary and "=> TerrariaRuntimeVocabulary.CanonicalDamageClassToken" in generator_client, "parent extraction must use the same canonical DamageClass vocabulary as runtime hydration")
    check("single_damage_class_parent_identity", "damageClassFullName" not in generator_client + parent_cards + parent_constants and '"modded"' not in generator_client and 'damage > 0 ? "generic" : "none"' not in generator_client, "parent facts must expose one exact damageClass token, never pseudo none/modded plus a duplicate field")
    check("modded_damage_class_case_preserved", "Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129);" in normalize and "Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129).ToLowerInvariant();" not in normalize and "DamageClass = RuntimeText.Safe(DamageClass, 129);" in dto and "DamageClass = RuntimeText.Safe(DamageClass, 129).ToLowerInvariant();" not in dto, "exact ModName/ClassName must preserve case and full bounded length across both DTO layers")
    check("canonical_parent_use_and_ammo_names", "CanonicalItemUseStyleToken" in vocabulary and "CanonicalAmmoCategoryToken" in vocabulary and all(x in generator_client for x in ("useStyleName = TerrariaRuntimeVocabulary.CanonicalItemUseStyleToken", "ammoCategoryName = TerrariaRuntimeVocabulary.CanonicalAmmoCategoryToken", "potion =", "notAmmo =")), "parent facts must carry exact canonical tModLoader names and independent potion/notAmmo flags")
    check("single_equipped_input", "passive" not in INPUT_KINDS and INPUT_KINDS == ("primary_use", "alternate_use", "hold", "equipped"), "Author API must expose one canonical equipped input")

    ammo = CAPABILITY_REGISTRY.get("configure_vanilla_ammo_item")
    check(
        "consumption_is_binding_scoped",
        "configure_consumption" not in CAPABILITY_REGISTRY
        and '"stackCost"' in program_schema
        and "public int StackCost { get; set; }" in dto,
        "stack cost must have one owner in binding.usePolicy and no capability/global shadow owner",
    )
    check("ammo_item_is_explicit", ammo is not None and tuple(ammo.params) == ("ammoCategory", "projectileId", "shootSpeedPxPerTick", "notAmmo"), "ammo item capability must author Item.ammo, Item.shoot and Item.notAmmo")
    check("ammo_item_consumption_independent", bool(ammo and not any(r.capability == "configure_consumption" for r in ammo.requirements)), "ammo stack handling must remain independent from direct-use input costs")
    check("ammo_projection_direct", "item.ammo = TerrariaRuntimeVocabulary.ResolveAmmoCategory" in apply and "item.shoot = Gameplay.AmmoProjectileId" in apply and "item.shootSpeed = Gameplay.AmmoShootSpeedPxPerTick" in apply and "item.notAmmo = Gameplay.NotAmmo" in apply, "ammo fields must project directly without category-derived projectile or runtime-entity speed leakage")
    check("ammo_shoot_speed_range_parity", ammo is not None and ammo.params["shootSpeedPxPerTick"].minimum == -20 and ammo.params["shootSpeedPxPerTick"].maximum == 80 and "Gameplay.AmmoShootSpeedPxPerTick = ClampFloat(Gameplay.AmmoShootSpeedPxPerTick, -20f, 80f);" in normalize, "ammo Item.shootSpeed contribution must preserve the exact Author range at the C# boundary")
    check("vanilla_projectile_id_guard", "Gameplay.AmmoProjectileId >= ProjectileID.Count" in normalize and VANILLA_PROJECTILE_TYPE_ID_MAX == 1021, "vanilla ammo projectile must be authored in stable 1..1021 and validated against ProjectileID.Count")
    check("no_plural_gameplay_ammo_alias", '"arrows"' not in apply + vocabulary and '"bullets"' not in apply + vocabulary, "plural ammo aliases are not canonical gameplay tokens")
    restore = CAPABILITY_REGISTRY.get("restore_resources_on_use")
    check("potion_flag_is_authored", restore is not None and tuple(restore.params) == ("healLife", "healMana", "potionSickness") and "item.potion = enabled && Gameplay.Potion;" in apply and "item.potion = Gameplay.HealLife > 0" not in apply, "Item.potion must be authored, binding-scoped, and not inferred from healing")
    check("generated_parent_preserves_exact_item_semantics", all(x in parent_cards for x in ('"potion"', '"usePolicy"', '"ammoCategory"', '"ammoProjectileId"', '"ammoShootSpeedPxPerTick"', '"notAmmo"')) and 'row.get("action")' not in parent_cards and 'row.get("target")' not in parent_cards, "generated parents must preserve exact binding usePolicy/ammo/potion facts for the next Author")
    check("loaded_rarity_guard", "RarityLoader.RarityCount" in normalize and "ClampInt(Gameplay.Rarity" not in normalize, "rarity must be an actually loaded ID, not silently clamped")
    check("loaded_buff_guards", "BuffLoader.BuffCount" in normalize and "BuffLoader.BuffCount" in dto and "extra buff row cannot be null" in normalize and "requires positive duration" in normalize and "buff.BuffCode > 0" in generated_item, "buff IDs and durations must fail closed against the loaded content registry")
    check("loaded_tile_wall_guards", "TileLoader.TileCount" in dto and "WallLoader.WallCount" in dto and "ClampInt(Gameplay.CreateTile" not in normalize and "ClampInt(Gameplay.CreateWall" not in normalize, "tile/wall IDs must be validated against loaded tModLoader content")
    tool = CAPABILITY_REGISTRY.get("configure_tool")
    stats = CAPABILITY_REGISTRY.get("configure_item_stats")
    axe = tool.params.get("axePowerTooltipPercent") if tool else None
    check("axe_tooltip_percent_parity", bool(
        tool and axe and "axePower" not in tool.params
        and axe.minimum == 0 and axe.maximum == 500 and axe.multiple_of == 5
        and axe.wire_name == "axePower" and axe.wire_divisor == 5
        and axe.to_wire(45) == 9
        and "Gameplay.AxePower = ClampInt(Gameplay.AxePower, 0, 100);" in normalize
    ), "Author axe tooltip percent must map exactly in steps of five to bounded Item.axe units")
    buff = CAPABILITY_REGISTRY.get("apply_generated_buff_on_use")
    regen = buff.params.get("lifeRegenHpPerSecond") if buff else None
    check("generated_buff_regen_half_hp_parity", bool(
        buff and regen and "lifeRegen" not in buff.params
        and regen.minimum == 0 and regen.maximum == 60 and regen.multiple_of == 0.5
        and regen.wire_name == "lifeRegen" and regen.wire_multiplier == 2
        and regen.to_wire(0.5) == 1
    ), "generated buff HP/s must map exactly by half-HP steps to Terraria lifeRegen units")
    check("item_value_semantics", bool(stats and "Item.value" in stats.params["valueCopper"].description and "resale" in stats.params["valueCopper"].description), "valueCopper must describe the exact Item.value field rather than pretending to be direct player resale value")

    collision = CAPABILITY_REGISTRY.get("set_projectile_collision")
    expected_collision = ("tileCollide", "ignoreWater", "bounceCount", "pierce", "extraUpdates", "npcImmunityMode", "localNpcHitCooldownTicks")
    check("explicit_projectile_collision", collision is not None and tuple(collision.params) == expected_collision, "projectile liquid and immunity semantics must be explicit")
    check("vanilla_projectile_defaults", "Projectile.ignoreWater = false;" in projectile and "Projectile.netImportant = false;" in projectile, "proxy SetDefaults must retain Terraria defaults until authored entity configuration")
    check("explicit_liquid_projection", "Projectile.ignoreWater = entity.Collision.IgnoreWater;" in projectile, "ignoreWater must come from authored collision data")
    check("explicit_immunity_projection", 'entity.Collision.NpcImmunityMode == "local"' in projectile and ": -2;" in projectile, "owner/local immunity must map to Terraria fields explicitly")
    check("no_id_static_immunity", "usesIDStaticNPCImmunity = true" not in projectile + executors, "ID-static immunity would leak across all generated entities sharing one proxy type")
    check("new_projectile_direct", "Projectile.NewProjectileDirect(" in projectile and "Projectile.NewProjectile(" not in projectile, "spawn path should use the official direct-return overload")
    check("held_projectile_static_set", "HeldProjDoesNotUsePlayerGfxOffY[Type] = true" in projectile, "shared held projectile type should use the stable held draw-offset set")
    check("owner_vector_sync", "SetOwnerSyncedVector" in executors and "minSyncIntervalTicks" in executors, "owner cursor vectors must be synced only on bounded meaningful changes")
    check("range_parity_spawn", "SpeedPxPerTick = Math.Clamp(SpeedPxPerTick, 0f, 80f);" in dto and "OffsetPx = Math.Clamp(OffsetPx, -128, 256);" in dto, "C# spawn clamps must match Author registry")
    check("range_parity_collision", "Pierce = Math.Clamp(Pierce, -1, 100);" in dto and "ExtraUpdates = Math.Clamp(ExtraUpdates, 0, 5);" in dto, "C# collision clamps must match Author registry")

    lowery = ROOT / "lowery.md"
    check("lowery_exists", lowery.is_file(), "root lowery.md must exist")
    if lowery.is_file():
        text = lowery.read_text(encoding="utf-8")
        for required in (
            "Gameplay Author-visible semantic aliases: **нет**",
            "Item.ammo",
            "Item.useAmmo",
            "GeneratedItem` и `GeneratedProjectile` — proxy-типы",
            "sand ammo не выставляется",
            "ID-static immunity не exposed",
            "VFX fallback palette",
            "ModName/ClassName",
            "effect_catalog.py",
            "псевдотокены `none`/`modded`",
        ):
            check(f"lowery:{required[:24]}", required in text, f"lowery.md missing guardrail: {required}")

    # Non-gameplay aliases remain intentionally finite and documented.
    check("provider_aliases_documented", all(x in transport for x in ('"openai", "openai_compat", "api", "remote"', '"local", "lmstudio", "lm_studio", "ollama", ""')), "documented provider aliases must match transport")
    check("image_backend_aliases_documented", all(x in image_config for x in ('"openai_compat_image": "image_api"', '"stable-diffusion.cpp": "sdcpp"', '"disabled": "off"')), "documented image backend aliases must match visual config")
    check("category_aliases_documented", all(x in categories for x in ('"placeable": "furniture"', '"trinket": "accessory"', '"thrown_stack": "consumable"')), "documented UI category aliases must match identity normalization")
    check("vfx_aliases_visual_only", all(x in vfx for x in ('"fire"', '"heat"', '"ice"', '"water"', '"electric"', '"lightning"')), "documented VFX aliases must remain confined to presentation color")

    total = len(checks)
    passed = sum(1 for row in checks if row["ok"])
    return {
        "schema": "infini.terraria-standardization-audit.v1",
        "ok": not issues,
        "score": passed,
        "scoreMax": total,
        "metrics": {
            "capabilities": len(CAPABILITY_REGISTRY),
            "canonicalDamageClasses": len(DAMAGE_CLASS_TMODLOADER_NAMES),
            "canonicalUseStyles": len(ITEM_USE_STYLE_TMODLOADER_NAMES),
            "canonicalAmmoCategories": len(AMMO_CATEGORY_TMODLOADER_NAMES),
            "authorInputs": len(INPUT_KINDS),
        },
        "checks": checks,
        "issues": issues,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    row = report()
    payload = json.dumps(row, ensure_ascii=False, indent=2) + "\n"
    if args.check:
        lowery_proc = subprocess.run([sys.executable, str(ROOT / "tools/generate_lowery.py"), "--check"], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        if lowery_proc.returncode:
            row["ok"] = False
            row["issues"].append({"code": "lowery_stale", "message": lowery_proc.stdout.strip()})
            payload = json.dumps(row, ensure_ascii=False, indent=2) + "\n"
        if OUTPUT.is_file() and OUTPUT.read_text(encoding="utf-8") != payload:
            print(f"[FAIL] stale {OUTPUT.relative_to(ROOT)}")
            return 1
        if not OUTPUT.is_file():
            print(f"[FAIL] missing {OUTPUT.relative_to(ROOT)}")
            return 1
        if not row["ok"]:
            print(payload)
            return 1
        print(f"[OK] Terraria standardization audit {row['score']}/{row['scoreMax']}")
        return 0
    if args.write or not args.check:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if row["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
