using System;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Systems;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void CancelledCraftReconnectResolvesOnlyOwnedJournal()
    {
        using var peers = new ReviewPeers(); peers.Mode(NetmodeID.Server, 255);
        var world = new GeneratedStationEscrowStateSystem();
        try
        {
            foreach (bool alreadyCompleted in new[] { false, true })
            {
                world.ClearWorld();
                using (var writer = new BinaryWriter(new MemoryStream())) world.NetSend(writer);
                string scope = GeneratedStationEscrowStateSystem.AuthorityScope;
                string token = new string('a', 32), request = new string('c', 32);
                WithPlayer((oldPlayer, oldOwner) =>
                {
                    EscrowBind(oldPlayer, oldOwner, token, 0);
                    oldOwner.InputA = new Item(ItemID.CopperShortsword, 1); oldOwner.InputB = new Item(ItemID.Wood, 1);
                    GeneratedStationEscrowStateSystem.CaptureOwnerState(token, oldOwner);
                    Equal(true, GeneratedStationEscrowStateSystem.TryBeginCraft(token, request, 0), "request before disconnect");
                    if (alreadyCompleted)
                        Equal(true, GeneratedStationEscrowStateSystem.CompleteCraft(token, request, true, "exact result", "ok"), "completion raced disconnect");
                    WithPlayer((player, owner) =>
                    {
                        owner.Initialize(); player.active = true; player.whoAmI = 7; Terraria.Main.player[7] = player;
                        int sends = 0; bool? success = null;
                        var send = typeof(InfiniCraftPlayer).GetMethod("SendCraftCommitResult", PersistenceStatic)!;
                        using var observer = new MonoMod.RuntimeDetour.ILHook(send, il => {
                            var cursor = new MonoMod.Cil.ILCursor(il);
                            cursor.Emit(Mono.Cecil.Cil.OpCodes.Ldarg_2);
                            cursor.EmitDelegate<Action<bool>>(value => { sends++; success = value; });
                            cursor.Emit(Mono.Cecil.Cil.OpCodes.Ret); // Only suppress the native socket boundary.
                        });
                        void Cancel(string requestId, string authorityScope, int version = 2)
                        {
                            using var bytes = new MemoryStream();
                            using (var writer = new BinaryWriter(bytes, System.Text.Encoding.UTF8, true)) {
                                writer.Write(version); writer.Write(authorityScope); writer.Write(token);
                                writer.Write(requestId); writer.Write("client cancel");
                            }
                            bytes.Position = 0;
                            InfiniCraftPlayer.HandleCancelServerCraftPacket(new BinaryReader(bytes), 7);
                        }
                        Cancel(request, scope);
                        Equal(0, sends, "another live session cannot steal the bearer claim");
                        Equal(false, GeneratedStationEscrowStateSystem.IsBoundOwner(token, owner), "foreign session remains unbound");
                        oldPlayer.active = false;
                        Cancel(request, new string('f', 32));
                        Equal(0, sends, "wrong world scope cannot resolve cancellation");
                        try { Cancel(request, scope, version: 1); throw new InvalidOperationException("old wire accepted"); }
                        catch (InvalidDataException) { }
                        Cancel(request, scope);
                        Equal(1, sends, "cancel alone binds replacement and returns terminal result");
                        Equal(alreadyCompleted, success, "committed success stays success; orphan becomes failure");
                        Equal(true, GeneratedStationEscrowStateSystem.IsBoundOwner(token, owner), "replacement owns exact durable escrow");
                        Equal(false, GeneratedStationEscrowStateSystem.CanCommitCraft(token, request, 0, oldOwner), "retired owner cannot commit after rebind");
                        Equal(false, GeneratedStationEscrowStateSystem.IsCraftPending(token, request), "orphan no longer blocks cancellation");
                        Equal(true, GeneratedStationEscrowStateSystem.TryReplayCraft(token, request, out var outcome), "terminal outcome remains replayable");
                        Equal(alreadyCompleted, outcome.Success, "canonical journal owns the result");
                        if (alreadyCompleted) Equal("exact result", outcome.ItemName, "cancel preserves committed item identity");
                        Equal(alreadyCompleted, owner.InputA.IsAir && owner.InputB.IsAir, "only committed result consumes materials");
                        if (!alreadyCompleted) {
                            Equal(ItemID.CopperShortsword, owner.InputA.type, "exact input A retained");
                            Equal(ItemID.Wood, owner.InputB.type, "exact input B retained");
                        }
                        Cancel(request, scope);
                        Equal(2, sends, "repeated cancellation replays the same result");
                        string unknown = new string('e', 32);
                        Cancel(unknown, scope);
                        Equal(2, sends, "unknown request creates no terminal claim");
                        Equal(false, GeneratedStationEscrowStateSystem.IsCraftPending(token, unknown), "unknown request is never admitted");
                        Equal(false, GeneratedStationEscrowStateSystem.TryReplayCraft(token, unknown, out _), "unknown request has no refund outcome");
                        Equal(0, player.inventory.Take(58).Count(i => !i.IsAir), "server cancellation never invents local refund copies");

                        // A currently owned worker must still be cancelled, not merely orphan-retired.
                        if (!alreadyCompleted)
                        {
                            string live = new string('d', 32);
                            Equal(true, GeneratedStationEscrowStateSystem.TryBeginCraft(token, live, 0), "next live craft admitted");
                            var prepared = new InfiniCrafterLocal.Common.Services.GeneratorClient.PreparedGenerationRequest();
                            typeof(InfiniCraftPlayer).GetField("_request", PersistenceInstance)!.SetValue(owner, prepared);
                            typeof(InfiniCraftPlayer).GetField("_serverRequestId", PersistenceInstance)!.SetValue(owner, live);
                            Cancel(live, scope);
                            Equal(true, prepared.CancellationToken.IsCancellationRequested, "live request worker token cancelled");
                            Equal(false, owner.HasPendingCraft, "live lane retired");
                            Equal(true, GeneratedStationEscrowStateSystem.TryReplayCraft(token, live, out var cancelled) && !cancelled.Success, "live cancel keeps canonical failure");
                        }
                    });
                });
            }
        }
        finally { world.ClearWorld(); }
    }

    private static byte[] EscrowRequest(string scope, string token, bool craft)
    {
        using var wire = new MemoryStream();
        using (var writer = new BinaryWriter(wire, System.Text.Encoding.UTF8, true))
        {
            writer.Write(craft ? InfiniNetPacketIds.RequestServerCraft : InfiniNetPacketIds.RequestStationEscrow);
            writer.Write(2); writer.Write(scope); writer.Write(token); writer.Write(new string('f', 32));
            if (craft)
            {
                writer.Write((byte)0);
                for (int i = 0; i < 2; i++)
                {
                    writer.Write((int)ItemID.CopperShortsword); writer.Write(0); writer.Write(1);
                    writer.Write(""); writer.Write("");
                }
            }
            else { writer.Write((byte)4); writer.Write((sbyte)-1); }
        }
        return wire.ToArray();
    }

    private static void EscrowBind(Player player, InfiniCraftPlayer owner, string token, int index)
    {
        owner.Initialize(); player.active = true; player.whoAmI = index; Terraria.Main.player[index] = player;
        Equal(true, GeneratedStationEscrowStateSystem.RestoreOwnerState(token, owner), "first live bearer-token admission");
        typeof(InfiniCraftPlayer).GetField("_stationEscrowClientId", PersistenceInstance)!.SetValue(owner, token);
    }

    private static void EscrowSessionTokenRotationAndConcurrentClaimRefused()
    {
        using var peers = new ReviewPeers(); peers.Mode(NetmodeID.Server, 255);
        var world = new GeneratedStationEscrowStateSystem(); world.ClearWorld();
        try
        {
            string token = new string('a', 32), rotated = new string('b', 32), request = new string('c', 32);
            var save = new TagCompound(); world.SaveWorldData(save);
            string scope = save.GetString("infiniStationEscrowAuthorityScopeV1");
            WithPlayer((player, owner) =>
            {
                EscrowBind(player, owner, token, 0);
                owner.InputA = new Item(ItemID.CopperShortsword, 1); owner.InputB = new Item(ItemID.Wood, 1);
                GeneratedStationEscrowStateSystem.CaptureOwnerState(token, owner);
                Equal(true, GeneratedStationEscrowStateSystem.TryBeginCraft(token, request, 0), "pending original craft");
                foreach (bool craftPacket in new[] { false, true })
                {
                    peers.Receive(EscrowRequest(scope, rotated, craftPacket), sender: 0);
                    Equal(token, (string)typeof(InfiniCraftPlayer).GetField("_stationEscrowClientId", PersistenceInstance)!.GetValue(owner)!, "refused request cannot replace live owner token");
                    Equal(ItemID.CopperShortsword, owner.InputA.type, "original input A retained");
                    Equal(ItemID.Wood, owner.InputB.type, "original input B retained");
                    Equal(true, GeneratedStationEscrowStateSystem.CanCommitCraft(token, request, 0, owner), "original journal remains eligible");
                }
                WithPlayer((otherPlayer, otherOwner) =>
                {
                    otherOwner.Initialize(); otherPlayer.active = true; otherPlayer.whoAmI = 1; Terraria.Main.player[1] = otherPlayer;
                    Equal(false, GeneratedStationEscrowStateSystem.RestoreOwnerState(token, otherOwner), "two live sessions cannot share one bearer claim");
                    Equal(true, otherOwner.InputA.IsAir, "refused session receives no cloned material");
                    Equal(false, GeneratedStationEscrowStateSystem.CanCommitCraft(token, request, 0, otherOwner), "foreign session cannot materialize output");
                });
                Equal(false, GeneratedStationEscrowStateSystem.CanCommitCraft(token, request, 1, owner), "wrong lane cannot commit");
                Equal(false, GeneratedStationEscrowStateSystem.CanCommitCraft(rotated, request, 0, owner), "rotated token cannot commit");
            });
        }
        finally { world.ClearWorld(); }
    }

    private static void EscrowSessionReconnectCommitAndReload()
    {
        using var serializer = WithPersistenceBoolSerializer();
        using var peers = new ReviewPeers(); peers.Mode(NetmodeID.Server, 255);
        var world = new GeneratedStationEscrowStateSystem(); world.ClearWorld();
        try
        {
            string token = new string('a', 32), request = new string('c', 32), pending = new string('d', 32);
            WithPlayer((oldPlayer, oldOwner) =>
            {
                EscrowBind(oldPlayer, oldOwner, token, 0);
                oldOwner.InputA = new Item(ItemID.CopperShortsword, 1); oldOwner.InputB = new Item(ItemID.Wood, 1);
                oldOwner.InputC = new Item(ItemID.DirtBlock, 1); oldOwner.InputD = new Item(ItemID.Torch, 1);
                GeneratedStationEscrowStateSystem.CaptureOwnerState(token, oldOwner);
                Equal(true, GeneratedStationEscrowStateSystem.TryBeginCraft(token, request, 0), "request before disconnect");
                oldPlayer.active = false;
                WithPlayer((player, owner) =>
                {
                    EscrowBind(player, owner, token, 7);
                    Equal(ItemID.CopperShortsword, owner.InputA.type, "reconnect restores exact durable inputs");
                    oldOwner.InputA.TurnToAir();
                    GeneratedStationEscrowStateSystem.CaptureOwnerState(token, oldOwner);
                    Equal(false, GeneratedStationEscrowStateSystem.CanCommitCraft(token, request, 0, oldOwner), "retired incarnation cannot commit");
                    Equal(true, GeneratedStationEscrowStateSystem.RestoreOwnerState(token, owner), "same-token retry still valid");
                    Equal(ItemID.CopperShortsword, owner.InputA.type, "stale capture cannot overwrite reconnected owner");
                    Equal(true, GeneratedStationEscrowStateSystem.CompleteCraft(token, request, true, new string('n', 140), new string('m', 550)), "durable material and outcome commit together");
                    Equal(true, GeneratedStationEscrowStateSystem.CompleteCraft(token, request, true, new string('n', 140), new string('m', 550)), "success replay idempotent");
                    Equal(false, GeneratedStationEscrowStateSystem.CanCommitCraft(token, request, 0, owner), "completed request cannot spawn again");
                    GeneratedStationEscrowStateSystem.RestoreOwnerState(token, owner);
                    Equal(true, owner.InputA.IsAir && owner.InputB.IsAir, "durable inputs consumed without a player-clone callback");
                    Equal(ItemID.DirtBlock, owner.InputC.type, "other lane C survives lane-zero commit");
                    Equal(ItemID.Torch, owner.InputD.type, "other lane D survives lane-zero commit");
                    owner.InputA = new Item(ItemID.StoneBlock, 1); owner.InputB = new Item(ItemID.Wood, 1);
                    GeneratedStationEscrowStateSystem.CaptureOwnerState(token, owner);
                    Equal(true, GeneratedStationEscrowStateSystem.TryBeginCraft(token, pending, 0), "later pending craft");
                    var save = new TagCompound(); world.SaveWorldData(save); world.LoadWorldData(PersistenceNbtRoundtrip(save));
                    Equal(true, GeneratedStationEscrowStateSystem.RestoreOwnerState(token, owner), "world reload drops transient session pins only");
                    Equal(ItemID.StoneBlock, owner.InputA.type, "restart keeps pending inputs");
                    Equal(ItemID.DirtBlock, owner.InputC.type, "other lane C survives world reload");
                    Equal(ItemID.Torch, owner.InputD.type, "other lane D survives world reload");
                    Equal(true, GeneratedStationEscrowStateSystem.TryReplayCraft(token, request, out var success) && success.Success, "committed result survives reload");
                    Equal(true, GeneratedStationEscrowStateSystem.TryReplayCraft(token, pending, out var failed) && !failed.Success, "pending restart resolves failure");
                });
            });
        }
        finally { world.ClearWorld(); }
    }

    private static void EscrowCommitRejectsFullWorldPoolBeforeAllocation()
    {
        using var itemPoolState = new NativeItemPoolState();
        using var peers = new ReviewPeers(); peers.Mode(NetmodeID.Server, 255);
        var world = new GeneratedStationEscrowStateSystem(); world.ClearWorld();

        try
        {
            Terraria.Main.item = Enumerable.Range(0, Terraria.Main.maxItems + 1).Select(_ => new Item(ItemID.Wood, 3) { active = true }).ToArray();
            Terraria.Main.item[Terraria.Main.maxItems].active = false; // Native dummy slot is never capacity.
            Terraria.Main.timeItemSlotCannotBeReusedFor = new int[Terraria.Main.maxItems + 1];
            Item[] before = (Item[])Terraria.Main.item.Clone();
            WithPlayer((player, owner) =>
            {
                string token = new string('a', 32), request = new string('c', 32);
                EscrowBind(player, owner, token, 0);
                owner.InputA = new Item(ItemID.StoneBlock, 1); owner.InputB = new Item(ItemID.Wood, 1);
                GeneratedStationEscrowStateSystem.CaptureOwnerState(token, owner);
                GeneratedStationEscrowStateSystem.TryBeginCraft(token, request, 0);
                object?[] args = { player, GeneratedItemData.Placeholder(), "", request, 0 };
                bool spawned = (bool)typeof(InfiniCraftPlayer).GetMethod("SpawnGeneratedItemServerSide", PersistenceStatic)!.Invoke(null, args)!;
                Equal(false, spawned, "full world refuses before native replacement allocation");
                Equal("world item pool is full; inputs remain in station", (string)args[2]!, "full-pool exact refusal");
                Equal(true, GeneratedStationEscrowStateSystem.CanCommitCraft(token, request, 0, owner), "allocation refusal does not consume transaction");
                Equal(ItemID.StoneBlock, owner.InputA.type, "input preserved on allocation refusal");
                Equal(true, Terraria.Main.item.Select((item, index) => ReferenceEquals(item, before[index])
                    && item.active == (index < Terraria.Main.maxItems) && item.stack == 3).All(value => value), "all existing drops and dummy slot survive unchanged");
                Terraria.Main.item[0].active = false;
                Terraria.Main.timeItemSlotCannotBeReusedFor[0] = 60;
                Equal(false, (bool)typeof(InfiniCraftPlayer).GetMethod("SpawnGeneratedItemServerSide", PersistenceStatic)!.Invoke(null, args)!, "cooling inactive slot is not reusable capacity");
                Equal("world item pool is full; inputs remain in station", (string)args[2]!, "reuse cooldown refusal");
                GeneratedStationEscrowStateSystem.CompleteCraft(token, request, false, "", "interrupted");
                Equal(false, (bool)typeof(InfiniCraftPlayer).GetMethod("SpawnGeneratedItemServerSide", PersistenceStatic)!.Invoke(null, args)!, "failed journal cannot materialize a late task result");
                Equal("server craft transaction no longer owns this session/lane", (string)args[2]!, "terminal journal refusal precedes allocation");
            });
        }
        finally {   world.ClearWorld(); }
    }
}
