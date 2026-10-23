#nullable enable
using System;
using System.Linq;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;
internal static partial class EngineRuntimeChecks
{
 private static void AtlasSpringTether()
 {
        using var actors = new SwarmRuntimeScope();
        Terraria.Main.player[0].active = true; Terraria.Main.player[0].dead = false; Terraria.Main.player[0].Center = new Vector2(500, 500);
        var spec = Entity(); spec.Kind = "free_projectile";
        spec.Movement = new() { Name = "move_spring_tether", Code = 21, Params = new() { SpringRestRadius = 2, SpringStiffness = .1f, SpringDamping = 0, SpringMaxSpeed = 8 } };
        var projectile = new Projectile { active = true, owner = 0, Center = Terraria.Main.player[0].MountedCenter + new Vector2(100, 0), velocity = Vector2.Zero };
        var generated = Attach(projectile); generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX);
        InvokeModifier(generated, "RunMovement"); ModifierNear(-6.8f, projectile.velocity.X, "spring tension reflects stretch");
        projectile.velocity = new Vector2(-80,0); InvokeModifier(generated, "RunMovement"); ModifierNear(8, projectile.velocity.Length(), "bounded speed");
        projectile.Center = Terraria.Main.player[0].MountedCenter + new Vector2(10,0); projectile.velocity = new Vector2(2,0);
        InvokeModifier(generated, "RunMovement"); Equal(new Vector2(2,0), projectile.velocity, "slack radius adds no force");
        spec.Movement.Params.SpringDamping = .5f; InvokeModifier(generated, "RunMovement"); ModifierNear(2 * MathF.Exp(-.5f), projectile.velocity.X, "explicit damping law");
        foreach (int updates in new[] {1,3,6}) {
            spec.Movement.Params.SpringDamping = .1f / updates;
            projectile.velocity = new Vector2(4f / updates,0);
            for(int i=0;i<10*updates;i++) InvokeModifier(generated,"RunMovement");
            ModifierNear(4*MathF.Exp(-1),projectile.velocity.X*updates,"world-time exponential damping across update clocks");
        }
        try { new RuntimeMovementSpec { Name="move_straight", Code=0, Params=spec.Movement.Params }.NormalizeAndValidate("free_projectile"); throw new Exception("foreign spring fields accepted"); }
        catch (System.IO.InvalidDataException) { }
 }
}
