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
        });
    }
}
