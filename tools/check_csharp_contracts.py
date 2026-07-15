#!/usr/bin/env python3
"""Lightweight static C# compile/contract scanner for the local tModLoader mod.

This is not a Roslyn/tModLoader build.  It is a portable compile-surface test
for this container: it catches common regressions from manual C# edits such as
brace imbalance, missing obvious using directives, wrong tML override signatures,
missing partial/executor targets, packet-id collisions, and generated contract
property drift.  On a real dev machine, run tools/try_tml_build_check.py with an
explicit csproj/tML setup for an actual compiler invocation.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ModSources" / "InfiniCrafterLocal"
ERRORS: list[str] = []


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def read_bundle(pattern: str) -> str:
    return "\n".join(read(path) for path in sorted(SRC.glob(pattern)) if path.exists())


def read_projectile_bundle() -> str:
    return read_bundle("Content/Projectiles/GeneratedProjectile*.cs")


def read_generated_item_data_bundle() -> str:
    return read_bundle("Common/Models/GeneratedItemData*.cs")


def read_player_bundle() -> str:
    return read_bundle("Common/Players/InfiniCraftPlayer*.cs")


def err(msg: str) -> None:
    ERRORS.append(msg)


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def strip_comments_and_strings(text: str) -> str:
    text = re.sub(r'@"(?:[^"]|"")*"', '""', text, flags=re.S)
    text = re.sub(r'"(?:\\.|[^"\\])*"', '""', text, flags=re.S)
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return text


def has_using(text: str, namespace: str) -> bool:
    return re.search(r"^\s*using\s+" + re.escape(namespace) + r"\s*;", text, flags=re.M) is not None


def token(clean: str, name: str) -> bool:
    return re.search(r"\b" + re.escape(name) + r"\b", clean) is not None


def check_braces(path: Path, text: str) -> None:
    clean = strip_comments_and_strings(text)
    bal = 0
    for ch in clean:
        if ch == "{":
            bal += 1
        elif ch == "}":
            bal -= 1
            if bal < 0:
                err(f"{rel(path)}: closing brace before opening brace")
                return
    if bal != 0:
        err(f"{rel(path)}: brace imbalance {bal:+d}")


def check_required_usings(path: Path, text: str) -> None:
    clean = strip_comments_and_strings(text)
    if (token(clean, "BinaryWriter") or token(clean, "BinaryReader") or token(clean, "InvalidDataException")) and not has_using(text, "System.IO") and "System.IO." not in clean:
        err(f"{rel(path)}: uses BinaryReader/BinaryWriter/InvalidDataException without System.IO")
    if (token(clean, "List") or token(clean, "Dictionary") or token(clean, "HashSet") or token(clean, "IEnumerable")) and not has_using(text, "System.Collections.Generic"):
        err(f"{rel(path)}: uses generic collections without System.Collections.Generic")
    if re.search(r"\.Select\s*\(|\.Where\s*\(|\.ToArray\s*\(|\.OrderBy|\.Count\s*\(", clean) and not has_using(text, "System.Linq"):
        err(f"{rel(path)}: uses LINQ extension methods without System.Linq")
    if (re.search(r"\b(?:Vector2|Rectangle)\b", clean) or re.search(r"\bColor\s+(?:\w+|\?)|new\s+Color\s*\(|Color\.", clean)) and not has_using(text, "Microsoft.Xna.Framework") and "Microsoft.Xna.Framework." not in clean:
        err(f"{rel(path)}: uses XNA framework structs without Microsoft.Xna.Framework")
    if (token(clean, "Texture2D") or token(clean, "SpriteBatch")) and not has_using(text, "Microsoft.Xna.Framework.Graphics") and "Microsoft.Xna.Framework.Graphics." not in clean:
        err(f"{rel(path)}: uses graphics types without Microsoft.Xna.Framework.Graphics")
    if token(clean, "Keys") and not has_using(text, "Microsoft.Xna.Framework.Input"):
        err(f"{rel(path)}: uses Keys without Microsoft.Xna.Framework.Input")
    if (token(clean, "TagCompound") or token(clean, "ItemIO")) and not has_using(text, "Terraria.ModLoader.IO"):
        err(f"{rel(path)}: uses TagCompound/ItemIO without Terraria.ModLoader.IO")
    if (token(clean, "SoundEngine") or token(clean, "SoundStyle")) and not has_using(text, "Terraria.Audio") and "Terraria.Audio." not in clean:
        err(f"{rel(path)}: uses Terraria audio types without Terraria.Audio")
    if token(clean, "EntitySource_ItemUse_WithAmmo") and not has_using(text, "Terraria.DataStructures"):
        err(f"{rel(path)}: uses EntitySource_ItemUse_WithAmmo without Terraria.DataStructures")


def required(path: Path, text: str, needle: str) -> None:
    if needle not in text:
        err(f"{rel(path)}: missing `{needle}`")


def method_names(text: str) -> set[str]:
    clean = strip_comments_and_strings(text)
    pattern = re.compile(
        r"\b(?:public|private|protected|internal)\s+"
        r"(?:override\s+|static\s+|sealed\s+|virtual\s+|async\s+|new\s+)*"
        r"[\w<>,\.\?\[\]\s]+?\s+"
        r"(\w+)\s*\(([^()]*)\)",
        re.M,
    )
    return {name for name, _ in pattern.findall(clean)}


def class_block(text: str, class_name: str) -> str:
    marker = re.search(r"\bclass\s+" + re.escape(class_name) + r"\b", text)
    if not marker:
        return ""
    start = text.find("{", marker.end())
    if start < 0:
        return ""
    bal = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            bal += 1
        elif text[i] == "}":
            bal -= 1
            if bal == 0:
                return text[start + 1:i]
    return ""


def class_property_names(text: str, class_name: str) -> set[str]:
    body = class_block(text, class_name)
    props = set(re.findall(r"\bpublic\s+[\w<>,\.\?\[\]\s]+?\s+(\w+)\s*\{\s*get\s*;", body))
    fields = set(re.findall(r"\bpublic\s+[\w<>,\.\?\[\]\s]+?\s+(\w+)\s*(?:=|;)", body))
    expr = set(re.findall(r"\bpublic\s+[\w<>,\.\?\[\]\s]+?\s+(\w+)\s*=>", body))
    return props | fields | expr


def method_block(text: str, method_name: str) -> str:
    marker = re.search(r"\b" + re.escape(method_name) + r"\s*\(", text)
    if not marker:
        return ""
    start = text.find("{", marker.end())
    if start < 0:
        return ""
    bal = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            bal += 1
        elif text[i] == "}":
            bal -= 1
            if bal == 0:
                return text[start + 1:i]
    return ""


def check_generated_item(text: str) -> None:
    path = SRC / "Content/Items/GeneratedItem.cs"
    for needle in [
        "public override bool AltFunctionUse(Player player)",
        "public override bool CanUseItem(Player player)",
        "public override bool ConsumeItem(Player player)",
        "public override bool? UseItem(Player player)",
        "public override void HoldItem(Player player)",
        "public override void UpdateAccessory(Player player, bool hideVisual)",
        "public override void UpdateEquip(Player player)",
        "public override bool IsArmorSet(Item head, Item body, Item legs)",
        "public override void UpdateArmorSet(Player player)",
        "public override bool Shoot(Player player, EntitySource_ItemUse_WithAmmo source, Vector2 position, Vector2 velocity, int type, int damage, float knockback)",
    ]:
        required(path, text, needle)
    for needle in [
        "UseBlockedReason(Player player)",
        "ShowLocalUseFeedback",
        "_lastUseBlockedNoticeTick",
        "_lastAltUseBlockedNoticeTick",
        "GeneratedItemData data = Data ?? GeneratedItemData.Placeholder()",
        "UseConditionSummary(gameplay)",
        "CompactGeneratedCombatSummary(data)",
        "modPlayer.LastGeneratedMobilityFailureMessage",
        "Mobility cooldown:",
    ]:
        required(path, text, needle)
    if "ItemID.Sets.ExtractinatorMode[Type]" in text:
        err("GeneratedItem.cs: shared GeneratedItem must not enable ExtractinatorMode globally")
    if "public override void ExtractinatorUse" in text:
        err("GeneratedItem.cs: per-instance extractinator output is unsupported because the tML hook is not instanced")


def check_projectile(text: str) -> None:
    path = SRC / "Content/Projectiles/GeneratedProjectile.cs"
    for needle in [
        "public sealed partial class GeneratedProjectile",
        "public override void SendExtraAI(BinaryWriter writer)",
        "public override void ReceiveExtraAI(BinaryReader reader)",
        "public override bool OnTileCollide(Vector2 oldVelocity)",
        "public override bool? Colliding(Rectangle projHitbox, Rectangle targetHitbox)",
        "public override void ModifyDamageHitbox(ref Rectangle hitbox)",
        "public override void OnHitNPC(NPC target, NPC.HitInfo hit, int damageDone)",
        "public override bool PreDraw(ref Color lightColor)",
        "public override void OnKill(int timeLeft)",
        "RunMovementExecutor(movement)",
        "InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)",
    ]:
        required(path, text, needle)
    if "_burstVisualTimer" in text:
        err("GeneratedProjectile.cs: remove unused _burstVisualTimer field; tML build reports CS0169")


def check_executor_split(text: str) -> None:
    path = SRC / "Content/Projectiles/GeneratedProjectile.Executors.cs"
    for needle in ["ProjectileRuntimeContext", "IGeneratedProjectileRuntimeExecutor", "FlailExecutor", "YoyoExecutor", "WhipExecutor"]:
        required(path, text, needle)
    if "ImpactBlinkExecutor" in text or "CanRun(ProjectileRuntimeContext context) => false" in text:
        err("GeneratedProjectile.Executors.cs: dead ImpactBlinkExecutor/no-op executor must stay removed")
    main_methods = method_names(read_projectile_bundle())
    for target in re.findall(r"\b(?:p|projectile)\.(\w+)\s*\(", strip_comments_and_strings(text)):
        if target not in main_methods:
            err(f"GeneratedProjectile.Executors.cs: executor calls missing GeneratedProjectile method `{target}`")


def check_player(text: str) -> None:
    path = SRC / "Common/Players/InfiniCraftPlayer.cs"
    for needle in [
        "public override void SyncPlayer(int toWho, int fromWho, bool newPlayer)",
        "public override void CopyClientState(ModPlayer targetCopy)",
        "public override void SendClientChanges(ModPlayer clientPlayer)",
        "public override void PostUpdate()",
    ]:
        required(path, text, needle)
    for needle in [
        "GeneratedMobilityCooldownTicks",
        "GeneratedMobilityCooldownSeconds",
        "LastGeneratedMobilityFailureMessage",
        "UnsupportedGeneratedMobility",
        "Unsafe blink destination",
    ]:
        required(path, text, needle)


def check_packet_ids() -> None:
    text = "\n".join(read(p) for p in SRC.rglob("*.cs"))
    ids = re.findall(r"public\s+const\s+byte\s+(\w+)\s*=\s*(\d+)", text)
    by_value: dict[str, list[str]] = {}
    for name, value in ids:
        by_value.setdefault(value, []).append(name)
    for value, names in by_value.items():
        if len(names) > 1:
            err(f"packet id collision {value}: {', '.join(names)}")


def check_visual_server_guards() -> None:
    for path in SRC.rglob("*.cs"):
        text = read(path)
        if "Lighting.AddLight" not in text:
            continue
        if "Main.netMode != NetmodeID.Server" not in text and "Main.netMode == NetmodeID.Server" not in text and "ShouldRunVisuals" not in text:
            err(f"{rel(path)}: Lighting.AddLight appears without any dedicated-server guard")


def check_model_property_references() -> None:
    model = read_generated_item_data_bundle()
    gameplay = class_property_names(model, "GameplaySpec")
    attack = class_property_names(model, "AttackSpec")
    accessory = class_property_names(model, "AccessorySpec")
    armor = class_property_names(model, "ArmorSpec")
    visual = class_property_names(model, "VisualSpec")
    runtime_state = class_property_names(model, "RuntimeStateSpec")
    state_meter = class_property_names(model, "StateMeterSpec")
    triggered_action = class_property_names(model, "TriggeredActionSpec")
    rejected_call = class_property_names(model, "RejectedEngineCallSpec")

    item = strip_comments_and_strings(read(SRC / "Content/Items/GeneratedItem.cs"))
    projectile = strip_comments_and_strings(read_projectile_bundle())

    # Direct generated contract references are compile-sensitive. Avoid broad local
    # variable names such as `a` or `gp` unless they are inside a tiny known block.
    for prop in re.findall(r"Data\.Gameplay\?*\.([A-Z]\w+)", item):
        if prop not in gameplay:
            err(f"GeneratedItem.cs: Data.Gameplay.{prop} is not declared in GameplaySpec")
    for prop in re.findall(r"Data\.Attack\?*\.([A-Z]\w+)", item + projectile):
        if prop not in attack:
            err(f"GeneratedItem/Projectile: Data.Attack.{prop} is not declared in AttackSpec")
    for prop in re.findall(r"Data\.Accessory\?*\.([A-Z]\w+)", item):
        if prop not in accessory:
            err(f"GeneratedItem.cs: Data.Accessory.{prop} is not declared in AccessorySpec")
    for prop in re.findall(r"Data\.Armor\?*\.([A-Z]\w+)", item):
        if prop not in armor:
            err(f"GeneratedItem.cs: Data.Armor.{prop} is not declared in ArmorSpec")
    for prop in re.findall(r"Data\.Visual\?*\.([A-Z]\w+)", item + projectile):
        if prop not in visual:
            err(f"GeneratedItem/Projectile: Data.Visual.{prop} is not declared in VisualSpec")

    summary_body = item[item.find("private string AccessorySummary") : item.find("public override bool AltFunctionUse")]
    for prop in re.findall(r"\ba\.([A-Z]\w+)", summary_body):
        if prop not in accessory:
            err(f"GeneratedItem.cs: AccessorySummary uses missing AccessorySpec.{prop}")

    update_accessory_body = item[item.find("public override void UpdateAccessory") : item.find("public override Vector2? HoldoutOffset")]
    for prop in re.findall(r"\ba\.([A-Z]\w+)", update_accessory_body):
        if prop not in accessory:
            err(f"GeneratedItem.cs: UpdateAccessory uses missing AccessorySpec.{prop}")

    armor_effect_body = item[item.find("private static void ApplyGeneratedArmorEffects") : item.find("public override bool IsArmorSet")]
    for prop in re.findall(r"\ba\.([A-Z]\w+)", armor_effect_body):
        if prop not in armor:
            err(f"GeneratedItem.cs: ApplyGeneratedArmorEffects uses missing ArmorSpec.{prop}")

    armor_set_body = item[item.find("public override void UpdateArmorSet") : item.find("public override void UpdateAccessory")]
    for prop in re.findall(r"\ba\.([A-Z]\w+)", armor_set_body):
        if prop not in armor:
            err(f"GeneratedItem.cs: UpdateArmorSet uses missing ArmorSpec.{prop}")

    # Explicit runtime fields that must exist after recent patches.
    for required_prop in ["GeneratedBuff", "AltGeneratedBuff", "HoldGeneratedBuff", "MobilityMode", "AltMobilityMode", "HoldLightStrength", "RuntimeState", "RejectedEngineCalls", "ConsumeChancePercent", "ChannelUse", "HeldVisibility", "ReleaseTiming", "HandPose", "InitialOffsetPx"]:
        if required_prop not in gameplay:
            err(f"GameplaySpec missing `{required_prop}`")
    for required_prop in ["DamageClass", "RuntimeLightStrength", "MobilityMode", "AoeDamageRadiusPx", "ImpactVfxRadiusPx", "ContactForgivenessPx", "SoundUseCatalogId", "SoundImpactCatalogId", "SoundPitchVariance", "ChargeTicks", "ChargePowerMultiplier", "SentryPlacement", "SentryAttackIntervalTicks", "SentryTargetRangeTiles", "SentryLifetimeTicks", "SecondaryLifetimeTicks"]:
        if required_prop not in attack:
            err(f"AttackSpec missing `{required_prop}`")
    for required_prop in ["Enabled", "LightStrength", "LightColorName", "MovementSpeed", "JumpSpeed", "MinionSlots", "SentrySlots", "ManaCostReduction", "AmmoSaveChance", "Aggro", "Endurance", "ArmorPenetration"]:
        if required_prop not in accessory:
            err(f"AccessorySpec missing `{required_prop}`")
    for required_prop in ["Enabled", "Slot", "SetKey", "Archetype", "Defense", "MaxLife", "MaxMana", "LifeRegen", "ManaRegen", "MovementSpeed", "MaxRunSpeed", "JumpSpeed", "GenericDamage", "MeleeDamage", "RangedDamage", "MagicDamage", "SummonDamage", "GenericCrit", "AttackSpeed", "Knockback", "FallDamageImmune", "LavaImmune", "WaterWalk", "MinionSlots", "SentrySlots", "ManaCostReduction", "AmmoSaveChance", "Aggro", "Endurance", "ArmorPenetration", "WhipRange", "SummonTagDamage", "LightStrength", "LightColorName", "SetBonusText", "SetBonusGenericDamage", "SetBonusMeleeDamage", "SetBonusRangedDamage", "SetBonusMagicDamage", "SetBonusSummonDamage", "SetBonusGenericCrit", "SetBonusMovementSpeed", "SetBonusLifeRegen", "SetBonusManaRegen", "SetBonusMinionSlots", "SetBonusSentrySlots", "SetBonusManaCostReduction", "SetBonusAmmoSaveChance", "SetBonusAggro", "SetBonusEndurance", "SetBonusArmorPenetration"]:
        if required_prop not in armor:
            err(f"ArmorSpec missing `{required_prop}`")
    for required_prop in ["ExecutionStatus", "StateMeters", "TriggeredActions"]:
        if required_prop not in runtime_state:
            err(f"RuntimeStateSpec missing `{required_prop}`")
    for required_prop in ["Id", "MaxValue", "GainOnHit", "SpendOnAltUse"]:
        if required_prop not in state_meter:
            err(f"StateMeterSpec missing `{required_prop}`")
    for required_prop in ["Trigger", "Action", "MeterId", "RequiredValue", "SpendValue"]:
        if required_prop not in triggered_action:
            err(f"TriggeredActionSpec missing `{required_prop}`")
    for required_prop in ["Fn", "Reason", "Policy"]:
        if required_prop not in rejected_call:
            err(f"RejectedEngineCallSpec missing `{required_prop}`")


def check_generated_item_data_authoring_preservation_contract() -> None:
    model_path = SRC / "Common/Models/GeneratedItemData.cs"
    model = read_generated_item_data_bundle()
    if "[JsonExtensionData]" not in model or "Dictionary<string, JsonElement> ExtensionData" not in model:
        err("GeneratedItemData.cs: missing JsonExtensionData extension bag for local authoring/debug round-trip")
    if "clone.ExtensionData.Clear();" not in model:
        err("GeneratedItemData.cs: StripBulkForTransport must clear ExtensionData before network/player-save payloads")
    if "public string ToLocalCacheJson()" not in model or "return ToJson();" not in model:
        err("GeneratedItemData.cs: missing explicit full local cache JSON contract")
    for future_prop in ["HeldVisibility", "ReleaseTiming", "HandPose", "InitialOffsetPx"]:
        if future_prop not in model:
            err(f"GeneratedItemData.cs: missing executable runtime-affordance field GameplaySpec.{future_prop}")



def check_projectile_child_runtime_guards() -> None:
    path = SRC / "Content/Projectiles/GeneratedProjectile.cs"
    projectile = read_projectile_bundle()
    required(path, projectile, "private int RuntimeChildCount(int requested)")
    required(path, projectile, "private bool CanRunChildEffect(bool rootOnly = false)")
    required(path, projectile, "private void SpawnChild(Vector2 center, Vector2 velocity, int damage, AttackSpec childSpec, float depth, int ignoreNpc = -1)")
    for needle in [
        "InfiniRuntimeAuthority.ShouldRunProjectileGameplay(Projectile)",
        "if (rootOnly && depth > 0.001f)",
        "return depth < Math.Max(0, _spec.MaxChildDepth);",
        "if (depth > Math.Max(0, _spec.MaxChildDepth)) return;",
        "CountOwnedGeneratedProjectiles(rootId) >= Math.Max(0, _spec.MaxChildProjectiles)",
        "RemainingGameplayChildBudget()",
        "return Math.Clamp(requested, 1, remaining);",
        "MaxChildProjectiles = Math.Max(4, _spec.MaxChildProjectiles / 2)",
        "MaxChildDepth = Math.Max(0, _spec.MaxChildDepth - 1)",
    ]:
        required(path, projectile, needle)
    if "Projectile.localAI[1] > 1f" in projectile or "Projectile.localAI[1] > 0f" in projectile:
        err("GeneratedProjectile.cs: child depth must use CanRunChildEffect/SpawnChild guard, not per-effect localAI thresholds")
    if "movement == 6" in projectile or "movement == 14" in projectile or "movement == 16" in projectile:
        err("GeneratedProjectile.cs: bounce budget must not be bypassed by movement-code special cases")

    chain_marker = "private void ChainProjectiles"
    if chain_marker in projectile:
        chain_body = projectile.split(chain_marker, 1)[1].split("private void", 1)[0]
        if "count = RuntimeChildCount(count);" not in chain_body:
            err("GeneratedProjectile.cs: ChainProjectiles must clamp chain count through RuntimeChildCount before the loop")

    for method_name in ["MiniMissiles", "VortexSpawn"]:
        marker = f"private void {method_name}"
        if marker not in projectile:
            err(f"GeneratedProjectile.cs: missing `{marker}`")
            continue
        body = projectile.split(marker, 1)[1].split("private void", 1)[0]
        if "CanRunChildEffect(rootOnly: true)" not in body:
            err(f"GeneratedProjectile.cs: {method_name} must stay root-only to avoid recursive child spam")
    spawn_body = projectile.split("private void SpawnChild", 1)[1].split("private bool SpawnPersistentVfxOverlay", 1)[0]
    if "Projectile.owner != Main.myPlayer" not in spawn_body:
        err("GeneratedProjectile.cs: SpawnChild must stay local-owner gated")
    if "Main.projectile[idx].netUpdate = true;" not in spawn_body:
        err("GeneratedProjectile.cs: SpawnChild must netUpdate spawned generated child projectiles")
    if "gp.BroadcastVisualSync();" not in spawn_body:
        err("GeneratedProjectile.cs: SpawnChild must broadcast compact visual sync for remote child sprites")

def check_vfx_audio_presentation_guards() -> None:
    vfx_path = SRC / "Common/VFX/InfiniVfxRuntime.cs"
    projectile_path = SRC / "Content/Projectiles/GeneratedProjectile.cs"
    library_path = SRC / "Common/Audio/InfiniSoundLibrary.cs"
    bridge_path = SRC / "Common/Audio/InfiniLuminanceSoundBridge.cs"
    future_path = SRC / "Common/Audio/InfiniFutureSoundCatalog.cs"
    model_path = SRC / "Common/Models/GeneratedItemData.cs"
    vfx = read(vfx_path)
    projectile = read_projectile_bundle()
    library = read(library_path)
    bridge = read(bridge_path)
    future = read(future_path)
    model = read_generated_item_data_bundle()
    for needle in [
        "private static bool SoundSlotTickAllowed",
        "InfiniLuminanceSoundBridge.TryUpdateLiveSoundCue",
        "SoundSlotTickAllowed(slot, state.Tick)",
        "spec.SoundUseCatalogId",
        "spec.SoundImpactCatalogId",
        "spec.SoundVolume",
        "spec.SoundPitch",
        "InfiniSoundLibrary.ForVfxCue",
        "private static int DustForEffect(AttackSpec spec)",
        "int code = spec?.EffectCode ?? -1;",
        "DustID.YellowStarDust",
    ]:
        required(vfx_path, vfx, needle)
    for needle in [
        "private int _lastImpactSoundLocalTick = -9999;",
        "localTick - _lastImpactSoundLocalTick < 4",
        "InfiniSoundLibrary.ForImpact",
        "_spec.SoundVolume",
        "_spec.SoundPitch",
    ]:
        required(projectile_path, projectile, needle)
    for needle in [
        "public const string ContractVersion = \"infini.terraria-sound-catalog.v8\";",
        "public const string BuiltInCatalogSource = \"terraria_vanilla\";",
        "private static readonly IReadOnlyDictionary<string, SoundStyle> BuiltInCatalog",
        "public static int BuiltInCatalogCount => BuiltInCatalog.Count;",
        "public static SoundStyle ForUse",
        "public static SoundStyle ForImpact",
        "public static SoundStyle ForVfxCue",
        "TryResolveBuiltIn",
        "FallbackUse",
        "FallbackImpact",
        "StyleFromCodes",
        '["melee_energy_slash"] = SoundID.Item60',
        '["sniper_heavy"] = SoundID.Item40',
        '["laser_space"] = SoundID.Item157',
        '["magic_spectral"] = SoundID.Item124',
        '["summon_lightning"] = SoundID.Item123',
        '["impact_electric"] = SoundID.Item94',
        '["impact_void"] = SoundID.Item113',
        '["impact_portal"] = SoundID.Item78',
        "style.Volume * authoredVolumeScale * volumeScale",
        "style.Pitch + authoredPitch + pitchJitter",
        "Math.Max(style.PitchVariance, authoredPitchVariance)",
        "Pitch = pitch",
        "PitchVariance = safeVariance",
        "InfiniFutureSoundCatalog.TryResolveOneShot",
    ]:
        required(library_path, library, needle)
    catalog_pairs = re.findall(r'^\s*\[\"([a-z0-9_]+)\"\]\s*=\s*SoundID\.(Item\d+)', library, flags=re.M)
    if len(catalog_pairs) < 85:
        err(f"{rel(library_path)}: exact built-in sound catalog is too small ({len(catalog_pairs)} < 85)")
    unique_sound_ids = {sound_id for _, sound_id in catalog_pairs}
    if len(unique_sound_ids) < 65:
        err(f"{rel(library_path)}: catalog collapses into too few actual SoundIDs ({len(unique_sound_ids)} < 65)")
    for stale in [
        "KnownProfiles", "HasAny(", "StyleFromRangedText", "StyleFromMagicText",
        "StyleFromMeleeText", "StyleFromSummonText", "StyleFromMaterialOrEffectText",
        "terra_blade", "last_prism", "starfury", "stardust_dragon",
    ]:
        haystack = library.lower() if stale == stale.lower() else library
        if stale in haystack:
            err(f"{rel(library_path)}: stale keyword/weapon sound router `{stale}`")
    if (SRC / "Common/Audio/InfiniExternalSoundPack.cs").exists():
        err("InfiniExternalSoundPack.cs: removed in v0.4.190; do not re-add fixed sound-pack bindings")
    if "InfiniExternalSoundPack" in library:
        err("InfiniSoundLibrary.cs: external sound-pack binding must stay removed; use future catalog seam instead")
    for needle in [
        "public const string ContractVersion = \"infini.external-sound-catalog.future-seam.v2\";",
        "TryResolveOneShot",
        "return false;",
        "embedding",
        "explicit catalog id/path/source",
        "never receives prose",
        "public bool IsImpact { get; }",
    ]:
        required(future_path, future, needle)
    for stale in ["QueryText", "soundUseSearchQuery", "soundImpactSearchQuery", "SoundUseSearchQuery", "SoundImpactSearchQuery"]:
        if stale in future or stale in library or stale in model:
            err(f"audio contract: stale text-query field `{stale}`")
    if "public bool Impact { get; }" in future and "InfiniFutureSoundCatalogRequest Impact(" in future:
        err("InfiniFutureSoundCatalog.cs: request member `Impact` collides with static factory `Impact`; use `IsImpact` for the bool flag")
    if "InfiniSoundLibrary.ForUse" not in model:
        err("GeneratedItemData.cs: item use sound must resolve through InfiniSoundLibrary")
    for needle in [
        "SoundUseCatalogId",
        "SoundImpactCatalogId",
        "SoundCatalogSource",
        "SoundPitchVariance",
        "SoundUseCatalogPath",
        "SoundImpactCatalogPath",
    ]:
        required(model_path, model, needle)

    for needle in [
        "public const string ContractVersion = \"infini.luminance-sound-bridge.v1\";",
        "using Luminance.Core.Sounds;",
        "LoopedSoundManager.CreateNew",
        "LoopedSoundInstance",
        "TryUpdateLiveSoundCue",
        "EnableLuminanceSoundBackend",
        "MaxActiveLoops",
        "LoopShouldStop",
        "instance.Update(projectile.Center)",
    ]:
        required(bridge_path, bridge, needle)
    build = read(SRC / "build.txt")
    if "modReferences = ParticleLibrary, Luminance" not in build:
        err("build.txt: Luminance remains an explicit modReference/future utility")
    config = read(SRC / "Common/Config/InfiniVfxClientConfig.cs")
    options = read(SRC / "Common/VFX/InfiniVfxClientOptions.cs")
    if "EnableLuminanceSoundBackend" not in config or "EnableLuminanceSoundBackend" not in options:
        err("Luminance sound backend must stay client-configurable")
    if "EnableExternalSoundPack" in config or "EnableExternalSoundPack" in options:
        err("EnableExternalSoundPack: removed in v0.4.190 with fixed sound-pack binding")
    if "DefaultValue(false)" not in config or "Config?.EnableLuminanceSoundBackend ?? false" not in options:
        err("Luminance live sound backend should remain explicit opt-in by default")

def check_generated_armor_contract() -> None:
    item_path = SRC / "Content/Items/GeneratedItem.cs"
    proxy_path = SRC / "Content/Items/GeneratedArmorItems.cs"
    player_path = SRC / "Common/Players/InfiniCraftPlayer.cs"
    model_path = SRC / "Common/Models/GeneratedItemData.cs"
    item = read(item_path)
    proxy = read(proxy_path)
    player = read_player_bundle()
    model = read_generated_item_data_bundle()
    for needle in [
        "[AutoloadEquip(EquipType.Head)]",
        "[AutoloadEquip(EquipType.Body)]",
        "[AutoloadEquip(EquipType.Legs)]",
        "public sealed class GeneratedHeadArmor : GeneratedItem",
        "public sealed class GeneratedBodyArmor : GeneratedItem",
        "public sealed class GeneratedLegsArmor : GeneratedItem",
        "GeneratedArmorItemTypes",
        "ItemTypeFor(GeneratedItemData data)",
        "IsArmorSlot(GeneratedItemData? data, string slot)",
    ]:
        required(proxy_path, proxy, needle)
    for tex in [
        "Assets/GeneratedItem_Head.png",
        "Assets/GeneratedItem_Body.png",
        "Assets/GeneratedItem_Arms.png",
        "Assets/GeneratedItem_FemaleBody.png",
        "Assets/GeneratedItem_Legs.png",
    ]:
        if not (SRC / tex).exists():
            err(f"missing generated armor placeholder equip texture {tex}")
    for needle in [
        "public ArmorSpec Armor",
        "item.defense = Math.Max(0, Armor.Defense)",
        "NormalizeArmorSlot",
        "isArmor",
        "item.accessory = false",
    ]:
        required(model_path, model, needle)
    for needle in [
        "ApplyGeneratedArmorEffects(player, Data?.Armor)",
        "player.statLifeMax2 += a.MaxLife",
        "player.GetDamage(DamageClass.Generic) += a.GenericDamage",
        "player.GetDamage(DamageClass.Melee) += a.MeleeDamage",
        "player.GetDamage(DamageClass.Ranged) += a.RangedDamage",
        "player.GetDamage(DamageClass.Magic) += a.MagicDamage",
        "player.GetDamage(DamageClass.Summon) += a.SummonDamage",
        "player.GetCritChance(DamageClass.Generic) += a.GenericCrit",
        "player.GetAttackSpeed(DamageClass.Generic) += a.AttackSpeed",
        "player.GetKnockback(DamageClass.Generic) += a.Knockback",
        "player.maxMinions += a.MinionSlots",
        "player.maxTurrets += a.SentrySlots",
        "player.manaCost = Math.Max(0.1f, player.manaCost - a.ManaCostReduction)",
        "AddGeneratedAmmoSaveChance(a.AmmoSaveChance)",
        "AddGeneratedAmmoSaveChance(a.SetBonusAmmoSaveChance)",
        "player.aggro += a.Aggro",
        "player.endurance += a.Endurance",
        "player.GetArmorPenetration(DamageClass.Generic) += a.ArmorPenetration",
        "Lighting.AddLight",
        "player.setBonus",
        "SetBonusGenericDamage",
        "SetBonusMinionSlots",
        "SetBonusSentrySlots",
        "SetBonusManaCostReduction",
        "SetBonusArmorPenetration",
    ]:
        required(item_path, item, needle)
    for needle in [
        "GeneratedArmorItemTypes.CanRepresent(data)",
        "GeneratedArmorItemTypes.ItemTypeFor(data)",
    ]:
        required(player_path, player, needle)


def check_network_read_write_shape() -> None:
    packet_ids = read(SRC / "Common/InfiniNetPacketIds.cs")
    for needle in ["CancelServerCraft = 12", "SyncGeneratedProjectileVfxEvent = 9", "RequestGeneratedItemById = 10", "SyncGeneratedHeldItemPresentation = 11"]:
        if needle not in packet_ids:
            err(f"InfiniNetPacketIds.cs: missing central packet id `{needle}`")
    projectile = read_projectile_bundle()
    if "writer.Write(ProjectileSyncVersion)" not in projectile or "reader.ReadInt32()" not in projectile:
        err("GeneratedProjectile.cs: versioned SendExtraAI/ReceiveExtraAI shape is incomplete")
    for needle in [
        "private const int ProjectileSyncVersion = 18",
        "writer.Write(_spec.RangeTiles)",
        "writer.Write(_spec.HomingStrength)",
        "writer.Write(_spec.BeamWidthPx)",
        "writer.Write(_spec.BeamChargeTicks)",
        "writer.Write(_spec.ChargeTicks)",
        "writer.Write(_spec.ChargePowerMultiplier)",
        "writer.Write(ShortNet(_spec.DamageClass, 96))",
        "writer.Write(_spec.SentryAttackIntervalTicks)",
        "writer.Write(_spec.SentryTargetRangeTiles)",
        "writer.Write(_spec.SentryLifetimeTicks)",
        "writer.Write(_beamLengthPx)",
        "_spec.RangeTiles = reader.ReadSingle()",
        "_spec.HomingStrength = reader.ReadSingle()",
        "_spec.BeamWidthPx = reader.ReadSingle()",
        "_spec.BeamChargeTicks = reader.ReadInt32()",
        "_spec.ChargeTicks = reader.ReadInt32()",
        "_spec.ChargePowerMultiplier = reader.ReadSingle()",
        "_spec.DamageClass = ReadStringKeepBase(reader, _spec.DamageClass, childShard)",
        "_spec.SentryAttackIntervalTicks = reader.ReadInt32()",
        "_spec.SentryTargetRangeTiles = reader.ReadSingle()",
        "_spec.SentryLifetimeTicks = reader.ReadInt32()",
        "_beamLengthPx = reader.ReadSingle()",
        "Collision.LaserScan",
        "CanPayChannelBeamMana",
        "owner.CheckMana(manaCost, true, false)",
        "writer.Write(ShortNet(_spec.SecondaryTrigger, 24))",
        "_spec.SecondaryTrigger = reader.ReadString()",
        "writer.Write(_spec.DelayTicks)",
        "_spec.DelayTicks = reader.ReadInt32()",
        "GeneratedSecondaryTriggerPolicy.Normalize",
        "ApplyOverheadBarrageAI",
        "SpawnExpireSecondaries();",
        "RemainingGameplayChildBudget",
        "_spawnedGameplayChildCount++",
        "GeneratedSecondaryTriggerPolicy.NormalizeForRuntimeFamily",
    ]:
        if needle not in projectile:
            err(f"GeneratedProjectile.cs: missing exact channel-beam runtime/sync guard `{needle}`")
    onkill = method_block(projectile, "OnKill")
    if "SpawnExpireSecondaries();" not in onkill:
        err("GeneratedProjectile.Impact.cs: on_expire helper exists without an OnKill call-site")
    trigger_policy = read(SRC / "Common/Models/GeneratedSecondaryTriggerPolicy.cs")
    if '_ => ""' not in trigger_policy or "NormalizeForRuntimeFamily" not in trigger_policy:
        err("GeneratedSecondaryTriggerPolicy.cs: unknown/incompatible triggers must normalize to inert empty state")
    for flag in ["SyncFlagMobility", "SyncFlagRuntimeLight", "SyncFlagSplitRadii"]:
        if flag not in projectile:
            err(f"GeneratedProjectile.cs: missing projectile sync flag `{flag}`")
    for needle in [
        "InfiniNetPacketIds.SyncGeneratedProjectileVfxEvent",
        "HandleProjectileVfxEventSyncPacket",
        "PendingProjectileVfxEvents",
        "FlushPendingVfxEventsForGeneratedItem",
        "BroadcastVfxEventSync",
        "RequestOneGeneratedItemForMissingProjectile",
    ]:
        if needle not in projectile:
            err(f"GeneratedProjectile.cs: missing multiplayer VFX/presentation resync guard `{needle}`")
    registry = read(SRC / "Common/Services/GeneratedItemRegistryService.cs")
    for needle in ["InfiniNetPacketIds.RequestGeneratedItemById", "RequestOneFromServer", "TryGet(id, out var data)", "FlushPendingProjectileVisualSyncForGeneratedItem(data.Id)", "FlushPendingVfxEventsForGeneratedItem(data.Id)"]:
        if needle not in registry:
            err(f"GeneratedItemRegistryService.cs: missing targeted generated item resync guard `{needle}`")
    for needle in ["MissingGeneratedItemRequestTicks", "MissingProjectileAssetRequestTicks", "MissingGeneratedItemRetryTicks", "MissingProjectileAssetRetryTicks", "MaybeRebroadcastVisualSyncForEarlyRemoteCatchup", "RequestProjectileAssetCatchupIfMissing(spritePath, _generatedItemId)", "TryResolveServerOwnedGeneratedProjectile(whoAmI, payload.Identity", "payload.GeneratedItemId = ShortNet(generated._generatedItemId, 96)", "payload.Center = generated.Projectile.Center", "PrunePendingProjectileVisualSyncLocked", "PruneTickMapLocked", "ClearPresentationSyncCaches"]:
        if needle not in projectile:
            err(f"GeneratedProjectile.cs: missing per-item multiplayer catch-up guard `{needle}`")
    held_layer = read(SRC / "Common/Players/GeneratedHeldItemDrawLayer.cs")
    player = read_player_bundle()
    mod = read(SRC / "InfiniCrafterLocal.cs")
    for needle in [
        "InfiniNetPacketIds.SyncGeneratedHeldItemPresentation",
        "HandleHeldItemPresentationSyncPacket",
        "MaybeBroadcastLocalHeldItem",
        "RemoteHeldPresentations",
        "player.itemLocation",
        "player.itemRotation",
        "ItemLocationX",
        "ItemLocationY",
        "ItemRotation",
        "payload.PlayerId = Math.Clamp(whoAmI",
        "sender.HeldItem?.ModItem is GeneratedItem authoritative",
        "PayloadItemLocation",
        "ClearNetCaches",
        "HeldSpriteOrigin",
        "RoleForwardOffset",
        "RequestHeldItemCatchup",
    ]:
        if needle not in held_layer and needle not in player:
            err(f"Generated held item sync/pose guard missing `{needle}`")
    if "private const int HeldItemPresentationSyncVersion = 4" not in held_layer:
        err("GeneratedHeldItemDrawLayer.cs: held item presentation sync must use v4 id+pose+animation-phase payload")
    held_payload_start = held_layer.find("private sealed class HeldItemPresentationPayload")
    held_payload_end = held_layer.find("private static readonly Dictionary", held_payload_start)
    held_build_start = held_layer.find("private static HeldItemPresentationPayload BuildLocalPayload")
    held_build_end = held_layer.find("private static void WriteHeldItemPresentationPayload", held_build_start)
    held_write_start = held_layer.find("private static void WriteHeldItemPresentationPayload")
    held_write_end = held_layer.find("private static void SendHeldItemPresentationPayload", held_write_start)
    held_transport = "".join([
        held_layer[held_payload_start:held_payload_end] if held_payload_start >= 0 and held_payload_end >= 0 else "",
        held_layer[held_build_start:held_build_end] if held_build_start >= 0 and held_build_end >= 0 else "",
        held_layer[held_write_start:held_write_end] if held_write_start >= 0 and held_write_end >= 0 else "",
    ])
    for removed in ["SpritePath", "RuntimeFamily", "WeaponFamily", "HandPose", "RotationMode", "UseStyle", "HoldoutOffsetX", "HoldoutOffsetY", "InitialOffsetPx", "ItemScale"]:
        if removed in held_transport:
            err(f"GeneratedHeldItemDrawLayer.cs: held presentation packet must be id+pose only; remove `{removed}` from payload/build/read/write")
    for phase_field in ["ActiveUse", "AnimationRemaining"]:
        if phase_field not in held_transport:
            err(f"GeneratedHeldItemDrawLayer.cs: v4 held presentation payload missing `{phase_field}`")
    for needle in ["registry.TryGet(payload.GeneratedItemId, out var registryData)", "RequestHeldItemCatchup(payload.GeneratedItemId, null)"]:
        if needle not in held_layer:
            err(f"GeneratedHeldItemDrawLayer.cs: missing registry catch-up guard `{needle}`")
    item_source = read(SRC / "Content/Items/GeneratedItem.cs")
    for needle in ["private void EnsureRuntimeHydration(Player? player = null)", "_lastRuntimeHydrationTouchTick", "GeneratedItems?.RegisterLocal(Data, persist: false, ensureAssets: true)", "GeneratedItems?.RequestOneFromServer(id, forceAssetRetry: false)"]:
        if needle not in item_source:
            err(f"GeneratedItem.cs: missing generic item hydration hook `{needle}`")
    for method_name in ["CanUseItem", "UseItem", "HoldItem", "UpdateEquip", "UpdateAccessory"]:
        block = method_block(item_source, method_name)
        if "EnsureRuntimeHydration(player);" not in block:
            err(f"GeneratedItem.cs: {method_name} must touch generic runtime hydration, not rely on projectile-side catch-up")
    if "GeneratedProjectile.ClearPresentationSyncCaches();" not in mod or "GeneratedHeldItemDrawLayer.ClearNetCaches();" not in mod:
        err("InfiniCrafterLocal.cs: missing multiplayer presentation cache cleanup on unload")
    if "InfiniNetPacketIds.SyncGeneratedHeldItemPresentation" not in mod:
        err("InfiniCrafterLocal.cs: missing held item presentation sync packet routing")
    for needle in ["EmitVanillaMotionPolish", "EmitVanillaImpactPolish", "DrawStockMotionPolish", "VanillaPolishDust", "AllowsVanillaMotionPolish"]:
        if needle not in projectile:
            err(f"GeneratedProjectile.cs: missing exact presentation polish helper `{needle}`")
    for forbidden in ["PresentationIdentityText", "HasPresentationIdentity", "PolishDustForIdentity"]:
        if forbidden in projectile:
            err(f"GeneratedProjectile.cs: fuzzy presentation router remains `{forbidden}`")
    for rel_path in ["Content/Items/GeneratedItem.cs"]:
        text = read(SRC / rel_path)
        if "NetPayloadVersion" in text or "GeneratedItemNetPayloadVersion" in text:
            if "reader.ReadInt32()" not in text:
                err(f"{rel_path}: NetReceive does not read payload version as int")
            if "reader.ReadString()" not in text:
                err(f"{rel_path}: NetReceive does not read JSON payload string")


def check_tml_feedback_warning_patterns() -> None:
    """Static guards for concrete tML/Roslyn warnings seen in the real build log."""
    mod = read(SRC / "InfiniCrafterLocal.cs")
    if re.search(r"\bpublic\s+const\s+string\s+Version\b", strip_comments_and_strings(mod)):
        err("InfiniCrafterLocal.cs: do not declare `Version`; it hides tModLoader.Mod.Version (CS0108). Use ModVersion.")
    if "public const string ModVersion" not in mod:
        err("InfiniCrafterLocal.cs: missing explicit ModVersion constant used by generator wire payloads")

    item = read(SRC / "Content/Items/GeneratedItem.cs")
    tooltip_body = strip_comments_and_strings(method_block(item, "ModifyTooltips"))
    if re.search(r"\bData\s*\?*\s*\.", tooltip_body):
        err("GeneratedItem.cs: ModifyTooltips must dereference JSON subspecs through safe local variables, not direct Data.*")
    for needle in [
        "GeneratedItemData data = Data ?? GeneratedItemData.Placeholder();",
        "GameplaySpec gameplay = data.Gameplay ?? new GameplaySpec();",
        "AttackSpec attack = data.Attack ?? new AttackSpec();",
        "VisualSpec visual = data.Visual ?? new VisualSpec();",
        "RecipeMetaSpec recipeMeta = data.RecipeMeta ?? new RecipeMetaSpec();",
    ]:
        if needle not in item:
            err(f"GeneratedItem.cs: nullable-safe tooltip guard missing `{needle}`")

    generator = read(SRC / "Common/Services/GeneratorClient.cs")
    if "Normalize(data!," in generator:
        err("GeneratorClient.cs: cache/blocking generation must narrow nullable data before Normalize; no `data!` suppression")
    if "data is null || !IsDeliverableGeneratedData(data)" not in generator:
        err("GeneratorClient.cs: generated payload should explicitly reject null before IsDeliverableGeneratedData/Normalize")

    quiet = read(SRC / "Common/Services/LocalHttpQuietFailure.cs")
    if "out string msg" in quiet:
        err("LocalHttpQuietFailure.cs: Dictionary.TryGetValue out var must be nullable (`out string? msg`) under nullable analysis")
    if "out string? msg" not in quiet or "msg ?? \"\"" not in quiet:
        err("LocalHttpQuietFailure.cs: missing nullable-safe LastMessage TryGetValue guard")

    bridge = read(SRC / "Common/Audio/InfiniLuminanceSoundBridge.cs")
    if "out LoopHandle handle" in bridge:
        err("InfiniLuminanceSoundBridge.cs: ActiveLoops.TryGetValue must use `out LoopHandle? handle` under nullable analysis")
    for needle in ["out LoopHandle? handle", "LoopedSoundInstance instance = handle.Instance;", "LoopedSoundInstance? instance = pair.Value.Instance;"]:
        if needle not in bridge:
            err(f"InfiniLuminanceSoundBridge.cs: missing nullable-safe loop handle guard `{needle}`")

    apply = read(SRC / "Common/Models/GeneratedItemData.Apply.cs")
    for needle in ["Attack.SoundCatalogSource ?? \"\""]:
        if needle not in apply:
            err(f"GeneratedItemData.Apply.cs: nullable string argument to InfiniSoundLibrary.ForUse must be coalesced: `{needle}`")

    held = read(SRC / "Common/Players/GeneratedHeldItemDrawLayer.cs")
    draw_body = method_block(held, "Draw")
    if "Item held = player.HeldItem;" in draw_body:
        err("GeneratedHeldItemDrawLayer.cs: player.HeldItem local must be nullable (`Item? held`) before fallback drawing")
    if "Item? held = player.HeldItem;" not in draw_body or "player.GetAdjustedItemScale(held)" not in draw_body:
        err("GeneratedHeldItemDrawLayer.cs: missing nullable-safe held-item draw scale guard")

    dump = read(SRC / "Common/Commands/InfiniDumpPictureCommand.cs")
    if "out dumpRel" in dump:
        err("InfiniDumpPictureCommand.cs: copied.TryGetValue must not assign possible-null directly into non-null dumpRel")
    if "out string? existingDumpRel" not in dump or "dumpRel = existingDumpRel ?? \"\";" not in dump:
        err("InfiniDumpPictureCommand.cs: missing nullable-safe copied asset path guard")

    visual = read(SRC / "Content/Projectiles/GeneratedProjectile.Visuals.cs")
    if "if (manifest is { HasSlots: true })" not in visual:
        err("GeneratedProjectile.Visuals.cs: nullable VFX manifest must be narrowed with a property pattern before InfiniVfxRuntime.Draw")

    particle_registry = read(SRC / "Common/VFX/VfxParticleSystemRegistry.cs")
    if "ParticleLibrary.Resources" in strip_comments_and_strings(particle_registry):
        err("VfxParticleSystemRegistry.cs: ParticleLibrary.Resources is internal; use the public texture path string")
    if "public override string Texture => \"ParticleLibrary/Assets/Textures/Star\";" not in particle_registry:
        err("VfxParticleSystemRegistry.cs: missing public ParticleLibrary texture path literal for V3 particle behavior")

    sentinels = read(SRC / "Common/InfiniTerrariaSentinels.cs")
    clean_sentinels = strip_comments_and_strings(sentinels)
    for needle in [
        "public const int NoBuffType = 0;",
        "public const int NoPrefix = 0;",
        "public const int FirstValidItemType = ItemID.None + 1;",
        "public const int FirstValidProjectileType = ProjectileID.None + 1;",
        "public const int MaxSupportedItemUseStyle = ItemUseStyleID.RaiseLamp;",
    ]:
        if needle not in sentinels:
            err(f"InfiniTerrariaSentinels.cs: missing sentinel contract `{needle}`")
    if "BuffID.None" in clean_sentinels or "PrefixID.None" in clean_sentinels:
        err("InfiniTerrariaSentinels.cs: BuffID/PrefixID do not expose None in current tML; keep local 0 sentinels")

    all_clean = strip_comments_and_strings("\n".join(read(path) for path in SRC.rglob("*.cs")))
    magic_patterns = [
        (r"\.prefix\s*(?:==|!=)\s*0\b", "raw prefix 0 sentinel"),
        (r"\.Prefix\s*\(\s*0\s*\)", "raw Prefix(0) sentinel"),
        (r"\.buffType\s*>\s*0\b", "raw buffType > 0 sentinel"),
        (r"for\s*\(\s*int\s+\w+\s*=\s*1\s*;\s*\w+\s*<\s*ItemLoader\.ItemCount", "raw first valid item id 1 loop"),
        (r"for\s*\(\s*int\s+\w+\s*=\s*1\s*;\s*\w+\s*<\s*ProjectileLoader\.ProjectileCount", "raw first valid projectile id 1 loop"),
        (r"Math\.Clamp\([^;]*ItemUseStyleID\.None\s*,\s*14\s*\)", "raw ItemUseStyleID upper bound 14"),
    ]
    for pattern, label in magic_patterns:
        if re.search(pattern, all_clean, flags=re.S):
            err(f"ChangeMagicNumberToID risk: {label}; use InfiniTerrariaSentinels/Terraria.ID constants")
    if "ChangeMagicNumberToID" in all_clean:
        err("ChangeMagicNumberToID analyzer text should not be checked into source")


def check_tml_feedback_warning_pattern_self_tests() -> None:
    tests = [
        ("Mod.Version shadow", r"\bpublic\s+const\s+string\s+Version\b", "public const string Version = \"0.0\";"),
        ("GeneratorClient data!", r"Normalize\(data!\s*,", "Normalize(data!, request.ParentA, request.ParentB);"),
        ("direct tooltip Data deref", r"Data\.", "if (Data.Gameplay.Stage.Length > 0) { }"),
        ("ParticleLibrary internal Resources", r"ParticleLibrary\.Resources", "ParticleLibrary.Resources.Assets.Textures.Star"),
        ("raw prefix zero", r"\.prefix\s*(?:==|!=)\s*0\b", "if (item.prefix != 0) { }"),
        ("raw buff zero", r"\.buffType\s*>\s*0\b", "if (item.buffType > 0) { }"),
        ("raw useStyle max", r"Math\.Clamp\([^;]*ItemUseStyleID\.None\s*,\s*14\s*\)", "Math.Clamp(x, ItemUseStyleID.None, 14);"),
    ]
    for name, pattern, bad in tests:
        if not re.search(pattern, strip_comments_and_strings(bad), flags=re.S):
            err(f"warning-pattern detector self-test failed for {name}")


def check_actual_build_hook_available() -> None:
    for rel_path in [
        "tools/try_tml_build_check.py",
        "tools/parse_tml_build_log.py",
        "tools/build_tml_windows.ps1",
        "tools/build_tml_windows.bat",
        "tools/collect_tml_build_errors_windows.ps1",
        "03_COLLECT_TMODLOADER_BUILD_ERRORS.bat",
    ]:
        if not (ROOT / rel_path).exists():
            err(f"missing tModLoader build workflow helper {rel_path}")

    parser = read(ROOT / "tools" / "parse_tml_build_log.py")
    for needle in ["TML_PREFIX_RE", "UI_ERROR_PREFIX_RE", "--mod", "dedupe", "format_summary"]:
        if needle not in parser:
            err(f"parse_tml_build_log.py: missing QoL tML client-log parser support `{needle}`")


def check_overhaul_qol_contract() -> None:
    config_path = SRC / "Common/Config/InfiniGameplayQolConfig.cs"
    if not config_path.exists():
        err("missing InfiniGameplayQolConfig.cs overhaul QoL config")
        return
    config = read(config_path)
    for needle in ["EnableInventoryAssetPrefetch", "InventoryAssetPrefetchIntervalTicks"]:
        if needle not in config:
            err(f"InfiniGameplayQolConfig.cs: missing QoL config `{needle}`")
    for removed in ["EnableStationQuickFill", "QuickFillSkipsHotbar"]:
        if removed in config:
            err(f"InfiniGameplayQolConfig.cs: removed station quick-fill config returned `{removed}`")

    player = read_player_bundle()
    for needle in [
        "TryClearAllInputsToInventory",
        "TryClearInputToInventory",
        "TickGeneratedInventoryAssetPrefetch",
        "EnableInventoryAssetPrefetch",
        "RegisterLocal(data, persist: true, ensureAssets: true)",
    ]:
        if needle not in player:
            err(f"InfiniCraftPlayer.cs: missing generated gameplay overhaul QoL guard `{needle}`")
    for removed in ["TryAutoFillStationInputs", "TryFillStationInputFromInventory", "TrySwapStationInputs"]:
        if removed in player:
            err(f"InfiniCraftPlayer.cs: removed station quick-fill/swap helper returned `{removed}`")

    ui = read(SRC / "Common/UI/InfiniCraftStationUISystem.cs")
    for needle in [
        "clearButton",
        "TryClearAllInputsToInventory",
        "Main.mouseRight",
        "RMB slot clears",
    ]:
        if needle not in ui:
            err(f"InfiniCraftStationUISystem.cs: missing station manual QoL surface `{needle}`")
    for removed in ["fillButton", "swapButton", "StationQuickFillEnabled", "QuickFillSkipsHotbar", "TryAutoFillStationInputs", "TrySwapStationInputs"]:
        if removed in ui:
            err(f"InfiniCraftStationUISystem.cs: removed Fill/Swap station UI surface returned `{removed}`")



def check_maintenance_qol_cleanup() -> None:
    projectile = read_projectile_bundle()
    send_block = projectile[projectile.find("public override void SendExtraAI"):projectile.find("public override void ReceiveExtraAI")]
    if "static string Short(" in send_block:
        err("GeneratedProjectile.cs: SendExtraAI must use shared ShortNet, not a local duplicate Short helper")
    if "writer.Write(""); // reserved" in send_block:
        err("GeneratedProjectile.cs: legacy empty reserved strings returned to SendExtraAI")
    for needle in ["writer.Write((byte)0); // reserved bitset", "reader.ReadByte(); // reserved bitset", "syncVersion != ProjectileSyncVersion"]:
        if needle not in projectile:
            err(f"GeneratedProjectile.cs: missing current-only projectile sync guard `{needle}`")
    for removed in ["private const int ProjectileSyncVersion = 5", "syncVersion <", "// v3 reserved", "v3/v4 ProjectileChild", "legacy v3-v5 manifest fallback slot"]:
        if removed in projectile:
            err(f"GeneratedProjectile.cs: legacy projectile sync branch still present `{removed}`")
    if "private const int ProjectileVisualSyncVersion = 3" not in projectile:
        err("GeneratedProjectile.cs: projectile visual sync packet version must be bumped for id-only payload")
    visual_start = projectile.find("private sealed class ProjectileVisualSyncPayload")
    visual_end = projectile.find("private sealed class ProjectileVfxEventSyncPayload", visual_start)
    build_start = projectile.find("private ProjectileVisualSyncPayload BuildVisualSyncPayload")
    build_end = projectile.find("private static string ShortNet", build_start)
    write_start = projectile.find("private static void WriteProjectileVisualSyncPayload")
    write_end = projectile.find("private static void SendProjectileVisualSyncPayload", write_start)
    visual_transport = "".join([
        projectile[visual_start:visual_end] if visual_start >= 0 and visual_end >= 0 else "",
        projectile[build_start:build_end] if build_start >= 0 and build_end >= 0 else "",
        projectile[write_start:write_end] if write_start >= 0 and write_end >= 0 else "",
    ])
    for removed in ["ProjectileSpritePath", "ProjectileSpriteStatus", "VisualMode", "TrailStyle", "ImpactStyle", "PrimaryColorName"]:
        if removed in visual_transport:
            err(f"GeneratedProjectile.cs: visual sync packet must be id-only; remove `{removed}` from payload/build/read/write")
    model_and_projectile = read_projectile_bundle() + read(SRC / "Common/Models/GeneratedItemData.Model.cs")
    for removed in ["ToyIdentity", "SpecialRule", "BehaviorActions", "BehaviorTimeline", "OnUseScript", "OnTickScript", "OnHitScript", "OnExpireScript", "ProjectileChild"]:
        if removed in model_and_projectile:
            err(f"GeneratedItemData/GeneratedProjectile: legacy prose/script field still present `{removed}`")
    bundle = read(SRC / "Common/Models/GeneratedItemData.cs") + read(SRC / "Common/Models/GeneratedItemData.Normalize.cs") + read(SRC / "Common/Models/GeneratedItemData.Apply.cs")
    for removed in ["ApplyCompatMigrations", "CompatNeedsRuntimeFamilyBackfill", "CompatLooksLikeShootRuntime", "CompatNeedsUseStyleBackfill", "CompatUseStyleForRuntimeFamily", "AttackRuntimeFamilyCompat"]:
        if removed in bundle:
            err(f"GeneratedItemData: legacy compat migration code still present `{removed}`")
    if (SRC / "Common/Models/GeneratedItemData.Compat.cs").exists():
        err("GeneratedItemData.Compat.cs should be deleted after test-world-only legacy cleanup")

    generator_client = read(SRC / "Common/Services/GeneratorClient.cs")
    if "ProjectileProfileFromItem" in generator_client:
        err("GeneratorClient.cs: retired parent projectile profile inference returned")
    vfx_manifest = read(SRC / "Common/Models/VfxManifestSpec.cs")
    for removed in ["public string Quality", "public string RenderQuality", "public string MinQuality"]:
        if removed in vfx_manifest:
            err(f"VfxManifestSpec.cs: retired quality alias returned `{removed}`")

    cache = read(SRC / "Common" / "Services" / "RuntimeSpriteCache.cs")
    for needle in ["DefaultMaxCachedTextures = 512", "RuntimeSpriteCacheMaxTextures", "EffectiveLimits", "CachedTexture", "LastAccessTick", "TrimTextureCacheIfNeeded", "while (_textures.Count > maxCachedTextures)", "DefaultMaxTextureDimensionPixels = 192", "DefaultMaxTextureFileMegabytes = 8", "IsRuntimePngFileSizeAllowed", "MaxMissingOrBadRecords", "TrimMissingOrBadCacheIfNeeded"]:
        if needle not in cache:
            err(f"RuntimeSpriteCache.cs: missing bounded texture cache guard `{needle}`")

    config = read(SRC / "Common" / "Config" / "InfiniGameplayQolConfig.cs")
    if "RuntimeSpriteCacheMaxTextures" not in config or "[Range(64, 2048)]" not in config:
        err("InfiniGameplayQolConfig.cs: missing RuntimeSpriteCacheMaxTextures client-side LRU knob")
    if "RuntimeSpriteMaxDimensionPixels" not in config or "RuntimeSpriteMaxPngFileMegabytes" not in config:
        err("InfiniGameplayQolConfig.cs: missing runtime sprite size/file guard knobs")

    env_utils = ROOT / "LocalGenerator" / "infini_local" / "core" / "env_utils.py"
    if not env_utils.exists():
        err("missing shared LocalGenerator/infini_local/core/env_utils.py")
    loader_defs = []
    for path in (ROOT / "LocalGenerator" / "infini_local").rglob("*.py"):
        if "def load_env_file" in read(path):
            loader_defs.append(rel(path))
    if loader_defs != ["LocalGenerator/infini_local/core/env_utils.py"]:
        err("load_env_file should have exactly one shared definition; found " + ", ".join(loader_defs))

def check_runtime_family_policy_owner() -> None:
    policy_path = SRC / "Common/Models/GeneratedRuntimeFamilyPolicy.cs"
    if not policy_path.exists():
        err("missing canonical Common/Models/GeneratedRuntimeFamilyPolicy.cs")
        return
    policy = read(policy_path)
    for needle in [
        "internal static class GeneratedRuntimeFamilyPolicy",
        "internal enum GeneratedHeldRenderRole",
        "public static string Normalize",
        "public static bool IsProjectileOwned",
        "public static bool UsesHeldProjectile",
        "public static bool UsesItemSpriteAsProjectile",
        "public static GeneratedHeldRenderRole HeldRenderRole",
    ]:
        if needle not in policy:
            err(f"GeneratedRuntimeFamilyPolicy.cs: missing canonical contract `{needle}`")

    consumers = {
        "Common/Models/GeneratedItemData.Normalize.cs": "GeneratedRuntimeFamilyPolicy.Normalize",
        "Common/Models/GeneratedItemData.Apply.cs": "GeneratedRuntimeFamilyPolicy.IsProjectileOwned",
        "Content/Items/GeneratedItem.cs": "GeneratedRuntimeFamilyPolicy.Normalize",
        "Content/Projectiles/GeneratedProjectile.Runtime.cs": "GeneratedRuntimeFamilyPolicy.Normalize",
        "Content/Projectiles/GeneratedProjectile.Visuals.cs": "GeneratedRuntimeFamilyPolicy.UsesItemSpriteAsProjectile",
    }
    forbidden = [
        'r is "swing" or "thrust" or "returning"',
        'family is "returning" or "thrust" or "yoyo" or "throw"',
        "IsFreeProjectileFamily",
    ]
    for rel_path, required in consumers.items():
        source = read(SRC / rel_path)
        if required not in source:
            err(f"{rel_path}: runtime family decision must use canonical policy `{required}`")
        for stale in forbidden:
            if stale in source:
                err(f"{rel_path}: duplicated runtime-family policy `{stale}`")

    runtime_literal = re.compile(
        r'\b(?:RuntimeFamily|runtimeFamily)\b[^;\n]*(?:==|!=|=|\bis\b)\s*"(?:none|swing|thrust|returning|flail|yoyo|whip|shoot|cast|throw|summon)"'
    )
    for path in SRC.rglob("*.cs"):
        if path == policy_path:
            continue
        if runtime_literal.search(read(path)):
            err(f"{rel(path)}: canonical runtime family literal bypasses GeneratedRuntimeFamilyPolicy")

    held = read(SRC / "Common/Players/GeneratedHeldItemDrawLayer.cs")
    for required in ["ResolveHeldRenderRole", "GeneratedRuntimeFamilyPolicy.HeldRenderRole", "GeneratedRuntimeFamilyPolicy.Normalize"]:
        if required not in held:
            err(f"GeneratedHeldItemDrawLayer.cs: missing canonical held-render role contract `{required}`")
    for stale in ["enum HeldRenderRole", "BuildHeldRoleText", "ContainsAny(role", "ContainsPresentationTerm"]:
        if stale in held:
            err(f"GeneratedHeldItemDrawLayer.cs: stale keyword-role router `{stale}`")


def check_project_namespace_references() -> None:
    """Catch project types referenced without their declaring namespace import.

    This is intentionally narrower than a C# compiler: only project-defined type names
    are considered, comments/strings are stripped, and same-namespace references pass.
    """
    declared: dict[str, set[str]] = {}
    files = list(SRC.rglob("*.cs"))
    for path in files:
        clean = strip_comments_and_strings(read(path))
        match = re.search(r"\bnamespace\s+([A-Za-z_][\w.]*)\s*[;{]", clean)
        if not match:
            continue
        ns = match.group(1)
        for name in re.findall(r"\b(?:class|struct|interface|enum|record(?:\s+struct|\s+class)?)\s+([A-Z][A-Za-z0-9_]*)\b", clean):
            if name.startswith(("Infini", "Generated", "Vfx")):
                declared.setdefault(name, set()).add(ns)

    for path in files:
        text = read(path)
        clean = strip_comments_and_strings(text)
        match = re.search(r"\bnamespace\s+([A-Za-z_][\w.]*)\s*[;{]", clean)
        current_ns = match.group(1) if match else ""
        usings = set(re.findall(r"^\s*using\s+([A-Za-z_][\w.]*)\s*;", text, flags=re.M))
        for name, namespaces in declared.items():
            if not token(clean, name):
                continue
            if any(current_ns == ns or current_ns.startswith(ns + ".") for ns in namespaces) or any(ns in usings for ns in namespaces):
                continue
            if any((ns + "." + name) in clean or ("global::" + ns + "." + name) in clean for ns in namespaces):
                continue
            if any(current_ns and ns.startswith(current_ns + ".") and (ns[len(current_ns) + 1:] + "." + name) in clean for ns in namespaces):
                continue
            err(f"{rel(path)}: project type `{name}` needs declaring namespace import ({', '.join(sorted(namespaces))})")


def check_strict_json_boundaries() -> None:
    for rel_path in (
        "Common/Models/GeneratedItemData.cs",
        "Common/Models/VfxManifestSpec.cs",
    ):
        source = read(SRC / rel_path)
        if "UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow" not in source:
            err(f"{rel_path}: nested JSON contract must reject unknown fields")


def check_exact_presentation_dispatch() -> None:
    visuals = read(SRC / "Content/Projectiles/GeneratedProjectile.Visuals.cs")
    registry = read(SRC / "Common/VFX/VfxRendererRegistry.cs")
    particles = read(SRC / "Common/VFX/VfxParticleAddress.cs")
    sound = read(SRC / "Common/Audio/InfiniLuminanceSoundBridge.cs")
    runtime = read(SRC / "Common/VFX/InfiniVfxRuntime.cs")
    forbidden_substring_dispatch = [
        r"\b(?:effect|anchor|renderer|role|curve|channel|lane|color|identity|text|value|token|name)\s*\.Contains\(",
        r"\b(?:effect|anchor|renderer|role|curve|channel|lane|color|identity|text|value|token|name)\s*\.StartsWith\(",
    ]
    for name, source in [("GeneratedProjectile.Visuals.cs", visuals), ("VfxRendererRegistry.cs", registry), ("VfxParticleAddress.cs", particles), ("InfiniVfxRuntime.cs", runtime)]:
        clean = strip_comments_and_strings(source)
        if any(re.search(pattern, clean) for pattern in forbidden_substring_dispatch):
            err(f"{name}: canonical presentation dispatch must not use substring routing")
    for forbidden in ["PresentationIdentityText", "HasPresentationIdentity", "PolishDustForIdentity"]:
        if forbidden in visuals:
            err(f"GeneratedProjectile.Visuals.cs: fuzzy presentation router remains `{forbidden}`")
    if "VfxRendererRegistry.ParseKind(slot.RendererKind)" not in sound:
        err("InfiniLuminanceSoundBridge.cs: live sound dispatch must use exact rendererKind")

def main() -> int:
    if not SRC.exists():
        err(f"missing source root: {SRC}")
    for path in SRC.rglob("*.cs"):
        text = read(path)
        check_braces(path, text)
        check_required_usings(path, text)
    check_generated_item(read(SRC / "Content/Items/GeneratedItem.cs"))
    check_projectile(read_projectile_bundle())
    check_executor_split(read(SRC / "Content/Projectiles/GeneratedProjectile.Executors.cs"))
    check_player(read_player_bundle())
    check_packet_ids()
    check_visual_server_guards()
    check_model_property_references()
    check_generated_item_data_authoring_preservation_contract()
    check_projectile_child_runtime_guards()
    check_vfx_audio_presentation_guards()
    check_generated_armor_contract()
    check_network_read_write_shape()
    check_tml_feedback_warning_patterns()
    check_tml_feedback_warning_pattern_self_tests()
    check_actual_build_hook_available()
    check_overhaul_qol_contract()
    check_maintenance_qol_cleanup()
    check_runtime_family_policy_owner()
    check_project_namespace_references()
    check_strict_json_boundaries()
    check_exact_presentation_dispatch()

    if ERRORS:
        print("[FAIL] C# contract scanner found issues:")
        for e in ERRORS:
            print(" -", e)
        return 1
    print("[OK] C# contract scanner passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
