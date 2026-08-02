#!/usr/bin/env python3
"""Portable static gate for the v5 low-level generated runtime.

This is deliberately smaller than the historical weapon-family scanner. It
checks syntax-shaped invariants, the exact v5 DTO/executor seam, packet ids and
absence of deleted macro/family entry points. A real tModLoader build remains a
separate required gate when the SDK and game references are available.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ModSources" / "InfiniCrafterLocal"
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def read(relative: str) -> str:
    path = SRC / relative
    if not path.is_file():
        fail(f"missing C# source: {relative}")
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def stripped(text: str) -> str:
    text = re.sub(r'@"(?:[^"]|"")*"', '""', text, flags=re.S)
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text, flags=re.S)
    text = re.sub(r"//.*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def require(text: str, needle: str, owner: str) -> None:
    if needle not in text:
        fail(f"{owner}: missing `{needle}`")


def forbid(text: str, needle: str, owner: str) -> None:
    if needle in text:
        fail(f"{owner}: forbidden legacy token `{needle}`")


def check_balanced_sources() -> None:
    if not SRC.is_dir():
        fail(f"missing source root: {SRC}")
        return
    for path in sorted(SRC.rglob("*.cs")):
        text = stripped(path.read_text(encoding="utf-8", errors="ignore"))
        balance = 0
        for char in text:
            if char == "{":
                balance += 1
            elif char == "}":
                balance -= 1
                if balance < 0:
                    fail(f"{path.relative_to(ROOT)}: closing brace before opening brace")
                    break
        if balance:
            fail(f"{path.relative_to(ROOT)}: brace imbalance {balance:+d}")


def check_runtime_contract() -> None:
    dto = read("Common/Models/RuntimeProgramSpec.cs")
    data = read("Common/Models/GeneratedItemData.cs") + read("Common/Models/GeneratedItemData.Model.cs")
    normalize = read("Common/Models/GeneratedItemData.Normalize.cs")
    colors = read("Common/VFX/RuntimeColorPolicy.cs")
    limits = read("Common/InfiniRuntimeLimits.cs")
    vocabulary = read("Common/Models/TerrariaRuntimeVocabulary.cs")
    generator_client = read("Common/Services/GeneratorClient.cs")
    generated_item = read("Content/Items/GeneratedItem.cs")
    for needle in [
        'CurrentApiVersion = "infini.runtime-program.v5"',
        'CurrentWireSchema = "infini.runtime-program.wire.v3"',
        "public string PrimaryEntityId { get; set; }",
        "public string PrimaryOwner { get; set; }",
        "public string Role { get; set; }",
        "NormalizeAndValidate()",
        "exactly one item_body",
        "multiple exclusive owners",
        "runtime entity event cycle",
        "event spawn budget exceeded",
        "target_and_fire has no explicit shotEntityId",
        "active primary/alternate binding requires explicit configure_item_use",
        "binding.Role != expectedRole",
        "VisualRoleFor(string? value)",
        "visual roles must equal",
    ]:
        require(dto, needle, "RuntimeProgramSpec.cs")
    require(data, "JsonUnmappedMemberHandling.Disallow", "GeneratedItemData.cs")
    require(data, "RuntimeProgramSpec RuntimeProgram", "GeneratedItemData.cs")
    require(normalize, "RuntimeProgram.NormalizeAndValidate();", "GeneratedItemData.Normalize.cs")
    require(normalize, "ValidateBindingCapabilityProjection();", "GeneratedItemData.Normalize.cs")
    require(normalize, "apply_item_effects has no compiled item effect capability", "GeneratedItemData.Normalize.cs")
    require(dto, "place_item requires an exact placement payload", "RuntimeProgramSpec.cs")
    require(normalize, "equip_passive has no compiled accessory/armor capability", "GeneratedItemData.Normalize.cs")
    require(limits, "MaxRuntimeEntities", "InfiniRuntimeLimits.cs")
    require(limits, "MaxRuntimeChildDepth", "InfiniRuntimeLimits.cs")
    require(limits, "MaxRuntimeEventSpawns", "InfiniRuntimeLimits.cs")
    for token in [
        '"generic" => DamageClass.Generic',
        '"melee_no_speed" => DamageClass.MeleeNoSpeed',
        '"summon_melee_speed" => DamageClass.SummonMeleeSpeed',
        '"eat_food" => ItemUseStyleID.EatFood',
        '"drink_liquid" => ItemUseStyleID.DrinkLiquid',
        '"raise_lamp" => ItemUseStyleID.RaiseLamp',
        '"rocket" => AmmoID.Rocket',
        '"stynger_bolt" => AmmoID.StyngerBolt',
        'ModContent.TryFind<DamageClass>(exact',
        'Unknown exact damageClass',
        'throw new InvalidDataException',
    ]:
        require(vocabulary, token, "TerrariaRuntimeVocabulary.cs")
    for forbidden in ["ResolveModded", '"rogue"', "?? DamageClass.Generic"]:
        forbid(vocabulary + data + normalize, forbidden, "canonical Terraria vocabulary")
    require(vocabulary, "CanonicalDamageClassToken", "TerrariaRuntimeVocabulary.cs")
    require(generator_client, "=> TerrariaRuntimeVocabulary.CanonicalDamageClassToken", "GeneratorClient.cs")
    forbid(generator_client, "damageClassFullName", "GeneratorClient.cs")
    forbid(generator_client, 'return damageClass is null ? (damage > 0 ? "generic" : "none") : "modded"', "GeneratorClient.cs")
    require(normalize, "Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129);", "GeneratedItemData.Normalize.cs")
    forbid(normalize, "Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129).ToLowerInvariant();", "GeneratedItemData.Normalize.cs")
    require(dto, "DamageClass = RuntimeText.Safe(DamageClass, 129);", "RuntimeProgramSpec.cs")
    forbid(dto, "DamageClass = RuntimeText.Safe(DamageClass, 129).ToLowerInvariant();", "RuntimeProgramSpec.cs")
    require(colors, "public static string NormalizeRequired", "RuntimeColorPolicy.cs")
    forbid(normalize + dto, "RuntimeColorPolicy.Normalize(", "authoritative runtime color boundary")
    require(normalize, "NormalizeRequiredHexColor", "GeneratedItemData.Normalize.cs")
    forbid(normalize, "NormalizeHexColor(", "GeneratedItemData.Normalize.cs")
    for loaded_guard in ["RarityLoader.RarityCount", "BuffLoader.BuffCount", "extra buff row cannot be null", "requires positive duration"]:
        require(normalize, loaded_guard, "GeneratedItemData.Normalize.cs")
    for loaded_guard in ["TileLoader.TileCount", "WallLoader.WallCount"]:
        require(dto, loaded_guard, "RuntimeProgramSpec.cs")
    require(dto, "BuffLoader.BuffCount", "RuntimeProgramSpec.cs")
    require(dto, "BuffId <= 0", "RuntimeProgramSpec.cs")
    require(generated_item, "buff.BuffCode > 0", "GeneratedItem.cs")
    forbid(normalize, "ClampInt(Gameplay.Rarity", "GeneratedItemData.Normalize.cs")
    forbid(normalize, "ClampInt(Gameplay.CreateTile", "GeneratedItemData.Normalize.cs")
    forbid(normalize, "ClampInt(Gameplay.CreateWall", "GeneratedItemData.Normalize.cs")
    forbid(dto, 'public const string Passive = "passive"', "RuntimeProgramSpec.cs")
    require(normalize, "Gameplay.AmmoProjectileId >= ProjectileID.Count", "GeneratedItemData.Normalize.cs")
    apply = read("Common/Models/GeneratedItemData.Apply.cs")
    for needle in ["item.potion = enabled && Gameplay.Potion;", "item.notAmmo = Gameplay.NotAmmo;", "item.ammo = TerrariaRuntimeVocabulary.ResolveAmmoCategory", "item.shoot = Gameplay.AmmoProjectileId;", "item.shootSpeed = Gameplay.AmmoShootSpeedPxPerTick;"]:
        require(apply, needle, "GeneratedItemData.Apply.cs")
    forbid(apply, "item.potion = Gameplay.HealLife > 0", "GeneratedItemData.Apply.cs")
    require(apply, "RuntimeProgram.PrimaryOwner != RuntimeProgramSpec.ItemBodyOwner", "GeneratedItemData.Apply.cs")


def check_item_dispatch() -> None:
    item = read("Content/Items/GeneratedItem.cs") + read("Content/Items/GeneratedItem.UseStyle.cs")
    for needle in [
        "RuntimeInputKind.AlternateUse : RuntimeInputKind.PrimaryUse",
        "BindingForInput(RuntimeInputKind.AlternateUse)",
        "RuntimeProgramExecutor",
        "SpawnRuntimeEntity",
        "BindingUsesItemBodyContact(binding)",
        "UsePolicy.ContactDamage",
    ]:
        require(item, needle, "GeneratedItem v5 dispatch")
    for legacy in ["AttackSpec", "RuntimeFamily", "WeaponFamily", "AltUseMode", "perform_melee_attack", "shoot_projectile"]:
        forbid(item, legacy, "GeneratedItem v5 dispatch")


def check_projectile_dispatch() -> None:
    projectile = read("Content/Projectiles/GeneratedProjectile.cs")
    executors = read("Content/Projectiles/GeneratedProjectile.Executors.cs")
    events = read("Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs")
    net = read("Content/Projectiles/GeneratedProjectile.NetSync.cs")
    runtime = read("Common/Runtime/RuntimeProgramExecutor.cs")
    packet_ids = read("Common/InfiniNetPacketIds.cs")
    packet_router = read("InfiniCrafterLocal.cs")
    for needle in [
        "RuntimeEntitySpec? _entity",
        "SpawnRuntimeEntity(",
        "MaxRuntimeSpawnCount",
        "MaxChildDepth",
        "ShouldRunLocalPlayerAction",
        "Projectile.NewProjectileDirect(",
        "Projectile.ignoreWater = entity.Collision.IgnoreWater",
        'Projectile.usesLocalNPCImmunity = entity.Collision.NpcImmunityMode == "local"',
        "Projectile.netImportant = entity.IsOwnerAttached",
        "HeldProjDoesNotUsePlayerGfxOffY",
    ]:
        require(projectile, needle, "GeneratedProjectile.cs")
    require(executors, "switch (movement.Code)", "GeneratedProjectile.Executors.cs")
    require(executors, "Projectile.Kill();", "GeneratedProjectile.Executors.cs")
    require(executors, "RejectUnknownController", "GeneratedProjectile.Executors.cs")
    require(events, "RuntimeProgramExecutor.ExecuteAction", "GeneratedProjectile.RuntimeEvents.cs")
    require(events, "EmitAndSyncVfxEvent", "GeneratedProjectile.RuntimeEvents.cs")
    require(executors, "EmitAndSyncVfxEvent(RuntimeEventKind.ChannelComplete", "GeneratedProjectile.Executors.cs")
    require(projectile, "IsPrimaryRuntimeEntity", "GeneratedProjectile.cs")
    require(projectile, "PrimaryOwner == RuntimeProgramSpec.ProjectileOwner", "GeneratedProjectile.cs")
    require(projectile, "PrimaryEntityId", "GeneratedProjectile.cs")
    require(projectile, "owner.heldProj = Projectile.whoAmI;", "GeneratedProjectile.cs")
    forbid(executors, "owner.heldProj = Projectile.whoAmI;", "GeneratedProjectile.Executors.cs")
    require(runtime, "switch (action.ActionCode)", "RuntimeProgramExecutor.cs")
    require(runtime, "default:\n                return;", "RuntimeProgramExecutor.cs")
    for needle in [
        "RuntimeNetVersion",
        "public override void SendExtraAI",
        "public override void ReceiveExtraAI",
        "_generatedItemId.Length > 96",
        "_entityId.Length > 48",
        "Projectile.friendly = false",
        "HandleVfxEventSyncPacket",
        "BroadcastAuthoritativeVfxEvent",
        "Main.netMode != NetmodeID.MultiplayerClient",
        "GeneratedItemRegistryService",
        "InfiniVfxRuntime.OnDetachedEvent",
        "packet.Send(-1, Projectile.owner)",
    ]:
        require(net, needle, "GeneratedProjectile.NetSync.cs")
    require(packet_ids, "SyncGeneratedProjectileVfxEvent", "InfiniNetPacketIds.cs")
    require(packet_router, "GeneratedProjectile.HandleVfxEventSyncPacket(reader, whoAmI)", "InfiniCrafterLocal.cs")
    for legacy in ["AttackSpec", "RuntimeFamily", "WeaponFamily", "GeneratedChildSpecPolicy", "GeneratedRuntimeFamilyPolicy"]:
        forbid(projectile + executors + events + net + runtime, legacy, "projectile v5 runtime")


def check_visual_vfx_contract() -> None:
    visual = read("Content/Projectiles/GeneratedProjectile.Visuals.cs")
    manifest = read("Common/Models/VfxManifestSpec.cs")
    runtime_dto = read("Common/Models/RuntimeProgramSpec.cs")
    renderer_registry = read("Common/VFX/VfxRendererRegistry.cs")
    vocabulary = read("Common/VFX/VfxCanonicalVocabulary.cs")
    runtime = read("Common/VFX/InfiniVfxRuntime.cs")
    require(visual, "_entity!.Visual", "GeneratedProjectile.Visuals.cs")
    require(manifest, "JsonUnmappedMemberHandling.Disallow", "VfxManifestSpec.cs")
    require(manifest, "EntityId", "VfxManifestSpec.cs")
    require(manifest, "Event", "VfxManifestSpec.cs")
    require(runtime, "entityId", "InfiniVfxRuntime.cs")
    require(runtime, "eventName", "InfiniVfxRuntime.cs")
    require(runtime, "InfiniVfxSlotEmissionKey", "InfiniVfxRuntime.cs")
    require(runtime, "slot.Id", "InfiniVfxRuntime.cs")
    require(
        runtime_dto,
        'AssetMode is not ("baked_sprite" or "reuse_item_icon" or "runtime_geometry" or "no_asset")',
        "RuntimeEntityVisualSpec",
    )
    require(manifest, 'Layer = ExactEnumText(Layer, "layer", "BeforeProjectiles", "AfterProjectiles");', "VfxManifestSpec.cs")
    forbid(manifest, "private static string EnumText(", "VfxManifestSpec.cs")
    for dead in [
        "public string Curve", "public int Variant", "public string Importance",
        "EstimateDrawCost(", "NormalizeKindName(", "NormalizeEventGroup(",
        "public static string Curve(", "public static string Importance(",
    ]:
        forbid(manifest + renderer_registry + vocabulary, dead, "dead VFX contract")
    for legacy in ["RuntimeFamily", "WeaponFamily", "AttackSpec"]:
        forbid(visual + manifest + runtime, legacy, "entity/event VFX")


def check_deleted_architecture() -> None:
    forbidden_files = [
        "Content/Projectiles/GeneratedProjectile.Runtime.cs",
        "Content/Projectiles/GeneratedProjectile.Impact.cs",
        "Content/Projectiles/GeneratedProjectile.ChargeRelease.cs",
        "Content/Projectiles/GeneratedProjectile.Sentry.cs",
        "Content/Projectiles/GeneratedProjectile.OverheadBarrage.cs",
        "Content/Projectiles/GeneratedChildSpecPolicy.cs",
        "Common/Models/GeneratedRuntimeFamilyPolicy.cs",
        "Common/Models/GeneratedSecondaryTriggerPolicy.cs",
        "Content/Items/GeneratedItem.Sentry.cs",
    ]
    for relative in forbidden_files:
        if (SRC / relative).exists():
            fail(f"legacy C# file still active: {relative}")
    active = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in sorted(SRC.rglob("*.cs"))
        if p.name != "GeneratedItemData.Normalize.cs"
    )
    for legacy in [
        "GeneratedRuntimeFamilyPolicy",
        "GeneratedChildSpecPolicy",
        "HandleProjectileVisualSyncPacket",
        "HandleProjectileVfxEventSyncPacket",
        "FlushPendingProjectileVisualSyncForGeneratedItem",
        "FlushPendingVfxEventsForGeneratedItem",
    ]:
        forbid(active, legacy, "active C# source")


def check_packet_ids() -> None:
    packet_source = read("Common/InfiniNetPacketIds.cs")
    values = re.findall(r"public const byte\s+(\w+)\s*=\s*(\d+)\s*;", packet_source)
    seen: dict[int, str] = {}
    for name, raw in values:
        value = int(raw)
        if value in seen:
            fail(f"packet id collision: {name} and {seen[value]} both use {value}")
        seen[value] = name


def main() -> int:
    check_balanced_sources()
    check_runtime_contract()
    check_item_dispatch()
    check_projectile_dispatch()
    check_visual_vfx_contract()
    check_deleted_architecture()
    check_packet_ids()
    if ERRORS:
        print("[FAIL] C# v5 contract scanner found issues:")
        for message in ERRORS:
            print(" -", message)
        return 1
    print("[OK] C# v5 low-level runtime contract scanner passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
