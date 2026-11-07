using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    // Real FNA CPU vertices; only FlushBatch is intercepted, before GPU upload.
    private static void WithVfxGeometryQueue(Action<SpriteBatch, Texture2D, Func<int>, Func<int, Vector3[]>, Func<int, Color[]>> check)
    {
        WithLighting((config, _) =>
        {
            const BindingFlags flags = BindingFlags.Instance | BindingFlags.NonPublic;
            var batch = CpuSpriteBatch(128);
            // Deliberately not 1x1: scale must convert source texels to pixels.
            var texture = CpuTexture(2, 3);
            var count = typeof(SpriteBatch).GetField("numSprites", flags)!;
            var vertices = typeof(SpriteBatch).GetField("vertexInfo", flags)!;
            var oldBatch = Terraria.Main.spriteBatch;
            var oldScreen = Terraria.Main.screenPosition;
            Action<SpriteBatch> flush = self => count.SetValue(self, 0);
            using var hook = new MonoMod.RuntimeDetour.Hook(typeof(SpriteBatch).GetMethod("FlushBatch", flags)!, flush);
            T[] Values<T>(int index) => CpuVertexValues<T>(((Array)vertices.GetValue(batch)!).GetValue(index)!);
            try
            {
                config.DrawBudgetMultiplier = 1f;
                Terraria.Main.spriteBatch = batch;
                Terraria.Main.screenPosition = new Vector2(40, 60);
                batch.Begin();
                check(batch, texture, () => (int)count.GetValue(batch)!, Values<Vector3>, Values<Color>);
            }
            finally
            {
                if ((bool)typeof(SpriteBatch).GetField("beginCalled", flags)!.GetValue(batch)!) batch.End();
                Terraria.Main.spriteBatch = oldBatch;
                Terraria.Main.screenPosition = oldScreen;
            }
        });
    }

    private static void AssertVfxNear(Vector2 expected, Vector2 actual, string label)
        => Equal(true, Vector2.Distance(expected, actual) < 0.001f, label + ": expected " + expected + ", got " + actual);

    private static Vector2 VfxVertexCenter(Vector3[] vertices)
    {
        Equal(4, vertices.Length, "one queued quad has four positions");
        Vector2 result = Vector2.Zero;
        foreach (Vector3 vertex in vertices) result += new Vector2(vertex.X, vertex.Y);
        return result / 4f;
    }

}
