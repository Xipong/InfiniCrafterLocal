using System;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;

internal static partial class EngineRuntimeChecks
{
    private static void ComposableMotionBeamVfxSnapshotUsesActualLine()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            var data = MotionDefinition("""
              {"aim":{"source":"initial","turnOwner":false},
               "beamGeometry":{"lengthPx":120,"widthPx":8,"raycastTiles":false}}
              """);
            var actor = MotionActor(data, owner, new Vector2(0, 2));
            actor.Host.AI();
            var snapshot = InfiniVfxProjectileSnapshot.Capture(actor.Body, data, data.RuntimeProgram.PrimaryEntityId);
            AssertVfxNear(Vector2.UnitX, snapshot.Forward, "VFX follows explicit motion axis, not unrelated velocity");
            AssertVfxNear(actor.Body.Center + new Vector2(120, 0), snapshot.Tip, "VFX uses actual beam endpoint, not body AABB");
        });
    }

    private static void ComposableMotionScaleRateSnapshotPreservesSmallExplicitScale()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            var data = MotionDefinition("{\"visualScaleRate\":{\"deltaPerUpdate\":0,\"maxScale\":20}}");
            var actor = MotionActor(data, owner, Vector2.UnitX);
            actor.Body.scale = 0.01f;
            var entity = data.RuntimeProgram.TryGetEntity(data.RuntimeProgram.PrimaryEntityId)!;
            var snapshot = InfiniVfxProjectileSnapshot.Capture(actor.Body, data, entity.Id);
            Equal(0.01f, snapshot.Pose.Scale, "explicit scale-rate body is not clamped to old implicit scale");
            Equal(true, snapshot.IsValidFor(entity), "new declared lower scale remains valid in VFX transport");
            var ordinary = MotionDefinition("{}");
            Equal(false, snapshot.IsValidFor(ordinary.RuntimeProgram.TryGetEntity(ordinary.RuntimeProgram.PrimaryEntityId)),
                "new envelope does not weaken ordinary historical body policy");
        });
    }

    private static void ComposableMotionAbsoluteTilePolicyRequiresReachableConsumer()
    {
        foreach (string component in new[] { "attachment", "lashGeometry" }) {
            var root = MotionAdmissionWire(component);
            FrontHandEntity(root)["collision"]!["tileCollide"] = true;
            MotionRefuses(root, component + " cannot promise unexecuted native tile collision");
            FrontHandEntity(root)["collision"]!["tileCollide"] = false;
            MotionAdmits(root, component + " explicit supported tile policy");
        }
        var phased = MotionAdmissionWire("attachment");
        FrontHandEntity(phased)["attachment"]!["window"] = JsonNode.Parse(
            "{\"phase\":\"always\",\"clock\":\"active\",\"startDelayTicks\":0,\"durationTicks\":12}");
        FrontHandEntity(phased)["collision"]!["tileCollide"] = true;
        MotionAdmits(phased, "finite attachment retains collision for its separate free-flight interval");
    }
}
