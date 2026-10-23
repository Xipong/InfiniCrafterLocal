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
 private static void AtlasEllipticOrbit()
 {
        using var actors = new SwarmRuntimeScope(); Terraria.Main.player[0].active = true; Terraria.Main.player[0].dead = false;
        Terraria.Main.player[0].Center = new Vector2(500,500);
        foreach (int updates in new[] {1,3,6}) {
            var spec = Entity(); spec.Kind = "free_projectile"; spec.Collision.ExtraUpdates = updates - 1;
            spec.Movement = new() { Name="move_elliptic_orbit", Code=22, Params=new() { EllipseRadiusAlong=4, EllipseRadiusAcross=2, EllipseAngularRate=.02f / updates, EllipsePhase=0 } };
            var projectile = new Projectile { active=true, owner=0, Center=new Vector2(320,320), tileCollide=true };
            var generated=Attach(projectile); generated.Configure(new GeneratedItemData(),spec,0,8,Vector2.UnitY);
            ModifierAge(generated, 60 * updates); InvokeModifier(generated,"RunMovement");
            Vector2 target=projectile.Center+projectile.velocity-Terraria.Main.player[0].MountedCenter;
            ModifierNear(-MathF.Sin(1.2f)*32, target.X,"oriented minor axis at world age");
            ModifierNear(MathF.Cos(1.2f)*64, target.Y,"oriented major axis at world age");
            Equal(false,projectile.tileCollide,"orbit explicitly ignores tiles");
            generated.Configure(new GeneratedItemData(),spec,0,8,Vector2.UnitY,preserveSyncedState:true);
            InvokeModifier(generated,"RunMovement");
            Equal(target,projectile.Center+projectile.velocity-Terraria.Main.player[0].MountedCenter,"hydration retains phase and axis");
        }
 }
}
