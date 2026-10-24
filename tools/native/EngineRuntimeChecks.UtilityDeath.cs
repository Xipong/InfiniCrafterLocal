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
    private static void UtilityDeathClearsContributions()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        WithPlayer((player, owner) =>
        {
            player.active = true;
            var buff = new GeneratedBuffSpec { DurationTicks = 600, LifeRegen = 5 };
            Equal(true, owner.ApplyGeneratedUtilityBuff(buff), "live utility admitted");
            var write = typeof(InfiniCraftPlayer).GetMethod("WriteGeneratedBuffState", MobilityConsumptionFlags)!;
            using var snapshot = new MemoryStream();
            write.Invoke(owner, new object[] { new BinaryWriter(snapshot) });
            player.dead = true; owner.UpdateDead(); owner.UpdateDead();
            Equal(0, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "death retires contributions idempotently");
            Equal(0, owner.CaptureGeneratedUtilityBuffPresentation().Current.LifeRegen, "death resets regen aggregate");
            Equal(false, owner.ApplyGeneratedUtilityBuff(buff), "dead owner rejects utility");
            snapshot.Position = 0; var reader = new BinaryReader(snapshot); reader.ReadByte();
            typeof(InfiniCraftPlayer).GetMethod("ReadGeneratedBuffState", MobilityConsumptionFlags)!.Invoke(owner, new object[] { reader });
            Equal(snapshot.Length, snapshot.Position, "dead snapshot still fully decoded");
            Equal(0, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "snapshot cannot restore utility while dead");
            player.dead = false;
            Equal(false, owner.ApplyGeneratedUtilityBuff(buff, activationTick: Terraria.Main.GameUpdateCount), "last dead tick is retired");
            Equal(true, owner.ApplyGeneratedUtilityBuff(buff), "fresh unanchored live activation remains valid");
            owner.ClearGeneratedUtilityState();
            Equal(0, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "world retirement clears contributions");
            owner.OnEnterWorld();
            Equal(true, owner.ApplyGeneratedUtilityBuff(buff, activationTick: Terraria.Main.GameUpdateCount), "world entry resets previous-life activation fence");
        });
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
