using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void QolReturnCatch()
    {
        var zero = Microsoft.Xna.Framework.Vector2.Zero;
        Equal(true, InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.ReturnPathReachesOwner(new(-60, 0), new(120, 0), zero, 20), "fast return crossing owner is caught");
        Equal(false, InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.ReturnPathReachesOwner(new(-60, 30), new(120, 0), zero, 20), "nearby trajectory is not a catch");
        Equal(false, InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.ReturnPathReachesOwner(new(-60, 0), new(-120, 0), zero, 20), "moving away does not catch");
        Equal(true, InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.ReturnPathReachesOwner(new(2, 0), zero, zero, 20), "stationary nearby return is caught");
    }
}
