from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"
LOCAL = ROOT / "LocalGenerator"


def read(path: Path) -> str:
    return read_text_with_partial_bundles(path)


def _contract_check_runtime_sprite_cache_exposes_debug_snapshot_and_manual_controls():
    cache = read(MOD / "Common" / "Services" / "RuntimeSpriteCache.cs")
    command = read(MOD / "Common" / "Commands" / "InfiniCacheCommand.cs")
    assert "RuntimeSpriteCacheDebugSnapshot" in cache
    assert "GetDebugSnapshot()" in cache
    assert "EstimatedTextureBytes" in cache
    assert "HitCount" in cache and "MissCount" in cache
    assert "RejectedFileSizeCount" in cache
    assert "RejectedDimensionCount" in cache
    assert "ClearMissingOrBad" in cache
    assert "public int Clear(bool clearMissingOrBad = true)" in cache
    assert "public sealed class InfiniCacheCommand" in command
    assert 'Command => "infinicache"' in command
    assert "caller.Reply" in command
    assert "Warm(caller" in command
    assert "Disk PNG/JSON files were not deleted" in command


def _contract_check_generated_swing_onhit_executes_bounded_authored_codes():
    item = read(MOD / "Content" / "Items" / "GeneratedItem.cs")
    config = read(MOD / "Common" / "Config" / "InfiniGameplayQolConfig.cs")
    assert "EnableGeneratedMeleeOnHitEffects" in config
    assert "GeneratedMeleeOnHitEffectsEnabled" in item
    assert "ApplyGeneratedSwingOnHitEffects" in item
    assert "attack.OnHitCode" in item
    assert "BuffID.OnFire" in item
    assert "BuffID.Frostburn" in item
    assert "BuffID.Poisoned" in item
    assert "BuffID.ShadowFlame" in item
    assert "BuffID.Bleeding" in item
    assert "HealGeneratedSwingOwner" in item
    assert "GeneratedSwingDustType" in item
    assert "SwingOnHitSummary" in item
    assert "small lifesteal" in item

    projectile = read(MOD / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    assert "private int DebuffDuration" in projectile
    assert "Math.Clamp(authored, 30, 600)" in projectile
    assert "target.AddBuff(BuffID.OnFire, DebuffDuration(240))" in projectile
    assert "target.AddBuff(BuffID.Electrified, DebuffDuration(140))" in projectile


def _contract_check_rebuild_qol_config_localization_and_contract_stamp():
    en = read(MOD / "Localization" / "en-US_Mods.InfiniCrafterLocal.hjson")
    ru = read(MOD / "Localization" / "ru-RU_Mods.InfiniCrafterLocal.hjson")
    contracts = read(LOCAL / "infini_local" / "core" / "contract_versions.py")
    assert "GeneratedGameplayQoL" in en
    assert "Generated melee on-hit effects" in en
    assert "No prompt text is parsed" in en
    assert "GeneratedGameplayQoL" in ru
    assert "Generated melee on-hit / On-hit эффекты ближнего боя" in ru
    assert "Текст prompt не парсится" in ru
    assert "REBUILD_GAMEPLAY_CACHE_DIAGNOSTICS_CONTRACT_VERSION" in contracts
    assert "rebuildGameplayCacheDiagnosticsContract" in contracts
    assert "generated_melee_onhit_and_cache_diagnostics_v0.4.209" in contracts


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_rebuild_gameplay_cache_diagnostics_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_runtime_sprite_cache_exposes_debug_snapshot_and_manual_controls',
            '_contract_check_generated_swing_onhit_executes_bounded_authored_codes',
            '_contract_check_rebuild_qol_config_localization_and_contract_stamp',
        ),
    )
