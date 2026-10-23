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
 private static void AtlasTravelingWave()
 {
        foreach (int updates in new[] {1,3,6}) {
            var spec=Entity(); spec.Kind="free_projectile"; spec.Collision.ExtraUpdates=updates-1;
            spec.Movement=new() {Name="move_traveling_wave",Code=23,Params=new() {WaveForwardSpeed=6f/updates,WaveDisplacementAmplitude=2,WavePhaseRate=.04f/updates,WaveStartPhase=.3f}};
            var projectile=new Projectile {active=true,owner=0,Center=Vector2.Zero};
            var generated=Attach(projectile); generated.Configure(new GeneratedItemData(),spec,0,8,Vector2.UnitX);
            Vector2 displacement=Vector2.Zero;
            for(int age=1;age<=60*updates;age++) {ModifierAge(generated,age);InvokeModifier(generated,"RunMovement");displacement+=projectile.velocity;}
            ModifierNear(360,displacement.X,"world-time forward displacement");
            ModifierNear((MathF.Sin(2.7f)-MathF.Sin(.3f))*32,displacement.Y,"exact bounded sine displacement");
            Vector2 step=projectile.velocity;
            generated.Configure(new GeneratedItemData(),spec,0,8,Vector2.UnitX,preserveSyncedState:true);InvokeModifier(generated,"RunMovement");
            Equal(step,projectile.velocity,"late hydration has no phase restart");
        }
 }
}
