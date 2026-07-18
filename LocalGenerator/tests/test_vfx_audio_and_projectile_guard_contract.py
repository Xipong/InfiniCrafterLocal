from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]


def _contract_check_chain_projectiles_uses_runtime_child_count_cap():
    src = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    body = src.split("private void ChainProjectiles", 1)[1].split("private void", 1)[0]
    assert "count = RuntimeChildCount(count);" in body
    assert "for (int chain = 0; chain < count; chain++)" in body


def _contract_check_projectile_impact_sound_uses_authored_volume_pitch_and_cooldown():
    src = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    assert "private int _lastImpactSoundLocalTick = -9999;" in src
    assert "localTick - _lastImpactSoundLocalTick < 4" in src
    assert "InfiniSoundLibrary.ForImpact" in src
    assert "_spec.SoundVolume" in src
    assert "_spec.SoundPitch" in src


def _contract_check_vfx_sound_cues_are_rate_limited_and_use_authored_audio_fields():
    src = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "InfiniVfxRuntime.cs").read_text(encoding="utf-8")
    assert "private static bool SoundSlotTickAllowed" in src
    assert "InfiniLuminanceSoundBridge.TryUpdateLiveSoundCue" in src
    assert "SoundSlotTickAllowed(slot, state.Tick)" in src
    assert "slot.RepeatEvery > 0" in src
    assert "spec.SoundUseCatalogId" in src
    assert "spec.SoundImpactCatalogId" in src
    assert "spec.UseSoundProfile" not in src
    assert "spec.SoundUse," not in src
    assert "spec.SoundVolume" in src
    assert "spec.SoundPitch" in src
    assert "InfiniSoundLibrary.ForVfxCue" in src
    play = src.split("private static void PlaySlotSound", 1)[1].split("private static void DrawLine", 1)[0]
    assert play.index("IsBuiltInCatalogId") < play.index("ForVfxCue")
    loop = (ROOT / "ModSources/InfiniCrafterLocal/Common/Audio/InfiniLuminanceSoundBridge.cs").read_text(encoding="utf-8")
    update = loop.split("public static bool TryUpdateLiveSoundCue", 1)[1].split("private static bool ShouldLoop", 1)[0]
    assert update.index("IsBuiltInCatalogId(spec.SoundUseCatalogId)") < update.index("ForVfxCue")


def _contract_check_vfx_director_sound_timing_survives_manifest_compilation():
    from infini_local.core.vfx_director_contract import vfx_director_surface
    from infini_local.core.vfx_manifest import _vfx_validate_director_output

    surface = vfx_director_surface()
    slot = {
        "event": "travel",
        "rendererKind": "soundCue",
        "backend": surface["backend"][0],
        "textureRole": surface["textureRole"][0],
        "particleRole": surface["particleRole"][0],
        "anchor": surface["anchor"][0],
        "channel": "sound",
        "lane": surface["lane"][0],
        "emissionMode": surface["emissionMode"][0],
        "blend": surface["blend"][0],
        "particleSystemId": surface["particleSystemId"][0],
        "scale": 1.0,
        "density": 0.25,
        "duration": 40,
        "alpha": 0.0,
        "spread": 0.0,
        "jitter": 0.0,
        "budgetWeight": 1.0,
        "signatureWeight": 0.4,
        "visualCost": 0.0,
        "fadeIn": 0.0,
        "fadeOut": 0.0,
        "startTick": 20,
        "repeatEvery": 60,
    }
    manifest = _vfx_validate_director_output(
        {
            "identity": "bounded travel audio",
            "effectMagnitude": 0.4,
            "visualBudgetClass": "small",
            "slots": [slot],
        },
        {
            "id": "sound_timing_contract",
            "gameplay": {"powerBudget": 1.0},
            "attack": {"enabled": True, "pattern": "basic", "runtimeFamily": "shoot"},
        },
        "sound_timing_contract",
    )
    assert manifest is not None
    assert manifest["slots"][0]["startTick"] == 20
    assert manifest["slots"][0]["repeatEvery"] == 60


def _contract_check_infini_sound_library_has_large_exact_catalog_without_weapon_name_classifier():
    src = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Audio" / "InfiniSoundLibrary.cs").read_text(encoding="utf-8")
    assert 'public const string ContractVersion = "infini.terraria-sound-catalog.v8";' in src
    assert 'public const string BuiltInCatalogSource = "terraria_vanilla";' in src
    assert "public static int BuiltInCatalogCount" in src
    assert "public static SoundStyle ForUse" in src
    assert "public static SoundStyle ForImpact" in src
    assert "public static SoundStyle ForVfxCue" in src
    assert "InfiniFutureSoundCatalog.TryResolveOneShot" in src
    assert "InfiniExternalSoundPack" not in src
    assert src.count('["') >= 90
    for exact_id in ["melee_thrust", "shotgun_heavy", "laser_space", "magic_wind_vortex", "summon_skittering", "impact_electric", "impact_crystal", "impact_void"]:
        assert f'["{exact_id}"]' in src
    for sound_id in ["SoundID.Item36", "SoundID.Item40", "SoundID.Item43", "SoundID.Item72", "SoundID.Item84", "SoundID.Item108", "SoundID.Item152", "SoundID.Item169"]:
        assert sound_id in src
    for forbidden in ["KnownProfiles", "StyleFromRangedText", "StyleFromMagicText", "StyleFromSummonText", "StyleFromMaterialOrEffectText", "HasAny", "terra blade", "last prism"]:
        assert forbidden not in src.lower() if forbidden == forbidden.lower() else forbidden not in src


def _contract_check_generated_item_use_sound_resolves_through_library():
    src = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs")
    assert "using InfiniCrafterLocal.Common.Audio;" in src
    assert "InfiniSoundLibrary.ForUse" in src
    for field in ["SoundUseCatalogId", "SoundImpactCatalogId", "SoundCatalogSource", "SoundUseCatalogPath", "SoundImpactCatalogPath", "SoundPitchVariance"]:
        assert field in src


def _contract_check_vfx_fallback_dust_uses_effect_before_color_guess():
    src = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "InfiniVfxRuntime.cs").read_text(encoding="utf-8")
    assert "private static int DustForEffect(AttackSpec spec)" in src
    assert "int effectDust = DustForEffect(spec);" in src
    assert "DustID.Electric" in src
    assert "DustID.YellowStarDust" in src
    assert "DustID.Shadowflame" in src


def _contract_check_external_luminance_sound_bridge_is_wired_for_live_vfx_audio():
    root = ROOT / "ModSources" / "InfiniCrafterLocal"
    build = (root / "build.txt").read_text(encoding="utf-8")
    bridge = (root / "Common" / "Audio" / "InfiniLuminanceSoundBridge.cs").read_text(encoding="utf-8")
    vfx = (root / "Common" / "VFX" / "InfiniVfxRuntime.cs").read_text(encoding="utf-8")
    config = (root / "Common" / "Config" / "InfiniVfxClientConfig.cs").read_text(encoding="utf-8")
    options = (root / "Common" / "VFX" / "InfiniVfxClientOptions.cs").read_text(encoding="utf-8")
    assert "modReferences = ParticleLibrary, Luminance" in build
    assert "using Luminance.Core.Sounds;" in bridge
    assert "LoopedSoundManager.CreateNew" in bridge
    assert "LoopedSoundInstance" in bridge
    assert "TryUpdateLiveSoundCue" in bridge
    assert "LoopShouldStop" in bridge
    assert "MaxActiveLoops" in bridge
    assert "Instance.Update(projectile.Center)" in bridge or "instance.Update(projectile.Center)" in bridge
    assert "InfiniLuminanceSoundBridge.TryUpdateLiveSoundCue" in vfx
    assert "EnableLuminanceSoundBackend" in config
    assert "EnableLuminanceSoundBackend" in options
    assert "DefaultValue(false)" in config
    assert "Config?.EnableLuminanceSoundBackend ?? false" in options


# One collected item per contract module; individual checks keep source order and tracebacks.
def test_vfx_audio_and_projectile_guard_contract_module_contract(request):
    from contract_checks import run_contract_checks

    run_contract_checks(
        globals(),
        request,
        (
            '_contract_check_chain_projectiles_uses_runtime_child_count_cap',
            '_contract_check_projectile_impact_sound_uses_authored_volume_pitch_and_cooldown',
            '_contract_check_vfx_sound_cues_are_rate_limited_and_use_authored_audio_fields',
            '_contract_check_vfx_director_sound_timing_survives_manifest_compilation',
            '_contract_check_infini_sound_library_has_large_exact_catalog_without_weapon_name_classifier',
            '_contract_check_generated_item_use_sound_resolves_through_library',
            '_contract_check_vfx_fallback_dust_uses_effect_before_color_guess',
            '_contract_check_external_luminance_sound_bridge_is_wired_for_live_vfx_audio',
        ),
    )
