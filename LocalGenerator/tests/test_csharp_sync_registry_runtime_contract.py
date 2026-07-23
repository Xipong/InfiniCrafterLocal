from __future__ import annotations

from pathlib import Path

from csharp_partial_reader import read_text_with_partial_bundles
ROOT = Path(__file__).resolve().parents[2]
MOD = ROOT / "ModSources" / "InfiniCrafterLocal"
REGISTRY_PATH = MOD / "Common" / "Services" / "GeneratedItemRegistryService.cs"
ASSET_SYNC_PATH = MOD / "Common" / "Services" / "GeneratedAssetSyncService.cs"
GENERATOR_PATH = MOD / "Common" / "Services" / "GeneratorClient.cs"
MODEL_PATH = MOD / "Common" / "Models" / "GeneratedItemData.cs"
COMMAND_PATH = MOD / "Common" / "Commands" / "GetInfiniCommand.cs"
PROJECTILE_PATH = MOD / "Content" / "Projectiles" / "GeneratedProjectile.cs"
ITEM_PATH = MOD / "Content" / "Items" / "GeneratedItem.cs"
WORLD_SYSTEM_PATH = MOD / "Common" / "Systems" / "InfiniCraftWorldExitSystem.cs"
MOD_ENTRY_PATH = MOD / "InfiniCrafterLocal.cs"


def _read(path: Path) -> str:
    return read_text_with_partial_bundles(path)


def _registry_request_handler_block() -> str:
    text = _read(REGISTRY_PATH)
    marker = "if (packetType == PacketRequestGeneratedRegistry || packetType == PacketRequestGeneratedRegistryForceAssets)"
    start = text.index(marker)
    end = text.index("public GeneratedItemData[] Snapshot()", start)
    return text[start:end]


def _check_getinfini_is_read_only_client_catchup_not_world_rebroadcast_or_registry_downgrade() -> None:
    block = _registry_request_handler_block()
    command = _read(COMMAND_PATH)
    assert "PacketRequestGeneratedRegistryForceAssets" in block
    assert "ReadKnownDefinitionHashes(reader)" in block
    assert "ComputeDefinitionHash(data)" in block
    assert "EnqueueDefinitionForClient(data, whoAmI, highPriority: false)" in block
    assert "NotifyNewItemCrafted" not in block
    assert "RegisterLocal(networkData" not in block
    assert "packet.Send(whoAmI)" not in block
    assert "ResetRetryState()" in command
    assert "RequestFullSyncFromServer(forceAssetRetry: true)" in command


def _check_targeted_generated_item_resync_by_id_exists() -> None:
    registry = _read(REGISTRY_PATH)
    assert "PacketRequestGeneratedItemById = InfiniNetPacketIds.RequestGeneratedItemById" in registry
    assert "RequestGeneratedItemById = 10" in _read(ROOT / "ModSources/InfiniCrafterLocal/Common/InfiniNetPacketIds.cs")
    assert "RequestOneFromServer" in registry
    assert "ShouldStartSingleHydrationRequest(id)" in registry
    assert "ShouldStartFullHydrationRequest()" in registry
    assert "_inFlightGeneratedItemHydration.TryGetValue(id" in registry
    assert "MaxHydrationRequestStateEntries" in registry
    assert "PruneHydrationRequestStateLocked(now)" in registry
    assert "_lastGeneratedItemHydrationRequestTick[id] = now" in registry
    assert "_inFlightGeneratedItemHydration.Remove(data.Id)" in registry
    assert "_inFlightGeneratedItemHydration.Clear();" in registry
    assert "_lastGeneratedItemHydrationRequestTick.Clear();" in registry
    assert "TryGet(id, out var cachedData)" in registry
    assert "NeedsRemoteDescriptorRefresh(cachedData, forceAssetRetry)" in registry
    assert "ShouldStartSingleHydrationRequest(id, allowCachedDefinition: true)" in registry
    assert "private bool ShouldStartSingleHydrationRequest(string id, bool allowCachedDefinition = false)" in registry
    assert "EnsureAssetsForData(cachedData, forceRetry: forceAssetRetry)" in registry
    assert "NeedsDescriptorRefreshForAsset" in _read(ASSET_SYNC_PATH)
    assets = _read(ASSET_SYNC_PATH)
    assert "forceDefinitionRefresh = false" in registry
    assert "forceDefinitionRefresh: true" in assets
    assert "x.Value.ItemId, itemId" in assets
    assert "ShouldStartServerAssetRequest" in assets
    asset_request = assets[assets.index("public void HandleAssetRequestPacket"):assets.index("public void HandleAssetChunkPacket")]
    assert asset_request.index("Main.netMode != NetmodeID.Server") < asset_request.index("reader.ReadByte()")
    asset_chunk = assets[assets.index("public void HandleAssetChunkPacket"):assets.index("private bool TryReadVerifiedAssetBundle")]
    assert asset_chunk.index("Main.netMode != NetmodeID.MultiplayerClient") < asset_chunk.index("reader.ReadByte()")
    assert "Dictionary<string, string>? known = ReadKnownDefinitionHashes(reader);" in registry
    request_start = registry.index("public void RequestOneFromServer")
    request_end = registry.index("private static void SendSingleHydrationRequest", request_start)
    cached_request = registry[request_start:request_end]
    assert cached_request.index("SendSingleHydrationRequest(id, forceAssetRetry)") < cached_request.index(
        "EnsureAssetsForData(cachedData, forceRetry: forceAssetRetry)"
    )
    assert "GeneratedHydrationDebugSnapshot" in registry
    assert "CacheHitCount" in registry
    assert "CacheMissCount" in registry
    assert "RetryCount" in registry
    assert "DuplicateSuppressedCount" in registry
    assert "HydrationRequestSentCount" in registry
    assert "packet.Write(PacketRequestGeneratedItemById)" in registry
    assert "TryGet(id, out var data)" in registry
    assert "PrepareForNetworkSync(data, forceHostAssetMetadata: true)" in registry
    assert "GeneratedProjectile.FlushPendingProjectileVisualSyncForGeneratedItem(data.Id);" in registry
    assert "GeneratedProjectile.FlushPendingVfxEventsForGeneratedItem(data.Id);" in registry


def _check_runtime_sprite_cache_can_recover_after_asset_download() -> None:
    sprite_cache = _read(MOD / "Common" / "Services" / "RuntimeSpriteCache.cs")
    asset_sync = _read(ASSET_SYNC_PATH)
    assert "public void Invalidate(string? path)" in sprite_cache
    assert "_missingOrBad.Remove" in sprite_cache
    assert "Main.QueueMainThreadAction(() => InfiniCrafterLocalMod.Sprites?.Invalidate(local));" in asset_sync


def _check_registry_and_asset_sync_are_current_world_scoped() -> None:
    registry = _read(REGISTRY_PATH)
    asset_sync = _read(ASSET_SYNC_PATH)
    generator = _read(GENERATOR_PATH)
    model = _read(MODEL_PATH)
    world_system = _read(WORLD_SYSTEM_PATH)
    assert "public static bool IsCurrentWorldData" in registry
    assert "data.RecipeMeta.WorldScoped" in registry
    assert "data.RecipeMeta.WorldId" in registry
    assert "Main.worldID.ToString()" in registry
    assert "if (!IsCurrentWorldData(data))" in registry
    assert "_byId.Values.Where(IsCurrentWorldData).ToArray()" in registry
    assert "&& IsCurrentWorldData(data)" in registry
    assert "if (!GeneratedItemRegistryService.IsCurrentWorldData(data)) return;" in asset_sync
    assert "InfiniCrafterLocalMod.GeneratedItems.TryGet(itemId, out GeneratedItemData data)" in asset_sync
    assert "BuildServerAssetDescriptors(data)" in asset_sync
    assert "GeneratedItemRegistryService.StampCurrentWorld(data);" in generator
    assert "clone.RecipeMeta.WorldId = SafeText(clone.RecipeMeta.WorldId, 32);" in model
    assert "WorldId = SafeText(source.RecipeMeta?.WorldId" in model
    assert "WorldScoped = source.RecipeMeta?.WorldScoped" in model
    load_start = registry.index("private void LoadLocalCache()")
    load_end = registry.index("private void PersistOne", load_start)
    load_block = registry[load_start:load_end]
    assert "CacheJsonTargetsCurrentWorld" in registry
    assert "JsonDocument.Parse" in registry
    assert 'TryGetProperty("RecipeMeta"' in registry
    assert 'TryGetProperty("WorldId"' in registry
    assert "if (!CacheJsonTargetsCurrentWorld(json))" in load_block
    assert load_block.index("if (!CacheJsonTargetsCurrentWorld(json))") < load_block.index("GeneratedItemData.FromJson(json)")
    assert "public override void OnWorldLoad()" in world_system
    assert "ReloadLocalCacheForCurrentWorld" in world_system
    assert "public override void OnWorldUnload()" in world_system


def _check_projectile_remote_visual_sync_is_explicit_and_tolerates_asset_ordering() -> None:
    projectile = _read(PROJECTILE_PATH)
    item = _read(ITEM_PATH)
    mod = _read(MOD_ENTRY_PATH)
    assert "PacketSyncGeneratedProjectileVisual = InfiniNetPacketIds.SyncGeneratedProjectileVisual" in projectile
    assert "SyncGeneratedProjectileVisual = 8" in _read(ROOT / "ModSources/InfiniCrafterLocal/Common/InfiniNetPacketIds.cs")
    assert "HandleProjectileVisualSyncPacket" in projectile
    assert "PendingProjectileVisualSync" in projectile
    assert "owner+identity" in projectile
    assert "generatedProjectile.BroadcastVisualSync();" in item
    assert "InfiniNetPacketIds.SyncGeneratedProjectileVisual" in mod
    assert "InfiniNetPacketIds.SyncGeneratedProjectileVfxEvent" in mod
    held_layer = _read(MOD / "Common" / "Players" / "GeneratedHeldItemDrawLayer.cs")
    player = _read(MOD / "Common" / "Players" / "InfiniCraftPlayer.cs")
    assert "PacketSyncGeneratedHeldItemPresentation = InfiniNetPacketIds.SyncGeneratedHeldItemPresentation" in held_layer
    assert "HandleHeldItemPresentationSyncPacket" in held_layer
    assert "MaybeBroadcastLocalHeldItem" in player
    assert "InfiniNetPacketIds.SyncGeneratedHeldItemPresentation" in mod
    assert "GeneratedProjectile.ClearPresentationSyncCaches();" in mod
    assert "GeneratedHeldItemDrawLayer.ClearNetCaches();" in mod
    assert "player.itemLocation" in held_layer and "player.itemRotation" in held_layer
    assert "ItemLocationX" in held_layer and "ItemLocationY" in held_layer and "ItemRotation" in held_layer
    assert "payload.PlayerId = Math.Clamp(whoAmI" in held_layer
    assert "sender.HeldItem?.ModItem is GeneratedItem authoritative" in held_layer
    assert "PayloadItemLocation" in held_layer
    assert "ClearNetCaches" in held_layer
    assert "HeldSpriteOrigin" in held_layer and "RoleForwardOffset" in held_layer
    assert "RemoteHeldPresentations" in held_layer
    assert "RequestHeldItemCatchup" in held_layer
    assert "GeneratedItemId" in projectile
    assert "ProjectileSpritePath" in projectile
    assert "WriteProjectileVisualSyncPayload" in projectile
    assert "ReadProjectileVisualSyncPayload" in projectile
    assert "ApplyPendingProjectileVisualSyncIfAny();" in projectile
    assert "ApplyProjectileVisualSyncPayload" in projectile
    assert "TryResolveServerOwnedGeneratedProjectile(whoAmI, payload.Identity" in projectile
    assert "payload.GeneratedItemId = ShortNet(generated._generatedItemId, 96)" in projectile
    assert "payload.Center = generated.Projectile.Center" in projectile
    assert "ClearPresentationSyncCaches" in projectile
    assert "DrawRuntimePlanFallback(px, center, dir, perp, c, len, width);" in projectile
    assert "TryDrawBundledProjectilePlaceholder(center, lightColor)" in projectile
    assert 'ModContent.Request<Texture2D>("InfiniCrafterLocal/Assets/GeneratedItem")' in projectile
    assert "remote peers can receive the projectile/VFX manifest before" in projectile
    assert "RequestProjectileAssetCatchupIfMissing(spritePath, _generatedItemId);" in projectile
    assert "MissingProjectileAssetRequestTicks" in projectile
    assert "MissingGeneratedItemRequestTicks" in projectile
    assert "FlushPendingProjectileVisualSyncForGeneratedItem" in projectile
    assert "MaybeRebroadcastVisualSyncForEarlyRemoteCatchup" in projectile
    assert "PacketSyncGeneratedProjectileVfxEvent = InfiniNetPacketIds.SyncGeneratedProjectileVfxEvent" in projectile
    assert "HandleProjectileVfxEventSyncPacket" in projectile
    assert "PendingProjectileVfxEvents" in projectile
    assert "FlushPendingVfxEventsForGeneratedItem" in projectile
    assert "BroadcastVfxEventSync" in projectile
    assert "gp.BroadcastVisualSync();" in projectile
    assert "RequestOneGeneratedItemForMissingProjectile" in projectile


def _check_projectile_packets_stay_light_but_restore_presentation_from_registry() -> None:
    projectile = _read(PROJECTILE_PATH)
    send_start = projectile.index("public override void SendExtraAI(BinaryWriter writer)")
    receive_start = projectile.index("public override void ReceiveExtraAI(BinaryReader reader)", send_start)
    send = projectile[send_start:receive_start]
    assert "private const int ProjectileSyncVersion = 20" in projectile
    assert "writer.Write(ShortNet(_generatedItemId, 96));" in send
    assert "writer.Write((byte)_runtimeVariant);" in send
    assert "_spec." not in send
    assert "VfxManifestJson = ShortNet" not in projectile
    assert "writer.Write(ShortNet(payload.VfxManifestJson" not in projectile
    assert "payload.VfxManifestJson" not in projectile
    assert "TryHydrateRuntimeVariantFromRegistry" in projectile
    assert "GeneratedChildSpecPolicy.TryCreateRuntimeVariant" in projectile
    assert "HydratePresentationFromRegistryIfPossible" in projectile
    assert "TryGetAttack(_generatedItemId)" in projectile
    assert "CopyMissingPresentationPaths(parent)" in projectile
    assert "GeneratedItems.TryGetVfxManifest(_generatedItemId)" in projectile


def _check_projectile_visual_sync_packet_is_id_only_registry_catchup() -> None:
    projectile = _read(PROJECTILE_PATH)
    assert "private const int ProjectileVisualSyncVersion = 3" in projectile
    assert "GeneratedItemId = ShortNet(_generatedItemId, 96)" in projectile
    assert "RequestOneGeneratedItemForMissingProjectile(payload.GeneratedItemId)" in projectile
    start = projectile.index("private sealed class ProjectileVisualSyncPayload")
    end = projectile.index("private sealed class ProjectileVfxEventSyncPayload", start)
    payload_block = projectile[start:end]
    build_start = projectile.index("private ProjectileVisualSyncPayload BuildVisualSyncPayload")
    build_end = projectile.index("private static string ShortNet", build_start)
    build_block = projectile[build_start:build_end]
    write_start = projectile.index("private static void WriteProjectileVisualSyncPayload")
    read_end = projectile.index("private static void SendProjectileVisualSyncPayload", write_start)
    transport_block = projectile[write_start:read_end]
    for forbidden in [
        "ProjectileSpritePath",
        "ProjectileSpriteStatus",
        "VisualMode",
        "TrailStyle",
        "ImpactStyle",
        "PrimaryColorName",
    ]:
        assert forbidden not in payload_block
        assert forbidden not in build_block
        assert forbidden not in transport_block


def _check_held_item_presentation_sync_packet_is_id_pose_animation_phase_registry_catchup() -> None:
    held = _read(MOD / "Common" / "Players" / "GeneratedHeldItemDrawLayer.cs")
    assert "private const int HeldItemPresentationSyncVersion = 4" in held
    assert "ResolveHeldPresentationData(held, remotePayload)" in held
    assert "registry.TryGet(id, out var canonical)" in held
    assert "RequestHeldItemCatchup(payload.GeneratedItemId, null)" in held
    start = held.index("private sealed class HeldItemPresentationPayload")
    end = held.index("private static readonly Dictionary", start)
    payload_block = held[start:end]
    build_start = held.index("private static HeldItemPresentationPayload BuildLocalPayload")
    build_end = held.index("private static void WriteHeldItemPresentationPayload", build_start)
    build_block = held[build_start:build_end]
    write_start = held.index("private static void WriteHeldItemPresentationPayload")
    read_end = held.index("private static void SendHeldItemPresentationPayload", write_start)
    transport_block = held[write_start:read_end]
    for required in ["GeneratedItemId", "ItemLocationX", "ItemLocationY", "ItemRotation", "Direction", "GravDir", "ActiveUse", "AnimationRemaining"]:
        assert required in payload_block
        assert required in build_block
        assert required in transport_block
    for forbidden in [
        "SpritePath",
        "RuntimeFamily",
        "WeaponFamily",
        "WeaponSubfamily",
        "HandPose",
        "RotationMode",
        "UseStyle",
        "HoldoutOffsetX",
        "HoldoutOffsetY",
        "InitialOffsetPx",
        "ItemScale",
    ]:
        assert forbidden not in payload_block
        assert forbidden not in build_block
        assert forbidden not in transport_block


def _check_generated_item_hooks_drive_registry_hydration_not_projectile_only() -> None:
    item = _read(ITEM_PATH)
    assert "private int _lastRuntimeHydrationTouchTick" in item
    assert "private void EnsureRuntimeHydration(Player? player = null)" in item
    assert "GeneratedItems?.RequestOneFromServer(id, forceAssetRetry: false)" in item
    assert "GeneratedItems?.RegisterLocal(Data, persist: false, ensureAssets: true)" in item
    for hook in [
        "public override bool CanUseItem(Player player)",
        "public override bool? UseItem(Player player)",
        "public override void HoldItem(Player player)",
        "public override void UpdateEquip(Player player)",
        "public override void UpdateAccessory(Player player, bool hideVisual)",
    ]:
        start = item.index(hook)
        end = item.find("\n    public override", start + len(hook))
        if end < 0:
            end = len(item)
        block = item[start:end]
        assert "EnsureRuntimeHydration(player);" in block


def _check_remote_compact_item_reference_resolves_before_ground_inventory_and_held_draw() -> None:
    item = _read(ITEM_PATH)
    held = _read(MOD / "Common" / "Players" / "GeneratedHeldItemDrawLayer.cs")

    net_receive = item[item.index("public override void NetReceive"):item.index("public override bool CanStack")]
    assert "EnsureRuntimeHydration();" in net_receive

    for hook in ["public override bool PreDrawInInventory", "public override bool PreDrawInWorld"]:
        start = item.index(hook)
        end = item.find("\n    public override", start + len(hook))
        if end < 0:
            end = len(item)
        block = item[start:end]
        assert "EnsureRuntimeHydration();" in block
        assert "GeneratedItemData drawData = ResolveRuntimeDataForPresentation();" in block
        assert "drawData.Visual.SpritePath" in block

    assert "private GeneratedItemData ResolveRuntimeDataForPresentation()" in item
    resolver = item[item.index("private GeneratedItemData ResolveRuntimeDataForPresentation()"):
                    item.index("public override void NetSend", item.index("private GeneratedItemData ResolveRuntimeDataForPresentation()"))]
    assert "GeneratedItemData.IsPlayerSaveReferenceOnly(Data)" in resolver
    assert "registry.TryGet(id, out var canonical)" in resolver

    assert "private static GeneratedItemData? ResolveHeldPresentationData" in held
    held_resolver = held[held.index("private static GeneratedItemData? ResolveHeldPresentationData"):
                         held.index("private static bool ShouldDrawHeldSprite")]
    assert "GeneratedItemData.IsPlayerSaveReferenceOnly(gi.Data)" in held_resolver
    held_identity = 'id = (gi.Data.Id ?? "").Trim();'
    assert held_identity in held_resolver
    held_prefix = held_resolver[:held_resolver.index(held_identity) + len(held_identity)]
    assert "if (string.IsNullOrWhiteSpace(id))" not in held_prefix
    assert "registry.TryGet(id, out var canonical)" in held_resolver


def _check_asset_download_hydration_is_deduped_cached_and_counted() -> None:
    asset_sync = _read(ASSET_SYNC_PATH)
    assert "CacheHitCount" in asset_sync
    assert "CacheMissCount" in asset_sync
    assert "RetryCount" in asset_sync
    assert "DuplicateSuppressedCount" in asset_sync
    assert "DownloadStartedCount" in asset_sync


def _check_runtime_asset_transport_is_runtime_only_hashed_atomic_and_paced() -> None:
    asset_sync = _read(ASSET_SYNC_PATH)
    registry = _read(REGISTRY_PATH)
    model = _read(MODEL_PATH)
    packet_ids = _read(ROOT / "ModSources/InfiniCrafterLocal/Common/InfiniNetPacketIds.cs")
    mod_entry = _read(MOD_ENTRY_PATH)

    files_start = asset_sync.index("public static IEnumerable<string> AssetFilesFromData")
    files_end = asset_sync.index("public static string FileNameFromPath", files_start)
    files_block = asset_sync[files_start:files_end]
    assert "AssetManifestPath" not in files_block
    assert "RecipeMeta.AssetFiles" not in files_block
    assert '.EndsWith(".png"' in files_block

    assert "ChunkPayloadBytes = 48 * 1024" in asset_sync
    assert "ChunksPerSecondPerClient = 16" in asset_sync
    assert "HttpDownloadConcurrency = 4" in asset_sync
    assert "SemaphoreSlim" in asset_sync
    assert "SHA256.HashData" in asset_sync
    assert "IsCompletePng" in asset_sync
    assert "ComputePngChunkCrc" in asset_sync
    assert "ZLibStream" in asset_sync
    assert "ValidatePngScanlines" in asset_sync
    assert "LooksLikePng" not in asset_sync
    assert 'local + ".part"' in asset_sync
    assert "File.Move(partPath, local, overwrite: true)" in asset_sync
    assert "MaxOutboundChunksPerClient = 512" in asset_sync
    assert "AssetBundlePayloadVersion" in asset_sync
    assert "EnqueueAssetBundles" in asset_sync
    assert "TryReadVerifiedAssetBundle" in asset_sync
    assert "if (expected is null" in asset_sync
    assert "if (IsValidCachedAsset(local, descriptor))" in asset_sync
    assert "Main.QueueMainThreadAction" in asset_sync
    assert "RequestGeneratedAsset = 16" in packet_ids
    assert "GeneratedAssetChunk = 17" in packet_ids
    assert "InfiniNetPacketIds.RequestGeneratedAsset" in mod_entry
    assert "InfiniNetPacketIds.GeneratedAssetChunk" in mod_entry
    assert "UpdateTransfers()" in asset_sync

    assert "DeflateStream" in registry
    assert "CompressionLevel.Fastest" in registry
    assert "WriteKnownDefinitionHashes" in registry
    assert "ReadKnownDefinitionHashes" in registry
    assert "EnqueueDefinitionForClient" in registry
    assert "ComputeDefinitionHash" in registry
    assert 'clone.Attack.VfxManifestJson = "";' in model
    assert '.Where(file => file.EndsWith(".png", StringComparison.OrdinalIgnoreCase))' in model


def _check_cached_item_and_projectile_use_hot_path_performs_zero_http_downloads() -> None:
    item = _read(ITEM_PATH)
    projectile = _read(PROJECTILE_PATH)
    asset_sync = _read(ASSET_SYNC_PATH)

    shoot = item[item.index("public override bool Shoot("):item.index("private static string AttackRuntimeFamily", item.index("public override bool Shoot("))]
    for forbidden in ["HttpClient", "QueueDownloads", "RequestOneFromServer", "ToNetworkJson", "SpritePath"]:
        assert forbidden not in shoot

    send_extra = projectile[projectile.index("public override void SendExtraAI"):projectile.index("public override void ReceiveExtraAI")]
    for forbidden in ["SpritePath", "AssetBaseUrl", "ToNetworkJson", "VfxManifestJson"]:
        assert forbidden not in send_extra

    queue = asset_sync[asset_sync.index("public void QueueDownloads"):asset_sync.index("private async Task DownloadOneAsync")]
    cache_hit = queue.index("if (IsValidCachedAsset(local, descriptor) && !forceRetry)")
    cache_hit_continue = queue.index("continue;", cache_hit)
    schedule_download = queue.index("_ = DownloadOneAsync", cache_hit)
    assert cache_hit < cache_hit_continue < schedule_download
    assert "_inFlight.ContainsKey(key)" in asset_sync
    assert "MaxInFlightDownloads" in asset_sync
    assert "HttpCompletionOption.ResponseHeadersRead" in asset_sync
    assert "total > MaxAssetBytes" in asset_sync
    assert "_duplicateSuppressedCount++" in asset_sync
    assert "_cacheHitCount++" in asset_sync
    assert "_cacheMissCount++" in asset_sync
    assert "_retryCount++" in asset_sync
    assert "File.Exists(local)" in asset_sync


def _check_projectile_runtime_state_reset_is_single_helper_not_three_near_duplicate_blocks() -> None:
    projectile = _read(PROJECTILE_PATH)
    assert "private void ClearResolvedRuntimeSpec" in projectile
    assert "private void ResetRuntimeSpecState" in projectile
    assert "ClearResolvedRuntimeSpec(Math.Max(_pendingNetworkSpecTicks, 45))" in projectile
    assert "ClearResolvedRuntimeSpec(pendingSpecTicks)" in projectile
    assert "ResetRuntimeSpecState(clearGeneratedId: true, deactivateProjectile: true)" in projectile
    assert "ResetRuntimeSpecState(deactivateProjectile: true)" in projectile
    assert projectile.count("new AttackSpec { Enabled = false, DustSpawnDenom = 0, BurstDustCap = 0, RuntimePlanAuthored = true }") == 1



def _check_csharp_client_does_not_cache_poll_after_structured_fatal_combine_failure() -> None:
    generator = _read(GENERATOR_PATH)
    player = _read(MOD / "Common" / "Players" / "InfiniCraftPlayer.cs")
    assert "LastRecipeFailureIsFatal" in generator
    assert "LastRecipeFailureStatusCode" in generator
    assert "LastRecipeFailureMessage" in generator
    assert "IsFatalRecipeStatusCode" in generator
    assert "return statusCode is 409 or 422 or 424 or 428 or 500" in generator
    assert "Do not turn 422/424" in generator
    assert "ReadErrorMessage(responseJson)" in generator
    assert "generator?.LastRecipeFailureIsFatal == true" in player
    assert "рецепт не прошёл проверку" in player
    assert 'ScheduleEarlyRetry("null_result_recovery")' in player




def _check_local_cache_preserves_python_authoring_extensions_but_network_strips_them() -> None:
    model = _read(MODEL_PATH)
    assert "[JsonExtensionData]" in model
    assert "public Dictionary<string, JsonElement> ExtensionData { get; set; } = new();" in model
    assert "ExtensionData ??= new Dictionary<string, JsonElement>();" in model
    assert "runtimePlan, recipeHealth, contractVersions, runtimeAffordance" in model
    assert "clone.ExtensionData.Clear();" in model
    assert "network/player-save payloads still strip this extension bag" in model


def _check_runtime_affordance_exposes_only_fields_with_runtime_consumers() -> None:
    model = _read(MODEL_PATH)
    for field in ["HeldVisibility", "ReleaseTiming", "HandPose", "InitialOffsetPx"]:
        expected_type = "int" if field == "InitialOffsetPx" else "string"
        assert f"public {expected_type} {field}" in model
    for dead in ["UseFantasy", "SpawnStyle", "RotationMode", "TrailMode", "ProjectileSizePolicy", "DrawDuringUse"]:
        assert f"public string {dead}" not in model
        assert f"public bool {dead}" not in model
    assert "Authored use/draw affordance fields with concrete runtime consumers." in model
    assert "Gameplay.InitialOffsetPx = ClampInt(Gameplay.InitialOffsetPx, -64, 64);" in model
    for field in ["HeldVisibility", "ReleaseTiming", "HandPose"]:
        assert f"Gameplay.{field} = SafeText(Gameplay.{field}, 32);" in model

def _check_local_registry_cache_is_full_not_network_payload() -> None:
    registry = _read(REGISTRY_PATH)
    model = _read(MODEL_PATH)
    persist_start = registry.index("private void PersistOne")
    persist_end = registry.index("private static string SafeFileName", persist_start)
    persist_block = registry[persist_start:persist_end]
    assert "ToLocalCacheJson()" in persist_block
    assert "ToNetworkJson()" not in persist_block
    assert "Local disk cache is not a network packet" in persist_block
    assert "public string ToLocalCacheJson()" in model
    method_start = model.index("public string ToLocalCacheJson()")
    method_end = model.index("public string ToNetworkJson()", method_start)
    method_block = model[method_start:method_end]
    assert "return ToJson();" in method_block
    assert "StripBulkForTransport" not in method_block
    assert "prompts, item knowledge" in method_block

# Coarse test bundle: the checks below used to be separate pytest items.
# Keeping them as helper checks cuts collection/runtime noise while preserving
# the same assertions inside one scenario-level contract per file.
def _run_coarse_contracts(tmp_path):
    import inspect as _inspect
    import pytest as _pytest

    for _name in [
    '_check_getinfini_is_read_only_client_catchup_not_world_rebroadcast_or_registry_downgrade',
    '_check_targeted_generated_item_resync_by_id_exists',
    '_check_runtime_sprite_cache_can_recover_after_asset_download',
    '_check_registry_and_asset_sync_are_current_world_scoped',
    '_check_projectile_remote_visual_sync_is_explicit_and_tolerates_asset_ordering',
    '_check_projectile_packets_stay_light_but_restore_presentation_from_registry',
    '_check_projectile_visual_sync_packet_is_id_only_registry_catchup',
    '_check_held_item_presentation_sync_packet_is_id_pose_animation_phase_registry_catchup',
    '_check_generated_item_hooks_drive_registry_hydration_not_projectile_only',
    '_check_remote_compact_item_reference_resolves_before_ground_inventory_and_held_draw',
    '_check_asset_download_hydration_is_deduped_cached_and_counted',
    '_check_runtime_asset_transport_is_runtime_only_hashed_atomic_and_paced',
    '_check_cached_item_and_projectile_use_hot_path_performs_zero_http_downloads',
    '_check_projectile_runtime_state_reset_is_single_helper_not_three_near_duplicate_blocks',
    '_check_csharp_client_does_not_cache_poll_after_structured_fatal_combine_failure',
    '_check_local_cache_preserves_python_authoring_extensions_but_network_strips_them',
    '_check_runtime_affordance_exposes_only_fields_with_runtime_consumers',
    '_check_local_registry_cache_is_full_not_network_payload'
    ]:
        _fn = globals()[_name]
        _sig = _inspect.signature(_fn)
        _kwargs = {}
        if "tmp_path" in _sig.parameters:
            _case_dir = tmp_path / _name
            _case_dir.mkdir(parents=True, exist_ok=True)
            _kwargs["tmp_path"] = _case_dir
        if "monkeypatch" in _sig.parameters:
            with _pytest.MonkeyPatch.context() as _mp:
                _kwargs["monkeypatch"] = _mp
                _fn(**_kwargs)
        else:
            _fn(**_kwargs)


def test_csharp_sync_registry_runtime_contract_coarse_contract(tmp_path):
    _run_coarse_contracts(tmp_path)
