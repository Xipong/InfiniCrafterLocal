from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECTILES = ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles"
ITEMS = ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items"
LIFECYCLE = ROOT / "contracts" / "field_lifecycle.json"


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _method(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated method: {signature}")


def _check_combat_extra_ai_is_identity_variant_and_compact_instance_state_only() -> None:
    source = _text(PROJECTILES / "GeneratedProjectile.NetSync.cs")
    send = _method(source, "public override void SendExtraAI(BinaryWriter writer)")
    receive = _method(source, "public override void ReceiveExtraAI(BinaryReader reader)")

    assert "private const int ProjectileSyncVersion = 20" in source
    assert "writer.Write(ShortNet(_generatedItemId, 96));" in send
    assert "writer.Write((byte)_runtimeVariant);" in send
    assert "_spec." not in send
    assert "SpritePathForNet" not in send
    assert "ShortNet(_spec" not in send

    # The only mutable instance values beyond identity/discriminant are bounded
    # projectile state that cannot be reconstructed from the hydrated root spec.
    writes = re.findall(r"writer\.Write\((.*?)\);", send, re.S)
    allowed_fragments = (
        "ProjectileSyncVersion",
        "_configured",
        "_generatedItemId",
        "_runtimeVariant",
        "_chargeTicksAccumulated",
        "_sentryFireTimer",
        "_beamLengthPx",
        "Projectile.localAI[1]",
        "Projectile.localAI[2]",
        "_spawnIgnoreNpc",
        "_spawnIgnoreTicks",
        "_stuckToTile",
        "_returningPhase",
    )
    assert writes
    assert all(any(fragment in expression for fragment in allowed_fragments) for expression in writes), writes

    assert "TryHydrateRuntimeVariantFromRegistry()" in receive
    assert "TryGetAttack(_generatedItemId)" in source
    assert "TryCreateRuntimeVariant" in source
    assert "RequestOneGeneratedItemForMissingProjectile(_generatedItemId)" in source
    assert not re.search(r"_spec\.\w+\s*=\s*reader\.Read", receive)
    assert "ReadStringKeepBase" not in receive
    assert "_spawnIgnoreNpc = reader.ReadInt32();" in receive
    assert "_spawnIgnoreTicks = reader.ReadInt32();" in receive
    assert "_spawnIgnoreNpc < -1 || _spawnIgnoreNpc >= Main.maxNPCs" in receive

    restore = _method(source, "private void ApplyResolvedRuntimeVariant(")
    assert "Math.Clamp(chargeTicks, 0, Math.Clamp(resolved.ChargeTicks, 1, 300))" in restore
    assert "Math.Clamp(sentryTimer, 0, Math.Clamp(resolved.SentryAttackIntervalTicks, 12, 180))" in restore
    assert "Math.Clamp(beamLength, 0f, ConfiguredRangePixels(560f))" in restore
    assert "Math.Clamp(rootIdentity, 0f, 1_000_000f)" in restore


def _check_every_derived_projectile_has_a_compact_deterministic_discriminant() -> None:
    policy = _text(PROJECTILES / "GeneratedChildSpecPolicy.cs")
    runtime = _text(PROJECTILES / "GeneratedProjectile.Runtime.cs")
    impact = _text(PROJECTILES / "GeneratedProjectile.Impact.cs")
    charge = _text(PROJECTILES / "GeneratedProjectile.ChargeRelease.cs")
    item = _text(ITEMS / "GeneratedItem.cs")

    for variant in (
        "Root",
        "StraightSecondary",
        "ChainSecondary",
        "RadialSecondary",
        "OverheadSecondary",
        "SporeSecondary",
        "MiniMissileSecondary",
        "VortexSecondary",
        "SentryShot",
        "ChargeReleasedShot",
        "SwingSecondary",
        "SwingOverheadSecondary",
    ):
        assert variant in policy

    assert "TryCreateRuntimeVariant(" in policy and "AttackSpec parent" in policy
    # C# enums do not define relational operators directly. The finite wire
    # discriminator check must compare the declared byte representation so the
    # compact-sync policy remains compilable as well as statically inspectable.
    assert not re.search(r"=>\s*variant\s*(?:>=|<=|>|<)", policy)
    assert "IsVariantAllowedForParent" in policy
    assert "!parent.Enabled || !parent.RuntimePlanAuthored" in policy
    assert "bool damagingChild = boundedChild && parent.SecondaryDamageMultiplier > 0f" in policy
    assert "GeneratedProjectileRuntimeVariant.SentryShot => boundedChild" in policy
    assert "GeneratedRuntimeFamilyPolicy.ChargeRelease" in policy
    assert "GeneratedRuntimeFamilyPolicy.Sentry" in policy
    assert "GeneratedRuntimeFamilyPolicy.Swing" in policy

    # Root keeps the default; every locally derived spec must name its wire
    # reconstruction policy instead of relying on a full AttackSpec copy.
    assert "GeneratedProjectileRuntimeVariant runtimeVariant = GeneratedProjectileRuntimeVariant.Root" in runtime
    assert "GeneratedProjectileRuntimeVariant runtimeVariant" in impact
    assert "ApplyGeneratedSpec(childSpec, new VfxManifestSpec(), _generatedItemId, runtimeVariant)" in impact
    for source in (charge, item):
        derived_calls = [
            match.group(0)
            for match in re.finditer(r"ApplyGeneratedSpec\((?:(?!\);).)*\);", source, re.S)
            if "Data.Attack" not in match.group(0)
        ]
        assert derived_calls
        assert all("GeneratedProjectileRuntimeVariant." in call for call in derived_calls), derived_calls


def _check_missing_registry_data_defers_harmlessly_and_retries_hydration() -> None:
    source = _text(PROJECTILES / "GeneratedProjectile.NetSync.cs")
    runtime = _text(PROJECTILES / "GeneratedProjectile.Runtime.cs")
    receive = _method(source, "public override void ReceiveExtraAI(BinaryReader reader)")

    # tML can emit the initial entity packet before ApplyGeneratedSpec. That
    # unconfigured packet legitimately has no registry id yet and must enter the
    # harmless grace window; a configured packet still requires a bounded id.
    assert "_generatedItemId.Length > 96" in receive
    assert "packetConfigured && _generatedItemId.Length <= 0" in receive
    assert "if (!packetConfigured)" in receive
    unconfigured = receive.index("if (!packetConfigured)")
    hydration = receive.index("TryHydrateRuntimeVariantFromRegistry()", unconfigured)
    assert "DeferUnconfiguredNetworkProjectile();" in receive[unconfigured:hydration]

    assert "private bool TryHydrateRuntimeVariantFromRegistry()" in source
    hydrate = _method(source, "private bool TryHydrateRuntimeVariantFromRegistry()")
    assert "TryGetAttack(_generatedItemId)" in hydrate
    assert "GeneratedChildSpecPolicy.TryCreateRuntimeVariant" in hydrate
    assert "RequestOneGeneratedItemForMissingProjectile(_generatedItemId)" in hydrate
    assert "ApplyResolvedRuntimeVariant" in hydrate

    # The id-only visual relay may arrive before ExtraAI. It is presentation
    # context, not authority to assume the Root runtime variant for a child.
    visual_sync = _method(source, "private void ApplyProjectileVisualSyncPayload(")
    assert "TryHydrateRuntimeVariantFromRegistry()" not in visual_sync
    assert "ApplyGeneratedSpec(" not in visual_sync

    defer = _method(source, "private void DeferUnconfiguredNetworkProjectile()")
    assert "ClearResolvedRuntimeSpec(Math.Max(_pendingNetworkSpecTicks, 45))" in defer
    assert "Projectile.damage = 0" in defer
    assert "Projectile.friendly = false" in defer
    assert "Projectile.hostile = false" in defer

    clear_resolved = _method(source, "private void ClearResolvedRuntimeSpec(")
    assert "_configured = false" in clear_resolved
    assert "_pendingNetworkSpecTicks = pendingSpecTicks" in clear_resolved
    assert "new AttackSpec { Enabled = false" in clear_resolved

    ai = _method(runtime, "public override void AI()")
    assert "TryHydrateRuntimeVariantFromRegistry()" in ai
    assert "_pendingNetworkSpecTicks" in ai


def _check_release_evidence_models_registry_hydration_not_attack_spec_packets() -> None:
    lifecycle = json.loads(_text(LIFECYCLE))
    compact = lifecycle["projectileCompactSync"]
    assert compact["version"] == 20
    assert compact["writeExpressions"] == [
        "ProjectileSyncVersion",
        "_configured",
        "ShortNet(_generatedItemId, 96)",
        "(byte)_runtimeVariant",
        "_chargeTicksAccumulated",
        "_sentryFireTimer",
        "_beamLengthPx",
        "Projectile.localAI[1]",
        "Projectile.localAI[2]",
        "_spawnIgnoreNpc",
        "_spawnIgnoreTicks",
        "_stuckToTile",
        "_returningPhase",
    ]
    assert [(row["target"], row["method"]) for row in compact["readSlots"]] == [
        ("syncVersion", "Int32"),
        ("packetConfigured", "Boolean"),
        ("_generatedItemId", "String"),
        ("_runtimeVariant", "Byte"),
        ("_chargeTicksAccumulated", "Int32"),
        ("_sentryFireTimer", "Int32"),
        ("_beamLengthPx", "Single"),
        ("Projectile.localAI[1]", "Single"),
        ("Projectile.localAI[2]", "Single"),
        ("_spawnIgnoreNpc", "Int32"),
        ("_spawnIgnoreTicks", "Int32"),
        ("_stuckToTile", "Boolean"),
        ("_returningPhase", "Boolean"),
    ]
    for policy in lifecycle["attack"].values():
        assert "registryHydration" in policy["requiredStages"]
        assert "netWrite" not in policy["requiredStages"]
        assert "netRead" not in policy["requiredStages"]

    parity = _text(ROOT / "tools" / "contract_parity.py")
    scanner = _text(ROOT / "tools" / "check_csharp_contracts.py")
    mutation = _text(ROOT / "tools" / "mutation_contract_gate.py")
    assert "combat ExtraAI must not write or read AttackSpec fields" in parity
    assert "registryHydration" in parity
    assert "compact v20 SendExtraAI order mismatch" in scanner
    assert "projectile_network_attack_spec_field_added" in mutation
    assert "projectile_variant_reconstruction_removed" in mutation
    assert "projectile_unconfigured_packet_no_longer_defers" in mutation
    assert "projectile_variant_byte_bound_made_uncompilable" in mutation
    assert "projectile_visual_relay_assumes_root_variant" in mutation


def _run_coarse_contract() -> None:
    _check_combat_extra_ai_is_identity_variant_and_compact_instance_state_only()
    _check_every_derived_projectile_has_a_compact_deterministic_discriminant()
    _check_missing_registry_data_defers_harmlessly_and_retries_hydration()
    _check_release_evidence_models_registry_hydration_not_attack_spec_packets()


def test_csharp_projectile_compact_sync_contract() -> None:
    _run_coarse_contract()


if __name__ == "__main__":
    _run_coarse_contract()
