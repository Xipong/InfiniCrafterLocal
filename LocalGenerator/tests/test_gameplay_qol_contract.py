from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
ITEM = ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Items" / "GeneratedItem.cs"
PLAYER = ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Players" / "InfiniCraftPlayer.cs"
CONTRACTS = ROOT / "LocalGenerator" / "infini_local" / "core" / "contract_versions.py"


def test_generated_item_has_low_noise_use_condition_and_alt_mobility_feedback():
    src = ITEM.read_text(encoding="utf-8")
    assert "UseBlockedReason(Player player)" in src
    assert "ShowLocalUseFeedback" in src
    assert "_lastUseBlockedNoticeTick" in src
    assert "_lastAltUseBlockedNoticeTick" in src
    assert "Mobility cooldown:" in src
    assert "modPlayer.LastGeneratedMobilityFailureMessage" in src
    assert "return used;" in src


def test_generated_tooltips_expose_compact_gameplay_qol_surface():
    src = ITEM.read_text(encoding="utf-8")
    assert "UseConditionSummary(Data?.Gameplay)" in src or "UseConditionSummary(gameplay)" in src
    assert "CompactGeneratedCombatSummary(Data)" in src or "CompactGeneratedCombatSummary(data)" in src
    for needle in [
        "SentrySlots",
        "ManaCostReduction",
        "AmmoSaveChance",
        "Aggro",
        "Endurance",
        "ArmorPenetration",
        "WhipRange",
        "SummonTagDamage",
        "set bonus ready",
    ]:
        assert needle in src


def test_infini_player_reports_mobility_failure_reason_and_cooldown():
    src = read_text_with_partial_bundles(PLAYER)
    assert "GeneratedMobilityCooldownTicks" in src
    assert "GeneratedMobilityCooldownSeconds" in src
    assert "LastGeneratedMobilityFailureMessage" in src
    assert "TryReserveGeneratedMobilityCooldown" in src
    assert "StartGeneratedMobilityCooldown" in src
    assert "UnsupportedGeneratedMobility" in src
    assert "Unsafe blink destination" in src
    assert "No valid spawn point" in src
    assert "Mobility is waiting for local control" in src



def test_projectile_impact_mobility_respects_shared_cooldown_and_tooltip_surface():
    projectile = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    item = ITEM.read_text(encoding="utf-8")
    assert "TryRunImpactMobility" in projectile
    assert "GetModPlayer<InfiniCraftPlayer>()" in projectile
    assert "TryReserveGeneratedMobilityCooldown(_spec.MobilityCooldownTicks)" in projectile
    assert "ImpactMobilitySummary" in item
    assert "blink_to_projectile_impact" in item
    assert "impact blink" in item
