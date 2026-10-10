#!/usr/bin/env python3
"""Portable static gate for the v5 low-level generated runtime.

This is deliberately smaller than the historical weapon-family scanner. It
checks syntax-shaped invariants, the exact v5 DTO/executor seam, packet ids and
absence of deleted macro/family entry points. A real tModLoader build remains a
separate required gate when the SDK and game references are available.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "ModSources" / "InfiniCrafterLocal"
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def read(relative: str) -> str:
    path = SRC / relative
    if not path.is_file():
        fail(f"missing C# source: {relative}")
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def stripped(text: str, keep_strings: bool = False) -> str:
    # A single lexical pass prevents // inside a URL/string from hiding code.
    # Spaces preserve offsets for structural observers and line diagnostics.
    pattern = r'//[^\n]*|/\*.*?\*/|@"(?:[^"]|"")*"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    def mask(match: re.Match[str]) -> str:
        value = match.group()
        if keep_strings and not value.startswith(("//", "/*")):
            return value
        return re.sub(r"[^\n]", " ", value)
    return re.sub(pattern, mask, text, flags=re.S)


def source_policy_issues(sources: dict[str, str]) -> list[str]:
    """Genuine source-language policies, not snapshots of unrelated implementation.

    Named Terraria sentinels, no authored tooltip renderer and no suppressed
    diagnostics are centralized here; comments/string decoys cannot satisfy them.
    """
    issues: list[str] = []
    for path, text in sources.items():
        code = stripped(text)
        if re.search(r"#\s*(?:pragma\s+warning\s+disable|nullable\s+disable\s+warnings)\b", code):
            issues.append(f"warning_suppression:{path}")
        if path.startswith("Common/Models/GeneratedItemData") or path == "Content/Items/GeneratedItem.cs":
            if re.search(r"\b(?:Tooltip|TooltipLine|ModifyTooltips|SetBonusText)\b|\bplayer\s*\.\s*setBonus\b", code):
                issues.append(f"authored_tooltip:{path}")
        patterns = []
        if path.startswith("Localization/") and path.endswith(".hjson"):
            for name in ("GeneratedItem", "GeneratedHeadArmor", "GeneratedBodyArmor", "GeneratedLegsArmor"):
                blocks = re.findall(r"\b" + name + r":\s*\{([^}]*)\}", stripped(text, keep_strings=True))
                if not blocks or any(re.search(r"\bTooltip\s*:", block) for block in blocks):
                    issues.append(f"proxy_tooltip:{path}:{name}")
        if path == "Common/Models/GeneratedItemData.Apply.cs":
            patterns = [r"\b(?:item|Item)\s*\.\s*useStyle\s*=\s*0\s*;"]
        elif path == "Common/Services/GeneratorClient.cs":
            patterns = [r"\.\s*shoot\s*(?:>|<=)\s*0\b", r"\bprojectileType\s*(?:<=|>=)\s*0\b",
                        r"\.\s*create(?:Tile|Wall)\s*>=\s*0\b", r"\.\s*rare\s*>=\s*3\b",
                        r'\b3\s*=>\s*"(?:Orange|#FFC896)"']
        elif path in {"Common/Commands/InfiniDumpCommand.cs", "Common/Commands/InfiniDumpPictureCommand.cs"}:
            patterns = [r"\.\s*shoot\s*>\s*0\b", r"\bprojectileType\s*>?=\s*0\b"]
        if any(re.search(pattern, stripped(text, keep_strings=True)) for pattern in patterns):
            issues.append(f"numeric_sentinel:{path}")
    named_ids = {
        "Common/Models/GeneratedItemData.Apply.cs": ("ItemUseStyleID.None",),
        "Common/Services/GeneratorClient.cs": ("ProjectileID.None", "ItemID.None", "AmmoID.None", "TileID.Dirt", "WallID.None", "ItemRarityID.Orange"),
    }
    for path, identifiers in named_ids.items():
        code = stripped(sources.get(path, ""))
        for identifier in identifiers:
            if re.search(r"\b" + re.escape(identifier).replace(r"\.", r"\s*\.\s*") + r"\b", code) is None:
                issues.append(f"named_sentinel:{path}:{identifier}")
    dumps = "\n".join(stripped(sources.get(path, "")) for path in ("Common/Commands/InfiniDumpCommand.cs", "Common/Commands/InfiniDumpPictureCommand.cs"))
    if re.search(r"\bProjectileID\s*\.\s*None\b", dumps) is None:
        issues.append("named_sentinel:dump:ProjectileID.None")
    return issues


def check_source_policies() -> None:
    sources = {path.relative_to(SRC).as_posix(): path.read_text(encoding="utf-8")
               for pattern in ("*.cs", "*.hjson") for path in sorted(SRC.rglob(pattern))}
    ERRORS.extend(source_policy_issues(sources))
    project = read("InfiniCrafterLocal.csproj")
    if re.search(r"<NoWarn(?:\s|>)", project):
        fail("warning_suppression:InfiniCrafterLocal.csproj:NoWarn")


def require(text: str, needle: str, owner: str) -> None:
    if needle not in text:
        fail(f"{owner}: missing `{needle}`")


def forbid(text: str, needle: str, owner: str) -> None:
    if needle in text:
        fail(f"{owner}: forbidden legacy token `{needle}`")


def braced_body(text: str, opening: int) -> str:
    mask = stripped(text)
    depth = 1
    for end in range(opening + 1, len(mask)):
        depth += (mask[end] == "{") - (mask[end] == "}")
        if depth == 0:
            return text[opening + 1:end]
    fail("unbalanced C# scope")
    return ""


def method_body(text: str, name: str, overload: int = 0) -> str:
    """Select a declaration and balanced body, not a call/comment or next-method split."""
    mask = stripped(text)
    matches = list(re.finditer(r"(?m)^[ \t]*(?:public|private|internal|protected)\s+[^;{=]*?\b"
                              + re.escape(name) + r"\s*\([^;{}]*\)\s*(\{|=>)", mask))
    if not matches:
        fail(f"missing C# method declaration: {name}")
        return ""
    match = matches[overload]
    if match.group(1) == "=>":
        return text[match.end():mask.index(";", match.end())]
    return braced_body(text, match.end() - 1)


def check_sampled_spawn_boundaries() -> None:
    """Bind sampled/target-relative launch state to its real admission consumers.

    These are source obligations; the actual seeded distribution, native spawn,
    delay and ExtraAI scenarios belong to EngineRuntimeChecks.
    """
    projectile = read("Content/Projectiles/GeneratedProjectile.cs")
    ai = read("Content/Projectiles/GeneratedProjectile.Executors.cs")
    net = read("Content/Projectiles/GeneratedProjectile.NetSync.cs")
    runtime = read("Common/Runtime/RuntimeProgramExecutor.cs")
    scheduler = read("Common/Runtime/RuntimeDelayedActionScheduler.cs")
    dto = read("Common/Models/RuntimeProgramSpec.cs")
    planner = read("Common/Runtime/RuntimeHitTargetSpawn.cs")
    obligations = (
        (projectile, "SpawnRuntimeEntity", (
            "entity.Spawn.AcceptsEmissionSpread(spreadOverride ?? entity.Spawn.SpreadRadians)",
            "new UnifiedRandom(initialVelocitySeed ?? Main.rand.Next())",
            "RuntimeSpawnVelocity.TrySample(entity.Spawn, direction, velocityRandom, out velocity)",
        )),
        (projectile, "Configure", (
            "_sampledInitialVelocity = entity.Spawn.VelocityDistribution is null ? null : Projectile.velocity",
            "else if ((entity.Spawn.VelocityDistribution is null) != (_sampledInitialVelocity is null))",
        )),
        (ai, "AI", ("_age == 0", "Projectile.velocity = _sampledInitialVelocity ??",)),
        (net, "ReceiveExtraAI", ("receivedVelocityPresence > 1", "!float.IsFinite(sampled.X)", "!float.IsFinite(sampled.Y)",)),
        (net, "SendExtraAI", ("writer.Write(_sampledInitialVelocity.HasValue)", "writer.Write(sampled.X)", "writer.Write(sampled.Y)",)),
        (scheduler, "TrySchedule", ("RuntimeHitTargetSpawnSnapshot.TryCapture(geometry, target, direction, out var captured)", "hitTargetSpawn = launch with { Seed = Main.rand.Next() }",)),
        (runtime, "SpawnHitTargetChildren", (
            "RuntimeEventActionSpec.SupportsTargetEmission(child)", "unattempted--",
            "initialNpcExclusion: snapshot.Exclusion", "initialTransform: transforms[i]",
            "initialVelocitySeed: velocitySeeds[i]", "budget.Return(1 - spawned)", "budget.Return(unattempted)",
        )),
        (planner, "TryPlan", ("!snapshot.Exclusion.CanApply", "new UnifiedRandom(snapshot.Seed)",)),
        (dto, "HasExactTargetEmissionOrigin", ("_offsetPresent && _aimPresent && _placementPresent", "OverTarget is not null",)),
    )
    for source, name, tokens in obligations:
        code = re.sub(r"\s+", "", stripped(method_body(source, name)))
        for token in tokens:
            require(code, re.sub(r"\s+", "", token), name)
    normalize = stripped(method_body(dto, "NormalizeAndValidate"))
    consumer = normalize.find("entity.NormalizeAndValidate(Limits)")
    for guard in ("RuntimeEventActionSpec.SupportsTargetEmission(child)", "spawn.AcceptsEmissionSpread(action.SpreadRadians)"):
        if normalize.find(guard) < 0 or consumer < normalize.find(guard):
            fail(f"sampled_spawn_raw_reference: {guard} must precede entity normalization")


def check_network_boundaries() -> None:
    # Method-scoped obligations: preserve authority, exact identities and fail
    # closed transport. Runtime behavior remains the EngineRuntimeChecks owner.
    asset = read("Common/Services/GeneratedAssetSyncService.cs")
    registry = read("Common/Services/GeneratedItemRegistryService.cs")
    net = read("Content/Projectiles/GeneratedProjectile.NetSync.cs")
    projectile = read("Content/Projectiles/GeneratedProjectile.cs")
    runtime = read("Common/Runtime/RuntimeProgramExecutor.cs")
    initial_exclusion = read("Common/Runtime/RuntimeInitialNpcExclusion.cs")
    projectile_ai = read("Content/Projectiles/GeneratedProjectile.Executors.cs")
    projectile_events = read("Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs")
    multiplayer = read("Common/Players/InfiniCraftPlayer.Multiplayer.cs")
    obligations = [
        (asset, "HandleAssetRequestPacket", ("Main.netMode != NetmodeID.Server", "GeneratedItems.TryGet(itemId, out GeneratedItemData data)", "BuildServerAssetDescriptors(data)"), ("packet.Send",)),
        (asset, "HandleAssetChunkPacket", ("ComputeSha256Hex(complete)", "CommitVerifiedAsset"), ()),
        (asset, "ComputeSha256Hex", ("SHA256.HashData",), ()),
        (asset, "DownloadAssetBytesWithBoundedStreamAsync", ("HttpCompletionOption.ResponseHeadersRead", "ContentLength", "total > MaxAssetBytes"), ("GetByteArrayAsync",)),
        (net, "SendExtraAI", ("writer.Write(_generatedItemId", "writer.Write(_entityId"), ()),
        (net, "ReceiveExtraAI", ("runtimeVersion is not (2 or 3) && runtimeVersion != RuntimeNetVersion", "_generatedItemId.Length > 96", "_entityId.Length > 48", "Projectile.friendly = false", "Projectile.velocity = Vector2.Zero", "TryHydrate()", "_preserveSyncedStateOnHydrate = true"), ()),
        (projectile, "Configure", ("preserveSyncedState", "Projectile.timeLeft = Math.Max(1, syncedTimeLeft)", "_remainingBounces = Math.Clamp(syncedBounces", "_activationDelayTicks = Math.Max(0, syncedActivationDelay)"), ()),
        (initial_exclusion, "TryCapture", ("RuntimeHitNpcGeneration.Get(npc)", "if (generation == 0) return false", "ReferenceEquals(Main.npc[npc.whoAmI], npc)"), ()),
        (initial_exclusion, "AppliesTo", ("RuntimeHitNpcGeneration.Get(npc) == Generation", "ReferenceEquals(Main.npc[NpcSlot], npc)"), ()),
        (projectile_ai, "AI", ("_initialNpcExclusion = _initialNpcExclusion.AfterUpdate()",), ()),
        (projectile_events, "CanHitNPC", ("_initialNpcExclusion.AppliesTo(target)",), ()),
        (net, "SendExtraAI", ("_initialNpcExclusion.Write(writer)",), ()),
        (net, "ReceiveExtraAI", ("RuntimeInitialNpcExclusion.Read(reader)", "if (!retainOwnerExclusion)", "_runtimePayloadRejected = true"), ()),
        (projectile, "TryHydrate", ("if (_runtimePayloadRejected) return false",), ()),
        (projectile, "SpawnRuntimeEntity", ("if (!projectile.active || projectile.ModProjectile is not GeneratedProjectile generated)", "projectile.active = false", "if (childDepth > 0) activationBudget.Return(remainingSpawnBudget - spawned)", "throw;"), ()),
        (runtime, "HealOwner", ("owner.Heal(heal)",), ("ShouldRunPlayerGameplay(owner)",)),
        (runtime, "DamageArea", ("AuthoredEventDamage(data, sourceEntity)", "owner.ApplyDamageToNPC"), ()),
        (runtime, "ChainDamage", ("AuthoredEventDamage(data, sourceEntity)", "owner.ApplyDamageToNPC"), ()),
        (runtime, "ShouldRunNpcEvent", ("RuntimeEventKind.OnHit or RuntimeEventKind.OnCrit", "ShouldRunLocalPlayerAction(owner)", "ShouldRunNpcGameplay()"), ()),
        (net, "HandleVfxEventSyncPacket", ("Main.netMode != NetmodeID.MultiplayerClient", "GeneratedItemRegistryService", "HasExactVfxSlot(data, entity.Id, payload.EventName)", "InfiniVfxRuntime.OnDetachedEvent"), ("remote?._data",)),
        (net, "BroadcastAuthoritativeVfxEvent", ("Main.netMode != NetmodeID.Server", "packet.Send(-1, Projectile.owner)"), ()),
        (multiplayer, "HandleRequestServerCraftPacket", ("int firstInputIndex = laneIndex * 2", "TrySnapshotServerEscrowInput(firstInputIndex, aRef", "TrySnapshotServerEscrowInput(firstInputIndex + 1, bRef", "GeneratedStationEscrowStateSystem.TryBeginCraft", "LogServerCraftTransaction"), ()),
        (multiplayer, "SendServerAuthoritativeResultIfNeeded", ("CompleteServerCraftTransaction(_serverRequestId, 0, success" ,), ()),
        (multiplayer, "CompleteServerCraftTransaction", ("LogServerCraftTransaction", "if (success) ClearServerStationEscrowLane(laneIndex)"), ()),
    ]
    for source, name, required, forbidden in obligations:
        code = re.sub(r"\s+", "", stripped(method_body(source, name)))
        for token in required:
            if re.sub(r"\s+", "", token) not in code:
                fail(f"{name}: missing code obligation `{token}`")
        for token in forbidden:
            if re.sub(r"\s+", "", token) in code:
                fail(f"{name}: forbidden code obligation `{token}`")
    # Native candidate coverage validates the shared decision; the source gate
    # must bind both real callers to it, not demand obsolete inline duplicates.
    scheduler = read("Common/Runtime/RuntimeDelayedActionScheduler.cs")
    for source, name, overload, tokens in (
        (runtime, "HasActionAuthority", 0, (
            "RuntimeEventActionCode.SpawnEntity or RuntimeEventActionCode.HealOwner or RuntimeEventActionCode.MoveOwner => InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner)",
            "RuntimeEventActionCode.ApplyStatus or RuntimeEventActionCode.DamageArea or RuntimeEventActionCode.ChainDamage => ShouldRunNpcEvent(action, owner)",
            "_ => false",
        )),
        (runtime, "ExecuteAction", -1, ("if (!HasActionAuthority(action, owner))", "budget.Return(reservedSpawnBudget)")),
        (scheduler, "TrySchedule", 0, ("if (!RuntimeProgramExecutor.HasActionAuthority(action, owner)) return false;",)),
    ):
        code = re.sub(r"\s+", "", stripped(method_body(source, name, overload=overload)))
        for token in tokens:
            require(code, re.sub(r"\s+", "", token), name)
    pull_authority = re.sub(r"\s+", "", stripped(method_body(runtime, "HasActionAuthority"), keep_strings=True))
    require(pull_authority, 'action.Mode=="owner_to_target"?InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(owner):InfiniRuntimeAuthority.ShouldRunNpcGameplay()', "HasActionAuthority:Pull")
    # Bounded request state cannot evict authoritative definitions.
    for token in ("MaxInFlightDownloads", "MaxKnownMissing", "SemaphoreSlim"):
        require(stripped(asset), token, "asset request bounds")
    forbid(stripped(asset), "GetByteArrayAsync", "bounded asset streaming")
    for token in ("MaxHydrationRequestStateEntries", "EnforceBoundedTickDictionary"):
        require(stripped(registry), token, "hydration request bounds")
    for token in ("_byId.Remove(", "_cachedDefinitionTouchTick"):
        forbid(stripped(registry), token, "authoritative registry retention")
    require(stripped(net), "SourceToken", "VFX generation identity")
    # Every rejecting branch consumes its own payload before return/send. A
    # discard in the next branch or a comment cannot make an earlier reject safe.
    utility = stripped(method_body(multiplayer, "HandleGeneratedUtilityBuffSyncPacket"))
    branches = re.findall(r"if\s*\(([^{};]+)\)\s*\{([^{}]*)\}", utility)
    for guard, terminal in (("playerId >= Main.maxPlayers", "return;"),
                            ("Main.netMode == NetmodeID.Server && playerId != whoAmI", "return;"),
                            ("player is null || !player.active", "return;"),
                            ("Main.netMode == NetmodeID.Server", "SendGeneratedBuffState(-1, whoAmI)")):
        candidates = [body for condition, body in branches if re.sub(r"\s+", "", condition) == re.sub(r"\s+", "", guard)]
        if not candidates or any(body.find("DiscardGeneratedBuffState(reader);") < 0
                                 or body.find("DiscardGeneratedBuffState(reader);") > body.find(terminal) for body in candidates):
            fail(f"utility_payload_consumed: {guard} must discard before {terminal}")
    # Operator diagnostics have intentional source-language identities.
    diagnostics = [("LogServerCraftTransaction", ("[InfiniCraftTx]",)),
                   ("HandleRequestServerCraftPacket", ('"received"', '"reserve_rejected"', '"reserved"', "aInput={firstInputIndex}", "bInput={firstInputIndex + 1}")),
                   ("CompleteServerCraftTransaction", ('success ? "committed" : "failed"',))]
    for name, tokens in diagnostics:
        body = stripped(method_body(multiplayer, name), keep_strings=True)
        for token in tokens:
            require(body, token, name)


def check_client_source_contracts() -> None:
    cache = read("Common/Services/RuntimeSpriteCache.cs")
    config = read("Common/Config/InfiniGameplayQolConfig.cs")
    constants = {name: int(value) for name, value in re.findall(r"const int\s+(\w+)\s*=\s*(\d+)", stripped(cache))}
    fields = re.findall(r"\[DefaultValue\((\d+)\)\]\s*\[Range\((\d+),\s*(\d+)\)\]\s*\[Slider\]\s*public int\s+(\w+)\s*=\s*(\d+)", stripped(config))
    bounds = {name: (int(default), int(low), int(high), int(value)) for default, low, high, name, value in fields}
    for field, suffix in (("RuntimeSpriteCacheMaxTextures", "CachedTextures"),
                          ("RuntimeSpriteMaxDimensionPixels", "TextureDimensionPixels"),
                          ("RuntimeSpriteMaxPngFileMegabytes", "TextureFileMegabytes")):
        default, low, high, value = bounds.get(field, (-1, -1, -1, -1))
        if (default != value or default != constants.get("DefaultMax" + suffix)
                or high != constants.get("Max" + suffix + "HardLimit") or not 0 < low <= default <= high):
            fail(f"runtime cache config parity:{field}: declarative UI and effective runtime bounds differ")
    require(config, "ConfigScope.ClientSide", "client QoL config")
    for token in ("RuntimeSpriteLimits", "IsRuntimePngFileSizeAllowed", "tex.Width > limits.MaxTextureDimensionPixels", "tex.Height > limits.MaxTextureDimensionPixels"):
        require(stripped(cache), token, "runtime cache admission")
    require(stripped(method_body(cache, "TrimMissingOrBadCacheIfNeeded")), "_missingOrBad.Count > MaxMissingOrBadRecords", "bounded bad asset cache")
    if constants.get("MaxMissingOrBadRecords", 0) <= 0:
        fail("bounded bad asset cache: positive retention cap required")
    ui = read("Common/UI/InfiniCraftStationUISystem.cs")
    player = read("Common/Players/InfiniCraftPlayer.cs")
    for token in ("clearButton", "TryClearAllInputsToInventory", "TryClearInputToInventory", "Main.mouseRight"):
        require(stripped(ui + player), token, "manual station clear")
    for token in ("fillButton", "swapButton", "TryAutoFillStationInputs", "TrySwapStationInputs", "TryFillStationInputFromInventory", "QuickFillSkipsHotbar", "StationQuickFillEnabled", "EnableStationQuickFill"):
        forbid(stripped(ui + player + config), token, "forbidden automatic station actions")
    prefetch = stripped(method_body(player, "TickGeneratedInventoryAssetPrefetch"))
    for token in ("!config.EnableInventoryAssetPrefetch", "InventoryAssetPrefetchIntervalTicks", "InventoryAssetPrefetchMaxItems", "if (ensured >= maxItems)", "GeneratedPrefetchCandidateItems", "GeneratedDataFromItem", "RegisterLocal(data, persist: true, ensureAssets: true)"):
        require(prefetch, token, "inventory prefetch")
    labels = {
        "en-US": ("Runtime sprite cache size", "Runtime sprite max side", "Runtime PNG file limit"),
        "ru-RU": ("Размер кэша спрайтов", "Максимальная сторона спрайта", "Лимит PNG-файла"),
    }
    for locale, text_labels in labels.items():
        text = read(f"Localization/{locale}_Mods.InfiniCrafterLocal.hjson")
        for token in ("InfiniGameplayQolConfig", *bounds.keys() & {"RuntimeSpriteCacheMaxTextures", "RuntimeSpriteMaxDimensionPixels", "RuntimeSpriteMaxPngFileMegabytes"}, *text_labels):
            require(text, token, "localized runtime cache controls")


def check_world_transactions() -> None:
    # Source owners for transactions not covered by the headless engine runner.
    # Method/branch scoping prevents adjacent methods or comment decoys from
    # satisfying guards. Persistence round trips remain EngineRuntimeChecks.World.
    item = read("Content/Items/GeneratedItem.cs")
    ledger = read("Common/Systems/GeneratedPlacementLedgerSystem.cs")
    state = read("Common/Players/InfiniCraftPlayer.CraftState.cs")
    journal = read("Common/Systems/GeneratedStationEscrowStateSystem.cs")
    mp = read("Common/Players/InfiniCraftPlayer.Multiplayer.cs")
    multi = read("Common/Players/InfiniCraftPlayer.MultiDev.cs")
    obligations = [
        (item, "ConsumeItem", ("RuntimeBindingAction.PlaceItem", "StackCost == 1 && ConsumeAcceptedPlacementReceipt(player)"), ()),
        (item, "UseItem", ("Action.Kind != RuntimeBindingAction.PlaceItem", "RuntimeEventKind.OnUse"), ()),
        (item, "ApplyActiveUseProjection", ("Item.mana = Math.Max(0, Data.Gameplay.ManaCost)", "bool applyingItemEffects = action.Kind == RuntimeBindingAction.ApplyItemEffects", "Data.ApplyUseEffectFields(Item, applyingItemEffects)"), ()),
        (item, "BindingUsesItemBodyContact", ("UsePolicy.ContactDamage",), ("RuntimeBindingAction", "TargetId")),
        (ledger, "AuthorizePlacement", ("PendingAuthorizations.Count", "MaxCellsPerGroup", "MaxGroups", "data.ToNetworkJson()"), ()),
        (ledger, "TryCommitAuthorizedPlacement", ("MaxCells - committedCells.Count", "Groups.Count >= MaxGroups"), ()),
        (ledger, "TryQueueReturn", ("Placements.Remove", "PendingReturns.Add", "PendingReturns.Remove", "PendingSpawnOutcome.Spawned"), ()),
        (ledger, "TrySpawnPendingReturnCore", ("GeneratedItemData.FromJson(pending.DefinitionJson)", "IsMaterialPlacementDefinition(data)", "string.Equals(data.Id, pending.GeneratedItemId, StringComparison.Ordinal)", "PendingSpawnOutcome.TransientFailure"), ("ItemID.", "registry.TryGet")),
        (ledger, "PostUpdateWorld", ("PendingReturns", "TrySpawnPendingReturn", "QuarantinedReturns.Add", "Claim = ReturnClaim(pending)"), ()),
        (ledger, "SaveWorldData", ("QuarantineSaveKey", "QuarantinedReturns.Select(QuarantineEnvelope)", "RawQuarantineEnvelopeSaveKey", "RawQuarantineEnvelopes.Select"), ()),
        (ledger, "QuarantineEnvelope", ("record.RawEnvelope.Clone()", "record.Claim.Clone()", "record.Cause", "record.Requeued"), ()),
        (ledger, "TryRequeueQuarantinedReturn", ("GeneratedItemRegistryService.IsCurrentWorldData(data)", "IsMaterialPlacementDefinition(data)", "record.Requeued", "record.RequeueDefinitionJson", "PendingReturns.Add"), ()),
        (ledger, "SendPlacementToServer", ("InfiniNetPacketIds.NotifyGeneratedPlacement",), ("generatedItemId",)),
        (ledger, "HandlePlacementPacket", ("Main.netMode != NetmodeID.Server", "TryCommitAuthorizedPlacement"), ("ReadString",)),
        (ledger, "CanDrop", ("TryQueueReturn(GeneratedPlacementLayer.Tile, i, j)", "return false"), ()),
        (journal, "SaveWorldData", ("CraftTransactionsSaveKey", "OwnersSaveKey", "OutcomesSaveKey"), ()),
        (journal, "LoadWorldData", ("GetList<TagCompound>(CraftTransactionsSaveKey).Take(MaxCraftTransactions)",), ()),
        (journal, "RememberOutcome", ("Outcomes.Count >= MaxOutcomes",), ("Remove(",)),
        (state, "SaveData", ("infiniStationEscrowClientId", "infiniStationEscrowMirror", "infiniPendingStationEscrow", "ItemIO.Save(_pendingStationEscrowItem)", "infiniPendingRemoteCrafts", "SavePendingRemoteCrafts"), ()),
        (state, "LoadData", ("_readOnlyRemoteStationClaim", "tag.Clone()", "if (remoteClaim) return;"), ("RestorePendingRemoteCrafts(",)),
        (state, "EnsureRemoteStationAuthority", ("IsExactAuthorityScope(current)", "StringComparison.Ordinal", "RestoreScopedRemoteStationClaim(retained)"), ()),
        (state, "RestoreScopedRemoteStationClaim", ("RestorePendingRemoteCrafts", "_stationEscrowUsesRemoteAuthority = true"), ()),
        (state, "OnEnterWorld", ("ResendPendingRemoteCrafts",), ("ClearPendingStationEscrowOperation",)),
        (mp, "FlushPendingStationEscrowRequest", ("packet.Write(_stationEscrowClientId)", "packet.Write(_pendingStationEscrowOperationId)"), ()),
        (mp, "HandleStationEscrowRequestPacket", ("string clientId = reader.ReadString()", "GeneratedStationEscrowStateSystem.RestoreOwnerState", "GeneratedStationEscrowStateSystem.TryReplay"), ()),
        (mp, "FinishStationEscrowRequest", ("GeneratedStationEscrowStateSystem.RememberOutcome",), ()),
        (mp, "TryReturnServerEscrowToInventory", (), ("RefundOne(",)),
        (mp, "TryReturnAllServerEscrowToInventory", (), ("RefundOne(",)),
        (multi, "AbortMultiDevCraftsForWorldExit", ("refundLocally && Main.netMode == NetmodeID.MultiplayerClient && job.AwaitingServerCommit",), ()),
    ]
    for source, name, required, forbidden in obligations:
        body = method_body(source, name, overload=-1)
        for token in required:
            # Save keys are actual string-literal contracts; code obligations
            # must never be satisfied by a string quoting a deleted guard.
            code = stripped(body, keep_strings=token.startswith("infini"))
            if re.sub(r"\s+", "", token) not in re.sub(r"\s+", "", code):
                fail(f"{name}: missing transaction obligation `{token}`")
        for token in forbidden:
            forbid(stripped(body), token, name)
    for name in ("BaseNoMeleeFor", "UseItemHitbox", "OnHitNPC"):
        body = stripped(method_body(item, name))
        require(body, "BindingUsesItemBodyContact", name)
        forbid(body, "PrimaryOwner", name)
    apply_fields = stripped(read("Common/Models/GeneratedItemData.Apply.cs"))
    ammo_projection = stripped(method_body(read("Common/Models/GeneratedItemData.Apply.cs"), "ApplyWeaponAmmoField"))
    require(ammo_projection, "activeSpawn && RuntimeProgram.WeaponAmmo", "explicit weapon ammo use lane")
    require(ammo_projection, "TerrariaRuntimeVocabulary.ResolveAmmoCategory(ammo.AmmoCategory) : AmmoID.None", "exact weapon ammo category and inactive clearing")
    require(stripped(method_body(item, "ApplyActiveUseProjection")), "Data.ApplyWeaponAmmoField(Item, spawning)", "selected active weapon ammo projection")
    ammo_shoot = stripped(method_body(item, "Shoot"), keep_strings=True)
    require(ammo_shoot, 'rootSpeedOverride: Data.RuntimeProgram.WeaponAmmo?.SpeedBasis == "native_shot" ? velocity.Length() : null', "ammo shot speed policy")
    require(ammo_shoot, "rootDamageOverride: damage, rootKnockbackOverride: knockback", "native ammo combat arguments without second scaling")
    for field in ("healLife", "healMana", "buffType", "buffTime"):
        authored = {"buffType": "BuffCode"}.get(field, field[0].upper() + field[1:])
        require(apply_fields, f"item.{field} = enabled ? Math.Max(0, Gameplay.{authored}) : 0;", "binding-scoped use effects")
    for body in (apply_fields, stripped(method_body(item, "ApplyActiveUseProjection"))):
        if not re.search(r"\b(?:item|Item)\.consumable\s*=\s*[^;]*\|\|\s*(?:Data\.)?Gameplay\.AmmoCategory\.Length\s*>\s*0\s*;", body):
            fail("ammo remains vanilla consumable: ammo cost is independent of direct use")
    require(stripped(ledger), "class GeneratedPlacementLedgerWall : GlobalWall", "wall ledger owner")
    require(stripped(journal), "class GeneratedStationEscrowStateSystem : ModSystem", "world station journal owner")
    for name in ("NetSend", "NetReceive", "Drop"):
        method_body(ledger, name)  # Require the exact override declaration.
    require(stripped(read("InfiniCrafterLocal.cs")), "GeneratedPlacementLedgerSystem.HandlePlacementPacket", "placement packet router")
    for name in ("RestoreOwnerState", "CaptureOwnerState", "TryReplay", "CanAcceptNewOperation", "TryBeginCraft", "TryReplayCraft", "IsCraftPending", "CompleteCraft"):
        method_body(journal, name)
    for token in ("ServerCommittedCraftRequests", "ServerCancelledCraftRequests", '"servercraft:"'):
        forbid(stripped(mp, keep_strings=True), token, "world-owned craft journal")
    forbid(stripped(read("Common/Players/InfiniCraftPlayer.cs")), "_stationEscrowResultCache", "world-owned outcome journal")
    refunds = stripped(method_body(state, "PendingRefundTagsForSave"))
    require(refunds, "_stationEscrowUsesRemoteAuthority && _awaitingServerCommit", "remote_pending_reconciliation")
    require(refunds, "AddMultiDevPendingRefunds(refunds, includeRemoteAwaiting: !_stationEscrowUsesRemoteAuthority)", "remote_pending_reconciliation")
    guard = re.search(r"if\s*\(\s*!_stationEscrowUsesRemoteAuthority\s*\)\s*\{", refunds)
    guarded = braced_body(refunds, guard.end() - 1) if guard else ""
    for token in ("if (HasInputA) AddRefundTag(refunds, InputA)", "if (HasInputB) AddRefundTag(refunds, InputB)", "for (int index = 2; index < 6; index++)"):
        require(guarded, token, "guarded_refund")
    apply = stripped(method_body(mp, "ApplyStationEscrowResult"))
    for action in ("ReturnOne", "ReturnAll"):
        branch = re.search(r"else\s+if\s*\(action\s*==\s*StationEscrowAction\." + action + r"[^{}]*\)\s*\{", apply)
        require(braced_body(apply, branch.end() - 1) if branch else "", "RefundOne(slot)", "ApplyStationEscrowResult:" + action)
    require(apply, "for (int slotIndex = 0; slotIndex < 6; slotIndex++)", "ApplyStationEscrowResult")
    for name in ("RestoreRemoteCraftMirror", "ClearRemoteCraftMirror"):
        method_body(mp, name)


def check_delivery_metadata() -> None:
    # Derive DTO membership from the actual Python producer, not a second field
    # roster. Any added/retired output must propagate to the C# consumer.
    producer = ast.parse((ROOT / "LocalGenerator/infini_local/pipelines/generated_parent_summary.py").read_text(encoding="utf-8"))
    function = next(n for n in producer.body if isinstance(n, ast.FunctionDef) and n.name == "generated_parent_summary_from_data")
    output = next(n.value for n in ast.walk(function) if isinstance(n, ast.Return) and isinstance(n.value, ast.Dict))
    expected = {key.value[0].upper() + key.value[1:]: "string[]" if isinstance(value, (ast.Subscript, ast.ListComp)) else "string"
                for key, value in zip(output.keys, output.values) if isinstance(key, ast.Constant)}
    schema = next(value.value for key, value in zip(output.keys, output.values) if isinstance(key, ast.Constant) and key.value == "schema")
    model = read("Common/Models/GeneratedItemData.Model.cs")
    mask = stripped(model)
    match = re.search(r"\bclass\s+GeneratedParentSummarySpec\s*\{", mask)
    block = ""
    if match:
        depth = 1
        for end in range(match.end(), len(mask)):
            depth += (mask[end] == "{") - (mask[end] == "}")
            if not depth:
                block = model[match.end():end]
                break
    fields = {name: kind for kind, name in re.findall(r"public\s+([\w.<>,\[\]?]+)\s+(\w+)\s*(?:\{\s*get\b|=>)", stripped(block))}
    if fields != expected or f'CurrentSchema = "{schema}"' not in stripped(block, keep_strings=True):
        fail(f"parent_summary_dto: expected producer fields {expected}, found {fields}")
    wire = stripped(method_body(read("Common/Services/GeneratorClient.cs"), "ToWireItem"))
    for token in ("GeneratedItemData.IsPlayerSaveReferenceOnly(existing)", "string generatedParentId = existing!.Id", "registry.TryGet(generatedParentId, out GeneratedItemData canonical)", "GeneratedItemRegistryService.IsCurrentWorldData(canonical)", "existing = canonical", "throw new InvalidOperationException"):
        require(wire, token, "ToWireItem")
    if wire.find("GeneratedItemData.IsPlayerSaveReferenceOnly(existing)") > wire.find("Item craftItem = CraftIdentityItem(item, existing)"):
        fail("ToWireItem: hydration must precede craft identity projection")
    prefilter = stripped(method_body(read("Common/Services/GeneratedItemRegistryService.cs"), "CacheJsonTargetsCurrentWorld"), keep_strings=True)
    for field in ("recipeMeta", "worldScoped", "worldId"):
        require(prefilter, f'TryGetProperty("{field}"', "world cache wire keys")
        forbid(prefilter, f'TryGetProperty("{field[0].upper() + field[1:]}"', "world cache wire keys")
    normalize = stripped(read("Common/Models/GeneratedItemData.Normalize.cs"), keep_strings=True)
    require(stripped(model, keep_strings=True), 'public string Slot { get; set; } = "";', "armor_slot")
    require(normalize, 'Armor.Enabled && Armor.Slot is not ("head" or "body" or "legs")', "armor_slot")
    forbid(normalize, 'Armor.Slot = "body"', "armor_slot")
    overlay = stripped(read("Common/Players/GeneratedEquipOverlayDrawLayer.cs"))
    require(overlay, "data.Accessory?.Enabled == true", "explicit equipment overlay")
    forbid(overlay, "Gameplay?.Kind", "explicit equipment overlay")
    held = stripped(method_body(read("Common/Players/GeneratedHeldItemDrawLayer.cs"), "ShouldDrawHeldSprite"), keep_strings=True)
    require(held, 'releaseTiming != "immediate"', "held sprite vocabulary")
    for retired in ('releaseTiming == "instant"', 'releaseTiming == "early"'):
        forbid(held, retired, "held sprite vocabulary")
    # The complete item+overlay+entity+impact domain must fit; changing a valid
    # budget consistently is allowed, unlike fixed 12/32 historical snapshots.
    declared = json.loads((ROOT / "contracts/schemas/runtime_program_author.schema.json").read_text(encoding="utf-8"))["properties"]["entities"]["maxItems"]
    limit = re.search(r"MaxRuntimeEntities\s*=\s*(\d+)", stripped(read("Common/InfiniRuntimeLimits.cs")))
    asset = read("Common/Services/GeneratedAssetSyncService.cs")
    capacity = re.search(r"MaxAssetFiles\s*=\s*(\d+)", stripped(asset))
    if not limit or int(limit.group(1)) != declared or not capacity or int(capacity.group(1)) < 2 * declared + 2:
        fail("asset_roster_capacity: Author/C# entity limits must agree and fit all item/overlay/entity/impact files")
    for token in ("count > MaxAssetFiles", "MaxAssetBundleBytes", "HasCompleteServerAssetRoster"):
        require(stripped(asset), token, "full asset roster admission")
    forbid(stripped(asset), ".Take(16)", "full asset roster admission")
    registry = stripped(read("Common/Services/GeneratedItemRegistryService.cs"))
    for token in ("descriptors.Length, GeneratedAssetSyncService.MaxAssetFiles", "descriptorCount > GeneratedAssetSyncService.MaxAssetFiles"):
        require(registry, token, "shared descriptor admission limit")


def check_balanced_sources() -> None:
    if not SRC.is_dir():
        fail(f"missing source root: {SRC}")
        return
    for path in sorted(SRC.rglob("*.cs")):
        text = stripped(path.read_text(encoding="utf-8", errors="ignore"))
        balance = 0
        for char in text:
            if char == "{":
                balance += 1
            elif char == "}":
                balance -= 1
                if balance < 0:
                    fail(f"{path.relative_to(ROOT)}: closing brace before opening brace")
                    break
        if balance:
            fail(f"{path.relative_to(ROOT)}: brace imbalance {balance:+d}")


def check_runtime_contract() -> None:
    dto = read("Common/Models/RuntimeProgramSpec.cs")
    data = read("Common/Models/GeneratedItemData.cs") + read("Common/Models/GeneratedItemData.Model.cs")
    normalize = read("Common/Models/GeneratedItemData.Normalize.cs")
    colors = read("Common/VFX/RuntimeColorPolicy.cs")
    limits = read("Common/InfiniRuntimeLimits.cs")
    vocabulary = read("Common/Models/TerrariaRuntimeVocabulary.cs")
    generator_client = read("Common/Services/GeneratorClient.cs")
    generated_item = read("Content/Items/GeneratedItem.cs")
    for needle in [
        'CurrentApiVersion = "infini.runtime-program.v5"',
        'CurrentWireSchema = "infini.runtime-program.wire.v3"',
        "public string PrimaryEntityId { get; set; }",
        "public string PrimaryOwner { get; set; }",
        "public string Role { get; set; }",
        "NormalizeAndValidate()",
        "exactly one item_body",
        "multiple exclusive owners",
        "runtime entity event cycle",
        "event spawn budget exceeded",
        "target_and_fire has no explicit shotEntityId",
        "active primary/alternate binding requires explicit configure_item_use",
        "binding.Role != expectedRole",
        "VisualRoleFor(string? value)",
        "visual roles must equal",
    ]:
        require(dto, needle, "RuntimeProgramSpec.cs")
    require(data, "JsonUnmappedMemberHandling.Disallow", "GeneratedItemData.cs")
    require(data, "RuntimeProgramSpec RuntimeProgram", "GeneratedItemData.cs")
    require(normalize, "RuntimeProgram.NormalizeAndValidate();", "GeneratedItemData.Normalize.cs")
    require(normalize, "ValidateBindingCapabilityProjection();", "GeneratedItemData.Normalize.cs")
    require(normalize, "apply_item_effects has no compiled item effect capability", "GeneratedItemData.Normalize.cs")
    require(dto, "place_item requires an exact placement payload", "RuntimeProgramSpec.cs")
    require(normalize, "equip_passive has no compiled accessory/armor capability", "GeneratedItemData.Normalize.cs")
    require(limits, "MaxRuntimeEntities", "InfiniRuntimeLimits.cs")
    require(limits, "MaxRuntimeChildDepth", "InfiniRuntimeLimits.cs")
    require(limits, "MaxRuntimeEventSpawns", "InfiniRuntimeLimits.cs")
    for token in [
        '"generic" => DamageClass.Generic',
        '"melee_no_speed" => DamageClass.MeleeNoSpeed',
        '"summon_melee_speed" => DamageClass.SummonMeleeSpeed',
        '"eat_food" => ItemUseStyleID.EatFood',
        '"drink_liquid" => ItemUseStyleID.DrinkLiquid',
        '"raise_lamp" => ItemUseStyleID.RaiseLamp',
        '"rocket" => AmmoID.Rocket',
        '"stynger_bolt" => AmmoID.StyngerBolt',
        'ModContent.TryFind<DamageClass>(exact',
        'Unknown exact damageClass',
        'throw new InvalidDataException',
    ]:
        require(vocabulary, token, "TerrariaRuntimeVocabulary.cs")
    for forbidden in ["ResolveModded", '"rogue"', "?? DamageClass.Generic"]:
        forbid(vocabulary + data + normalize, forbidden, "canonical Terraria vocabulary")
    require(vocabulary, "CanonicalDamageClassToken", "TerrariaRuntimeVocabulary.cs")
    require(generator_client, "=> TerrariaRuntimeVocabulary.CanonicalDamageClassToken", "GeneratorClient.cs")
    forbid(generator_client, "damageClassFullName", "GeneratorClient.cs")
    forbid(generator_client, 'return damageClass is null ? (damage > 0 ? "generic" : "none") : "modded"', "GeneratorClient.cs")
    require(normalize, "Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129);", "GeneratedItemData.Normalize.cs")
    forbid(normalize, "Gameplay.DamageClass = SafeText(Gameplay.DamageClass, 129).ToLowerInvariant();", "GeneratedItemData.Normalize.cs")
    require(dto, "DamageClass = RuntimeText.Safe(DamageClass, 129);", "RuntimeProgramSpec.cs")
    forbid(dto, "DamageClass = RuntimeText.Safe(DamageClass, 129).ToLowerInvariant();", "RuntimeProgramSpec.cs")
    require(colors, "public static string NormalizeRequired", "RuntimeColorPolicy.cs")
    forbid(normalize + dto, "RuntimeColorPolicy.Normalize(", "authoritative runtime color boundary")
    require(normalize, "NormalizeRequiredHexColor", "GeneratedItemData.Normalize.cs")
    forbid(normalize, "NormalizeHexColor(", "GeneratedItemData.Normalize.cs")
    for loaded_guard in ["RarityLoader.RarityCount", "BuffLoader.BuffCount", "extra buff row cannot be null", "requires positive duration"]:
        require(normalize, loaded_guard, "GeneratedItemData.Normalize.cs")
    for loaded_guard in ["TileLoader.TileCount", "WallLoader.WallCount"]:
        require(dto, loaded_guard, "RuntimeProgramSpec.cs")
    require(dto, "BuffLoader.BuffCount", "RuntimeProgramSpec.cs")
    require(dto, "BuffId <= 0", "RuntimeProgramSpec.cs")
    require(generated_item, "buff.BuffCode > 0", "GeneratedItem.cs")
    forbid(normalize, "ClampInt(Gameplay.Rarity", "GeneratedItemData.Normalize.cs")
    forbid(normalize, "ClampInt(Gameplay.CreateTile", "GeneratedItemData.Normalize.cs")
    forbid(normalize, "ClampInt(Gameplay.CreateWall", "GeneratedItemData.Normalize.cs")
    forbid(dto, 'public const string Passive = "passive"', "RuntimeProgramSpec.cs")
    require(normalize, "Gameplay.AmmoProjectileId >= ProjectileID.Count", "GeneratedItemData.Normalize.cs")
    apply = read("Common/Models/GeneratedItemData.Apply.cs")
    for needle in ["item.potion = enabled && Gameplay.Potion;", "item.notAmmo = Gameplay.NotAmmo;", "item.ammo = TerrariaRuntimeVocabulary.ResolveAmmoCategory", "item.shoot = Gameplay.AmmoProjectileId;", "item.shootSpeed = Gameplay.AmmoShootSpeedPxPerTick;"]:
        require(apply, needle, "GeneratedItemData.Apply.cs")
    forbid(apply, "item.potion = Gameplay.HealLife > 0", "GeneratedItemData.Apply.cs")
    require(apply, "RuntimeProgram.PrimaryOwner != RuntimeProgramSpec.ItemBodyOwner", "GeneratedItemData.Apply.cs")


def check_item_dispatch() -> None:
    item = read("Content/Items/GeneratedItem.cs") + read("Content/Items/GeneratedItem.UseStyle.cs")
    for needle in [
        "RuntimeInputKind.AlternateUse : RuntimeInputKind.PrimaryUse",
        "BindingForInput(RuntimeInputKind.AlternateUse)",
        "RuntimeProgramExecutor",
        "SpawnRuntimeEntity",
        "BindingUsesItemBodyContact(binding)",
        "UsePolicy.ContactDamage",
    ]:
        require(item, needle, "GeneratedItem v5 dispatch")
    for legacy in ["AttackSpec", "RuntimeFamily", "WeaponFamily", "AltUseMode", "perform_melee_attack", "shoot_projectile"]:
        forbid(item, legacy, "GeneratedItem v5 dispatch")


def check_projectile_dispatch() -> None:
    projectile = read("Content/Projectiles/GeneratedProjectile.cs")
    executors = read("Content/Projectiles/GeneratedProjectile.Executors.cs")
    events = read("Content/Projectiles/GeneratedProjectile.RuntimeEvents.cs")
    net = read("Content/Projectiles/GeneratedProjectile.NetSync.cs")
    runtime = read("Common/Runtime/RuntimeProgramExecutor.cs")
    packet_ids = read("Common/InfiniNetPacketIds.cs")
    packet_router = read("InfiniCrafterLocal.cs")
    for needle in [
        "RuntimeEntitySpec? _entity",
        "SpawnRuntimeEntity(",
        "MaxRuntimeSpawnCount",
        "MaxChildDepth",
        "ShouldRunLocalPlayerAction",
        "Projectile.NewProjectileDirect(",
        "Projectile.ignoreWater = entity.Collision.IgnoreWater",
        'Projectile.usesLocalNPCImmunity = entity.Collision.NpcImmunityMode == "local"',
        "Projectile.netImportant = entity.IsOwnerAttached",
        "HeldProjDoesNotUsePlayerGfxOffY",
    ]:
        require(projectile, needle, "GeneratedProjectile.cs")
    require(executors, "switch (movement.Code)", "GeneratedProjectile.Executors.cs")
    require(executors, "Projectile.Kill();", "GeneratedProjectile.Executors.cs")
    require(executors, "RejectUnknownController", "GeneratedProjectile.Executors.cs")
    require(events, "RuntimeProgramExecutor.ExecuteAction", "GeneratedProjectile.RuntimeEvents.cs")
    require(events, "EmitAndSyncVfxEvent", "GeneratedProjectile.RuntimeEvents.cs")
    require(executors, "EmitAndSyncVfxEvent(RuntimeEventKind.OnRelease", "GeneratedProjectile.Executors.cs")
    require(executors, "EmitAndSyncVfxEvent(RuntimeEventKind.ChannelComplete", "GeneratedProjectile.Executors.cs")
    require(events, "foreach (RuntimeEventActionSpec action", "GeneratedProjectile.RuntimeEvents.cs")
    require(projectile, "IsPrimaryRuntimeEntity", "GeneratedProjectile.cs")
    require(projectile, "PrimaryOwner == RuntimeProgramSpec.ProjectileOwner", "GeneratedProjectile.cs")
    require(projectile, "PrimaryEntityId", "GeneratedProjectile.cs")
    require(projectile, "owner.heldProj = Projectile.whoAmI;", "GeneratedProjectile.cs")
    forbid(executors, "owner.heldProj = Projectile.whoAmI;", "GeneratedProjectile.Executors.cs")
    require(runtime, "switch (action.ActionCode)", "RuntimeProgramExecutor.cs")
    require(runtime, "default:\n                return;", "RuntimeProgramExecutor.cs")
    for needle in [
        "RuntimeNetVersion",
        "public override void SendExtraAI",
        "public override void ReceiveExtraAI",
        "_generatedItemId.Length > 96",
        "_entityId.Length > 48",
        "Projectile.friendly = false",
        "HandleVfxEventSyncPacket",
        "BroadcastAuthoritativeVfxEvent",
        "Main.netMode != NetmodeID.MultiplayerClient",
        "GeneratedItemRegistryService",
        "InfiniVfxRuntime.OnDetachedEvent",
        "packet.Send(-1, Projectile.owner)",
    ]:
        require(net, needle, "GeneratedProjectile.NetSync.cs")
    require(packet_ids, "SyncGeneratedProjectileVfxEvent", "InfiniNetPacketIds.cs")
    require(packet_router, "GeneratedProjectile.HandleVfxEventSyncPacket(reader, whoAmI)", "InfiniCrafterLocal.cs")
    for legacy in ["AttackSpec", "RuntimeFamily", "WeaponFamily", "GeneratedChildSpecPolicy", "GeneratedRuntimeFamilyPolicy"]:
        forbid(projectile + executors + events + net + runtime, legacy, "projectile v5 runtime")


def check_visual_vfx_contract() -> None:
    visual = read("Content/Projectiles/GeneratedProjectile.Visuals.cs")
    manifest = read("Common/Models/VfxManifestSpec.cs")
    runtime_dto = read("Common/Models/RuntimeProgramSpec.cs")
    renderer_registry = read("Common/VFX/VfxRendererRegistry.cs")
    vocabulary = read("Common/VFX/VfxCanonicalVocabulary.cs")
    runtime = read("Common/VFX/InfiniVfxRuntime.cs")
    require(visual, "_entity!.Visual", "GeneratedProjectile.Visuals.cs")
    require(manifest, "JsonUnmappedMemberHandling.Disallow", "VfxManifestSpec.cs")
    require(manifest, "EntityId", "VfxManifestSpec.cs")
    require(manifest, "Event", "VfxManifestSpec.cs")
    require(runtime, "entityId", "InfiniVfxRuntime.cs")
    require(runtime, "eventName", "InfiniVfxRuntime.cs")
    require(runtime, "InfiniVfxSlotEmissionKey", "InfiniVfxRuntime.cs")
    require(runtime, "slot.Id", "InfiniVfxRuntime.cs")
    for guard in ('slot.RendererKind == "impactSprite" && !impactEntityIds.Add(slot.EntityId)',
                  'rendererKind == InfiniVfxRendererKind.ImpactSprite && TextureRole != "impact"',
                  'VfxRendererRegistry.ConsumesSpriteTexture(rendererKind) && TextureRole == "none"'):
        require(stripped(manifest, keep_strings=True), guard, "authored texture role admission")
    require(stripped(read("Common/Models/GeneratedItemData.cs")), "entity.Visual.ImpactSpritePath = FileNameOnly", "impact wire path")
    require(stripped(read("Common/Services/GeneratedAssetSyncService.cs")), "yield return entity.Visual.ImpactSpritePath", "impact asset roster")
    presentation_selection = read("Common/Models/SpritePresentation.cs")
    require(stripped(runtime), "SpritePresentation.Resolve(data, entityId, textureRole).Path", "paired impact resolver dispatch")
    require(stripped(presentation_selection, keep_strings=True), 'role == "impact"', "impact role resolver")
    require(stripped(presentation_selection), "entity.Visual.ImpactSpritePath", "impact role resolver")
    require(stripped(visual), "InfiniVfxRuntime.Draw(Projectile, _data, _entity.Id,", "entity VFX dispatch")
    require(
        runtime_dto,
        'AssetMode is not ("baked_sprite" or "reuse_item_icon" or "runtime_geometry" or "no_asset")',
        "RuntimeEntityVisualSpec",
    )
    require(manifest, 'Layer = ExactEnumText(Layer, "layer", "BeforeProjectiles", "AfterProjectiles");', "VfxManifestSpec.cs")
    forbid(manifest, "private static string EnumText(", "VfxManifestSpec.cs")
    for dead in [
        "public string Curve", "public int Variant", "public string Importance",
        "EstimateDrawCost(", "NormalizeKindName(", "NormalizeEventGroup(",
        "public static string Curve(", "public static string Importance(",
    ]:
        forbid(manifest + renderer_registry + vocabulary, dead, "dead VFX contract")
    for legacy in ["RuntimeFamily", "WeaponFamily", "AttackSpec"]:
        forbid(visual + manifest + runtime, legacy, "entity/event VFX")


def check_vfx_sound_contract() -> None:
    # Read the actual VFX owner, never a second list of samples/Author controls.
    source = ast.parse((ROOT / "LocalGenerator/infini_local/core/vfx_manifest.py").read_text(encoding="utf-8"))
    catalog = next(ast.literal_eval(node.value) for node in source.body
                   if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "_SOUND_IDS" for target in node.targets))
    schema_function = next(node for node in source.body if isinstance(node, ast.FunctionDef) and node.name == "_sound_schema")
    fields = set(ast.literal_eval(next(node.value for node in schema_function.body if isinstance(node, ast.Return)))["properties"])
    manifest = read("Common/Models/VfxManifestSpec.cs")
    controls = read("Common/Models/VfxSoundSpec.cs")
    exact = re.findall(r'"(\w+)"\s*=>\s*SoundID\.(\w+)', stripped(manifest, keep_strings=True))
    if len(exact) != len(catalog) or dict(exact) != {name: name for name in catalog}:
        fail("VFX sound exact palette must match every canonical SoundID member")
    properties = set(re.findall(r'\bpublic\s+[\w?<>\[\]]+\s+(\w+)\s*\{\s*get\s*;\s*set\s*;', stripped(controls)))
    if properties != {field[0].upper() + field[1:] for field in fields}:
        fail("VFX sound DTO must expose exactly the canonical control fields")
    # VfxManifestSpec and VfxSlotSpec share the method name: narrow ownership to
    # the slot declaration, otherwise a valid root normalizer can hide a loss.
    slot_declaration = manifest[manifest.index("public sealed class VfxSlotSpec"):]
    normalized = stripped(method_body(slot_declaration, "NormalizeAndValidate"), keep_strings=True)
    require(normalized, 'rendererKind != InfiniVfxRendererKind.SoundCue', "VFX sound renderer ownership")
    require(normalized, 'if (SoundId is null)', "VFX sound explicit selector dependency")
    require(normalized, 'Sound.NormalizeAndValidate();', "VFX sound strict controls")
    playback = stripped(method_body(manifest, "ResolveSoundStyle"))
    require(playback, 'Sound is { } sound ? sound.ApplyTo(sample) : sample with', "VFX sound explicit/legacy split")
    require(playback, 'Volume = Math.Clamp(Alpha, 0.05f, 1f)', "VFX sound legacy volume")
    require(playback, 'Pitch = Math.Clamp(PhaseOffset * 0.25f, -0.5f, 0.5f)', "VFX sound legacy phase")
    apply = stripped(method_body(controls, "ApplyTo"))
    require(apply, 'new SoundStyle(sample.SoundPath, sample.Variants, sample.Type)', "VFX sound independent pitch")
    for field in fields:
        member = field[0].upper() + field[1:]
        require(apply, f'{member} = {member}', "VFX sound exact controls")
    for member in ("Identifier", "MaxInstances", "SoundLimitBehavior", "RerollAttempts", "LimitsArePerVariant", "PlayOnlyIfFocused", "PauseBehavior", "IsLooped", "VariantsWeights"):
        require(apply, f'{member} = sample.{member}', "VFX sound native playback policy")
    for path, method in (("Common/VFX/InfiniItemVfxRuntime.cs", "EmitLocal"), ("Common/VFX/InfiniVfxRuntime.cs", "EmitSlot")):
        consumer = stripped(method_body(read(path), method))
        require(consumer, 'SoundStyle sound = slot.ResolveSoundStyle();', "VFX sound shared playback projection")
        require(consumer, 'if (sound.Volume > 0f) SoundEngine.PlaySound(sound, center);', "VFX sound explicit silence")


def check_deleted_architecture() -> None:
    forbidden_files = [
        "Content/Projectiles/GeneratedProjectile.Runtime.cs",
        "Content/Projectiles/GeneratedProjectile.Impact.cs",
        "Content/Projectiles/GeneratedProjectile.ChargeRelease.cs",
        "Content/Projectiles/GeneratedProjectile.Sentry.cs",
        "Content/Projectiles/GeneratedProjectile.OverheadBarrage.cs",
        "Content/Projectiles/GeneratedChildSpecPolicy.cs",
        "Common/Models/GeneratedChildSpecPolicy.cs",
        "Common/Models/GeneratedRuntimeFamilyPolicy.cs",
        "Common/Models/GeneratedSecondaryTriggerPolicy.cs",
        "Content/Items/GeneratedItem.Sentry.cs",
    ]
    for relative in forbidden_files:
        if (SRC / relative).exists():
            fail(f"legacy C# file still active: {relative}")
    active = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in sorted(SRC.rglob("*.cs"))
        if p.name != "GeneratedItemData.Normalize.cs"
    )
    for legacy in [
        "GeneratedRuntimeFamilyPolicy",
        "GeneratedChildSpecPolicy",
        "HandleProjectileVisualSyncPacket",
        "HandleProjectileVfxEventSyncPacket",
        "FlushPendingProjectileVisualSyncForGeneratedItem",
        "FlushPendingVfxEventsForGeneratedItem",
    ]:
        forbid(active, legacy, "active C# source")


def check_packet_ids() -> None:
    packet_source = read("Common/InfiniNetPacketIds.cs")
    values = re.findall(r"public const byte\s+(\w+)\s*=\s*(\d+)\s*;", stripped(packet_source))
    # Public protocol identities are stable, not merely non-colliding.
    ids = {name: int(raw) for name, raw in values}
    if ids.get("SyncGeneratedProjectileVfxEvent") != 9:
        fail("stable packet id: SyncGeneratedProjectileVfxEvent must remain 9")
    seen: dict[int, str] = {}
    for name, raw in values:
        value = int(raw)
        if value in seen:
            fail(f"packet id collision: {name} and {seen[value]} both use {value}")
        seen[value] = name


def main() -> int:
    check_balanced_sources()
    check_source_policies()
    check_runtime_contract()
    check_item_dispatch()
    check_projectile_dispatch()
    check_network_boundaries()
    check_sampled_spawn_boundaries()
    check_client_source_contracts()
    check_world_transactions()
    check_delivery_metadata()
    check_visual_vfx_contract()
    check_vfx_sound_contract()
    check_deleted_architecture()
    check_packet_ids()
    if ERRORS:
        print("[FAIL] C# v5 contract scanner found issues:")
        for message in ERRORS:
            print(" -", message)
        return 1
    print("[OK] C# v5 low-level runtime contract scanner passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
