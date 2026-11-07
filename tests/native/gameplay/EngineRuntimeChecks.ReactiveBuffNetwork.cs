using System;
using System.Collections;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void ReactiveUtilityCanonicalServerSnapshotSurvivesOwnerCorrection()
    {
        foreach (bool kill in new[] { false, true })
        {
            using var f = new QuickUtilityPeers(cost: 0);
            f.Mode(2); MaterialClock(500);
            var serverItem = ReactiveUtilityItem(exhaustion: 120);
            var data = serverItem.Data;
            var action = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.ItemEntityId)!.Events.Single();
            action.Event = kill ? RuntimeEventKind.OnEnemyKill : RuntimeEventKind.OnHurt;
            data.RuntimeProgram.NormalizeAndValidate(); f.Peers.Register(data);
            f.Server.armor[3] = serverItem.Item;
            var ownerItem = AttachItem(new GeneratedItem(), new Item { type = ItemID.CopperShortsword, stack = 1 }, data);
            f.Owner.armor[3] = ownerItem.Item;
            var hurt = new Player.HurtInfo { Damage = 10 };
            var victim = new NPC { type = NPCID.Zombie, whoAmI = 0, realLife = -1,
                lastInteraction = 1, friendly = false, life = 0, lifeMax = 100 };
            void ServerOccurrence()
            {
                // Exact server-side callback produced by native Player.Hurt or
                // GlobalNPC.OnKill, never a mod packet carrying client buff stats.
                if (kill) new GeneratedEquipmentKillGlobalNPC().OnKill(victim);
                else f.ServerBuff.PostHurt(hurt);
            }
            f.Mode(1); f.OwnerBuff.ResetEffects(); ItemLoader.UpdateAccessory(ownerItem.Item, f.Owner, false);
            if (!kill) f.OwnerBuff.PostHurt(hurt); // actual owner prediction / HUD timer
            f.Mode(2); f.ServerBuff.ResetEffects(); ItemLoader.UpdateAccessory(serverItem.Item, f.Server, false);
            f.Peers.Sent.Clear(); ServerOccurrence();
            Equal(60, ExhaustionBuffTicks(f.ServerBuff), "native server occurrence commits canonical utility " + action.Event);
            Equal(.25f, f.ServerBuff.CaptureGeneratedUtilityBuffPresentation().Current.MovementSpeed, "server derives stats from its equipment group");
            byte[][] packets = f.Peers.Sent.ToArray();
            byte[] snapshot = packets.Single(p => p[0] == InfiniNetPacketIds.SyncGeneratedUtilityBuff);
            if (kill) Equal(1, packets.Count(p => p[0] == InfiniNetPacketIds.EquipmentEnemyKill), "existing server kill notification remains owner reaction producer");
            f.Mode(1); foreach (byte[] packet in packets) f.Peers.Receive(packet, 256);
            Equal(60, ExhaustionBuffTicks(f.OwnerBuff), "real owner decoder preserves server-confirmed utility");
            Equal(1, f.OwnerBuff.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "owner prediction and server state are one contribution");
            var cooldowns = (IDictionary)typeof(InfiniCraftPlayer).GetField("_reactionCooldowns", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(f.OwnerBuff)!;
            Equal(1, cooldowns.Count, "owner keeps local reaction cooldown for HUD after snapshot");
            f.Mode(3); f.Peers.Receive(snapshot, 256);
            Equal(.25f, f.RemoteBuff.CaptureGeneratedUtilityBuffPresentation().Current.MovementSpeed, "real remote decoder receives the same accepted group");

            f.Mode(2); ExhaustionBuffTick(f.ServerBuff); MaterialClock(501); f.Peers.Sent.Clear(); ServerOccurrence();
            Equal(59, ExhaustionBuffTicks(f.ServerBuff), "repeat native callback inside cooldown cannot refresh canonical duration");
            Equal(0, f.Peers.Sent.Count(p => p[0] == InfiniNetPacketIds.SyncGeneratedUtilityBuff), "no duplicate utility commit snapshot");
            f.Mode(1);
            Equal(true, f.OwnerBuff.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 500, MovementSpeed = 1f }), "untrusted owner can only predict extra stats locally");
            byte[] claimPayload = ExhaustionSnapshot(f.OwnerBuff);
            byte[] claim = new byte[claimPayload.Length + 1]; claim[0] = InfiniNetPacketIds.SyncGeneratedUtilityBuff; claimPayload.CopyTo(claim, 1);
            f.Mode(2); f.Peers.Sent.Clear(); f.Peers.Receive(claim, 1);
            Equal(59, ExhaustionBuffTicks(f.ServerBuff), "client snapshot/replay cannot refresh server utility duration");
            Equal(1, f.ServerBuff.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "server ignores all client-authored contribution numbers");
            byte[] correction = f.Peers.Sent.Single(p => p[0] == InfiniNetPacketIds.SyncGeneratedUtilityBuff);
            f.Mode(1); f.Peers.Receive(correction, 256);
            Equal(59, ExhaustionBuffTicks(f.OwnerBuff), "authority correction retains canonical reaction buff instead of erasing it");
            Equal(.25f, f.OwnerBuff.CaptureGeneratedUtilityBuffPresentation().Current.MovementSpeed, "authority correction removes forged bonus");
            Equal(1, f.OwnerBuff.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "no duplicated utility after correction roundtrip");
            Equal(1, cooldowns.Count, "stat correction cannot clear owner's retained reaction HUD timer");
        }
    }
}
