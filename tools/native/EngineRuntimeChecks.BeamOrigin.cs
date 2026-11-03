using System;
using System.Text.Json.Nodes;
using Microsoft.Xna.Framework;
using InfiniCrafterLocal.Common.Models;
using Terraria;
using MonoMod.RuntimeDetour;

internal static partial class EngineRuntimeChecks
{
    // Baseline-compilable JSON tracer: the integration owner can replay this
    // test-only patch against frozen products for native RED, without new DTO symbols.
    private static void BeamAxialOriginPreservesLengthAndSharedConsumers()
    {
        WithPlayer((owner, _) => WithBodyGeometryQueue((count, positions) => {
            using var actors = new NativeActorState();
            foreach (string source in new[] { "initial", "velocity" })
            foreach (float? offset in new float?[] { null, 0, -32, 16, -30720, 30720 }) {
                var geometryJson = new JsonObject { ["lengthPx"] = 64, ["widthPx"] = 8, ["raycastTiles"] = false };
                if (offset.HasValue) geometryJson["startOffsetPx"] = offset.Value;
                var data = MotionDefinition(new JsonObject {
                    ["aim"] = new JsonObject { ["source"] = source, ["turnOwner"] = false },
                    ["beamGeometry"] = geometryJson
                }.ToJsonString(), entity => entity["visual"]!["assetMode"] = "runtime_geometry");
                var (host, body) = MotionActor(data, owner, new Vector2(0, 2));
                host.AI();
                Vector2 center = body.Center, velocity = body.velocity;
                float scale = body.scale;
                var geometry = BeamGeometry(host);
                Vector2 axis = source == "initial" ? Vector2.UnitX : Vector2.UnitY;
                Vector2 expectedStart = center + axis * (offset ?? 0);
                AssertVfxNear(expectedStart, geometry.Start, "beam start uses signed offset on exact MotionAxis");
                AssertVfxNear(expectedStart + axis * 64, geometry.End, "offset translates both endpoints, never length");
                BeamNear(64, Vector2.Distance(geometry.Start, geometry.End), "beam length remains authored");
                BeamNear(8, geometry.Width, "offset does not change width");
                Equal(center, body.Center, "line origin does not move body center");
                Equal(velocity, body.velocity, "line origin does not change body velocity");
                Equal(scale, body.scale, "line origin does not change PNG scale");
                Equal(true, host.ShouldUpdatePosition(), "beam offset does not imply attachment");
                Equal(true, host.TryCapturePresentationGeometry("beam", out var path), "VFX captures shared offset line");
                AssertVfxNear(geometry.Start, path[0], "VFX start equals collision start");
                AssertVfxNear(geometry.End, path[1], "VFX end equals collision end");
                int drawn = count();
                DrawBodyGeometry(host);
                Equal(drawn + 1, count(), "one runtime_geometry body for the shifted beam");
                AssertBodySegment(positions(drawn), geometry.Start, geometry.End, geometry.Width);
                Equal(true, host.Colliding(default, BodyTarget(expectedStart + axis * 8)) == true,
                    "collision includes authored shifted segment, including behind the pivot");
                Equal(false, host.Colliding(default, BodyTarget(expectedStart - axis * 24)) == true,
                    "collision excludes space behind shifted segment");
                Equal(false, host.Colliding(default, BodyTarget(expectedStart + axis * 88)) == true,
                    "collision does not silently extend length");
            }
        }));
    }

    private static void BeamAxialOriginRaycastRetainsOffsetStartAndLengthBudget()
    {
        WithPlayer((owner, _) => {
            using var actors = new NativeActorState();
            var data = MotionDefinition("""
              {"aim":{"source":"initial","turnOwner":false},
               "beamGeometry":{"lengthPx":64,"widthPx":8,"raycastTiles":true,"startOffsetPx":-32}}
              """);
            var (host, body) = MotionActor(data, owner, new Vector2(0, 2));
            host.AI();
            int scans = 0;
            using var scan = new Hook(typeof(Collision).GetMethod(nameof(Collision.LaserScan))!,
                (Action<Vector2, Vector2, float, float, float[]>)((start, direction, width, max, samples) => {
                    scans++;
                    AssertVfxNear(body.Center - Vector2.UnitX * 32, start, "LaserScan starts at shifted origin");
                    AssertVfxNear(Vector2.UnitX, direction, "LaserScan retains explicit aim axis");
                    BeamNear(64, max, "offset does not consume or extend raycast length budget");
                    BeamNear(8, width, "offset does not change raycast width");
                    samples[0] = 48; samples[1] = 24; samples[2] = 32;
                }));
            var geometry = BeamGeometry(host);
            Equal(1, scans, "one shared bounded native scan");
            AssertVfxNear(body.Center - Vector2.UnitX * 32, geometry.Start, "clipping preserves shifted start");
            AssertVfxNear(body.Center - Vector2.UnitX * 8, geometry.End, "shortest ray clips from shifted start");
            Equal(true, host.TryCapturePresentationGeometry("beam", out var path), "clipped shifted VFX line exists");
            AssertVfxNear(geometry.Start, path[0], "clipped VFX origin remains shared");
            AssertVfxNear(geometry.End, path[1], "clipped VFX endpoint remains shared");
        });
    }

    private static void BeamAxialOriginAdmissionIsStrictAndHistoricalAbsenceRoundtrips()
    {
        var baseline = MotionDefinition("""
          {"aim":{"source":"initial","turnOwner":false},
           "beamGeometry":{"lengthPx":64,"widthPx":8,"raycastTiles":false}}
          """);
        var root = JsonNode.Parse(baseline.ToJson())!.AsObject();
        var geometry = FrontHandEntity(root)["beamGeometry"]!.AsObject();
        Equal(false, geometry.ContainsKey("startOffsetPx"), "historical absent offset stays absent after native roundtrip");
        foreach (string valid in new[] { "0", "-0", "0e-100", "1e-45", "-1e-45" }) {
            geometry["startOffsetPx"] = JsonNode.Parse(valid);
            var accepted = GeneratedItemData.FromJson(root.ToJsonString());
            Equal(true, accepted is not null, "zero or representable subnormal offset admits " + valid);
            var offset = accepted!.RuntimeProgram.TryGetEntity(accepted.RuntimeProgram.PrimaryEntityId)!.BeamGeometry!.StartOffsetPx;
            Equal(true, offset.HasValue, "explicit offset presence survives " + valid);
            float stored = offset.GetValueOrDefault();
            if (valid == "1e-45") Equal(true, stored > 0, "positive representable subnormal does not collapse");
            else if (valid == "-1e-45") Equal(true, stored < 0, "negative representable subnormal does not collapse");
            else Equal(0f, stored, "explicit mathematical zero remains neutral " + valid);
        }
        foreach (string invalid in new[] { "null", "true", "\"-32\"", "-30720.001", "30720.001", "{}", "1e-100", "-1e-100" }) {
            geometry["startOffsetPx"] = JsonNode.Parse(invalid);
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "strict native offset refusal " + invalid);
        }
        geometry.Remove("startOffsetPx");
        geometry["startOffsetBlocks"] = -2;
        Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "Author units are not accepted as native wire keys");
        geometry.Remove("startOffsetBlocks");
        geometry["futureOrigin"] = 1;
        Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "unknown origin key stays fail closed");
    }
}
