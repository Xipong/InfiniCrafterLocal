using System;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void VelocityScaleLatePhasesAndLegacy()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            var phases = MotionDefinition("""
                {"velocityScale":[
                 {"multiplierPerUpdate":1.2,"window":{"phase":"always","clock":"active","startDelayTicks":0,"durationTicks":1}},
                 {"multiplierPerUpdate":0.2,"window":{"phase":"always","clock":"active","startDelayTicks":1,"durationTicks":1}}]}
                """);
            var (host, body) = MotionActor(phases, owner, new Vector2(10, 0));
            host.AI(); AssertVfxNear(new Vector2(12, 0), body.velocity, "first half-open interval accelerates");
            host.AI(); AssertVfxNear(new Vector2(2.4f, 0), body.velocity, "second interval strongly brakes");
            host.AI(); AssertVfxNear(new Vector2(2.4f, 0), body.velocity, "outside both intervals leaves speed alone");
            var capped = MotionActor(MotionDefinition("{\"velocityScale\":[{\"multiplierPerUpdate\":1.2,\"maxSpeed\":5}]}"), owner, new Vector2(10,0));
            capped.Host.AI(); AssertVfxNear(new Vector2(5,0), capped.Body.velocity, "cap follows multiplication");
            var zero = MotionActor(MotionDefinition("{\"velocityScale\":[{\"multiplierPerUpdate\":0}]}"), owner, new Vector2(10,3));
            zero.Host.AI(); Equal(Vector2.Zero, zero.Body.velocity, "zero is a stop, not identity");
            var legacy = MotionActor(MotionDefinition("{\"velocityRetention\":{\"multiplierPerUpdate\":0.5},\"speedModifier\":{\"speedMultiplierPerUpdate\":0.8,\"maxSpeed\":80,\"window\":{\"phase\":\"always\"}}}"), owner, new Vector2(10,0));
            legacy.Host.AI(); AssertVfxNear(new Vector2(4,0), legacy.Body.velocity, "saved early plus late scalers still execute");
        });
    }

    private static void VelocityScaleNativeAdmissionAndSubupdates()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            foreach (int updates in new[] {1, 2, 4}) {
                var data=MotionDefinition("{\"velocityScale\":[{\"multiplierPerUpdate\":0.5}]}", b => b["collision"]!["updatesPerTick"]=updates);
                var actor=MotionActor(data,owner,new Vector2(16,0));
                for (int i=0;i<updates;i++) actor.Host.AI();
                AssertVfxNear(new Vector2(16f * MathF.Pow(.5f,updates),0),actor.Body.velocity,"per-update multiplier respects explicit subupdates");
            }
            foreach (string invalid in new[] {
                "{\"velocityScale\":null}",
                "{\"velocityScale\":[]}",
                "{\"velocityScale\":[{\"multiplierPerUpdate\":1e-60}]}",
                "{\"velocityScale\":[{\"multiplierPerUpdate\":1.0000000000000002}]}",
                "{\"velocityScale\":[{\"multiplierPerUpdate\":0.5,\"maxSpeed\":null}]}",
                "{\"velocityScale\":[{\"multiplierPerUpdate\":0.5},{\"multiplierPerUpdate\":1.1}]}",
                "{\"velocityScale\":[{\"multiplierPerUpdate\":0.5}],\"velocityRetention\":{\"multiplierPerUpdate\":1}}"
            }) {
                bool rejected=false;
                try { MotionDefinition(invalid); } catch (InvalidOperationException) { rejected=true; }
                Equal(true,rejected,"strict native scale admission rejects null/empty/overlap/legacy mix");
            }
        });
    }
}
