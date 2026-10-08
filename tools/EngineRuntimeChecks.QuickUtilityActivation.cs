using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Items;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    // Baseline-compilable: no static dependency on candidate symbols/constants.
    private const byte QuickUtilityPacket = 25;
    private static void QuickUtilityClear()
        => typeof(GeneratedItem).Assembly.GetType("InfiniCrafterLocal.Common.Runtime.GeneratedQuickUtilityActivation")?
            .GetMethod("Clear", BindingFlags.Static | BindingFlags.NonPublic)?.Invoke(null, null);
    private sealed class QuickUtilityRecipeBoundary : Exception { }
    private sealed class QuickUtilityPeers : IDisposable
    {
        internal readonly MobilityConsumptionNativeScope Native = new();
        private readonly LiteralCostStaticScope StaticCost = new();
        internal readonly ReviewPeers Peers = new();
        internal readonly GeneratedQuickUseSystem Bridge = new();
        internal readonly GeneratedItemData Data;
        internal readonly Player Owner, Server, Remote;
        internal readonly InfiniCraftPlayer OwnerBuff, ServerBuff, RemoteBuff;
        internal readonly MobilityConsumptionProbeItem OwnerItem, ServerItem;
        internal readonly List<IDisposable> Stops = new();
        private readonly PropertyInfo content = typeof(ContentInstance<InfiniCraftPlayer>).GetProperty("Instance")!;
        private readonly object? previousContent;
        private readonly byte kind;
        private int boundaries;
        internal int EquipmentSends, EquipmentSlot = -1;
        internal readonly List<int> EquipmentSlots = new();
        internal bool ApplyEquipmentSync;
        internal QuickUtilityPeers(byte quickKind = 1, int cost = 1, int stack = 3, bool initialSync = true, bool voidBag = false)
        {
            previousContent = content.GetValue(null); kind = quickKind; QuickUtilityClear();
            Data = LiteralCostData("none", cost, 1 - cost);
            Data.Id = "quick-utility-251";
            Data.Gameplay.HealLife = kind == 1 ? 7 : 0;
            Data.Gameplay.HealMana = kind == 2 ? 5 : 0;
            Data.Gameplay.Potion = true;
            Data.Gameplay.GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 120,
                JumpBoost = 1.5f, EmitLightStrength = .5f, LightColorName = "white" };
            Data = GeneratedItemData.FromJson(Data.ToNetworkJson())!;
            Peers.Register(Data);
            (Owner, OwnerBuff) = PlayerPair(); (Server, ServerBuff) = PlayerPair(); (Remote, RemoteBuff) = PlayerPair();
            OwnerItem = MobilityConsumptionHost(Data); OwnerItem.Item.stack = stack;
            ServerItem = MobilityConsumptionHost(Data); ServerItem.Item.stack = stack;
            OwnerItem.SetStaticDefaults(); ServerItem.SetStaticDefaults();
            Owner.inventory[0] = OwnerItem.Item; Server.inventory[0] = ServerItem.Item;
            if (voidBag)
            {
                Owner.inventory[0] = new Item(); Server.inventory[0] = new Item();
                Owner.inventory[1] = new Item(ItemID.VoidLens); Server.inventory[1] = new Item(ItemID.VoidLens);
                Owner.bank4.item[0] = OwnerItem.Item; Server.bank4.item[0] = ServerItem.Item;
                Equal(true, Owner.useVoidBag(), "native owner open Void Bag consumer is enabled");
            }
            // Actual generated compact writer -> actual decoder, not reflected token injection.
            if (initialSync) CopyEquipment();
            Stops.Add(PersistenceObserveNetworkSend((message, slot) => {
                if (message != MessageID.SyncEquipment) return;
                EquipmentSends++; EquipmentSlot = slot; EquipmentSlots.Add(slot);
                Equal(stack, OwnerItem.Item.stack, "native equipment witness is sent before stack debit");
                Equal(57, Owner.statLife, "native equipment witness precedes life heal");
                Equal(20, Owner.statMana, "native equipment witness precedes mana heal");
                if (ApplyEquipmentSync)
                {
                    if (slot < 58 && voidBag)
                        Server.inventory[slot] = Owner.inventory[slot].Clone(); // ordinary vanilla bag sync fixture
                    else CopyEquipment(); // socket boundary interception, real generated compact writer/decoder
                }
            }));
            foreach (string name in new[] { nameof(Player.QuickHeal), nameof(Player.QuickMana) })
            {
                Stops.Add(new ILHook(typeof(Player).GetMethod(name, Type.EmptyTypes)!, il => {
                    var c = new ILCursor(il);
                    if (!c.TryGotoNext(MoveType.AfterLabel, i => i.MatchCall<Recipe>(nameof(Recipe.FindRecipes))))
                        throw new InvalidOperationException("quick post-consumption boundary missing: " + name);
                    c.EmitDelegate<Action>(() => { boundaries++; throw new QuickUtilityRecipeBoundary(); });
                }));
            }
            Bridge.Load();
            Mode(1); Peers.Sent.Clear();
        }
        private void CopyEquipment()
        {
            using var wire = new MemoryStream();
            OwnerItem.NetSend(new BinaryWriter(wire)); wire.Position = 0;
            ServerItem.NetReceive(new BinaryReader(wire));
        }
        private static (Player, InfiniCraftPlayer) PlayerPair()
        {
            var p = new Player(); var mp = new InfiniCraftPlayer(); PrepareMobilityConsumptionPlayer(p);
            p.itemAnimation = p.itemAnimationMax = p.itemTime = p.itemTimeMax = 0;
            typeof(ModType<Player>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(mp, p);
            typeof(Player).GetField("modPlayers", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(p, new ModPlayer[] { mp });
            return (p, mp);
        }
        internal void Mode(int role)
        {
            Peers.Mode(role == 2 ? NetmodeID.Server : NetmodeID.MultiplayerClient, role == 2 ? 255 : role == 3 ? 2 : 1);
            (Player p, InfiniCraftPlayer mp) = role == 2 ? (Server, ServerBuff) : role == 3 ? (Remote, RemoteBuff) : (Owner, OwnerBuff);
            Terraria.Main.player[1] = p; content.SetValue(null, mp);
        }
        internal void Quick()
        {
            Mode(1); int before = boundaries;
            // Independent repeated-use fixture: reset the real native potion-sickness
            // arrays as well as potionDelay (no loader hook roster exists in this seam).
            Array.Clear(Owner.buffType); Array.Clear(Owner.buffTime);
            try { if (kind == 1) Owner.QuickHeal(); else Owner.QuickMana(); }
            catch (QuickUtilityRecipeBoundary) { }
            Equal(before + 1, boundaries, "actual quick-use crossed native heal/consume tail once");
        }
        internal byte[] Take(byte op)
        {
            byte[][] packets = Peers.Sent.Where(p => p.Length > 2 && p[0] == QuickUtilityPacket && p[2] == op).ToArray();
            Equal(1, packets.Length, "exact one quick utility packet op=" + op);
            Peers.Sent.Clear(); return packets[0];
        }
        internal byte[] Prepare() { Quick(); return Take(1); }
        internal byte[] Ready(byte[] prepare) { Mode(2); Peers.Receive(prepare, 1); return Take(2); }
        internal byte[] Commit(byte[] ready) { Mode(1); Peers.Receive(ready, 256); return Take(3); }
        internal void ReceiveServer(byte[] packet, int sender = 1) { Mode(2); Peers.Sent.Clear(); Peers.Receive(packet, sender); }
        internal int Ticks(InfiniCraftPlayer mp) => (int)typeof(InfiniCraftPlayer).GetField("_generatedBuffTicks", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(mp)!;
        public void Dispose()
        {
            Bridge.Unload(); for (int i = Stops.Count - 1; i >= 0; i--) Stops[i].Dispose();
            content.SetValue(null, previousContent); QuickUtilityClear(); Peers.Dispose(); StaticCost.Dispose(); Native.Dispose();
        }
    }

    private static void RT02NativeQuickUtilityOpenedVoidPrerequisite()
    {
        foreach (byte kind in new byte[] { 1, 2 })
        foreach (bool serverClosed in new[] { false, true })
        {
            using var f = new QuickUtilityPeers(kind, stack: 1, initialSync: false, voidBag: true);
            f.Server.inventory[1] = serverClosed ? new Item(ItemID.ClosedVoidBag) : new Item();
            Equal(false, f.Server.useVoidBag(), "server has not yet observed owner opening bag");
            f.ApplyEquipmentSync = true;
            byte[] prepare = f.Prepare();
            Equal(true, f.Server.useVoidBag(), "native bag prerequisite synchronization reaches server before Prepare");
            Equal("1,220", string.Join(",", f.EquipmentSlots), "exact open bag then bank4 native slot order");
            Equal(kind == 1 ? 64 : 57, f.Owner.statLife, "stale bag native heal once");
            Equal(kind == 2 ? 25 : 20, f.Owner.statMana, "stale bag native mana once");
            Equal(0, f.OwnerItem.Item.stack, "stale bag final stack native debit once");
            byte[] ready = f.Ready(prepare), commit = f.Commit(ready);
            f.ServerItem.Item.TurnToAir();
            f.ReceiveServer(commit);
            Equal(120, f.Ticks(f.ServerBuff), "valid opened-void activation reaches canonical utility");
            Equal(0, f.ServerItem.UseCalls, "bag sync never replays server native use");
        }
    }

    private static void RT02NativeQuickUtilityFreshInventoryAndVoidWitness()
    {
        foreach (byte kind in new byte[] { 1, 2 })
        foreach (bool voidBag in new[] { false, true })
        {
            using var f = new QuickUtilityPeers(kind, stack: 1, initialSync: false, voidBag: voidBag);
            f.ApplyEquipmentSync = true;
            byte[] prepare = f.Prepare();
            Equal(voidBag ? 2 : 1, f.EquipmentSends, "fresh quick use publishes prerequisite and selected native equipment witnesses");
            Equal(voidBag ? PlayerItemSlotID.Bank4_0 : PlayerItemSlotID.Inventory0,
                f.EquipmentSlot, "native inventory/void slot mapping is exact");
            Equal(0, f.OwnerItem.Item.stack, "fresh final stack consumed natively once");
            byte[] ready = f.Ready(prepare), commit = f.Commit(ready);
            f.ServerItem.Item.TurnToAir();
            f.ReceiveServer(commit);
            Equal(120, f.Ticks(f.ServerBuff), "fresh unsynced inventory and open Void Bag activation reaches authority");
            Equal(0, f.ServerItem.UseCalls, "fresh synchronization does not execute server native use");
        }
    }

    private static void RT02NativeQuickUtilityWriterServerRemote()
    {
        foreach (byte kind in new byte[] { 1, 2 })
        foreach (int cost in new[] { 0, 1 })
        foreach (int stack in new[] { 1, 3 })
        foreach (int selector in new[] { 0, 2 })
        {
            using var f = new QuickUtilityPeers(kind, cost, stack); f.Owner.altFunctionUse = selector;
            byte[] prepare = f.Prepare();
            Equal(kind == 1 ? 64 : 57, f.Owner.statLife, "native HP exactly once");
            Equal(kind == 2 ? 25 : 20, f.Owner.statMana, "native mana exactly once");
            Equal(stack - cost, f.OwnerItem.Item.stack, "native stack cost exactly once");
            Equal(1, f.OwnerItem.UseCalls, "owner production UseItem once");
            Equal(0, f.Owner.itemAnimation, "quick use never created manual animation");
            Equal(120, f.Ticks(f.OwnerBuff), "prediction uses authored utility");
            byte[] ready = f.Ready(prepare);
            Equal(0, f.Ticks(f.ServerBuff), "prepare never executes utility");
            byte[] commit = f.Commit(ready);
            // Model native inventory sync arriving before Commit, including TurnToAir.
            f.ServerItem.Item.stack = f.OwnerItem.Item.stack;
            if (f.ServerItem.Item.stack == 0) f.ServerItem.Item.TurnToAir();
            f.ReceiveServer(commit);
            Equal(120, f.Ticks(f.ServerBuff), "canonical utility reaches authoritative server");
            Equal(57, f.Server.statLife, "bridge never heals server again");
            Equal(20, f.Server.statMana, "bridge never restores server mana again");
            Equal(stack - cost, f.ServerItem.Item.stack, "bridge never charges stack again");
            Equal(0, f.ServerItem.UseCalls, "bridge never replays UseItem/spawn/VFX");
            byte[] snapshot = f.Peers.Sent.Single(p => p[0] == InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedUtilityBuff);
            f.Mode(3); f.Peers.Receive(snapshot, 256); Equal(120, f.Ticks(f.RemoteBuff), "real remote decoder retains entries");
            f.Mode(1); f.Peers.Receive(snapshot, 256); f.Owner.jumpSpeedBoost = 0;
            f.OwnerBuff.PostUpdateEquips(); Equal(1.5f, f.Owner.jumpSpeedBoost, "authoritative owner snapshot not a second contribution");
            // An exact replay after countdown must not refresh the utility duration.
            f.Mode(2); typeof(InfiniCraftPlayer).GetMethod("TickGeneratedUtilityBuff", BindingFlags.Instance | BindingFlags.NonPublic)!.Invoke(f.ServerBuff, null); int before = f.Ticks(f.ServerBuff);
            f.ReceiveServer(commit); Equal(before, f.Ticks(f.ServerBuff), "commit replay cannot refresh");
            Equal(0, f.Peers.Sent.Count, "commit replay sends no snapshot");
            f.ReceiveServer(prepare); Equal(0, f.Peers.Sent.Count, "prepare replay cannot issue another ticket");
        }
    }

    private static void RT02NativeQuickUtilityManualAndSnapshotControls()
    {
        using var f = new QuickUtilityPeers();
        // Manual native generic-use path is already reachable on the server.
        f.Mode(2); f.Server.itemAnimation = f.Server.itemAnimationMax = 20;
        Equal(true, f.ServerItem.CanUseItem(f.Server), "manual server admission");
        f.Native.RunNativeSuffix(f.Server);
        Equal(120, f.Ticks(f.ServerBuff), "manual server utility retained");
        Equal(1, f.ServerItem.UseCalls, "manual actual UseItem once");
        Equal(64, f.Server.statLife, "manual native heal once");
        Equal(3, f.ServerItem.Item.stack, "manual server retains owner-only native consumption boundary");
        Equal(0, f.Peers.Sent.Count(p => p[0] == QuickUtilityPacket), "manual server must not claim quick activation");
        f.Mode(1); f.Peers.Sent.Clear(); f.Owner.itemAnimation = f.Owner.itemAnimationMax = 20;
        Equal(true, f.OwnerItem.CanUseItem(f.Owner), "manual owner admission");
        f.Native.RunNativeSuffix(f.Owner);
        Equal(0, f.Peers.Sent.Count(p => p[0] == QuickUtilityPacket), "manual owner must not duplicate server utility activation");
        // Arbitrary predicted snapshots still cannot grant client stat magnitudes.
        var old = new InfiniCraftPlayer(); f.OwnerBuff.CopyClientState(old);
        f.OwnerBuff.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 21600, JumpBoost = 8 });
        f.OwnerBuff.SendClientChanges(old);
        byte[] forged = f.Peers.Sent.Single(p => p[0] == InfiniCrafterLocal.Common.InfiniNetPacketIds.SyncGeneratedUtilityBuff);
        f.Mode(2); f.Peers.Sent.Clear(); f.Peers.Receive(forged, 1);
        f.Server.jumpSpeedBoost = 0; f.ServerBuff.PostUpdateEquips(); Equal(1.5f, f.Server.jumpSpeedBoost, "client snapshot never authoritative");
        // Candidate selectors are read-only and cannot manufacture a receipt.
        f.Mode(1); f.Peers.Sent.Clear(); f.Owner.potionDelay = 0; f.Owner.statLife = 57;
        f.Owner.QuickHeal_GetItemToUse(); Equal(0, f.Peers.Sent.Count, "selector-only scan no activation");
    }

    private static void RT02NativeQuickUtilityLifetimeAndCapacity()
    {
        foreach (int age in new[] { 180, 181 })
        {
            using var f = new QuickUtilityPeers(); f.Data.Gameplay.GeneratedBuff.DurationTicks = 360;
            MaterialClock(uint.MaxValue - 50UL); byte[] claim = f.Prepare();
            byte[] ready = f.Ready(claim), commit = f.Commit(ready);
            MaterialClock(unchecked((uint)(uint.MaxValue - 50UL + (ulong)age)));
            f.ReceiveServer(commit); Equal(age == 180 ? 180 : 0, f.Ticks(f.ServerBuff), "server ticket exact age/wrap fence and elapsed canonical duration " + age);
        }
        using (var f = new QuickUtilityPeers())
        {
            byte[] ready = f.Ready(f.Prepare()), commit = f.Commit(ready);
            MaterialClock(Terraria.Main.GameUpdateCount + 120); f.ReceiveServer(commit);
            Equal(0, f.Ticks(f.ServerBuff), "live ticket never resurrects expired canonical effect");
        }
        using (var f = new QuickUtilityPeers(cost: 0))
        {
            byte[] first = Array.Empty<byte>();
            for (int i = 0; i < 8; i++)
            {
                f.Mode(1); f.Owner.statLife = 57; f.Owner.potionDelay = 0;
                byte[] claim = f.Prepare(); if (i == 0) first = claim;
                f.Ready(claim); // intentionally withhold Ready delivery / Commit
            }
            f.Mode(1); f.Owner.statLife = 57; f.Owner.potionDelay = 0; f.Quick();
            Equal(0, f.Peers.Sent.Count(p => p[0] == QuickUtilityPacket), "capacity refusal creates no ninth ticket");
            Equal(64, f.Owner.statLife, "capacity refusal never blocks native healing");
            Equal(3, f.OwnerItem.Item.stack, "capacity refusal preserves literal zero cost");
            MaterialClock(Terraria.Main.GameUpdateCount + 181);
            f.ReceiveServer(first); Equal(0, f.Peers.Sent.Count, "expired cursor still blocks an old prepare");
            f.Mode(1); f.Owner.statLife = 57; f.Owner.potionDelay = 0;
            byte[] fresh = f.Prepare(); byte[] ready = f.Ready(fresh); byte[] commit = f.Commit(ready);
            f.ReceiveServer(commit); Equal(120, f.Ticks(f.ServerBuff), "expired pending reclamation retains new occurrence progress");
        }
    }

    private static byte[] QuickUtilityMutate(byte[] packet, string field)
    {
        byte[] bytes = (byte[])packet.Clone();
        if (field == "owner") bytes[3] = 2;
        else if (field == "kind") bytes[4] = 9;
        else if (field == "slot") bytes[5] = 1;
        else if (field == "token") bytes[6] ^= 0x40;
        else if (field == "version") bytes[1] = 99;
        else if (field == "ticket") bytes[^1] ^= 0x40;
        else if (field == "truncated") Array.Resize(ref bytes, 10);
        else
        {
            // Skip fixed header and exact byte-count identities; never guess UTF8 chars.
            int pos = 22, itemBytes = bytes[pos++]; pos += itemBytes;
            int hashBytes = bytes[pos++];
            if (field == "definition") bytes[pos] = bytes[pos] == (byte)'a' ? (byte)'b' : (byte)'a';
            else if (field == "binding") { pos += hashBytes; int bindingBytes = bytes[pos++]; bytes[pos] ^= 1; }
            else throw new ArgumentException(field);
        }
        return bytes;
    }

    private static void RT02NativeQuickUtilityAuthorityFences()
    {
        foreach (string field in new[] { "owner", "kind", "slot", "token", "version", "definition", "binding", "truncated", "wrong-sender", "server-item-replaced" })
        {
            using var f = new QuickUtilityPeers(); byte[] claim = f.Prepare();
            if (field == "server-item-replaced") f.Server.inventory[0] = MobilityConsumptionHost(f.Data).Item;
            else if (field != "wrong-sender") claim = QuickUtilityMutate(claim, field);
            f.ReceiveServer(claim, field == "wrong-sender" ? 2 : 1);
            Equal(0, f.Ticks(f.ServerBuff), field + " no authoritative effect");
            Equal(0, f.Peers.Sent.Count, field + " no ticket");
        }
        foreach (string fence in new[] { "expired", "wrong-ticket", "wrong-sender", "definition-after-ready", "binding-after-ready", "owner-replaced", "death", "death-then-respawn-replay", "unload", "ready-wrong-sender", "ready-replay", "ready-expired" })
        {
            using var f = new QuickUtilityPeers(); byte[] claim = f.Prepare(), ready = f.Ready(claim);
            if (fence == "ready-expired")
            {
                MaterialClock(Terraria.Main.GameUpdateCount + 181); f.Mode(1); f.Peers.Receive(ready, 256);
                Equal(0, f.Peers.Sent.Count, "late Ready cannot revive native activation"); continue;
            }
            if (fence == "ready-wrong-sender")
            {
                f.Mode(1); f.Peers.Receive(ready, 2); Equal(0, f.Peers.Sent.Count, "foreign Ready ignored"); continue;
            }
            byte[] commit = f.Commit(ready);
            if (fence == "ready-replay")
            {
                f.Mode(1); f.Peers.Receive(ready, 256); Equal(0, f.Peers.Sent.Count, "Ready replay no second Commit"); continue;
            }
            if (fence == "expired") MaterialClock(Terraria.Main.GameUpdateCount + 181);
            if (fence == "wrong-ticket") commit = QuickUtilityMutate(commit, "ticket");
            if (fence == "definition-after-ready") f.Data.Gameplay.GeneratedBuff.JumpBoost = 2;
            if (fence == "binding-after-ready") f.Data.RuntimeProgram.Bindings[0].Id = "changed_primary";
            f.Mode(2);
            if (fence == "owner-replaced") Terraria.Main.player[1] = new Player { whoAmI = 1, active = true };
            if (fence is "death" or "death-then-respawn-replay") f.Server.dead = true;
            if (fence == "unload") QuickUtilityClear();
            f.Peers.Sent.Clear(); f.Peers.Receive(commit, fence == "wrong-sender" ? 2 : 1);
            Equal(0, f.Ticks(f.ServerBuff), fence + " refuses stale or foreign authority");
            Equal(0, f.Peers.Sent.Count, fence + " no authoritative relay");
            if (fence == "death-then-respawn-replay")
            {
                // Prune while dead, keep stream high-water, then reactivate the SAME Player.
                typeof(GeneratedItem).Assembly.GetType("InfiniCrafterLocal.Common.Runtime.GeneratedQuickUtilityActivation")?
                    .GetMethod("Prune", BindingFlags.Static | BindingFlags.NonPublic)?.Invoke(null, null);
                f.Server.dead = false; f.ReceiveServer(claim); Equal(0, f.Peers.Sent.Count, "respawn replay cannot rewind cursor");
            }
        }
    }
}
