from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"


def _text(relative: str) -> str:
    return (MOD / relative).read_text(encoding="utf-8")


def _method(source: str, name: str, next_name: str) -> str:
    return source.split(name, 1)[1].split(next_name, 1)[0]


def test_asset_notifications_are_server_authored_and_downloads_are_stream_bounded() -> None:
    source = _text("Common/Services/GeneratedAssetSyncService.cs")
    handle = _method(source, "public void HandlePacket", "public void QueueDownloads")
    server_branch = handle.split("if (Main.netMode == NetmodeID.Server)", 1)[1]

    assert "packet.Send" not in server_branch
    assert "HttpCompletionOption.ResponseHeadersRead" in source
    assert "ContentLength" in source
    assert "MaxAssetBytes" in source
    assert "GetByteArrayAsync" not in source
    assert "total > MaxAssetBytes" in source
    assert "MaxInFlightDownloads" in source
    assert "MaxKnownMissing" in source


def test_registry_bounds_only_hydration_request_state_not_authoritative_definitions() -> None:
    source = _text("Common/Services/GeneratedItemRegistryService.cs")
    assert "MaxHydrationRequestStateEntries" in source
    assert "EnforceBoundedTickDictionary" in source
    assert "_byId.Remove(" not in source
    assert "_cachedDefinitionTouchTick" not in source


def test_projectile_relay_validates_live_sender_owned_projectile_and_canonicalizes_payload() -> None:
    source = _text("Content/Projectiles/GeneratedProjectile.NetSync.cs")
    visual = _method(source, "public static void HandleProjectileVisualSyncPacket", "private const int ProjectileVfxEventSyncVersion")
    vfx = _method(source, "public static void HandleProjectileVfxEventSyncPacket", "public static void ClearPresentationSyncCaches")

    assert "TryResolveServerOwnedGeneratedProjectile" in source
    assert "TryResolveServerOwnedGeneratedProjectile(whoAmI, payload.Identity" in visual
    assert "TryResolveServerOwnedGeneratedProjectile(whoAmI, payload.Identity" in vfx
    assert "generated._generatedItemId" in visual
    assert "generated._generatedItemId" in vfx
    assert "generated.Projectile.Center" in vfx
    assert "generated.Projectile.velocity" in vfx
    assert "TryAcceptProjectileRelay" in visual
    assert "TryAcceptProjectileRelay" in vfx


def test_projectile_pending_and_request_maps_are_expiring_and_bounded() -> None:
    source = _text("Content/Projectiles/GeneratedProjectile.NetSync.cs")
    partial_class_source = source + _text("Content/Projectiles/GeneratedProjectile.cs")
    assert "PendingProjectileVisualSyncMaxEntries" in source
    assert "PrunePendingProjectileVisualSyncLocked" in source
    assert "PendingVisualSyncExpiryTicks" in source
    assert "PendingProjectileVfxEventMaxEntries" in source
    assert "PendingProjectileVfxEvents.Count >= PendingProjectileVfxEventMaxEntries" in source
    assert "PruneTickMapLocked(MissingGeneratedItemRequestTicks" in partial_class_source
    assert "PruneTickMapLocked(MissingProjectileAssetRequestTicks" in partial_class_source


def test_server_craft_dedupe_and_cancel_caches_are_bounded() -> None:
    player = _text("Common/Players/InfiniCraftPlayer.cs")
    multiplayer = _text("Common/Players/InfiniCraftPlayer.Multiplayer.cs")

    assert "MaxServerCraftRequestCacheEntries" in player
    assert "ServerCommittedCraftRequestOrder" in player
    assert "ServerCancelledCraftRequestOrder" in player
    assert "RememberServerCraftCommit" in multiplayer
    assert "MarkServerCraftCancelled" in multiplayer
    assert re.search(r"while \(ServerCommittedCraftRequestOrder\.Count > MaxServerCraftRequestCacheEntries\)", multiplayer)
    assert re.search(r"while \(ServerCancelledCraftRequestOrder\.Count > MaxServerCraftRequestCacheEntries\)", multiplayer)
