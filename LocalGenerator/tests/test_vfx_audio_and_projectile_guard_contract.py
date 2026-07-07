from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]


def test_chain_projectiles_uses_runtime_child_count_cap():
    src = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    body = src.split("private void ChainProjectiles", 1)[1].split("private void", 1)[0]
    assert "count = RuntimeChildCount(count);" in body
    assert "for (int chain = 0; chain < count; chain++)" in body


def test_projectile_impact_sound_uses_authored_volume_pitch_and_cooldown():
    src = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    assert "private int _lastImpactSoundLocalTick = -9999;" in src
    assert "localTick - _lastImpactSoundLocalTick < 4" in src
    assert "InfiniSoundLibrary.ForImpact" in src
    assert "_spec.SoundVolume" in src
    assert "_spec.SoundPitch" in src


def test_vfx_sound_cues_are_rate_limited_and_use_authored_audio_fields():
    src = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "InfiniVfxRuntime.cs").read_text(encoding="utf-8")
    assert "private static bool SoundSlotTickAllowed" in src
    assert "InfiniLuminanceSoundBridge.TryUpdateLiveSoundCue" in src
    assert "SoundSlotTickAllowed(slot, state.Tick)" in src
    assert "slot.RepeatEvery > 0" in src
    assert "spec.UseSoundProfile" in src
    assert "spec.SoundUse" in src
    assert "spec.SoundVolume" in src
    assert "spec.SoundPitch" in src
    assert "InfiniSoundLibrary.ForVfxCue" in src


def test_infini_sound_library_has_named_profiles_and_shared_resolvers():
    src = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Audio" / "InfiniSoundLibrary.cs").read_text(encoding="utf-8")
    assert "public const string ContractVersion = \"infini.vanilla-sound-catalog.v6\";" in src
    assert "public static readonly string[] KnownProfiles" in src
    assert "public static SoundStyle ForUse" in src
    assert "public static SoundStyle ForImpact" in src
    assert "public static SoundStyle ForVfxCue" in src
    assert "InfiniFutureSoundCatalog.TryResolveOneShot" in src
    assert "InfiniExternalSoundPack" not in src
    for profile in ["electric", "explosion", "crystal", "slime", "heal", "shadow", "leaf", "shotgun", "sniper", "laser", "whip", "zenith", "sentry", "meteor"]:
        assert f'"{profile}"' in src
    for sound_id in ["SoundID.Item36", "SoundID.Item40", "SoundID.Item41", "SoundID.Item43", "SoundID.Item72", "SoundID.Item84", "SoundID.Item108", "SoundID.Item152", "SoundID.Item169"]:
        assert sound_id in src
    for helper in ["StyleFromRangedText", "StyleFromMagicText", "StyleFromSummonText", "StyleFromMaterialOrEffectText"]:
        assert helper in src


def test_generated_item_use_sound_resolves_through_library():
    src = read_text_with_partial_bundles(ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "Models" / "GeneratedItemData.cs")
    assert "using InfiniCrafterLocal.Common.Audio;" in src
    assert "InfiniSoundLibrary.ForUse" in src
    for field in ["SoundUseCatalogId", "SoundImpactCatalogId", "SoundUseSearchQuery", "SoundImpactSearchQuery", "SoundCatalogSource", "SoundUseCatalogPath", "SoundImpactCatalogPath"]:
        assert field in src


def test_vfx_fallback_dust_uses_effect_before_color_guess():
    src = (ROOT / "ModSources" / "InfiniCrafterLocal" / "Common" / "VFX" / "InfiniVfxRuntime.cs").read_text(encoding="utf-8")
    assert "private static int DustForEffect(AttackSpec spec)" in src
    assert "int effectDust = DustForEffect(spec);" in src
    assert "DustID.Electric" in src
    assert "DustID.YellowStarDust" in src
    assert "DustID.Shadowflame" in src


def test_external_luminance_sound_bridge_is_wired_for_live_vfx_audio():
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


def test_external_kenney_sound_pack_bridge_removed_and_future_catalog_seam_exists():
    root = ROOT / "ModSources" / "InfiniCrafterLocal"
    audio_dir = root / "Common" / "Audio"
    future = (audio_dir / "InfiniFutureSoundCatalog.cs").read_text(encoding="utf-8")
    library = (audio_dir / "InfiniSoundLibrary.cs").read_text(encoding="utf-8")
    config = (root / "Common" / "Config" / "InfiniVfxClientConfig.cs").read_text(encoding="utf-8")
    options = (root / "Common" / "VFX" / "InfiniVfxClientOptions.cs").read_text(encoding="utf-8")

    assert not (audio_dir / "InfiniExternalSoundPack.cs").exists()
    assert not (ROOT / "tools" / "import_kenney_rpg_sounds.py").exists()
    assert "EnableExternalSoundPack" not in config
    assert "EnableExternalSoundPack" not in options
    assert "InfiniExternalSoundPack" not in library

    assert "infini.embedding-sound-catalog.future-seam.v1" in future
    assert "TryResolveOneShot" in future
    assert "return false;" in future
    assert "embedding" in future.lower()
    assert "concrete asset/id" in future
    assert "InfiniFutureSoundCatalog.TryResolveOneShot" in library
    assert "public bool IsImpact { get; }" in future
    assert "public bool Impact { get; }" not in future
    for field in ["CatalogId", "CatalogPath", "CatalogSource", "QueryText"]:
        assert field in future


def test_contract_stamp_mentions_future_sound_catalog_seam():
    src = (ROOT / "LocalGenerator" / "infini_local" / "core" / "contract_versions.py").read_text(encoding="utf-8")
    assert "futureSoundCatalogSeam" in src
    assert "embedding_sound_catalog_future_seam_v0.4.190" in src
    assert "externalSoundPackContract" not in src
