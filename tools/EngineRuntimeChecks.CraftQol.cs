using System;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void CraftQolMetadataCommitNeverWaitsForWorkerLock()
        => CraftQolMetadataCommitNeverWaitsForWorkerLockAsync().GetAwaiter().GetResult();

    private static async Task CraftQolMetadataCommitNeverWaitsForWorkerLockAsync()
    {
        await using var server = new CraftHttpFixture(0) { HoldDiscovery = true };
        var client = new GeneratorClient { Endpoint = server.Endpoint };
        using var retired = new System.Threading.CancellationTokenSource();
        Task worker = Task.Run(() => client.RefreshAssetTransportMetadata(retired.Token));
        var generator = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Generator")!;
        object? previous = generator.GetValue(null);
        try
        {
            await server.Held.Task.WaitAsync(TimeSpan.FromSeconds(5));
            generator.SetValue(null, client);
            Task commit = Task.Run(() => typeof(InfiniCraftPlayer).GetMethod("StampHostAssetSyncMetadata",
                BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, new object[] { GeneratedItemData.Placeholder() }));
            await commit.WaitAsync(TimeSpan.FromMilliseconds(250));
            Equal(1, server.DiscoveryRequests, "update stamp starts zero metadata HTTP requests");
            Task getters = Task.Run(() => { _ = client.AssetBaseUrlForSharing(); _ = client.AssetTransportForSharing(); });
            await getters.WaitAsync(TimeSpan.FromMilliseconds(250));
            Equal(1, server.DiscoveryRequests, "sharing snapshot reads start zero metadata HTTP requests");
        }
        finally
        {
            retired.Cancel(); server.Release();
            try { await worker; } catch (OperationCanceledException) { }
            generator.SetValue(null, previous);
        }
    }

    private static void CraftQolPartialRefundRetainsOnlyRemainder()
    {
        using var serializer = WithPersistenceBoolSerializer();
        int mode = Terraria.Main.netMode; Item[] items = Terraria.Main.item;
        int[] timers = Terraria.Main.timeItemSlotCannotBeReusedFor;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.item = Enumerable.Range(0, Terraria.Main.maxItems + 1).Select(_ => new Item(ItemID.Wood, 3) { active = true }).ToArray();
            Terraria.Main.timeItemSlotCannotBeReusedFor = new int[Terraria.Main.maxItems + 1];
            WithPlayer((player, owner) =>
            {
                owner.Initialize();
                for (int i = 0; i < 58; i++) player.inventory[i] = new Item(ItemID.Wood, 9999);
                player.inventory[0].stack = 9997;
                typeof(InfiniCraftPlayer).GetMethod("RefundOne", CraftFields)!.Invoke(owner, new object[] { new Item(ItemID.Wood, 5) });
                var save = new TagCompound(); owner.SaveData(save);
                Equal(9999, player.inventory[0].stack, "partial inventory merge is committed once");
                Equal(3, ItemIO.Load(save.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Single()).stack,
                    "durable pending claim contains only undelivered remainder");
                player.inventory[1].TurnToAir();
                typeof(InfiniCraftPlayer).GetMethod("RestoreDeferredExitRefunds", CraftFields)!.Invoke(owner, null);
                Equal(3, player.inventory[1].stack, "retry never recreates already delivered part");
            });
        }
        finally { Terraria.Main.netMode = mode; Terraria.Main.item = items; Terraria.Main.timeItemSlotCannotBeReusedFor = timers; }
    }

    private static void CraftQolCancelPacketReplaysCommittedOutcomeWithoutNewRefund()
    {
        int mode = Terraria.Main.netMode; Player[] players = Terraria.Main.player;
        var world = new InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem();
        try
        {
            Terraria.Main.netMode = NetmodeID.Server;
            Terraria.Main.player = new Player[Terraria.Main.maxPlayers]; world.ClearWorld();
            using (var scope = new System.IO.BinaryWriter(new System.IO.MemoryStream())) world.NetSend(scope);
            WithPlayer((player, owner) =>
            {
                owner.Initialize(); player.active = true; player.whoAmI = 3; Terraria.Main.player[3] = player;
                string client = new string('b', 32), request = new string('c', 32);
                typeof(InfiniCraftPlayer).GetField("_stationEscrowClientId", CraftFields)!.SetValue(owner, client);
                Equal(true, InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.RestoreOwnerState(client, owner), "bound server owner admitted");
                Equal(true, InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.TryBeginCraft(client, request, 1), "journal owns craft");
                Equal(true, InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.CompleteCraft(client, request, true, "exact output", "ok"), "output committed before cancel races");
                int sends = 0; bool? success = null;
                var send = typeof(InfiniCraftPlayer).GetMethod("SendCraftCommitResult", BindingFlags.Static | BindingFlags.NonPublic)!;
                using var observer = new MonoMod.RuntimeDetour.ILHook(send, il =>
                {
                    var cursor = new MonoMod.Cil.ILCursor(il);
                    cursor.Emit(Mono.Cecil.Cil.OpCodes.Ldarg_2);
                    cursor.EmitDelegate<Action<bool>>(value => { sends++; success = value; throw new InvalidOperationException("observed packet boundary"); });
                });
                using var bytes = new System.IO.MemoryStream();
                using (var writer = new System.IO.BinaryWriter(bytes, System.Text.Encoding.UTF8, true))
                {
                    writer.Write((int)typeof(InfiniCraftPlayer).GetField("RemoteStationProtocolVersion", BindingFlags.Static | BindingFlags.NonPublic)!.GetRawConstantValue()!);
                    writer.Write(InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.AuthorityScope);
                    writer.Write(request); writer.Write("cancel");
                }
                bytes.Position = 0;
                try { InfiniCraftPlayer.HandleCancelServerCraftPacket(new System.IO.BinaryReader(bytes), 3); }
                catch (InvalidOperationException error) when (error.Message == "observed packet boundary") { }
                Equal(1, sends, "cancel replays one exact outcome");
                Equal(true, success, "late cancel never converts committed output to false/refund authority");
                Equal(0, player.inventory.Take(58).Count(i => !i.IsAir), "cancel replay creates no material copy");
            });
        }
        finally { world.ClearWorld(); Terraria.Main.netMode = mode; Terraria.Main.player = players; }
    }

    private static void CraftQolRemoteCancelRetainsClaimUntilHostOutcome()
    {
        using var serializer = WithPersistenceBoolSerializer();
        int mode = Terraria.Main.netMode;
        var world = new InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem();
        try
        {
            Terraria.Main.netMode = NetmodeID.Server; world.ClearWorld();
            using (var scopeWriter = new System.IO.BinaryWriter(new System.IO.MemoryStream())) world.NetSend(scopeWriter);
            string scope = InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.AuthorityScope;
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            WithPlayer((player, owner) =>
            {
                owner.Initialize();
                typeof(InfiniCraftPlayer).GetField("_stationEscrowUsesRemoteAuthority", CraftFields)!.SetValue(owner, true);
                typeof(InfiniCraftPlayer).GetField("_stationEscrowOriginScope", CraftFields)!.SetValue(owner, scope);
                typeof(InfiniCraftPlayer).GetField("_serverRequestId", CraftFields)!.SetValue(owner, new string('e', 32));
                typeof(InfiniCraftPlayer).GetField("_awaitingServerCommit", CraftFields)!.SetValue(owner, true);
                var request = new GeneratorClient.PreparedGenerationRequest { RefundA = new Item(ItemID.Wood, 1), RefundB = new Item(ItemID.StoneBlock, 1) };
                typeof(InfiniCraftPlayer).GetField("_request", CraftFields)!.SetValue(owner, request);
                Equal(true, owner.TryCancelCraftLane(0), "remote cancel reuses exact existing protocol");
                Equal(true, owner.HasPendingCraft, "remote cancel retains original request until canonical outcome");
                Equal(0, player.inventory.Take(58).Count(i => !i.IsAir), "cancel creates no client refund authority");
                var save = new TagCompound(); owner.SaveData(save);
                var row = save.GetList<TagCompound>("infiniPendingRemoteCrafts").Single();
                Equal(true, row.GetBool("cancelRequested"), "pending cancel durably retains intent");
                Equal(new string('e', 32), row.GetString("requestId"), "pending cancel retains exact request identity");
                WithPlayer((replacement, restored) =>
                {
                    restored.Initialize(); restored.LoadData(PersistenceNbtRoundtrip(save));
                    typeof(InfiniCraftPlayer).GetMethod("RefreshRemoteStationAuthority", CraftFields)!.Invoke(restored, null);
                    Equal(true, restored.HasPendingCraft, "same-world reconnect restores exact pending owner");
                    var after = new TagCompound(); restored.SaveData(after);
                    Equal(true, after.GetList<TagCompound>("infiniPendingRemoteCrafts").Single().GetBool("cancelRequested"), "reconnect cannot restart a cancelled generation");
                    Equal(0, replacement.inventory.Take(58).Count(i => !i.IsAir), "reconnect creates no client material copies");
                });
            });
        }
        finally { world.ClearWorld(); Terraria.Main.netMode = mode; }
    }

    private static void CraftQolServerDeadlinePreservesDurableEscrow()
    {
        int mode = Terraria.Main.netMode; Player[] players = Terraria.Main.player;
        var world = new InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem();
        using var serializer = WithPersistenceBoolSerializer();
        try
        {
            Terraria.Main.netMode = NetmodeID.Server; Terraria.Main.player = new Player[Terraria.Main.maxPlayers]; world.ClearWorld();
            WithPlayer((player, owner) =>
            {
                owner.Initialize(); player.active = true; player.whoAmI = 3; Terraria.Main.player[3] = player;
                string client = new string('a', 32), requestId = new string('d', 32);
                typeof(InfiniCraftPlayer).GetField("_stationEscrowClientId", CraftFields)!.SetValue(owner, client);
                Equal(true, InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.RestoreOwnerState(client, owner), "live owner admitted");
                owner.RestoreServerStationEscrowSlots(Enumerable.Range(0, 6).Select(_ => new Item(ItemID.Wood, 1)).ToArray());
                InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.CaptureOwnerState(client, owner);
                Equal(true, InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.TryBeginCraft(client, requestId, 1), "world journal starts exact lane");
                Type type = typeof(InfiniCraftPlayer).GetNestedType("MultiDevCraftJob", BindingFlags.NonPublic)!;
                object job = Activator.CreateInstance(type, true)!;
                var request = new GeneratorClient.PreparedGenerationRequest { RefundA = new Item(ItemID.Wood, 1), RefundB = new Item(ItemID.Wood, 1) };
                type.GetField("Request", CraftFields)!.SetValue(job, request);
                type.GetField("RequestId", CraftFields)!.SetValue(job, requestId);
                type.GetField("LaneIndex", CraftFields)!.SetValue(job, 1);
                type.GetField("ElapsedTicks", CraftFields)!.SetValue(job, InfiniCraftPlayer.CraftRecoveryTimeoutTicks - 1);
                type.GetField("Task", CraftFields)!.SetValue(job, new TaskCompletionSource<GeneratedItemData?>().Task);
                ((Array)typeof(InfiniCraftPlayer).GetField("_multiDevJobs", CraftFields)!.GetValue(owner)!).SetValue(job, 0);
                var send = typeof(InfiniCraftPlayer).GetMethod("SendCraftCommitResult", BindingFlags.Static | BindingFlags.NonPublic)!;
                using var observer = new MonoMod.RuntimeDetour.ILHook(send, il => new MonoMod.Cil.ILCursor(il).Emit(Mono.Cecil.Cil.OpCodes.Ret));
                typeof(InfiniCraftPlayer).GetMethod("TickMultiDevCrafts", CraftFields)!.Invoke(owner, null);
                Equal(true, request.CancellationToken.IsCancellationRequested, "host deadline cancels worker immediately");
                Equal(false, owner.IsCraftLanePending(1), "host retires transient lane");
                Equal(0, player.inventory.Take(58).Count(i => !i.IsAir), "host never refunds world-owned request copies");
                var save = new TagCompound(); world.SaveWorldData(save);
                Equal(6, save.GetList<TagCompound>("infiniStationEscrowOwnersV1").Single().GetList<TagCompound>("slots").Count, "all sole material slots survive timeout");
                world.LoadWorldData(PersistenceNbtRoundtrip(save));
                Equal(true, InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.TryReplayCraft(client, requestId, out var outcome), "deadline failure durably replays");
                Equal(false, outcome.Success, "deadline never commits output");
                Equal("craft deadline exceeded", outcome.Message, "deadline keeps exact terminal reason");
            });
        }
        finally { world.ClearWorld(); Terraria.Main.netMode = mode; Terraria.Main.player = players; }
    }

    private static void CraftQolTerminalOutcomeSurvivesClear()
    {
        CombatText[] combat = Terraria.Main.combatText;
        int mode = Terraria.Main.netMode;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            WithPlayer((player, owner) =>
            {
                owner.Initialize();
                Terraria.Main.combatText = Enumerable.Range(0, 100).Select(_ => new CombatText { active = true }).ToArray();
                typeof(InfiniCraftPlayer).GetField("_request", CraftFields)!.SetValue(owner,
                    new GeneratorClient.PreparedGenerationRequest { RefundA = new Item(ItemID.Wood, 1), RefundB = new Item(ItemID.StoneBlock, 1) });
                typeof(InfiniCraftPlayer).GetMethod("FailCraft", CraftFields)!.Invoke(owner, new object[] { "exact player-facing recipe failure", "technical detail" });
                Equal(InfiniCraftPlayer.CraftLaneOutcomeKind.Failed, owner.GetCraftLaneOutcome(0).Kind, "failure survives transient clear");
                Equal("exact player-facing recipe failure", owner.GetCraftLaneOutcome(0).Message, "outcome retains actual detail");
                Equal("exact player-facing recipe failure", owner.CraftLaneStatus(0), "existing UI status writer sees retained terminal detail");
                for (int tick = 0; tick < 30 * 60; tick++) typeof(InfiniCraftPlayer).GetMethod("TickCraftLanePresentation", CraftFields)!.Invoke(owner, null);
                Equal(InfiniCraftPlayer.CraftLaneOutcomeKind.None, owner.GetCraftLaneOutcome(0).Kind, "outcome presentation is bounded");
                Equal(2, player.inventory.Take(58).Count(i => !i.IsAir), "presentation expiry does not refund again");
            });
        }
        finally { Terraria.Main.netMode = mode; Terraria.Main.combatText = combat; }
    }

    private static void CraftQolCancellationKeepsIndependentLane()
    {
        int mode = Terraria.Main.netMode;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            WithPlayer((player, owner) =>
            {
                owner.Initialize();
                var request = new GeneratorClient.PreparedGenerationRequest { RefundA = new Item(ItemID.Wood, 1), RefundB = new Item(ItemID.StoneBlock, 1) };
                Type type = typeof(InfiniCraftPlayer).GetNestedType("MultiDevCraftJob", BindingFlags.NonPublic)!;
                var requests = new[] { request, new GeneratorClient.PreparedGenerationRequest() };
                Array jobs = (Array)typeof(InfiniCraftPlayer).GetField("_multiDevJobs", CraftFields)!.GetValue(owner)!;
                for (int i = 0; i < 2; i++)
                {
                    object job = Activator.CreateInstance(type, true)!;
                    type.GetField("Request", CraftFields)!.SetValue(job, requests[i]);
                    type.GetField("LaneIndex", CraftFields)!.SetValue(job, i + 1);
                    type.GetField("Task", CraftFields)!.SetValue(job, new TaskCompletionSource<GeneratedItemData?>().Task);
                    jobs.SetValue(job, i);
                }
                Equal(true, owner.TryCancelCraftLane(1), "native cancel accepts exact lane owner");
                Equal(true, request.CancellationToken.IsCancellationRequested, "exact lane token cancelled");
                Equal(false, requests[1].CancellationToken.IsCancellationRequested, "independent lane keeps worker");
                Equal(false, owner.TryCancelCraftLane(1), "repeat cancellation cannot refund twice");
                Equal(2, player.inventory.Take(58).Count(i => !i.IsAir), "cancel refunds one exact A/B pair");
                Equal(InfiniCraftPlayer.CraftLaneOutcomeKind.Cancelled, owner.GetCraftLaneOutcome(1).Kind, "cancel outcome survives clear");
            });
        }
        finally { Terraria.Main.netMode = mode; }
    }

    private static void CraftQolIdleLaneReturnDoesNotDependOnLaneZero()
    {
        int mode = Terraria.Main.netMode; bool inventory = Terraria.Main.playerInventory;
        CombatText[] combat = Terraria.Main.combatText;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.playerInventory = false;
            WithPlayer((player, owner) =>
            {
                owner.Initialize();
                owner.InputC = new Item(ItemID.Wood, 1);
                owner.InputD = new Item(ItemID.StoneBlock, 1);
                typeof(InfiniCraftPlayer).GetField("_request", CraftFields)!.SetValue(owner, new GeneratorClient.PreparedGenerationRequest());
                typeof(InfiniCraftPlayer).GetField("_task", CraftFields)!.SetValue(owner, new TaskCompletionSource<GeneratedItemData?>().Task);
                owner.PostUpdate();
                Equal(false, owner.HasAnyInput, "closed inventory returns idle extra lane despite running lane zero");
                Equal(true, owner.HasPendingCraft, "pending lane retains exact craft owner");
                Equal(2, player.inventory.Take(58).Count(i => !i.IsAir), "idle A/B returned once");
            });
        }
        finally { Terraria.Main.netMode = mode; Terraria.Main.playerInventory = inventory; Terraria.Main.combatText = combat; }
    }

    private static void CraftQolDeadlineRetiresIncompleteWorkers()
    {
        int mode = Terraria.Main.netMode; bool inventory = Terraria.Main.playerInventory;
        CombatText[] combat = Terraria.Main.combatText;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.playerInventory = true;
            Terraria.Main.combatText = Enumerable.Range(0, 100).Select(_ => new CombatText { active = true }).ToArray();
            WithPlayer((player, owner) =>
            {
                owner.Initialize();
                var request = new GeneratorClient.PreparedGenerationRequest {
                    RefundA = new Item(ItemID.CopperShortsword, 1), RefundB = new Item(ItemID.WoodenSword, 1) };
                var held = new TaskCompletionSource<GeneratedItemData?>();
                typeof(InfiniCraftPlayer).GetField("_request", CraftFields)!.SetValue(owner, request);
                typeof(InfiniCraftPlayer).GetField("_task", CraftFields)!.SetValue(owner, held.Task);
                typeof(InfiniCraftPlayer).GetField("_totalCraftTicks", CraftFields)!.SetValue(owner, InfiniCraftPlayer.CraftRecoveryTimeoutTicks - 1);
                owner.PostUpdate();
                Equal(true, request.CancellationToken.IsCancellationRequested, "owned deadline cancels even an incomplete HTTP worker");
                Equal(false, owner.HasPendingCraft, "deadline retires result and retry consumer");
                held.SetResult(GeneratedItemData.Placeholder()); owner.PostUpdate();
                Equal(2, player.inventory.Take(58).Count(i => !i.IsAir), "late result cannot spend/refund inputs twice");
            });
        }
        finally { Terraria.Main.netMode = mode; Terraria.Main.playerInventory = inventory; Terraria.Main.combatText = combat; }
    }

    private static void CraftQolDeliveryFullPoolRetainsReadyWorker()
    {
        int mode = Terraria.Main.netMode; bool inventory = Terraria.Main.playerInventory;
        CombatText[] combat = Terraria.Main.combatText;
        Item[] items = Terraria.Main.item; int[] timers = Terraria.Main.timeItemSlotCannotBeReusedFor;
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.playerInventory = true;
            Terraria.Main.combatText = Enumerable.Range(0, 100).Select(_ => new CombatText { active = true }).ToArray();
            Terraria.Main.item = Enumerable.Range(0, Terraria.Main.maxItems + 1).Select(i => new Item(ItemID.Wood, 3) { active = true }).ToArray();
            Terraria.Main.timeItemSlotCannotBeReusedFor = new int[Terraria.Main.maxItems + 1];
            WithPlayer((player, owner) =>
            {
                owner.Initialize();
                var request = new GeneratorClient.PreparedGenerationRequest {
                    RefundA = new Item(ItemID.CopperShortsword, 1), RefundB = new Item(ItemID.WoodenSword, 1) };
                Task<GeneratedItemData?> ready = Task.FromResult<GeneratedItemData?>(GeneratedItemData.Placeholder());
                typeof(InfiniCraftPlayer).GetField("_request", CraftFields)!.SetValue(owner, request);
                typeof(InfiniCraftPlayer).GetField("_task", CraftFields)!.SetValue(owner, ready);
                for (int retry = 0; retry < 3; retry++) owner.PostUpdate();
                Equal(true, owner.HasPendingCraft, "capacity pressure retains the original craft owner");
                Equal(true, ReferenceEquals(ready, typeof(InfiniCraftPlayer).GetField("_task", CraftFields)!.GetValue(owner)), "delivery retries do not regenerate");
                Equal(0, player.inventory.Take(58).Count(i => !i.IsAir), "ready output creates no mirror refund");
                Equal(true, owner.IsCraftLaneWaitingForDelivery(0), "pure delivery-wait observation exposes ready output");
                // Retained production allocation boundary, not a fabricated successful mod spawn.
                var spawn = typeof(InfiniCraftPlayer).GetMethod("SpawnGeneratedItemServerSide", BindingFlags.Static | BindingFlags.NonPublic)!;
                int allocations = 0;
                using var observer = new MonoMod.RuntimeDetour.ILHook(spawn, il =>
                {
                    var site = il.Body.Instructions.Single(i => i.OpCode == Mono.Cecil.Cil.OpCodes.Call
                        && i.Operand is Mono.Cecil.MethodReference m && m.DeclaringType.FullName == "Terraria.Item" && m.Name == "NewItem");
                    new MonoMod.Cil.ILCursor(il) { Index = il.Body.Instructions.IndexOf(site) }.EmitDelegate<Action>(() =>
                    { allocations++; throw new InvalidOperationException("observed delivery allocation boundary"); });
                });
                owner.PostUpdate();
                Equal(0, allocations, "full pool never reaches native replacement allocator");
                Terraria.Main.item[2].active = false;
                foreach (int timer in new[] { 60, -1 })
                {
                    Terraria.Main.timeItemSlotCannotBeReusedFor[2] = timer; owner.PostUpdate();
                    Equal(0, allocations, "nonzero timer retains delivery wait without regeneration");
                }
                Terraria.Main.timeItemSlotCannotBeReusedFor[2] = 0;
                Equal(false, owner.IsCraftLaneWaitingForDelivery(0), "released exact native capacity ends capacity wait");
                // World-exit policy keeps materials under the pre-existing player-save owner.
                using var serializer = WithPersistenceBoolSerializer();
                var save = new TagCompound(); owner.SaveData(save);
                Equal(2, save.GetList<TagCompound>("infiniPendingCraftRefunds").Count, "undelivered craft saves exactly one material pair");
                owner.AbortTransientCraftForWorldExit();
                Equal(0, player.inventory.Take(58).Count(i => !i.IsAir), "saved world-exit craft does not also refund inventory");
                Equal(true, request.CancellationToken.IsCancellationRequested, "world exit retires ready consumer");
            });
        }
        finally { Terraria.Main.netMode = mode; Terraria.Main.playerInventory = inventory; Terraria.Main.combatText = combat; Terraria.Main.item = items; Terraria.Main.timeItemSlotCannotBeReusedFor = timers; }
    }

    private static void CraftQolRefundFullPoolRetainsExactSavedClaim()
    {
        int mode = Terraria.Main.netMode;
        Item[] items = Terraria.Main.item;
        int[] timers = Terraria.Main.timeItemSlotCannotBeReusedFor;
        using var serializer = WithPersistenceBoolSerializer();
        try
        {
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.item = Enumerable.Range(0, Terraria.Main.maxItems + 1)
                .Select(i => new Item(ItemID.Wood, 3) { active = i < Terraria.Main.maxItems,
                    timeSinceItemSpawned = i == 7 ? 999 : 1 }).ToArray();
            Terraria.Main.timeItemSlotCannotBeReusedFor = new int[Terraria.Main.maxItems + 1];
            Item[] before = (Item[])Terraria.Main.item.Clone();
            WithPlayer((player, owner) =>
            {
                owner.Initialize();
                for (int i = 0; i < 58; i++) player.inventory[i] = new Item(ItemID.Wood, 9999);
                owner.InputA = new Item(ItemID.CopperShortsword, 1);
                owner.InputA.prefix = PrefixID.Legendary;
                Equal(true, owner.TryClearInputToInventory(0), "retrieval transfers the sole claim");
                Equal(true, Terraria.Main.item.Select((item, i) => ReferenceEquals(item, before[i])
                    && item.stack == 3 && item.type == ItemID.Wood).All(v => v), "refund never replaces full-pool occupied drop");
                var save = new TagCompound(); owner.SaveData(save);
                for (int reload = 0; reload < 3; reload++)
                {
                    owner.LoadData(PersistenceNbtRoundtrip(save));
                    typeof(InfiniCraftPlayer).GetMethod("RestoreDeferredExitRefunds", CraftFields)!.Invoke(owner, null);
                    save = new TagCompound(); owner.SaveData(save);
                    var rows = save.GetList<TagCompound>("infiniDeferredCraftRefundsV1");
                    Equal(1, rows.Count, "full-pool native save/reload retains one unresolved local claim");
                    Item exact = ItemIO.Load(rows.Single());
                    Equal((int)ItemID.CopperShortsword, exact.type, "exact item retained");
                    Equal((byte)PrefixID.Legendary, exact.prefix, "exact prefix retained");
                    Equal(1, exact.stack, "exact stack retained");
                }
                Terraria.Main.item[2].active = false;
                foreach (int timer in new[] { 60, -1 })
                {
                    Terraria.Main.timeItemSlotCannotBeReusedFor[2] = timer;
                    typeof(InfiniCraftPlayer).GetMethod("RestoreDeferredExitRefunds", CraftFields)!.Invoke(owner, null);
                    var cooling = new TagCompound(); owner.SaveData(cooling);
                    Equal(1, cooling.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Count, "nonzero native timer retains claim");
                    Equal(true, ReferenceEquals(before[7], Terraria.Main.item[7]), "cooling retry never overwrites oldest occupied drop");
                }
                Terraria.Main.item[2].active = true;
                player.inventory[4].TurnToAir();
                typeof(InfiniCraftPlayer).GetMethod("RestoreDeferredExitRefunds", CraftFields)!.Invoke(owner, null);
                Equal((int)ItemID.CopperShortsword, player.inventory[4].type, "capacity return delivers original claim");
                Equal((byte)PrefixID.Legendary, player.inventory[4].prefix, "delivery preserves prefix");
                typeof(InfiniCraftPlayer).GetMethod("RestoreDeferredExitRefunds", CraftFields)!.Invoke(owner, null);
                var done = new TagCompound(); owner.SaveData(done);
                Equal(0, done.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Count, "delivered claim retires exactly once");
                Equal(1, player.inventory.Take(58).Count(i => i.type == ItemID.CopperShortsword), "no duplicate inventory refund");
                player.inventory[4] = new Item(ItemID.Wood, 9999);
                owner.InputA = new Item(ItemID.WoodenSword, 1); owner.InputA.prefix = PrefixID.Legendary;
                owner.TryClearInputToInventory(0);
                Terraria.Main.item[2].active = false; Terraria.Main.timeItemSlotCannotBeReusedFor[2] = 0;
                typeof(InfiniCraftPlayer).GetMethod("RestoreDeferredExitRefunds", CraftFields)!.Invoke(owner, null);
                Equal((int)ItemID.WoodenSword, Terraria.Main.item[2].type, "actual native free-slot delivery receives exact refund");
                Equal((byte)PrefixID.Legendary, Terraria.Main.item[2].prefix, "actual native free-slot delivery retains exact prefix");
                var delivered = new TagCompound(); owner.SaveData(delivered);
                Equal(0, delivered.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Count, "world delivery retires sole claim");
                Equal(true, ReferenceEquals(before[7], Terraria.Main.item[7]), "free slot retry preserves older occupied drop");
            });
        }
        finally { Terraria.Main.netMode = mode; Terraria.Main.item = items; Terraria.Main.timeItemSlotCannotBeReusedFor = timers; }
    }
}
