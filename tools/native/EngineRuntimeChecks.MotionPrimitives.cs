#nullable enable
using System;
using System.Linq;
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

    private static void AtlasMotionWireAdmission()
    {
        var options = new System.Text.Json.JsonSerializerOptions { PropertyNamingPolicy = System.Text.Json.JsonNamingPolicy.CamelCase };
        foreach (var row in new[] {
            (21, "move_spring_tether", "{\"springRestRadius\":2,\"springStiffness\":0.1,\"springDamping\":0,\"springMaxSpeed\":8}"),
            (22, "move_elliptic_orbit", "{\"ellipseRadiusAlong\":4,\"ellipseRadiusAcross\":2,\"ellipseAngularRate\":-0.02,\"ellipsePhase\":0}"),
            (23, "move_traveling_wave", "{\"waveForwardSpeed\":6,\"waveDisplacementAmplitude\":2,\"wavePhaseRate\":0.04,\"waveStartPhase\":0.3}") })
        {
            var p = System.Text.Json.Nodes.JsonNode.Parse(row.Item3)!.AsObject();
            var admitted = System.Text.Json.JsonSerializer.Deserialize<RuntimeParamsSpec>(p.ToJsonString(), options)!;
            new RuntimeMovementSpec { Code=row.Item1, Name=row.Item2, Params=admitted }.NormalizeAndValidate("free_projectile");
            foreach (string field in p.Select(kv=>kv.Key).ToArray())
            foreach (string mutation in new[] { "missing", "null", "string", "out_of_range" })
            {
                var bad=p.DeepClone().AsObject();
                if(mutation=="missing") bad.Remove(field);
                else bad[field]=System.Text.Json.Nodes.JsonNode.Parse(mutation=="null" ? "null" : mutation=="string" ? "\"1\"" : "1000000");
                bool rejected=false;
                try {
                    var invalid=System.Text.Json.JsonSerializer.Deserialize<RuntimeParamsSpec>(bad.ToJsonString(),options)!;
                    new RuntimeMovementSpec {Code=row.Item1,Name=row.Item2,Params=invalid}.NormalizeAndValidate("free_projectile");
                } catch(Exception e) when(e is System.IO.InvalidDataException or System.Text.Json.JsonException) { rejected=true; }
                Equal(true,rejected,row.Item2+" rejects "+mutation+" "+field);
            }
            bool nullRejected=false;
            try { new RuntimeMovementSpec {Code=row.Item1,Name=row.Item2,Params=null!}.NormalizeAndValidate("free_projectile"); }
            catch(System.IO.InvalidDataException) { nullRejected=true; }
            Equal(true,nullRejected,"null movement params cannot bypass required fields");
        }
        foreach(string json in new[] {"{}","{\"accelerationX\":0,\"accelerationY\":null,\"startDelayTicks\":0,\"durationTicks\":1}","{\"accelerationX\":2.0000000000000000001,\"accelerationY\":0,\"startDelayTicks\":0,\"durationTicks\":1}"})
        {
            bool rejected=false;
            try { System.Text.Json.JsonSerializer.Deserialize<RuntimeVectorAccelerationSpec>(json,options)!.Validate(); }
            catch(Exception e) when(e is System.IO.InvalidDataException or System.Text.Json.JsonException) { rejected=true; }
            Equal(true,rejected,"vector acceleration raw JSON admission");
        }
    }

    private static void AtlasSpeedRamp()
    {
        foreach (int updates in new[] {1, 3, 6}) {
            var spec = Entity(); spec.Kind = "free_projectile"; spec.Collision.ExtraUpdates = updates - 1;
            spec.SpeedRamp = new() { StartSpeed = 12f / updates, EndSpeed = 3f / updates, StartDelayTicks = 2, DurationTicks = 4 };
            var projectile = new Projectile { active = true, owner = 0, velocity = new Vector2(3, 4) };
            var generated = Attach(projectile); generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX);
            ModifierAge(generated, 4 * updates); InvokeModifier(generated, "ApplyActiveModifiers");
            ModifierNear(7.5f, projectile.velocity.Length() * updates, "absolute halfway speed");
            ModifierNear(.75f, projectile.velocity.X / projectile.velocity.Y, "heading retained");
            projectile.velocity *= 20; InvokeModifier(generated, "ApplyActiveModifiers");
            ModifierNear(7.5f, projectile.velocity.Length() * updates, "history-independent speed envelope");
            ModifierAge(generated, 6 * updates); InvokeModifier(generated, "ApplyActiveModifiers");
            ModifierNear(3f, projectile.velocity.Length() * updates, "exact phase endpoint");
            projectile.velocity = Vector2.Zero; InvokeModifier(generated, "ApplyActiveModifiers");
            Equal(Vector2.Zero, projectile.velocity, "stalled projectile remains stalled");
        }
    }

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

    private static void AtlasVectorAcceleration()
    {
        foreach (int updates in new[] {1, 3, 6}) {
            var spec = Entity(); spec.Kind = "free_projectile"; spec.Collision.ExtraUpdates = updates - 1;
            spec.VectorAcceleration = new() { AccelerationX = .3f / updates / updates, AccelerationY = -.1f / updates / updates, StartDelayTicks = 2, DurationTicks = 4 };
            var projectile = new Projectile { active = true, owner = 0, velocity = Vector2.Zero };
            var generated = Attach(projectile); generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX);
            for (int age = 1; age <= 8 * updates; age++) { ModifierAge(generated, age); InvokeModifier(generated, "ApplyActiveModifiers"); }
            ModifierNear(1.2f, projectile.velocity.X * updates, "world-time X impulse");
            ModifierNear(-.4f, projectile.velocity.Y * updates, "world-time Y impulse");
            ModifierAge(generated, 7 * updates); generated.Configure(new GeneratedItemData(), spec, 0, 8, Vector2.UnitX, preserveSyncedState: true);
            Vector2 before = projectile.velocity; InvokeModifier(generated, "ApplyActiveModifiers");
            Equal(before, projectile.velocity, "hydration cannot restart elapsed acceleration");
        }
    }
}
