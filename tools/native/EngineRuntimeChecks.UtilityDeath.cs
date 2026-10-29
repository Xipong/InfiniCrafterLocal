using System;
using System.IO;
using System.Linq;
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
            Equal(true, owner.ApplyGeneratedUtilityBuff(buff), "short live utility admitted");
            Equal(true, owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 72000, ManaRegen = 6 }), "exact twenty-minute effect admitted");
            Equal(true, owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 72001, MovementSpeed = .1f }), "long effect admitted");
            Equal(true, owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 0, JumpBoost = 1f }), "permanent effect admitted");
            Float32BuffTick.Invoke(owner, null); Float32BuffTick.Invoke(owner, null);
            Equal(71999, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Single(row => row.MovementSpeed == .1f).RemainingTicks,
                "long contribution now has less than twenty minutes remaining");
            Equal(true, owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, MovementSpeed = .1f }), "shorter identical refresh admitted");
            var write = typeof(InfiniCraftPlayer).GetMethod("WriteGeneratedBuffState", MobilityConsumptionFlags)!;
            using var snapshot = new MemoryStream();
            write.Invoke(owner, new object[] { new BinaryWriter(snapshot) });
            player.dead = true; owner.UpdateDead(); owner.UpdateDead();
            var afterDeath = owner.CaptureGeneratedUtilityBuffPresentation();
            Equal(2, afterDeath.Entries.Count, "death retains short contributions idempotently");
            Equal(5, afterDeath.Current.LifeRegen, "short potion effect remains in aggregate");
            Equal(6, afterDeath.Current.ManaRegen, "initial duration of exactly twenty minutes survives death");
            Equal(0f, afterDeath.Current.MovementSpeed, "initial long duration is retired even below twenty minutes remaining and after shorter refresh");
            Equal(0f, afterDeath.Current.JumpBoost, "permanent effect expires on death");
            Equal(false, owner.ApplyGeneratedUtilityBuff(buff), "dead owner rejects utility");
            snapshot.Position = 0; var reader = new BinaryReader(snapshot); reader.ReadByte();
            typeof(InfiniCraftPlayer).GetMethod("ReadGeneratedBuffState", MobilityConsumptionFlags)!.Invoke(owner, new object[] { reader });
            Equal(snapshot.Length, snapshot.Position, "dead snapshot still fully decoded");
            Equal(2, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "dead snapshot preserves short effects without restoring long or permanent ones");
            player.dead = false;
            owner.OnRespawn();
            player.lifeRegen = player.manaRegenBonus = 0;
            owner.PostUpdateEquips();
            Equal(5, player.lifeRegen, "retained short potion effect executes after respawn");
            Equal(6, player.manaRegenBonus, "retained twenty-minute potion effect executes after respawn");
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
