from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"
LOCAL = ROOT / "LocalGenerator"


def read(path: Path) -> str:
    return read_text_with_partial_bundles(path)


def test_dead_impact_blink_executor_is_not_registered():
    executors = read(MOD / "Content" / "Projectiles" / "GeneratedProjectile.Executors.cs")
    assert "ImpactBlinkExecutor" not in executors
    assert "CanRun(ProjectileRuntimeContext context) => false" not in executors
    assert "new WhipExecutor()" in executors


def test_projectile_extra_ai_uses_shared_shortnet_and_compact_reserved_flag():
    projectile = read(MOD / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    send_start = projectile.index("public override void SendExtraAI")
    send_end = projectile.index("public override void ReceiveExtraAI", send_start)
    send = projectile[send_start:send_end]
    assert "static string Short(" not in send
    assert "writer.Write(ShortNet(_generatedItemId" in send
    assert "writer.Write((byte)0); // reserved bitset" in send
    assert 'writer.Write(""); // reserved' not in send
    assert "private const int ProjectileSyncVersion = 6" in projectile
    assert "syncVersion != ProjectileSyncVersion" in projectile
    assert "expected {ProjectileSyncVersion}" in projectile
    assert "syncVersion <" not in projectile
    assert "// v3 reserved" not in projectile
    assert "v3/v4 ProjectileChild" not in projectile
    assert "legacy v3-v5 manifest fallback slot" not in projectile
    assert "reader.ReadByte(); // reserved bitset" in projectile
    assert "writer.Write(ShortNet(_spec.ProjectileImpact, 120));\n        writer.Write(ShortNet(_spec.SoundUse, 80));" in projectile


def test_csharp_attack_spec_no_legacy_prose_script_fields():
    model = read(MOD / "Common" / "Models" / "GeneratedItemData.cs")
    runtime = read(MOD / "Content" / "Projectiles" / "GeneratedProjectile.cs")
    dump = read(MOD / "Common" / "Commands" / "InfiniDumpPictureCommand.cs")
    for removed in [
        "ToyIdentity",
        "SpecialRule",
        "BehaviorActions",
        "BehaviorTimeline",
        "OnUseScript",
        "OnTickScript",
        "OnHitScript",
        "OnExpireScript",
        "ProjectileChild",
    ]:
        assert removed not in model
        assert removed not in runtime
        assert removed not in dump


def test_csharp_runtime_compat_migrations_are_removed_for_test_worlds_only():
    data_bundle = read(MOD / "Common" / "Models" / "GeneratedItemData.cs")
    assert not (MOD / "Common" / "Models" / "GeneratedItemData.Compat.cs").exists()
    for removed in [
        "ApplyCompatMigrations",
        "CompatNeedsRuntimeFamilyBackfill",
        "CompatLooksLikeShootRuntime",
        "CompatNeedsUseStyleBackfill",
        "CompatUseStyleForRuntimeFamily",
        "AttackRuntimeFamilyCompat",
    ]:
        assert removed not in data_bundle
    assert "Attack.RuntimeFamily = NormalizeRuntimeFamily(Attack.RuntimeFamily);" in data_bundle


def test_no_retired_parent_projectile_profile_or_vfx_quality_aliases():
    client = read(MOD / "Common" / "Services" / "GeneratorClient.cs")
    vfx = read(MOD / "Common" / "Models" / "VfxManifestSpec.cs")
    assert "projectileProfile = ProjectileProfileFromItem" not in client
    assert "ProjectileProfileFromItem" not in client
    assert "public string Quality" not in vfx
    assert "public string RenderQuality" not in vfx
    assert "public string MinQuality" not in vfx


def test_runtime_sprite_cache_has_bounded_lru_trim():
    cache = read(MOD / "Common" / "Services" / "RuntimeSpriteCache.cs")
    config = read(MOD / "Common" / "Config" / "InfiniGameplayQolConfig.cs")
    assert "DefaultMaxCachedTextures = 512" in cache
    assert "RuntimeSpriteCacheMaxTextures" in cache
    assert "EffectiveLimits" in cache
    assert "CachedTexture" in cache
    assert "LastAccessTick" in cache
    assert "TrimTextureCacheIfNeeded" in cache
    assert "while (_textures.Count > maxCachedTextures)" in cache
    assert "texture.Dispose();" in cache
    assert "MaxMissingOrBadRecords = 256" in cache
    assert "TrimMissingOrBadCacheIfNeeded" in cache
    assert "RuntimeSpriteCacheMaxTextures" in config
    assert "[Range(64, 2048)]" in config


def test_env_loader_is_shared_not_duplicated():
    assert (LOCAL / "infini_local" / "core" / "env_utils.py").exists()
    matches = []
    for path in (LOCAL / "infini_local").rglob("*.py"):
        text = read(path)
        if "def load_env_file" in text:
            matches.append(path.relative_to(LOCAL).as_posix())
    assert matches == ["infini_local/core/env_utils.py"]
    bootstrap = read(LOCAL / "infini_local" / "core" / "config_bootstrap.py")
    assert "from infini_local.core.env_utils import env_path, env_str, load_env_file" in bootstrap
    assert "load_env_file(CONFIG_PATH)" in bootstrap
    vfx_config = read(LOCAL / "infini_local" / "core" / "vfx_manifest_config.py")
    assert "from infini_local.core.env_utils import load_env_file" in vfx_config
    assert "load_env_file(ROOT / \"config.env\")" in vfx_config
    vfx = read(LOCAL / "infini_local" / "core" / "vfx_manifest.py")
    assert "from infini_local.core.vfx_manifest_config import (" in vfx
    assert "from infini_local.core.env_utils import load_env_file" not in vfx
    web = read(LOCAL / "infini_local" / "web" / "server.py")
    api = read(LOCAL / "infini_local" / "web" / "api.py")
    pipeline = read(LOCAL / "infini_local" / "pipelines" / "pipeline_support.py")
    assert "from infini_local.core.config_bootstrap import (" in web
    assert "from infini_local.core.config_bootstrap import (" in pipeline
    assert "from infini_local.pipelines.item_power_knowledge import (" in api
    assert "from infini_local.pipelines.item_power_knowledge import (" in pipeline
    assert "def fingerprint_tags" not in web
    assert "def fingerprint_tags" not in pipeline


def test_maintenance_contract_stamp_exists():
    contracts = read(LOCAL / "infini_local" / "core" / "contract_versions.py")
    assert "maintainability_gameplay_qol_cleanup_v0.4.203" in contracts
    assert "maintenanceQolContract" in contracts


def test_maintenance_hardening_contracts_for_review_findings():
    repair = read(ROOT / "tools" / "repair_tmodloader_tplr_strings.py")
    endpoint = read(LOCAL / "infini_local" / "services" / "combine_endpoint.py")
    combine = read(LOCAL / "infini_local" / "pipelines" / "combine_pipeline.py")
    vfx = read(LOCAL / "infini_local" / "core" / "vfx_manifest.py")
    identity = read(LOCAL / "infini_local" / "core" / "item_identity_tools.py")
    gui = read(LOCAL / "infini_local" / "desktop" / "settings_gui.py")
    gui_theme = read(LOCAL / "infini_local" / "desktop" / "settings_gui_theme.py")
    item = read(MOD / "Content" / "Items" / "GeneratedItem.cs")
    extract = read(MOD / "Content" / "Items" / "GeneratedExtractinatorMaterial.cs")
    player = read(MOD / "Common" / "Players" / "InfiniCraftPlayer.cs")
    client = read(MOD / "Common" / "Services" / "GeneratorClient.cs")

    assert "ENGINE_RUNTIME_API_VERSION" in repair
    assert '"v0.4.30"' not in repair
    assert "combine_response_not_json_serializable" in endpoint
    assert "json_module.dumps(data" in endpoint
    assert "globals())" not in combine
    assert "def _dev_fallback_helpers" in combine
    assert "from infini_local.core.item_identity_tools import (" in vfx
    assert "def stable_hash" not in vfx
    assert "def tags_of" in identity
    assert "Settings GUI v0.4.239" in gui_theme
    assert "from infini_local.desktop.settings_gui_theme import" in gui
    assert "LogLowNoiseWarning" in item
    assert "[GeneratedItem]" in item
    assert "[GeneratedExtractinatorMaterial]" in extract
    assert "InfiniGameplayQolConfig unavailable" in player
    assert "? envTimeout : 240" in client
    assert "repair_json_sync_and_low_noise_fallback_logs_v0.4.205" in read(LOCAL / "infini_local" / "core" / "contract_versions.py")
