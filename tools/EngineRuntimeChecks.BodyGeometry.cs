using System;
using System.Collections.Generic;
using System.Reflection;
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
            var asset = (ReLogic.Content.Asset<Texture2D>)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(ReLogic.Content.Asset<Texture2D>));
            foreach (var field in asset.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic))
                if (field.FieldType == typeof(Texture2D)) field.SetValue(asset, texture);
            asset.GetType().GetProperty("State")!.SetValue(asset, ReLogic.Content.AssetState.Loaded);
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

    private static Rectangle BodyTarget(Vector2 point) => new((int)point.X - 2, (int)point.Y - 2, 4, 4);

    private static void RuntimeBeamBodyMatchesCollisionGeometry()
    {
        WithPlayer((owner, _) => WithBodyGeometryQueue((count, positions) =>
        {
            var oldOwner = Terraria.Main.player[0];
            try
            {
                owner.active = true; owner.whoAmI = 0; owner.position = new Vector2(300, 300);
                Terraria.Main.player[0] = owner;
                foreach (Vector2 aim in new[] { Vector2.UnitX, Vector2.UnitY, new Vector2(-3, 4) })
                foreach (float range in new[] { 0.5f, 20f })
                {
                    var entity = Entity(); entity.Visual.AssetMode = "runtime_geometry";
                    entity.Controller.Code = RuntimeControllerCode.ChannelBeam;
                    entity.Controller.Params.RangeTiles = range; entity.Controller.Params.WidthPx = range < 1f ? 1f : 12f;
                    var projectile = new Projectile { owner = 0, velocity = aim, Center = new Vector2(900, 900), scale = 3f, rotation = 2f, gfxOffY = 17f };
                    var generated = Attach(projectile);
                    generated.Configure(new GeneratedItemData(), entity, 0, 8, Vector2.UnitX);
                    Vector2 direction = aim.SafeNormalize(Vector2.UnitX);
                    Vector2 start = owner.MountedCenter + direction * 18f;
                    Vector2 end = start + direction * Math.Max(16f, range * 16f);
                    float width = Math.Max(2f, entity.Controller.Params.WidthPx);
                    int before = count(); DrawBodyGeometry(generated);
                    Equal(before + 1, count(), "one beam body quad");
                    AssertBodySegment(positions(before), start, end, width);
                    foreach (Vector2 point in new[] { start, (start + end) * 0.5f, end })
                        Equal(true, generated.Colliding(default, BodyTarget(point)) == true, "real collision includes rendered beam endpoint/interior");
                    Equal(true, generated.Colliding(default, BodyTarget(end + direction * 40f)) == false, "no collision past rendered beam");
                    Equal(true, generated.Colliding(default, BodyTarget((start + end) * 0.5f + new Vector2(-direction.Y, direction.X) * (width + 20f))) == false, "no collision outside beam width");
                    foreach (string mode in new[] { "baked_sprite", "reuse_item_icon", "no_asset" })
                    {
                        entity.Visual.AssetMode = mode; DrawBodyGeometry(generated);
                        Equal(before + 1, count(), "non-runtime modes never synthesize geometry for absent PNG");
                    }
                }
            }
            finally { Terraria.Main.player[0] = oldOwner; }
        }));
    }

    private static void RuntimeOrdinaryBodyPreservesForwardAndSpinGeometry()
    {
        WithBodyGeometryQueue((count, positions) =>
        {
            foreach (Vector2 direction in new[] { Vector2.UnitX, Vector2.UnitY, -Vector2.UnitX })
            foreach (int movement in new[] { 0, 14, 16, 17 })
            {
                var projectile = new Projectile { Center = new Vector2(100, 120), velocity = direction,
                    rotation = direction.ToRotation() + MathHelper.PiOver2, scale = 1f };
                var generated = Attach(projectile);
                var entity = Entity(); entity.Visual.AssetMode = "runtime_geometry";
                entity.Movement.Code = movement; entity.Hitbox.WidthPx = 30; entity.Hitbox.HeightPx = 20;
                generated.Configure(new GeneratedItemData(), entity, 0, 8, direction);
                int index = count(); DrawBodyGeometry(generated);
                Equal(index + 1, count(), "ordinary body retains one quad");
                Vector2 axis = movement is 14 or 16 or 17 ? projectile.rotation.ToRotationVector2() : direction;
                AssertBodySegment(positions(index), projectile.Center - axis * 15f, projectile.Center + axis * 15f, 7f);
                Equal(true, generated.Colliding(default, BodyTarget(projectile.Center)) is null, "ordinary body retains vanilla collision return");
            }
        });
    }

    private static void RuntimeWhipBodyMatchesLiveCollisionPoints()
    {
        WithPlayer((owner, _) => WithBodyGeometryQueue((count, positions) =>
        {
            var oldOwner = Terraria.Main.player[0];
            try
            {
                owner.active = true; owner.whoAmI = 0; owner.direction = 1; owner.position = new Vector2(300, 300);
                owner.itemAnimationMax = 20; owner.itemAnimation = 10; Terraria.Main.player[0] = owner;
                var entity = Entity(); entity.Visual.AssetMode = "runtime_geometry";
                entity.Kind = RuntimeEntityKind.OwnerAttachedProjectile;
                entity.Movement.Name = "move_whip_lash"; entity.Movement.Code = 18;
                entity.Movement.Params.RangeTiles = 10f; entity.Movement.Params.Segments = 12;
                entity.Hitbox.WidthPx = 20; entity.Hitbox.HitboxScale = 1.5f;
                var projectile = new Projectile { owner = 0, width = 12, height = 12, scale = 3f, gfxOffY = 17f };
                var generated = Attach(projectile); generated.Configure(new GeneratedItemData(), entity, 0, 8, Vector2.UnitX);
                var points = (List<Vector2>)typeof(GeneratedProjectile).GetField("_whipPoints", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(generated)!;
                DrawBodyGeometry(generated); Equal(0, count(), "uninitialized whip invents no short body/trail");
                Equal(true, generated.Colliding(default, BodyTarget(projectile.Center)) is null, "empty whip retains vanilla collision return");
                points.Add(owner.MountedCenter); DrawBodyGeometry(generated); Equal(0, count(), "one point invents no segment"); points.Clear();
                foreach (float multiplier in new[] { 0.75f, 1.5f })
                {
                    owner.whipRangeMultiplier = multiplier; generated.AI();
                    Equal(13, points.Count, "real AI authored segment count");
                    int before = count(); DrawBodyGeometry(generated);
                    Equal(before + points.Count - 1, count(), "one quad per actual whip segment");
                    for (int i = 1; i < points.Count; i++)
                    {
                        AssertBodySegment(positions(before + i - 1), points[i - 1], points[i], 15f);
                        Equal(true, generated.Colliding(default, BodyTarget((points[i - 1] + points[i]) * 0.5f)) == true, "real collision at each rendered segment");
                    }
                    Equal(true, generated.Colliding(default, BodyTarget(points[^1])) == true, "real collision at rendered whip tip");
                    Equal(true, generated.Colliding(default, BodyTarget(points[^1] + new Vector2(1000, 1000))) == false, "outside whip rejects collision");
                }
                entity.Hitbox.WidthPx = 2; entity.Hitbox.HitboxScale = 0.5f;
                int index = count(); DrawBodyGeometry(generated);
                AssertBodySegment(positions(index), points[0], points[1], 4f);
                typeof(GeneratedProjectile).GetField("_activationDelayTicks", BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(generated, 1);
                Equal(true, generated.Colliding(default, BodyTarget(points[^1])) == false, "activation delay collision guard unchanged");
            }
            finally { Terraria.Main.player[0] = oldOwner; }
        }));
    }
}
