using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static RuntimeBodyGeometrySpec ExplicitBody(string source = "body_segment") => new() {
        Schema = "infini.body-geometry.v1", Source = source, WidthPx = .5f, Color = "#13579B", Opacity = .4f,
        LengthPx = source == "body_segment" ? 37f : null, Axis = source == "body_segment" ? "rotation" : null,
    };

    private static void ExplicitBodyGeometryAdmission()
    {
        string good = JsonSerializer.Serialize(ExplicitBody());
        Equal(good, JsonSerializer.Serialize(JsonSerializer.Deserialize<RuntimeBodyGeometrySpec>(good)), "explicit body geometry exact wire roundtrip");
        string path = JsonSerializer.Serialize(ExplicitBody("collision_path"));
        Equal(path, JsonSerializer.Serialize(JsonSerializer.Deserialize<RuntimeBodyGeometrySpec>(path)), "collision path exact wire roundtrip");
        foreach (string invalid in new[] {
            "null", "{}", good.Replace("37", "null"), good.Replace("37", "0"), good.Replace("37", "4097"),
            good.Replace("0.5", "1025"), good.Replace("0.4", "-1"), good.Replace("#13579B", "white"),
            good.Replace("rotation", "auto"), good.Replace("body_segment", "sword"), good.Replace("v1", "v2"),
            good.Replace("\"opacity\":0.4,", ""), good.Replace("\"axis\":\"rotation\"", "\"axis\":null"),
            good[..^1] + ",\"widthPx\":2}", good[..^1] + ",\"unknown\":1}", path[..^1] + ",\"axis\":\"rotation\"}",
        }) {
            bool rejected = false;
            try { JsonSerializer.Deserialize<RuntimeBodyGeometrySpec>(invalid); } catch (Exception e) when (e is JsonException or InvalidDataException or InvalidOperationException) { rejected = true; }
            Equal(true, rejected, "malformed present geometry must be refused: " + invalid);
        }
        var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.CamelCase };
        bool nullRejected = false;
        try { JsonSerializer.Deserialize<RuntimeEntityVisualSpec>("{\"geometry\":null}", options); }
        catch (Exception e) when (e is JsonException or InvalidDataException) { nullRejected = true; }
        Equal(true, nullRejected, "present null cannot select an implicit body");
        foreach (string failure in new[] { "mode", "aim", "path", "geometry" }) {
            var entity = new RuntimeEntitySpec { Id = "body", Kind = RuntimeEntityKind.FreeProjectile };
            entity.Movement = new RuntimeMovementSpec { Name = "move_straight", Code = 0 };
            entity.Spawn.Enabled = true;
            entity.VisualRole = entity.Visual.Role = RuntimeEntityKind.VisualRoleFor(entity.Kind);
            entity.Visual.AssetMode = "runtime_geometry";
            entity.Visual.Geometry = ExplicitBody(failure == "path" ? "collision_path" : "body_segment");
            if (failure == "aim") {
                entity.Visual.Geometry.Axis = "aim";
                entity.Aim = new RuntimeMotionAimSpec { Source = "facing", TurnOwner = true };
            }
            if (failure == "path") {
                entity.Aim = new RuntimeMotionAimSpec { Source = "facing", TurnOwner = true };
                entity.BeamGeometry = new RuntimeBeamGeometrySpec { LengthPx = 90, WidthPx = 12, RaycastTiles = false };
            }
            entity.NormalizeAndValidate(new RuntimeLimitsSpec());
            // Each negative differs from an admitted fixture in one dependency only.
            if (failure == "mode") entity.Visual.AssetMode = "no_asset";
            else {
                var missingDependency = JsonSerializer.SerializeToNode(entity, options)!.AsObject();
                missingDependency.Deserialize<RuntimeEntitySpec>(options)!.NormalizeAndValidate(new RuntimeLimitsSpec());
                var dependencyOwner = failure == "geometry" ? missingDependency["visual"]!.AsObject() : missingDependency;
                Equal(true, dependencyOwner.Remove(failure == "geometry" ? "geometry" : failure == "aim" ? "aim" : "beamGeometry"),
                    "negative removes exactly the admitted dependency");
                entity = missingDependency.Deserialize<RuntimeEntitySpec>(options)!;
            }
            bool refused = false;
            try { entity.NormalizeAndValidate(new RuntimeLimitsSpec()); }
            catch (InvalidDataException) { refused = true; }
            Equal(true, refused, "native admission enforces geometry dependency: " + failure);
            if (failure == "geometry") {
                entity.Visual.AssetMode = "no_asset";
                entity.NormalizeAndValidate(new RuntimeLimitsSpec());
                Equal(null, entity.Visual.Geometry, "explicit no_asset needs no body design");
            }
        }
        string delivered = BeamFixture(false).ToNetworkJson();
        Equal(true, GeneratedItemData.FromJson(delivered) is not null, "current explicit body admits through full native delivery reader");
        var missing = JsonNode.Parse(delivered)!.AsObject();
        Equal(true, FrontHandEntity(missing)["visual"]!.AsObject().Remove("geometry"), "remove only final body's geometry");
        Equal(true, GeneratedItemData.FromJson(missing.ToJsonString()) is null, "full native reader refuses absent body geometry");
        Equal(true, ContractJsonDiagnostics.LastError?.Message.Contains("explicit body geometry", StringComparison.Ordinal) == true, "refusal is caused by missing geometry");
    }

    private static void ExplicitBodyGeometryDrawsAuthoredDimensionsAndActualPath()
    {
        WithPlayer((owner, _) => WithVfxGeometryQueue((batch, texture, count, positions, colors) => {
            using var actors = new NativeActorState();
            var oldPixel = Terraria.GameContent.TextureAssets.MagicPixel;
            Terraria.GameContent.TextureAssets.MagicPixel = CpuTextureAsset(texture);
            try {
                owner.active = true; owner.whoAmI = 0; owner.direction = -1; Terraria.Main.player[0] = owner;
                var data = GeneratedItemData.Placeholder(); data.VfxManifest = VfxManifestSpec.Empty();
                var entity = new RuntimeEntitySpec { Id = "body", Kind = RuntimeEntityKind.FreeProjectile };
                entity.Visual.AssetMode = "runtime_geometry"; entity.Visual.Geometry = ExplicitBody();
                entity.Hitbox.WidthPx = 100; entity.Hitbox.HeightPx = 80; entity.LifetimeTicks = 120;
                entity.Light.Color = "#FF0000";
                data.RuntimeProgram.Entities = new[] { entity };
                var projectile = new Projectile { owner = 0, active = true, Center = new Vector2(150, 180), velocity = new Vector2(0, 4), rotation = .3f };
                var generated = Attach(projectile); generated.Configure(data, entity, 0, 8, Vector2.UnitX);
                projectile.rotation = .3f; projectile.scale = 3; projectile.alpha = 200;
                foreach (string axisName in new[] { "rotation", "velocity", "aim" }) {
                    entity.Visual.Geometry.Axis = axisName;
                    if (axisName == "aim") entity.Aim = new RuntimeMotionAimSpec { Source = "facing", TurnOwner = true };
                    Vector2 axis = axisName == "rotation" ? projectile.rotation.ToRotationVector2() : axisName == "velocity" ? Vector2.UnitY : -Vector2.UnitX;
                    string before = JsonSerializer.Serialize(data); int direction = owner.direction; int index = count();
                    DrawBodyGeometry(generated);
                    Equal(index + 1, count(), "one explicit segment");
                    AssertBodySegment(positions(index), projectile.Center - axis * 18.5f, projectile.Center + axis * 18.5f, .5f);
                    foreach (Color c in colors(index)) Equal(new Color(19,87,155) * .4f, c, "explicit RGBA independent of Light and projectile alpha");
                    Equal(before, JsonSerializer.Serialize(data), "drawing never edits model data");
                    Equal(direction, owner.direction, "aim presentation does not turn player");
                    Equal(3f, projectile.scale, "presentation never changes scale");
                }
                entity.Visual.Geometry = ExplicitBody("collision_path");
                entity.LashGeometry = new() { Clock = "owner_animation", Anchor = "owner_center", ReachPx = 96,
                    Segments = 16, SweepStartRadians = -1.2f, SweepEndRadians = 1.2f, BendRatio = .2f,
                    UseOwnerGravity = false, UseOwnerWhipRangeMultiplier = false };
                typeof(GeneratedProjectile).GetMethod("BuildLashPoints", TestInstance)!.Invoke(generated,
                    new object[] { new Vector2(30,40), Vector2.UnitX, .35f, 96f, 16, -1.2f, 1.2f, .2f, 1f, 1, 1f });
                var points = (List<Vector2>)typeof(GeneratedProjectile).GetField("_whipPoints", TestInstance)!.GetValue(generated)!;
                var frozen = points.ToArray(); int first = count(); DrawBodyGeometry(generated);
                Equal(first + points.Count - 1, count(), "explicit skin follows all native lash segments");
                for (int i = 1; i < points.Count; i++) AssertBodySegment(positions(first+i-1), points[i-1], points[i], .5f);
                for (int i = 0; i < points.Count; i++) Equal(frozen[i], points[i], "skin never changes collision path");
                entity.Visual = new RuntimeEntityVisualSpec { AssetMode = "runtime_geometry" };
                first = count(); DrawBodyGeometry(generated);
                Equal(first, count(), "missing body geometry refuses drawing instead of inferring a skin from collision");
                Equal(null, entity.Visual.Geometry, "refused drawing never authors geometry");
                entity.Visual.Geometry = ExplicitBody("collision_path");
                entity.BeamGeometry = new RuntimeBeamGeometrySpec { LengthPx = 90, WidthPx = 12, RaycastTiles = false };
                entity.Aim = new RuntimeMotionAimSpec { Source = "cursor", TurnOwner = true };
                projectile.ai[0] = 1; projectile.ai[1] = 0; owner.direction = -1;
                first = count(); DrawBodyGeometry(generated);
                Equal(first+1,count(),"beam takes shared collision precedence over authored lash");
                AssertBodySegment(positions(first),projectile.Center,projectile.Center+Vector2.UnitX*90,.5f);
                Equal(-1,owner.direction,"read-only beam geometry does not turn player");

            } finally { Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; }
        }));
    }
}
