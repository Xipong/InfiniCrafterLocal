using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Systems;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
using Terraria.ModLoader.IO;

internal static partial class EngineRuntimeChecks
{
    private static void EscrowTakeAcknowledgementPreservesChangedCursor()
    {
        using var serializer = WithPersistenceBoolSerializer();
        using var peers = new ReviewPeers();
        var world = new GeneratedStationEscrowStateSystem();
        Item oldMouse = Terraria.Main.mouseItem;
        try
        {
            foreach (string scenario in new[] { "empty", "occupied", "merge", "full" })
                WithPlayer((player, owner) =>
                {
                    owner.Initialize(); player.whoAmI = 0; player.active = true;
                    Terraria.Main.player[0] = player; peers.Mode(NetmodeID.MultiplayerClient, 0); peers.Sent.Clear();
                    foreach (Item item in player.inventory) item.TurnToAir();
                    string scope = new string('b', 32);
                    PersistenceReceiveScope(world, scope);
                    Equal(true, owner.EnsureRemoteStationAuthority(), "current escrow authority");
                    owner.InputA = new Item(ItemID.Wood, 1);
                    Terraria.Main.mouseItem = new Item();
                    Equal(true, owner.TryTakeInputToMouse(0), "take begins with empty cursor");
                    using var request = new BinaryReader(new MemoryStream(peers.Sent.Single()));
                    request.ReadByte(); request.ReadInt32(); request.ReadString(); request.ReadString();
                    string operation = request.ReadString(); byte action = request.ReadByte(); sbyte index = request.ReadSByte();
                    if (scenario != "empty") Terraria.Main.mouseItem = new Item(ItemID.StoneBlock, 7);
                    player.inventory[58] = Terraria.Main.mouseItem.Clone();
                    if (scenario == "merge") player.inventory[0] = new Item(ItemID.Wood, 3);
                    if (scenario == "full")
                        for (int i = 0; i < 58; i++) player.inventory[i] = new Item(ItemID.StoneBlock, 9999);
                    var synced = new List<int>();
                    using var network = PersistenceObserveNetworkSend((message, slot) => {
                        Equal((int)MessageID.SyncEquipment, message, "refund uses native equipment sync"); synced.Add(slot);
                    });
                    using var stream = new MemoryStream();
                    using (var writer = new BinaryWriter(stream, System.Text.Encoding.UTF8, true)) {
                        writer.Write(InfiniNetPacketIds.StationEscrowResult); writer.Write(3); writer.Write(scope);
                        writer.Write(operation); writer.Write(action); writer.Write(index); writer.Write(true); writer.Write("");
                    }
                    byte[] ack = stream.ToArray();
                    peers.Receive(ack); peers.Receive(ack); // duplicate ACK must never deliver twice
                    Equal(true, owner.InputA.IsAir, "ack consumes the escrow mirror once");
                    Equal(false, owner.HasPendingStationEscrowOperation, "ack settles exact operation");
                    Equal(scenario == "empty" ? ItemID.Wood : ItemID.StoneBlock, Terraria.Main.mouseItem.type, "RTT cursor identity retained");
                    Equal(scenario == "empty" ? 1 : 7, Terraria.Main.mouseItem.stack, "RTT cursor quantity retained");
                    Equal(Terraria.Main.mouseItem.type, player.inventory[58].type, "mouse equipment identity remains exact");
                    Equal(scenario == "merge" ? 4 : scenario == "occupied" ? 1 : 0,
                        player.inventory.Take(58).Where(i => i.type == ItemID.Wood).Sum(i => i.stack), "exact one-unit inventory delivery");
                    Equal(scenario == "full" ? "" : scenario == "empty" ? "58" : "0", string.Join(",", synced), "one exact changed slot synchronized to server");
                    var save = new TagCompound(); owner.SaveData(save);
                    var deferred = save.GetList<TagCompound>("infiniDeferredCraftRefundsV1");
                    Equal(scenario == "full" ? 1 : 0, deferred.Count, "full inventory retains sole durable claim");
                    if (deferred.Count != 0) {
                        Item refund = ItemIO.Load(deferred.Single());
                        Equal(ItemID.Wood, refund.type, "deferred claim identity"); Equal(1, refund.stack, "deferred claim quantity");
                    }
                });
        }
        finally { world.ClearWorld(); Terraria.Main.mouseItem = oldMouse; }
    }

    private static void SentryOriginalDamageUsesSelectedPrefixedBase()
    {
        using var state = new SentryLifeScope();
        foreach (int prefix in new[] { 0, (int)PrefixID.Legendary, (int)PrefixID.Broken })
        foreach (string entityId in new[] { "root", "alt" })
        {
            foreach (Projectile p in Terraria.Main.projectile) p.active = false;
            var data = RootCombatFixture(37, 4, "summon");
            var host = RootCombatHost(data);
            var entity = data.RuntimeProgram.TryGetEntity(entityId)!;
            entity.NativeSentry = true;
            if (prefix != 0) Equal(true, host.Item.Prefix(prefix), "native source prefix accepted");
            var oracle = RootCombatHost(data);
            oracle.Item.damage = entity.Damage.Damage;
            if (prefix != 0) Equal(true, oracle.Item.Prefix(prefix), "independent selected-base prefix oracle");
            int expectedBase = oracle.Item.damage;
            int finalDamage = expectedBase * 2; // final native damage already contains owner bonus
            using var turrets = new Hook(typeof(Player).GetMethod(nameof(Player.UpdateMaxTurrets))!, (Action<Player>)(_ => { }));
            using var native = new Hook(NativeProjectileEntry(),
                (Func<IEntitySource, Vector2, Vector2, int, int, float, int, float, float, float, Projectile>)
                ((source, position, velocity, type, damage, knockback, owner, a, b, c) => {
                    var p = Terraria.Main.projectile[0] = new Projectile { whoAmI = 0, owner = owner, active = true,
                        damage = damage, knockBack = knockback, velocity = velocity, Center = position };
                    typeof(Projectile).GetProperty("ModProjectile")!.SetValue(p, Attach(p));
                    return p;
                }));
            Equal(1, GeneratedProjectile.SpawnRuntimeEntity(data, entityId, state.Owner,
                state.Owner.GetSource_ItemUse(host.Item), Vector2.Zero, Vector2.UnitX, 0, 1,
                rootDamageOverride: finalDamage), "actual spawn configures sentry");
            Projectile sentry = Terraria.Main.projectile[0];
            Equal(finalDamage, sentry.damage, "initial final native damage remains intact");
            Equal(expectedBase, sentry.originalDamage, "native update receives selected prefix base without player bonus");
            var generated = (GeneratedProjectile)sentry.ModProjectile;
            generated.Configure(data, entity, 0, 1, Vector2.UnitX, preserveSyncedState: true);
            Equal(expectedBase, sentry.originalDamage, "network hydration preserves native synchronized base");
        }
    }
}
