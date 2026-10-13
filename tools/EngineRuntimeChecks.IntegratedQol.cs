using System;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void IntegratedQolRemoteCancelAcknowledgementUsesActualOutcome()
    {
        using var itemPoolState = new NativeItemPoolState();
        using var serializer = WithPersistenceBoolSerializer();

        var world = new InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem();
        try
        {
            Terraria.Main.netMode = NetmodeID.Server; world.ClearWorld();
            using (var writer = new System.IO.BinaryWriter(new System.IO.MemoryStream())) world.NetSend(writer);
            string scope = InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.AuthorityScope;
            Terraria.Main.netMode = NetmodeID.MultiplayerClient;
            Terraria.Main.combatText = Enumerable.Range(0, 100).Select(_ => new CombatText { active = true }).ToArray();
            foreach (int lane in new[] { 0, 1, 2 })
            foreach (bool success in new[] { false, true })
            WithPlayer((player, owner) =>
            {
                owner.Initialize(); owner.TrySetMultiDevWindowCount(3, syncServer: false);
                typeof(InfiniCraftPlayer).GetField("_stationEscrowUsesRemoteAuthority", CraftFields)!.SetValue(owner, true);
                typeof(InfiniCraftPlayer).GetField("_stationEscrowOriginScope", CraftFields)!.SetValue(owner, scope);
                string requestId = new string('c', 32);
                var request = new GeneratorClient.PreparedGenerationRequest { RefundA = new Item(ItemID.Wood), RefundB = new Item(ItemID.StoneBlock) };
                CraftLane(owner, lane, ("_request", "Request", request),
                    ("_serverRequestId", "RequestId", requestId), ("_awaitingServerCommit", "AwaitingServerCommit", true));
                Equal(true, owner.TryCancelCraftLane(lane), "cancel retains exact pending host owner");
                Equal(true, owner.IsCraftLaneCancellationPending(lane), "pure cancel pending state");
                owner.HandleCraftCommitResult(new string('d', 32), success, "Wrong", "wrong ack");
                Equal(true, owner.IsCraftLanePending(lane), "foreign ack cannot clear cancelled request");
                owner.HandleCraftCommitResult(requestId, success, "Exact committed name", "craft cancelled");
                Equal(false, owner.IsCraftLanePending(lane), "exact host acknowledgement retires pending owner");
                Equal(false, owner.IsCraftLaneCancellationPending(lane), "cancel indicator retires with owner");
                Equal(success ? InfiniCraftPlayer.CraftLaneOutcomeKind.Succeeded : InfiniCraftPlayer.CraftLaneOutcomeKind.Cancelled,
                    owner.GetCraftLaneOutcome(lane).Kind, "late committed success outranks local cancel intent");
                Equal(success, owner.StationInput(lane * 2).IsAir, "only failure acknowledgement restores slot mirror");
                Equal(0, player.inventory.Take(58).Count(i => !i.IsAir), "ack creates no client inventory refund authority");
                var save = new Terraria.ModLoader.IO.TagCompound(); owner.SaveData(save);
                Equal(0, save.GetList<Terraria.ModLoader.IO.TagCompound>("infiniPendingRemoteCrafts").Count, "resolved ack leaves no pending saved request");
                Equal(false, owner.HasPendingCraftRefunds, "ack cannot create deferred material copies");
                WithForgePresentationLanguages(locale =>
                {
                    string status = owner.CraftLaneStatus(lane);
                    Equal(!success, status.Contains(locale == "ru-RU" ? "Материалы остаются в кузне хозяина" : "Ingredients remain in the host forge"), "canonical failed host ack states retention, not inventory delivery");
                    Equal(false, status.Contains(locale == "ru-RU" ? "Материалы доставлены" : "Ingredients delivered"), "client never infers native refund delivery");
                });
                owner.HandleCraftCommitResult(requestId, !success, "Replayed", "contradictory late ack");
                Equal(success ? InfiniCraftPlayer.CraftLaneOutcomeKind.Succeeded : InfiniCraftPlayer.CraftLaneOutcomeKind.Cancelled,
                    owner.GetCraftLaneOutcome(lane).Kind, "late repeated ack cannot replace accepted outcome");
            });
        }
        finally { world.ClearWorld();   }
    }

    private static void IntegratedQolNativeProxyCapacityRecovery()
    {
        const BindingFlags statics = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
        const BindingFlags instance = BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic;
        var savedFields = new System.Collections.Generic.Dictionary<FieldInfo, object?>();
        void Capture(Type type, bool recursive = true)
        {
            if (type.ContainsGenericParameters) return;
            foreach (var field in type.GetFields(statics).Where(f => !f.IsInitOnly && !f.IsLiteral)) savedFields[field] = field.GetValue(null);
            if (recursive) foreach (var nested in type.GetNestedTypes(BindingFlags.Public | BindingFlags.NonPublic)) Capture(nested);
        }
        foreach (var type in new[] { typeof(ItemID), typeof(AmmoID), typeof(Terraria.GameContent.Prefixes.PrefixLegacy), typeof(ItemUseStyleID), typeof(Item),
                     typeof(Terraria.Main), typeof(Terraria.Lang), typeof(Terraria.GameContent.TextureAssets), typeof(Terraria.ModLoader.RecipeLoader) }) Capture(type, type == typeof(ItemID) || type == typeof(AmmoID) || type == typeof(Terraria.GameContent.Prefixes.PrefixLegacy) || type == typeof(ItemUseStyleID));
        var list = (System.Collections.Generic.IList<Terraria.ModLoader.ModItem>)typeof(Terraria.ModLoader.ItemLoader).GetField("items", statics)!.GetValue(null)!;
        var count = typeof(Terraria.ModLoader.ItemLoader).GetProperty("ItemCount")!;
        int oldCount = (int)count.GetValue(null)!; int listCount = list.Count;
        var singleton = typeof(Terraria.ModLoader.ContentInstance<InfiniCrafterLocal.Content.Items.GeneratedItem>).GetProperty("Instance")!;
        object? oldSingleton = singleton.GetValue(null);
        var registry = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("GeneratedItems")!;
        object? oldRegistry = registry.GetValue(null);
        var generator = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("Generator")!;
        object? oldGenerator = generator.GetValue(null);
        var assetProperty = typeof(global::InfiniCrafterLocal.InfiniCrafterLocalMod).GetProperty("AssetSync")!;
        object? oldAssets = assetProperty.GetValue(null);
        using var assets = new GeneratedAssetSyncService();
        string png = System.IO.Path.Combine(Terraria.Program.SavePath, "native-capacity-fixture.png");
        System.IO.File.WriteAllBytes(png, AssetOwnerCanonical);
        var factories = (System.Collections.IList)typeof(SetFactory).GetField("SetFactories", statics)!.GetValue(null)!;
        object[] oldFactories = factories.Cast<object>().ToArray();
        var world = new InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem();
        using var serializer = WithPersistenceBoolSerializer();
        int acknowledgements = 0;
        // Only the absent peer transport is intercepted. Native allocation, hydration,
        // PostUpdate, escrow transition and persistence run unchanged.
        using var ackTransport = new MonoMod.RuntimeDetour.ILHook(typeof(InfiniCraftPlayer).GetMethod("SendCraftCommitResult", statics)!, il =>
        {
            var cursor = new MonoMod.Cil.ILCursor(il);
            cursor.Emit(Mono.Cecil.Cil.OpCodes.Ldarg_2);
            cursor.EmitDelegate<Action<bool>>(success => { Equal(true, success, "only committed success acknowledged"); acknowledgements++; });
            cursor.Emit(Mono.Cecil.Cil.OpCodes.Ret);
        });
        using var vanillaTransport = new MonoMod.RuntimeDetour.ILHook(typeof(NetMessage).GetMethod("SendData", statics)!,
            il => new MonoMod.Cil.ILCursor(il).Emit(Mono.Cecil.Cil.OpCodes.Ret));
        try
        {
            var template = new InfiniCrafterLocal.Content.Items.GeneratedItem();
            var shell = new Item();
            typeof(Terraria.ModLoader.ModType<Item>).GetProperty("Entity", instance)!.SetValue(template, shell);
            typeof(Terraria.ModLoader.ModType).GetProperty("Mod")!.SetValue(template, new global::InfiniCrafterLocal.InfiniCrafterLocalMod());
            typeof(Terraria.ModLoader.ModType<Item, Terraria.ModLoader.ModItem>).GetField("_isCloneable", instance)!.SetValue(template, true);
            int proxyType = (int)typeof(Terraria.ModLoader.ItemLoader).GetMethod("Register", statics)!.Invoke(null, new object[] { template })!;
            shell.type = proxyType;
            typeof(Item).GetProperty("ModItem")!.SetValue(shell, template);
            singleton.SetValue(null, template);
            // Actual installed loader array initialization, without game/content/assets/GPU bootstrap.
            factories.Clear();
            typeof(Terraria.ModLoader.ItemLoader).GetMethod("ResizeArrays", statics)!.Invoke(null, new object[] { true });
            Equal(proxyType, Terraria.ModLoader.ModContent.ItemType<InfiniCrafterLocal.Content.Items.GeneratedItem>(), "native registered template type");
            foreach (var assembly in new[] { typeof(InfiniCraftPlayer).Assembly, typeof(Item).Assembly })
                Console.WriteLine("LOADED " + assembly.Location + " SHA256=" + Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.IO.File.ReadAllBytes(assembly.Location))).ToLowerInvariant());
            var control = new Item(proxyType);
            Equal(true, control.ModItem is InfiniCrafterLocal.Content.Items.GeneratedItem, "native SetDefaults constructs actual proxy");
            registry.SetValue(null, null); generator.SetValue(null, new GeneratorClient()); assetProperty.SetValue(null, assets);
            foreach (int mode in new[] { NetmodeID.SinglePlayer, NetmodeID.Server })
            foreach (int lane in new[] { 0, 1, 2 })
            {
                Terraria.Main.netMode = mode; world.ClearWorld();
                Terraria.Main.player = Enumerable.Range(0, Terraria.Main.maxPlayers).Select(_ => new Player()).ToArray();
                Terraria.Main.playerInventory = true;
                Terraria.Main.combatText = Enumerable.Range(0, 100).Select(_ => new CombatText { active = true }).ToArray();
                Terraria.Main.item = Enumerable.Range(0, Terraria.Main.maxItems + 1).Select(_ => new Item(ItemID.Wood, 3) { active = true }).ToArray();
                Terraria.Main.timeItemSlotCannotBeReusedFor = new int[Terraria.Main.maxItems + 1];
                WithPlayer((player, owner) =>
                {
                    owner.Initialize(); player.active = true; player.whoAmI = 3; Terraria.Main.player[3] = player;
                    owner.TrySetMultiDevWindowCount(3, syncServer: false);
                    string client = new string('a', 32), requestId = new string('b', 32);
                    typeof(InfiniCraftPlayer).GetField("_stationEscrowClientId", CraftFields)!.SetValue(owner, client);
                    if (mode == NetmodeID.Server)
                    {
                        Equal(true, InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.RestoreOwnerState(client, owner), "actual journal binds live owner");
                        owner.RestoreServerStationEscrowSlots(Enumerable.Range(0, 6).Select(_ => new Item(ItemID.Wood)).ToArray());
                        InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.CaptureOwnerState(client, owner);
                        Equal(true, InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.TryBeginCraft(client, requestId, lane), "actual journal owns exact lane");
                    }
                    var data = AssetOwnerData("capacity-recovery-" + mode + "-" + lane, png); data.Name = "Exact capacity output";
                    data.Gameplay.Damage = 17; data.RuntimeProgram.ItemUse.Configured = true;
                    Equal(true, GeneratedItemData.FromJson(data.ToNetworkJson()) is not null, "strict completed result with actual fixture PNG admitted");
                    Equal(true, assets.HasCompleteServerAssetRoster(data), "real integrated asset roster admits exact PNG");
                    var request = new GeneratorClient.PreparedGenerationRequest { RefundA = new Item(ItemID.CopperShortsword), RefundB = new Item(ItemID.WoodenSword) };
                    Task<GeneratedItemData?> ready = Task.FromResult<GeneratedItemData?>(data);
                    int timeout = (int)typeof(InfiniCraftPlayer).GetField("CraftRecoveryTimeoutTicks", statics)!.GetRawConstantValue()!;
                    CraftLane(owner, lane, ("_request", "Request", request), ("_task", "Task", ready),
                        ("_totalCraftTicks", "ElapsedTicks", timeout + 10),
                        ("_serverRequestId", "RequestId", mode == NetmodeID.Server ? requestId : ""));
                    if (lane == 0) typeof(InfiniCraftPlayer).GetField("_elapsedTicks", CraftFields)!.SetValue(owner, InfiniCraftPlayer.CraftDurationTicks);
                    Item occupied = Terraria.Main.item[7]; int allocatedBefore = Item.numberOfNewItems;
                    for (int tick = 0; tick < 3; tick++) owner.PostUpdate();
                    Equal(true, owner.IsCraftLanePending(lane), "completed result survives 20-minute deadline while full");
                    Equal(false, request.CancellationToken.IsCancellationRequested, "full pool preserves ready request");
                    object? retainedTask = lane == 0 ? typeof(InfiniCraftPlayer).GetField("_task", CraftFields)!.GetValue(owner)
                        : ((Array)typeof(InfiniCraftPlayer).GetField("_multiDevJobs", CraftFields)!.GetValue(owner)!).GetValue(lane - 1)!.GetType().GetField("Task")!
                            .GetValue(((Array)typeof(InfiniCraftPlayer).GetField("_multiDevJobs", CraftFields)!.GetValue(owner)!).GetValue(lane - 1));
                    Equal(true, ReferenceEquals(ready, retainedTask), "capacity wait never replaces original generation result");
                    Equal(allocatedBefore, Item.numberOfNewItems, "no allocation/regeneration during pressure");
                    Terraria.Main.item[2].active = false;
                    foreach (int timer in new[] { 60, -1 }) { Terraria.Main.timeItemSlotCannotBeReusedFor[2] = timer; owner.PostUpdate(); }
                    Equal(true, owner.IsCraftLanePending(lane), "cooling and negative timers keep exact owner");
                    Terraria.Main.timeItemSlotCannotBeReusedFor[2] = 0; owner.PostUpdate();
                    Equal(false, owner.IsCraftLanePending(lane), "capacity release commits actual proxy then retires consumer; outcome=" + owner.GetCraftLaneOutcome(lane));
                    Equal(InfiniCraftPlayer.CraftLaneOutcomeKind.Succeeded, owner.GetCraftLaneOutcome(lane).Kind, "native delivery succeeds");
                    Item output = Terraria.Main.item[2];
                    Equal(true, output.active && output.ModItem is InfiniCrafterLocal.Content.Items.GeneratedItem, "actual native allocator published proxy");
                    Equal(data.Id, ((InfiniCrafterLocal.Content.Items.GeneratedItem)output.ModItem!).Data.Id, "SetData retains exact completed definition");
                    Equal(17, output.damage, "actual native proxy projects completed gameplay");
                    Equal(png, ((InfiniCrafterLocal.Content.Items.GeneratedItem)output.ModItem!).Data.Visual.SpritePath, "actual native proxy retains exact PNG selector");
                    Equal(allocatedBefore + 1, Item.numberOfNewItems, "exactly one native allocation");
                    for (int tick = 0; tick < 3; tick++) owner.PostUpdate();
                    Equal(allocatedBefore + 1, Item.numberOfNewItems, "no late output allocation");
                    Equal(0, player.inventory.Take(58).Count(i => !i.IsAir), "success produces zero material refunds");
                    Equal(false, owner.HasPendingCraftRefunds, "success creates no pending refund claim");
                    Equal(true, ReferenceEquals(occupied, Terraria.Main.item[7]) && occupied.stack == 3, "old occupied drop never replaced");
                    if (mode == NetmodeID.Server)
                    {
                        Equal(true, InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.TryReplayCraft(client, requestId, out var outcome), "journal durably owns success");
                        Equal(true, outcome.Success, "journal success, not refund");
                        var save = new Terraria.ModLoader.IO.TagCompound(); world.SaveWorldData(save);
                        var savedOwner = save.GetList<Terraria.ModLoader.IO.TagCompound>("infiniStationEscrowOwnersV1").Single();
                        Equal(client, savedOwner.GetString("clientId"), "saved exact material owner");
                        var remaining = savedOwner.GetList<Terraria.ModLoader.IO.TagCompound>("slots");
                        Equal(4, remaining.Count, "success spends only exact lane pair");
                        foreach (var row in remaining)
                        {
                            Equal(false, row.GetInt("index") / 2 == lane, "committed lane has no saved refund copy");
                            Equal(1, Terraria.ModLoader.IO.ItemIO.Load(row.GetCompound("item")).stack, "unrelated saved escrow remains one exact unit");
                        }
                        var roundtrip = PersistenceNbtRoundtrip(save); owner.AbortTransientCraftForWorldExit(); world.ClearWorld(); world.LoadWorldData(roundtrip);
                        Equal(true, InfiniCrafterLocal.Common.Systems.GeneratedStationEscrowStateSystem.TryReplayCraft(client, requestId, out var after) && after.Success, "native save/unload/reload keeps exact committed success");
                    }
                    if (mode == NetmodeID.Server) Equal(lane + 1, acknowledgements, "one exact host acknowledgement per committed lane");
                    Console.WriteLine($"OBSERVED native proxy recovery mode={mode} lane={lane} type={output.type} id={data.Id} allocations=1 refunds=0");
                });
            }
        }
        finally
        {
            world.ClearWorld(); registry.SetValue(null, oldRegistry); generator.SetValue(null, oldGenerator); assetProperty.SetValue(null, oldAssets); singleton.SetValue(null, oldSingleton);
            while (list.Count > listCount) list.RemoveAt(list.Count - 1); count.SetValue(null, oldCount);
            foreach (var pair in savedFields) pair.Key.SetValue(null, pair.Value);
            factories.Clear(); foreach (var factory in oldFactories) factories.Add(factory);
        }
    }

    private static void IntegratedQolStationRefundCapacityRecovery()
    {
        using var itemPoolState = new NativeItemPoolState();
        using var serializer = WithPersistenceBoolSerializer();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.playerInventory = true;
        Terraria.Main.item = Enumerable.Range(0, Terraria.Main.maxItems + 1)
            .Select(_ => new Item(ItemID.Wood) { active = true }).ToArray();
        Terraria.Main.timeItemSlotCannotBeReusedFor = new int[Terraria.Main.maxItems + 1];
        WithPlayer((player, owner) =>
        {
            owner.Initialize();
            owner.TrySetMultiDevWindowCount(3, syncServer: false);
            for (int slot = 0; slot < 58; slot++) player.inventory[slot] = new Item(ItemID.Wood, 9999);
            int[] materials = { ItemID.CopperShortsword, ItemID.WoodenSword, ItemID.IronBroadsword };
            owner.InputA = new Item(materials[0]);
            owner.InputC = new Item(materials[1]);
            owner.InputE = new Item(materials[2]);
            for (int lane = 0; lane < materials.Length; lane++)
            {
                Equal(true, owner.TryClearInputToInventory(lane * 2), "public retrieval accepts each idle lane");
                Equal(false, owner.TryClearInputToInventory(lane * 2), "empty input cannot refund again");
            }
            Equal(false, owner.HasAnyInput, "retrieval transfers all three sole input owners");
            Equal(true, owner.HasStationState && owner.HasPendingCraftRefunds, "pending refunds keep station visible");
            var save = new Terraria.ModLoader.IO.TagCompound(); owner.SaveData(save);
            Equal(materials.Length, save.GetList<Terraria.ModLoader.IO.TagCompound>("infiniDeferredCraftRefundsV1").Count,
                "each undelivered input has one durable claim");
            for (int slot = 0; slot < materials.Length; slot++) player.inventory[slot].TurnToAir();
            owner.PostUpdate();
            Equal(false, owner.HasPendingCraftRefunds, "native lifecycle delivers when inventory capacity returns");
            Equal(false, owner.HasStationState, "empty station no longer requires refund visibility");
            owner.PostUpdate();
            foreach (int material in materials)
                Equal(1, player.inventory.Take(58).Where(item => item.type == material).Sum(item => item.stack),
                    "retry preserves exactly one unit of each original input");
        });
    }

}
