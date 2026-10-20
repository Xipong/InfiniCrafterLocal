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

    private static async Task CraftQolUnknownMetadataPreservesAcceptedRoutingAsync()
    {
        var generator = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Generator")!;
        object? previous = generator.GetValue(null); int mode = Terraria.Main.netMode;
        string? url = Environment.GetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL");
        await using var server = new CraftHttpFixture(0) { HoldDiscovery = true };
        var client = new GeneratorClient { Endpoint = server.Endpoint };
        try
        {
            Terraria.Main.netMode = NetmodeID.Server;
            Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", null);
            generator.SetValue(null, client);
            var source = Pb02Data("cold-http-metadata", "http");
            string before = source.ToJson();
            Task<GeneratedItemData> prepare = Task.Run(() => Pb02Prepare(source));
            var cold = await prepare.WaitAsync(TimeSpan.FromMilliseconds(250));
            Equal("http", cold.RecipeMeta.AssetTransport, "unobserved snapshot cannot assert native transport");
            Equal(source.RecipeMeta.AssetBaseUrl, cold.RecipeMeta.AssetBaseUrl, "unobserved host retains accepted validated HTTP route");
            Equal(before, source.ToJson(), "cold publication never mutates accepted definition");
            Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", "https://192.0.2.45:5055/path");
            Equal("https://192.0.2.45:5055", Pb02Prepare(source).RecipeMeta.AssetBaseUrl, "cold configured host URL overrides retained route without inventing mode");
            Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", null);
            await server.Held.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Equal(1, server.DiscoveryRequests, "cold publication queues discovery on a worker");
            var held = await Task.Run(() => Pb02Prepare(source)).WaitAsync(TimeSpan.FromMilliseconds(250));
            Equal("http", held.RecipeMeta.AssetTransport, "registry consumer never waits on held discovery lock");
            Equal(1, server.DiscoveryRequests, "pending discovery is coalesced");
            foreach (string invalid in new[] { "ftp://192.0.2.17:5055", "http://127.0.0.1:5055", "http://0.0.0.0:5055", "http://224.0.0.1:5055" })
            {
                var foreign = Pb02Data("cold-invalid-route", "http"); foreign.RecipeMeta.AssetBaseUrl = invalid;
                Equal("", Pb02Prepare(foreign).RecipeMeta.AssetBaseUrl, "unknown preserves no unsafe foreign route: " + invalid);
            }
            var coldNative = Pb02Prepare(Pb02Data("cold-native-metadata", "native"));
            Equal("native", coldNative.RecipeMeta.AssetTransport, "unknown retains accepted native transport too");
            Equal("", coldNative.RecipeMeta.AssetBaseUrl, "accepted native never acquires an HTTP route");
            server.HoldDiscovery = false; server.Release();
            await Task.Run(() => client.RefreshAssetTransportMetadata()).WaitAsync(TimeSpan.FromSeconds(5));
            var native = Pb02Prepare(source);
            Equal("native", native.RecipeMeta.AssetTransport, "actually observed native host supersedes accepted HTTP");
            Equal("", native.RecipeMeta.AssetBaseUrl, "observed native removes HTTP route");
            Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", "https://192.0.2.45:5055");
            Equal("native", Pb02Prepare(source).RecipeMeta.AssetTransport, "configured URL cannot override observed native mode");
            Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", null);
            server.DiscoveryJson = "{\"multiplayer\":{\"assetTransport\":\"http\",\"assetPublicBaseUrl\":\"http://192.0.2.44:5055/path\"}}";
            await Task.Run(() => client.RefreshAssetTransportMetadata()).WaitAsync(TimeSpan.FromSeconds(5));
            var http = Pb02Prepare(source);
            Equal("http://192.0.2.44:5055", http.RecipeMeta.AssetBaseUrl, "observed current host supersedes foreign accepted URL");
            Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", "https://192.0.2.45:5055/path");
            Equal("https://192.0.2.45:5055", Pb02Prepare(source).RecipeMeta.AssetBaseUrl, "validated configured host override wins");
            Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", null);
            server.DiscoveryStatus = 503;
            await Task.Run(() => client.RefreshAssetTransportMetadata()).WaitAsync(TimeSpan.FromSeconds(5));
            Equal("http://192.0.2.44:5055", Pb02Prepare(source).RecipeMeta.AssetBaseUrl, "failed discovery is not observed native");
            server.DiscoveryStatus = 200; server.DiscoveryJson = "{}";
            await Task.Run(() => client.RefreshAssetTransportMetadata()).WaitAsync(TimeSpan.FromSeconds(5));
            Equal("http://192.0.2.44:5055", Pb02Prepare(source).RecipeMeta.AssetBaseUrl, "missing mode is not observed native");
            using var cancelled = new System.Threading.CancellationTokenSource(); cancelled.Cancel();
            try { client.StampAssetTransportMetadata(source, true, cancelled.Token); throw new InvalidOperationException("cancel must throw"); }
            catch (OperationCanceledException) { }
            Equal(before, source.ToJson(), "cancelled snapshot projection cannot mutate accepted definition");
        }
        finally { server.Release(); generator.SetValue(null, previous); Terraria.Main.netMode = mode; Environment.SetEnvironmentVariable("INFINI_ASSET_PUBLIC_BASE_URL", url); }
    }

    private static async Task CraftQolFatalHttpRefundPresentationTracksDeliveryAsync()
    {
        using var itemPoolState = new NativeItemPoolState();
        using var serializer = WithPersistenceBoolSerializer();

        Terraria.Main.netMode = NetmodeID.SinglePlayer; Terraria.Main.playerInventory = true;
        Terraria.Main.item = Enumerable.Range(0, Terraria.Main.maxItems + 1).Select(_ => new Item(ItemID.Wood, 3) { active = true }).ToArray();
        Terraria.Main.timeItemSlotCannotBeReusedFor = new int[Terraria.Main.maxItems + 1];
        Terraria.Main.combatText = Enumerable.Range(0, 100).Select(_ => new CombatText { active = true }).ToArray();
        await using var server = new CraftHttpFixture(0) { FatalGeneration = true, FailureStatus = 424,
            FailureJson = "{\"error\":\"llm_auth_failed\",\"playerMessage\":\"Generation failed: check credentials and access before retrying.\"}" };
        var client = new GeneratorClient { Endpoint = server.Endpoint };
        foreach (bool full in new[] { true, false })
        {
            var request = new GeneratorClient.PreparedGenerationRequest { RefundA = new Item(ItemID.CopperShortsword), RefundB = new Item(ItemID.WoodenSword) };
            Equal(true, await Task.Run(() => client.GeneratePreparedBlocking(request)).WaitAsync(TimeSpan.FromSeconds(5)) is null, "real fatal HTTP rejected craft");
            Equal(424, request.FailureStatusCode, "native request owns actual HTTP 424");
            WithForgePresentationLanguages(locale => WithPlayer((player, owner) =>
            {
                owner.Initialize();
                if (full) for (int i = 0; i < 58; i++) player.inventory[i] = new Item(ItemID.Wood, 9999);
                typeof(InfiniCraftPlayer).GetField("_request", CraftFields)!.SetValue(owner, request);
                typeof(InfiniCraftPlayer).GetField("_task", CraftFields)!.SetValue(owner, Task.FromResult<GeneratedItemData?>(null));
                owner.PostUpdate();
                var save = new TagCompound(); owner.SaveData(save);
                Equal(full ? 2 : 0, save.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Count, "sole native refund owner retains exact remainders");
                Equal(full ? 0 : 2, player.inventory.Take(58).Count(i => i.type == ItemID.CopperShortsword || i.type == ItemID.WoodenSword), "actual ingredient delivery, not message inference");
                Equal("Generation failed: check credentials and access before retrying.", owner.GetCraftLaneOutcome(0).Message, "current generation detail survives without historical prose rewriting");
                Equal(true, owner.CraftLaneStatus(0).Contains(full ? (locale == "ru-RU" ? "Возврат ожидает свободного места" : "Return waiting for free space") : (locale == "ru-RU" ? "Материалы доставлены" : "Ingredients delivered")), "native terminal presentation distinguishes pending and delivered");
                if (full)
                {
                    player.inventory[0].TurnToAir(); player.inventory[1].TurnToAir(); owner.PostUpdate();
                    Equal(false, owner.HasPendingCraftRefunds, "real deferred consumer retires delivered claims");
                    Equal(false, owner.CraftLaneStatus(0).Contains(locale == "ru-RU" ? "Возврат ожидает свободного места" : "Return waiting for free space"), "presentation never freezes a stale pending claim");
                }
                owner.PostUpdate();
                Equal(2, player.inventory.Take(58).Count(i => i.type == ItemID.CopperShortsword || i.type == ItemID.WoodenSword), "later presentation creates no refund copies");
            }));
        }

    }

    private static void CraftQolPartialRefundRetainsOnlyRemainder()
    {
        using var itemPoolState = new NativeItemPoolState();
        using var serializer = WithPersistenceBoolSerializer();

        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.item = Enumerable.Range(0, Terraria.Main.maxItems + 1).Select(_ => new Item(ItemID.Wood, 3) { active = true }).ToArray();
        Terraria.Main.timeItemSlotCannotBeReusedFor = new int[Terraria.Main.maxItems + 1];
        WithPlayer((player, owner) =>
        {
            owner.Initialize();
            for (int i = 0; i < 58; i++) player.inventory[i] = new Item(ItemID.Wood, 9999);
            player.inventory[0].stack = 9997;
            owner.InputA = new Item(ItemID.Wood, 5);
            Equal(true, owner.TryClearInputToInventory(0), "public station retrieval accepts exact input");
            var save = new TagCompound(); owner.SaveData(save);
            Equal(9999, player.inventory[0].stack, "partial inventory merge is committed once");
            Equal(3, ItemIO.Load(save.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Single()).stack,
                "durable pending claim contains only undelivered remainder");
            player.inventory[1].TurnToAir();
            owner.PostUpdate();
            Equal(3, player.inventory[1].stack, "retry never recreates already delivered part");
        });

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
                    writer.Write(client); writer.Write(request); writer.Write("cancel");
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
                    Equal(true, restored.EnsureRemoteStationAuthority(), "public authority refresh accepts matching world");
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
                var request = new GeneratorClient.PreparedGenerationRequest { RefundA = new Item(ItemID.Wood, 1), RefundB = new Item(ItemID.Wood, 1) };
                CraftLane(owner, 1, ("_request", "Request", request), ("_serverRequestId", "RequestId", requestId),
                    ("_totalCraftTicks", "ElapsedTicks", InfiniCraftPlayer.CraftRecoveryTimeoutTicks - 1),
                    ("_task", "Task", new TaskCompletionSource<GeneratedItemData?>().Task));
                var send = typeof(InfiniCraftPlayer).GetMethod("SendCraftCommitResult", BindingFlags.Static | BindingFlags.NonPublic)!;
                using var observer = new MonoMod.RuntimeDetour.ILHook(send, il => new MonoMod.Cil.ILCursor(il).Emit(Mono.Cecil.Cil.OpCodes.Ret));
                owner.PostUpdate();
                Equal(true, request.CancellationToken.IsCancellationRequested, "host deadline cancels worker immediately");
                Equal(false, owner.IsCraftLanePending(1), "host retires transient lane");
                Equal(0, player.inventory.Take(58).Count(i => !i.IsAir), "host never refunds world-owned request copies");
                var save = new TagCompound(); world.SaveWorldData(save);
                Equal(6, save.GetList<TagCompound>("infiniStationEscrowOwnersV1").Single().GetList<TagCompound>("slots").Count, "all sole material slots survive timeout");
                world.LoadWorldData(PersistenceNbtRoundtrip(save));
                Equal(true, InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.TryReplayCraft(client, requestId, out var outcome), "deadline failure durably replays");
                Equal(false, outcome.Success, "deadline never commits output");
                Equal("craft deadline exceeded", outcome.Message, "deadline keeps exact terminal reason");
                WithForgePresentationLanguages(locale => Equal(true,
                    owner.CraftLaneStatus(1).Contains(locale == "ru-RU" ? "Материалы остаются в кузне хозяина" : "Ingredients remain in the host forge"),
                    "actual journal terminal path observes server retention"));
            });
        }
        finally { world.ClearWorld(); Terraria.Main.netMode = mode; Terraria.Main.player = players; }
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
                var requests = new[] { request, new GeneratorClient.PreparedGenerationRequest() };
                for (int i = 0; i < 2; i++)
                {
                    CraftLane(owner, i + 1, ("_request", "Request", requests[i]),
                        ("_task", "Task", new TaskCompletionSource<GeneratedItemData?>().Task));
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
        using var itemPoolState = new NativeItemPoolState();

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

    private static void CraftQolDeadlineRetiresIncompleteWorkers()
    {
        using var itemPoolState = new NativeItemPoolState();

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

    private static void CraftQolRefundFullPoolRetainsExactSavedClaim()
    {
        using var itemPoolState = new NativeItemPoolState();

        using var serializer = WithPersistenceBoolSerializer();
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
                owner.PostUpdate();
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
                owner.PostUpdate();
                var cooling = new TagCompound(); owner.SaveData(cooling);
                Equal(1, cooling.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Count, "nonzero native timer retains claim");
                Equal(true, ReferenceEquals(before[7], Terraria.Main.item[7]), "cooling retry never overwrites oldest occupied drop");
            }
            Terraria.Main.item[2].active = true;
            player.inventory[4].TurnToAir();
            owner.PostUpdate();
            Equal((int)ItemID.CopperShortsword, player.inventory[4].type, "capacity return delivers original claim");
            Equal((byte)PrefixID.Legendary, player.inventory[4].prefix, "delivery preserves prefix");
            owner.PostUpdate();
            var done = new TagCompound(); owner.SaveData(done);
            Equal(0, done.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Count, "delivered claim retires exactly once");
            Equal(1, player.inventory.Take(58).Count(i => i.type == ItemID.CopperShortsword), "no duplicate inventory refund");
            player.inventory[4] = new Item(ItemID.Wood, 9999);
            owner.InputA = new Item(ItemID.WoodenSword, 1); owner.InputA.prefix = PrefixID.Legendary;
            owner.TryClearInputToInventory(0);
            Terraria.Main.item[2].active = false; Terraria.Main.timeItemSlotCannotBeReusedFor[2] = 0;
            owner.PostUpdate();
            Equal((int)ItemID.WoodenSword, Terraria.Main.item[2].type, "actual native free-slot delivery receives exact refund");
            Equal((byte)PrefixID.Legendary, Terraria.Main.item[2].prefix, "actual native free-slot delivery retains exact prefix");
            Equal(2, Terraria.Main.item[2].whoAmI, "world refund retains native-allocated item identity");
            var delivered = new TagCompound(); owner.SaveData(delivered);
            Equal(0, delivered.GetList<TagCompound>("infiniDeferredCraftRefundsV1").Count, "world delivery retires sole claim");
            Equal(true, ReferenceEquals(before[7], Terraria.Main.item[7]), "free slot retry preserves older occupied drop");
        });

    }
}
