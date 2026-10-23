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
        using var scope = new SwarmRuntimeScope();
        foreach (string movement in new[] { "Yoyo", "Flail" })
        {
            var data = SwarmGameplayFixture();
            var entity = data.RuntimeProgram.TryGetEntity("root")!;
            entity.Movement.Params.ReturnSpeed = 500;
            var owner = Terraria.Main.player[0];
            owner.channel = false;
            var generated = SwarmHost(data, entity);
            generated.Projectile.Center = owner.MountedCenter - new Microsoft.Xna.Framework.Vector2(60, 0);
            generated.Projectile.velocity = new Microsoft.Xna.Framework.Vector2(120, 0);
            typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile).GetMethod(movement,
                System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!
                .Invoke(generated, new object[] { entity.Movement.Params });
            Equal(false, generated.Projectile.active, movement + " catches a return that crosses the owner in one update");
        }

    }
    private static void CleanupHealRejectsRetiredOwners()
    {
        using var scope = new SwarmRuntimeScope();
        var data = SwarmGameplayFixture();
        var entity = data.RuntimeProgram.TryGetEntity("root")!;
        var player = Terraria.Main.player[0];
        var action = new RuntimeEventActionSpec { ActionCode = RuntimeEventActionCode.HealOwner,
            DamageFraction = 1, MaxHeal = 20 };
        foreach (string state in new[] { "dead", "inactive", "zero-life" })
        {
            player.active = state != "inactive";
            player.dead = state == "dead";
            player.statLife = state == "zero-life" ? 0 : 50;
            player.statLifeMax2 = 100;
            int before = player.statLife, budget = 0;
            InfiniCrafterLocal.Common.Runtime.RuntimeProgramExecutor.ExecuteAction(data, entity, action, player,
                new Terraria.DataStructures.EntitySource_Misc("retired owner heal"), Microsoft.Xna.Framework.Vector2.Zero,
                Microsoft.Xna.Framework.Vector2.UnitX, null, 100, 0, ref budget);
            Equal(before, player.statLife, state + " cannot be healed by a late proc");
        }
    }

}
