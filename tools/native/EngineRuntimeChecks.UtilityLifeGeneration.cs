using System;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.Runtime;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.DataStructures;
using Terraria.ID;
internal static partial class EngineRuntimeChecks
{
    private static void UtilityLifeGeneration()
    {
        using var state = new NativeActorState();
        var write = typeof(InfiniCraftPlayer).GetMethod("WriteGeneratedBuffState", MobilityConsumptionFlags)!;
        var read = typeof(InfiniCraftPlayer).GetMethod("ReadGeneratedBuffState", MobilityConsumptionFlags)!;
        byte[] Capture(InfiniCraftPlayer owner) {
            using var stream = new MemoryStream(); write.Invoke(owner, new object[] { new BinaryWriter(stream) }); return stream.ToArray();
        }
        void Receive(InfiniCraftPlayer owner, byte[] bytes) {
            using var stream = new MemoryStream(bytes); var reader = new BinaryReader(stream); reader.ReadByte();
            read.Invoke(owner, new object[] { reader }); Equal(stream.Length, stream.Position, "life snapshot fully decoded before decision");
        }
        var hostPlayer = new Player { active = true, whoAmI = 1 }; var host = NativeDtoBindPlayer(hostPlayer);
        var clientPlayer = new Player { active = true, whoAmI = 1 }; var client = NativeDtoBindPlayer(clientPlayer);
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        host.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 400, LifeRegen = 5 });
        byte[] beforeDeath = Capture(host);
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Receive(client, beforeDeath);
        Equal(1, client.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "join aligns with authoritative generation");
        clientPlayer.dead = true; client.UpdateDead(); client.UpdateDead(); clientPlayer.dead = false; client.OnRespawn();
        Receive(client, beforeDeath);
        Equal(0, client.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "late pre-death snapshot cannot resurrect after respawn");
        Terraria.Main.netMode = NetmodeID.SinglePlayer; hostPlayer.dead = true; host.RetireGeneratedUtilityState("death");
        hostPlayer.dead = false; host.OnRespawn(); host.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 600, LifeRegen = 5 });
        byte[] freshLife = Capture(host);
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Receive(client, freshLife);
        Equal(600, client.CaptureGeneratedUtilityBuffPresentation().Current.RemainingTicks, "new-life authority restores legitimate effect");
        Receive(client, beforeDeath);
        Equal(600, client.CaptureGeneratedUtilityBuffPresentation().Current.RemainingTicks, "older epoch cannot overwrite fresh contribution");
        // The host acknowledgement can precede native client UpdateDead.
        Terraria.Main.netMode = NetmodeID.SinglePlayer; hostPlayer.dead = true; host.RetireGeneratedUtilityState("death");
        byte[] hostDead = Capture(host);
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Receive(client, hostDead);
        clientPlayer.dead = true; client.UpdateDead(); clientPlayer.dead = false; client.OnRespawn();
        Terraria.Main.netMode = NetmodeID.SinglePlayer; hostPlayer.dead = false; host.OnRespawn();
        host.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 700, LifeRegen = 5 }); freshLife = Capture(host);
        Terraria.Main.netMode = NetmodeID.MultiplayerClient; Receive(client, freshLife);
        Equal(700, client.CaptureGeneratedUtilityBuffPresentation().Current.RemainingTicks, "early server-death acknowledgement not counted twice");
    }

    private static void DelayedUtilityCannotCrossLife()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var clock = typeof(Terraria.Main).GetField("_gameUpdateCount", BindingFlags.Static | BindingFlags.NonPublic)!;
        object? previousClock = clock.GetValue(null);
        try {
            WithPlayer((player, owner) => {
                player.active = true; player.whoAmI = 0; Terraria.Main.player[0] = player;
                var data = GeneratedItemData.Placeholder();
                data.RuntimeProgram.EffectGroups = new[] { new RuntimeItemEffectGroupSpec { Id = "delayed", GeneratedBuff = new GeneratedBuffSpec { DurationTicks = 600, LifeRegen = 5 } } };
                var body = new RuntimeEntitySpec { Kind = RuntimeEntityKind.ItemBody };
                var action = new RuntimeEventActionSpec { ActionCode = RuntimeEventActionCode.ApplyGeneratedBuff, Event = RuntimeEventKind.OnHurt, EffectGroupId = "delayed", DelayTicks = 10 };
                clock.SetValue(null, 100u);
                Equal(true, RuntimeDelayedActionScheduler.TrySchedule(data, body, action, player,
                    new EntitySource_Misc("InfiniRuntimeEquipmentReaction"), Vector2.Zero, Vector2.UnitX, null, 0, 0, new RuntimeSpawnBudget(0)), "real delayed generated buff queued");
                clock.SetValue(null, 101u); player.dead = true; owner.UpdateDead();
                clock.SetValue(null, 102u);
                Equal(false, RuntimeDelayedActionScheduler.TrySchedule(data, body, action, player,
                    new EntitySource_Misc("InfiniRuntimeEquipmentReaction"), Vector2.Zero, Vector2.UnitX, null, 0, 0, new RuntimeSpawnBudget(0)), "dead owner cannot enqueue a contribution for a future life");
                player.dead = false; owner.OnRespawn();
                clock.SetValue(null, 111u); RuntimeDelayedActionScheduler.Update();
                Equal(0, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "pre-death delayed event cannot create a fresh-life contribution");
            });
        } finally { clock.SetValue(null, previousClock); RuntimeDelayedActionScheduler.Clear(); }
    }
}
