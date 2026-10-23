using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void QolReturnCatch()
    {
        using var scope = new SwarmRuntimeScope();
        var data = SwarmGameplayFixture(); var entity = data.RuntimeProgram.TryGetEntity("root")!;
        entity.Movement.Code = 5; entity.Movement.Params.ReturnAfterTicks = 60;
        var host = SwarmHost(data, entity); host.Projectile.timeLeft = 100;
        var snapshot = host.CaptureReturnStatus(host.Projectile.owner, host.Projectile.Center)!;
        Equal("outbound", snapshot.Phase, "readout exposes actual initial lifecycle");
        Equal(60, snapshot.ReturnInTicks, "readout uses authored return deadline");
        var begin = typeof(InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile).GetMethod("BeginReturn", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!;
        begin.Invoke(host, null); Equal(true, host.Projectile.netUpdate, "return transition synchronizes promptly");
        Equal("returning", host.CaptureReturnStatus(host.Projectile.owner, host.Projectile.Center)!.Phase, "readout follows live returning flag");
        host.Configure(data, entity, 0, 8, Microsoft.Xna.Framework.Vector2.UnitX, preserveSyncedState: true);
        Equal("returning", host.CaptureReturnStatus(host.Projectile.owner, host.Projectile.Center)!.Phase, "hydration retains return lifecycle");
        var rows = GeneratedReturnStatusView.Build(new[] { snapshot, snapshot }, System.Globalization.CultureInfo.InvariantCulture);
        Equal(1, rows.Count, "same item return instances share one readout");
        Equal(true, rows[0].Name.EndsWith("×2", StringComparison.Ordinal), "readout preserves active instance count");
        host.Projectile.active = false;
        Equal(true, host.CaptureReturnStatus(host.Projectile.owner, host.Projectile.Center) is null, "retired source leaves no ghost status");
        var zero = Microsoft.Xna.Framework.Vector2.Zero;
        Equal(true, InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.ReturnPathReachesOwner(new(-60, 0), new(120, 0), zero, 20), "fast return crossing owner is caught");
        Equal(false, InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.ReturnPathReachesOwner(new(-60, 30), new(120, 0), zero, 20), "nearby trajectory is not a catch");
        Equal(false, InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.ReturnPathReachesOwner(new(-60, 0), new(-120, 0), zero, 20), "moving away does not catch");
        Equal(true, InfiniCrafterLocal.Content.Projectiles.GeneratedProjectile.ReturnPathReachesOwner(new(2, 0), zero, zero, 20), "stationary nearby return is caught");
    }
}
