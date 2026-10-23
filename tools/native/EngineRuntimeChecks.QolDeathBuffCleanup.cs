using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void QolDeathBuffCleanup()
    {
        WithPlayer((player, owner) => {
            owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 600, LifeRegen = 10, MovementSpeed = .5f });
            Equal(1, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "real buff active before death");
            owner.UpdateDead();
            var after = owner.CaptureGeneratedUtilityBuffPresentation();
            Equal(0, after.Entries.Count, "death retires active timed effects");
            Equal(0, after.Current.RemainingTicks, "HUD aggregate cannot survive death");
            Equal(0, after.Current.LifeRegen, "regen cannot return after respawn");
            Equal(1, owner.LastGeneratedUtilityRetirement!.Value.Contributions, "cleanup receipt retains retired contribution count");
            var buff = new GeneratedBuffSpec { DurationTicks = 600, LifeRegen = 10 };
            player.dead = true;
            Equal(false, owner.ApplyGeneratedUtilityBuff(buff), "new buff cannot reactivate dead player");
            player.dead = false;
            Equal(false, owner.ApplyGeneratedUtilityBuff(buff, activationTick: Terraria.Main.GameUpdateCount), "delayed pre-respawn occurrence cannot resurrect retired effect");
            Equal(true, owner.ApplyGeneratedUtilityBuff(buff), "fresh live activation remains supported");
            owner.RetireGeneratedUtilityState("world_unload");
            Equal(0, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "world transition retires contribution owner as well as exhaustion");
            Equal("world_unload", owner.LastGeneratedUtilityRetirement!.Value.Reason, "inspection explains cleanup boundary");
        });
    }
}
