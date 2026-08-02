from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CS = ROOT / "ModSources" / "InfiniCrafterLocal"


def _read(path: str) -> str:
    return (CS / path).read_text("utf-8", errors="ignore")


def test_impact_path_has_exact_model_sync_and_cache_owners() -> None:
    model = _read("Common/Models/RuntimeProgramSpec.cs")
    wire = _read("Common/Models/GeneratedItemData.cs")
    assets = _read("Common/Services/GeneratedAssetSyncService.cs")
    runtime = _read("Common/VFX/InfiniVfxRuntime.cs")

    assert "ImpactSpritePath" in model
    assert "entity.Visual.ImpactSpritePath = FileNameOnly" in wire
    assert "yield return entity.Visual.ImpactSpritePath" in assets
    resolver = runtime.split("internal static string ResolveTexturePath")[1].split("private static")[0]
    assert 'role == "impact"' in resolver
    assert "entity.Visual.ImpactSpritePath" in resolver


def test_impact_emissions_have_world_lifetime_not_projectile_lifetime() -> None:
    runtime = _read("Common/VFX/InfiniVfxRuntime.cs")
    detached = _read("Common/VFX/InfiniDetachedVfxSystem.cs")

    assert "SpriteEmissions" not in runtime
    assert "InfiniDetachedVfxSystem.Enqueue" in runtime
    assert "class InfiniDetachedVfxSystem : ModSystem" in detached
    assert "On_Main.DrawProjectiles" in detached
    assert "Main.GameUpdateCount" in detached


def test_event_relay_is_server_authoritative_and_survives_remote_projectile_removal() -> None:
    events = _read("Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs")
    net = _read("Content/Projectiles/GeneratedProjectile.NetSync.cs")

    assert "BroadcastAuthoritativeVfxEvent" in events
    server = net.split("private void BroadcastAuthoritativeVfxEvent")[1].split("private static")[0]
    assert "NetmodeID.Server" in server
    client = net.split("public static void HandleVfxEventSyncPacket")[1]
    assert "GeneratedItemRegistryService" in client
    assert "InfiniVfxRuntime.OnDetachedEvent" in client
    assert "remote?._data" not in client


def test_draw_budget_is_spent_per_actual_draw_call() -> None:
    runtime = _read("Common/VFX/InfiniVfxRuntime.cs")
    trail = runtime.split("private static void DrawTrail(")[1].split("private static void DrawCross")[0]
    cross = runtime.split("private static void DrawCross(")[1].split("private static void DrawLine")[0]

    assert "VfxManifestSpec manifest" in trail
    assert "ref InfiniVfxState state" in trail
    assert "SpendDraw(manifest, ref state, 1)" in trail
    assert "VfxManifestSpec manifest" in cross
    assert cross.count("SpendDraw(manifest, ref state, 1)") >= 2


def test_remote_detached_events_share_per_source_particle_lifetime_budget() -> None:
    runtime = _read("Common/VFX/InfiniVfxRuntime.cs")
    detached = _read("Common/VFX/InfiniDetachedVfxSystem.cs")
    remote = runtime.split("public static bool OnDetachedEvent")[1].split("private static bool Matches")[0]

    assert "detachedParticleBudget: true" in remote
    assert "TrySpendDetachedParticle" in runtime
    assert "ParticleBudgetsBySource" in detached
    assert "MaxRuntimeLifetimeTicks" in detached


def test_mp_asset_transport_carries_the_full_item_overlay_entity_and_impact_roster() -> None:
    sync = _read("Common/Services/GeneratedAssetSyncService.cs")
    registry = _read("Common/Services/GeneratedItemRegistryService.cs")
    limits = _read("Common/InfiniRuntimeLimits.cs")

    assert "MaxRuntimeEntities = 12" in limits
    assert "MaxAssetFiles = 32" in sync
    assert ".Take(16)" not in sync
    assert "count > MaxAssetFiles" in sync
    assert "descriptors.Length, GeneratedAssetSyncService.MaxAssetFiles" in registry
    assert "descriptorCount > GeneratedAssetSyncService.MaxAssetFiles" in registry
    assert "MaxAssetBundleBytes" in sync
    assert "HasCompleteServerAssetRoster" in sync