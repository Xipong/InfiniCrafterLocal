using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Projectiles;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void WithBodyGeometryQueue(Action<Func<int>, Func<int, Vector3[]>> check)
    {
        WithVfxGeometryQueue((batch, texture, count, positions, colors) =>
        {
            var oldPixel = Terraria.GameContent.TextureAssets.MagicPixel;
            var asset = CpuTextureAsset(texture);
            try { Terraria.GameContent.TextureAssets.MagicPixel = asset; check(count, positions); }
            finally { Terraria.GameContent.TextureAssets.MagicPixel = oldPixel; }
        });
    }

    private static void DrawBodyGeometry(GeneratedProjectile generated)
        => typeof(GeneratedProjectile).GetMethod("DrawAuthoredEntityVisual", BindingFlags.Instance | BindingFlags.NonPublic)!
            .Invoke(generated, new object[] { Color.White });

    private static void AssertBodySegment(Vector3[] vertices, Vector2 start, Vector2 end, float width)
    {
        start -= Terraria.Main.screenPosition; end -= Terraria.Main.screenPosition;
        AssertVfxNear((start + end) * 0.5f, VfxVertexCenter(vertices), "body segment midpoint");
        Vector2 direction = Vector2.Normalize(end - start), normal = new(-direction.Y, direction.X);
        float minAlong = float.MaxValue, maxAlong = float.MinValue, minAcross = float.MaxValue, maxAcross = float.MinValue;
        foreach (var vertex in vertices)
        {
            Vector2 relative = new Vector2(vertex.X, vertex.Y) - start;
            float along = Vector2.Dot(relative, direction), across = Vector2.Dot(relative, normal);
            minAlong = Math.Min(minAlong, along); maxAlong = Math.Max(maxAlong, along);
            minAcross = Math.Min(minAcross, across); maxAcross = Math.Max(maxAcross, across);
        }
        Equal(true, Math.Abs(minAlong) < 0.002f && Math.Abs(maxAlong - Vector2.Distance(start, end)) < 0.002f, "body endpoints match collision segment");
        Equal(true, Math.Abs(minAcross + width * 0.5f) < 0.002f && Math.Abs(maxAcross - width * 0.5f) < 0.002f, "body width matches collision width");
    }

    private static void TexturedBodyUsesDeclaredAxisAndPreservesNativeSpin()
    {
        WithPlayer((owner, _) => WithVfxGeometryQueue((batch, _, count, positions, _) =>
        {
            using var actors = new NativeActorState();
            using var cache = new BorrowedSpriteCache();
            Texture2D body = CpuTexture(64, 8), root = CpuTexture(128, 16);
            string bodyPath = Path.Combine(Terraria.Program.SavePath, "body.png"), rootPath = Path.Combine(Terraria.Program.SavePath, "root.png");
            cache.Textures.Add(bodyPath, Activator.CreateInstance(cache.Record, body, 0f, 0L)!);
            cache.Textures.Add(rootPath, Activator.CreateInstance(cache.Record, root, 0f, 0L)!);
            owner.active = true; owner.whoAmI = 0; owner.position = new Vector2(300, 300); owner.channel = true;
            Terraria.Main.player[0] = owner; Terraria.Main.myPlayer = 1;
            Terraria.Main.netMode = Terraria.ID.NetmodeID.SinglePlayer;
            var cases = new[] {
                (Name: "straight-right/entity-axis", Move: 0, Facing: 1, Reuse: false, Modern: true, Scale: 1.7f, Offset: (float?)null, Axis: 45f),
                (Name: "straight-left/signed-axis", Move: 0, Facing: -1, Reuse: false, Modern: true, Scale: 1.7f, Offset: (float?)null, Axis: 45f),
                (Name: "thrust-19/held-axis", Move: 19, Facing: -1, Reuse: false, Modern: true, Scale: 1.7f, Offset: (float?)null, Axis: 45f),
                (Name: "glaive-14/native-spin", Move: 14, Facing: -1, Reuse: false, Modern: true, Scale: 1.7f, Offset: (float?)null, Axis: 45f),
                (Name: "reuse-root/independent-selector-and-clamp", Move: 0, Facing: -1, Reuse: true, Modern: true, Scale: 0.01f, Offset: (float?)null, Axis: 45f),
                (Name: "legacy-absence/raw-native-pose", Move: 0, Facing: 1, Reuse: false, Modern: false, Scale: 1.7f, Offset: (float?)null, Axis: 45f),
            }.Concat(from axis in new[] { 0f, -90f }
                from facing in new[] { -1, 1 }
                from offset in new[] { 0f, 1.57f }
                select (Name: $"explicit-velocity/axis={axis}/facing={facing}/offset={offset}",
                    Move: 0, Facing: facing, Reuse: false, Modern: true, Scale: 1.7f,
                    Offset: (float?)offset, Axis: axis)).ToArray();
            foreach (var c in cases)
            {
                string label = c.Name + ": ";
                var data = GeneratedItemData.Placeholder(); data.Id = "textured_body_axis";
                data.VfxManifest = VfxManifestSpec.Empty();
                data.Visual.SpritePath = rootPath;
                data.RuntimeProgram.PrimaryEntityId = "body"; data.RuntimeProgram.PrimaryOwner = RuntimeProgramSpec.ProjectileOwner;
                var entity = new RuntimeEntitySpec { Id = "body", Kind = c.Move == 19 ? RuntimeEntityKind.OwnerAttachedProjectile : RuntimeEntityKind.FreeProjectile };
                entity.Visual.AssetMode = c.Reuse ? "reuse_item_icon" : "baked_sprite";
                entity.Visual.SpritePath = bodyPath; entity.Visual.SpriteStatus = "generated";
                entity.Movement.Code = c.Move;
                entity.Movement.Name = c.Move == 19 ? "move_forward_then_retract" : c.Move == 14 ? "move_returning_glaive" : "move_straight";
                entity.Movement.Params.RangeTiles = 5; entity.Movement.Params.DurationTicks = 30; entity.Movement.Params.ReturnAfterTicks = 60;
                entity.Hitbox.WidthPx = entity.Hitbox.HeightPx = 24; entity.LifetimeTicks = 120;
                data.RuntimeProgram.Entities = new[] { entity };
                if (c.Modern)
                {
                    data.Visual.RenderSizePx = 80; data.Visual.ForwardAngleDegrees = -30;
                    entity.Visual.RenderSizePx = 40; entity.Visual.ForwardAngleDegrees = c.Axis;
                }
                if (c.Offset is { } authoredOffset)
                    entity.Rotation = new RuntimeRotationSpec { Mode = "velocity", OffsetRadians = authoredOffset };
                Vector2 aim = Vector2.Normalize(new Vector2(-3, 4));
                var projectile = new Projectile { owner = 0, whoAmI = 7, active = true, Center = new Vector2(400), velocity = aim, rotation = 0.23f, spriteDirection = c.Facing };
                var generated = Attach(projectile);
                generated.Configure(data, entity, 0, 8, aim); generated.AI(); projectile.scale = c.Scale;
                float rotation = projectile.rotation, scale = projectile.scale;
                Vector2 velocity = projectile.velocity, center = projectile.Center;
                int width = projectile.width, height = projectile.height;
                string definition = JsonSerializer.Serialize(data);
                int index = count(); Color light = Color.White;
                Equal(false, generated.PreDraw(ref light), label + "public PreDraw suppresses vanilla proxy");
                if (!c.Modern) {
                    Equal(index, count(), label + "missing selected PNG metadata refuses draw instead of using historical native-frame scale");
                    Equal(rotation, projectile.rotation, label + "refused draw preserves native rotation");
                    Equal(scale, projectile.scale, label + "refused draw preserves physics scale");
                    continue;
                }
                Equal(index + 1, count(), label + "one selected authored texture quad");
                float degrees = !c.Modern ? 0 : c.Reuse ? -30 : c.Axis;
                Vector2 actual = BodyForwardFromCpuQueue(batch, index, degrees, label);
                float radians = degrees * MathF.PI / 180;
                Vector2 native = new Vector2(MathF.Cos(radians) * c.Facing, MathF.Sin(radians)).RotatedBy(rotation);
                Vector2 expected = c.Offset is { } offset ? aim.RotatedBy(offset) : c.Modern && c.Move != 14 ? aim : native;
                AssertVfxNear(expected, actual, label + "UV-derived declared forward");
                Equal(rotation, projectile.rotation, label + "draw preserves native rotation");
                Equal(scale, projectile.scale, label + "draw preserves physics scale");
                Equal(velocity, projectile.velocity, label + "draw preserves velocity");
                Equal(width, projectile.width, label + "draw preserves hitbox width");
                Equal(height, projectile.height, label + "draw preserves hitbox height");
                Equal(center, projectile.Center, label + "draw preserves center");
                Equal(definition, JsonSerializer.Serialize(data), label + "draw preserves authored definition");
                float longest = 0;
                var quad = positions(index);
                foreach (var a in quad) foreach (var b in quad) longest = Math.Max(longest, Vector3.Distance(a, b));
                float baseSize = !c.Modern ? 64 : c.Reuse ? 80 : 40;
                float expectedDiagonal = baseSize * Math.Clamp(c.Scale, 0.1f, 8f) * MathF.Sqrt(1 + 1f / 64);
                Equal(true, Math.Abs(longest - expectedDiagonal) < 0.001, label + "selected authored size independent of texture canvas");
                var queued = (Array)typeof(SpriteBatch).GetField("textureInfo", TestInstance)!.GetValue(batch)!;
                Equal(true, ReferenceEquals(c.Reuse ? root : body, queued.GetValue(index)), label + "actual root/entity texture selected");
                if (c.Move == 19) Equal(7, owner.heldProj, label + "real thrust claims held projectile");
                Console.WriteLine($"PASS textured body scenario: {c.Name}");
            }
        }));
    }

    // Recover signed texture axes from the actual paired FNA UVs/positions,
    // not the quad's principal axis, which would hide SpriteEffects flips.
    private static Vector2 BodyForwardFromCpuQueue(SpriteBatch batch, int index, float degrees, string label)
    {
        var vertices = (Array)typeof(SpriteBatch).GetField("vertexInfo", TestInstance)!.GetValue(batch)!;
        var value = vertices.GetValue(index)!;
        Vector3[] p = CpuVertexValues<Vector3>(value); Vector2[] uv = CpuVertexValues<Vector2>(value);
        Equal(4, p.Length, label + "FNA ABI four positions"); Equal(4, uv.Length, label + "FNA ABI four paired UVs");
        Vector2 Basis(bool vertical)
        {
            float min = uv.Min(v => vertical ? v.Y : v.X), max = uv.Max(v => vertical ? v.Y : v.X);
            Equal(true, max - min > 0.9f, label + "full frame UV extent");
            Vector2 low = Vector2.Zero, high = Vector2.Zero; int nl = 0, nh = 0;
            for (int i = 0; i < 4; i++)
            {
                float v = vertical ? uv[i].Y : uv[i].X; Vector2 pos = new(p[i].X, p[i].Y);
                if (Math.Abs(v - min) < 0.001) { low += pos; nl++; }
                if (Math.Abs(v - max) < 0.001) { high += pos; nh++; }
            }
            Equal(2, nl, label + "two low UV vertices"); Equal(2, nh, label + "two high UV vertices");
            return Vector2.Normalize(high / nh - low / nl);
        }
        float angle = degrees * MathF.PI / 180;
        return Vector2.Normalize(Basis(false) * MathF.Cos(angle) + Basis(true) * MathF.Sin(angle));
    }

    private static Rectangle BodyTarget(Vector2 point) => new((int)point.X - 2, (int)point.Y - 2, 4, 4);

}
