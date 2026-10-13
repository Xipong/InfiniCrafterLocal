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

    private static Rectangle BodyTarget(Vector2 point) => new((int)point.X - 2, (int)point.Y - 2, 4, 4);

}
