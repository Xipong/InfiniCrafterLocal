#nullable enable
using System;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;
using Terraria.GameContent;
using Terraria.ID;

namespace ResonanceLattice.Core;

/// <summary>
/// World-space rendering of the lattice: jagged energy arcs along network edges and a glow
/// at every charged node, drawn in <see cref="PostDrawTiles"/> so they sit under entities.
/// Runs on every machine; clients use the synced node charges.
/// </summary>
public sealed partial class LatticeWorldSystem
{
    public override void PostDrawTiles()
    {
        if (Networks.Count == 0)
            return;
        EnsureGraph();

        SpriteBatch spriteBatch = Main.spriteBatch;
        Texture2D pixel = TextureAssets.MagicPixel.Value;
        var screen = new Rectangle((int)Main.screenPosition.X - 160, (int)Main.screenPosition.Y - 160, Main.screenWidth + 320, Main.screenHeight + 320);
        uint frameBucket = Main.GameUpdateCount / 2u;

        for (int n = 0; n < Networks.Count; n++)
        {
            LatticeNetwork network = Networks[n];
            float fraction = MathHelper.Clamp(network.TotalCharge() / Math.Max(1f, network.Capacity), 0f, 1f);
            bool surging = network.IsSurging;
            if (fraction <= 0.02f && !surging)
                continue;

            Color edgeColor = surging
                ? Color.Lerp(new Color(255, 90, 60), Color.White, (float)Math.Sin(Main.GameUpdateCount * 0.3) * 0.5f + 0.5f)
                : Color.Lerp(new Color(50, 90, 255), new Color(140, 240, 255), fraction);
            float alpha = surging ? 0.9f : 0.2f + 0.7f * fraction;
            float width = (surging ? 3f : 2f) + 2f * fraction;

            for (int e = 0; e < network.Edges.Count; e++)
            {
                (LatticeNode a, LatticeNode b) = network.Edges[e];
                if (!EdgeOnScreen(a.WorldCenter, b.WorldCenter, screen))
                    continue;
                DrawJaggedBeam(spriteBatch, pixel, a.WorldCenter, b.WorldCenter, edgeColor * alpha, width, e * 131 + n * 17 + (int)frameBucket);
            }

            for (int i = 0; i < network.Nodes.Count; i++)
            {
                LatticeNode node = network.Nodes[i];
                Vector2 c = node.WorldCenter;
                if (!screen.Contains((int)c.X, (int)c.Y))
                    continue;
                float nodeFraction = MathHelper.Clamp(node.Charge / LatticeLimits.NodeCapacity, 0f, 1f);
                if (nodeFraction <= 0.02f && !surging)
                    continue;
                int size = 4 + (int)(6f * nodeFraction);
                var rect = new Rectangle((int)c.X - size / 2, (int)c.Y - size / 2, size, size);
                spriteBatch.Draw(pixel, rect, (surging ? Color.White : new Color(170, 245, 255)) * (0.35f + 0.65f * nodeFraction));
                if (surging && Main.rand.NextBool(4))
                    Dust.NewDust(c - new Vector2(8, 8), 16, 16, DustID.Electric, 0f, 0f, 100, default, 1f);
            }
        }
    }

    private static bool EdgeOnScreen(Vector2 a, Vector2 b, Rectangle screen)
    {
        int minX = (int)Math.Min(a.X, b.X) - 32;
        int maxX = (int)Math.Max(a.X, b.X) + 32;
        int minY = (int)Math.Min(a.Y, b.Y) - 32;
        int maxY = (int)Math.Max(a.Y, b.Y) + 32;
        return maxX >= screen.X && minX <= screen.X + screen.Width && maxY >= screen.Y && minY <= screen.Y + screen.Height;
    }

    /// <summary>Draw a 3-segment jagged beam between two points using the 1x1 magic pixel.</summary>
    private static void DrawJaggedBeam(SpriteBatch spriteBatch, Texture2D pixel, Vector2 from, Vector2 to, Color color, float width, int seed)
    {
        var rng = new Random(seed);
        Vector2 dir = to - from;
        float length = dir.Length();
        if (length < 1f)
            return;
        Vector2 normal = Vector2.Normalize(new Vector2(-dir.Y, dir.X));
        Vector2 previous = from;
        const int segments = 3;
        for (int i = 1; i <= segments; i++)
        {
            Vector2 point = i == segments ? to : Vector2.Lerp(from, to, i / (float)segments) + normal * (rng.NextFloat(-1f, 1f) * length * 0.08f);
            Vector2 segment = point - previous;
            float segLength = segment.Length();
            if (segLength > 0.5f)
            {
                spriteBatch.Draw(
                    pixel,
                    previous,
                    pixel.Bounds(),
                    color,
                    segment.ToRotation(),
                    Vector2.Zero,
                    new Vector2(segLength, width),
                    SpriteEffects.None,
                    0f);
            }
            previous = point;
        }
    }
}
