#nullable enable
using System;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    private float ContactGeometryAngle()
    {
        var shape = _entity!.ContactGeometry!;
        return shape.AngleRadians + (shape.Orientation == "velocity"
            ? Projectile.velocity.SafeNormalize(_initialDirection).ToRotation() : 0f);
    }

    private bool ContactGeometryCollides(Rectangle target)
    {
        var shape = _entity!.ContactGeometry!;
        float scale = _entity.Hitbox.HitboxScale * HitboxCurveScale();
        float x = shape.LengthPx * scale / 2f, y = shape.WidthPx * scale / 2f;
        float angle = -ContactGeometryAngle();
        Span<Vector2> quad = stackalloc Vector2[4];
        quad[0] = new Vector2(target.Left, target.Top);
        quad[1] = new Vector2(target.Right, target.Top);
        quad[2] = new Vector2(target.Right, target.Bottom);
        quad[3] = new Vector2(target.Left, target.Bottom);
        for (int i = 0; i < 4; i++) quad[i] = (quad[i] - Projectile.Center).RotatedBy(angle);
        if (shape.Shape == "ellipse")
        {
            // Transform the rectangle into ellipse unit space. Circle versus
            // convex polygon is exact: center containment or an edge within r.
            for (int i = 0; i < 4; i++) quad[i] /= new Vector2(x, y);
            if (QuadContains(quad, Vector2.Zero)) return true;
            for (int i = 0; i < 4; i++)
                if (SegmentDistanceSquared(Vector2.Zero, quad[i], quad[(i + 1) % 4]) <= 1f) return true;
            return false;
        }
        if (shape.Shape == "capsule")
        {
            Vector2 a = new(-x, 0), b = new(x, 0);
            if (QuadContains(quad, a) || QuadContains(quad, b)) return true;
            for (int i = 0; i < 4; i++)
            {
                Vector2 c = quad[i], d = quad[(i + 1) % 4];
                if (SegmentsIntersect(a, b, c, d)
                    || SegmentDistanceSquared(a, c, d) <= y * y
                    || SegmentDistanceSquared(b, c, d) <= y * y
                    || SegmentDistanceSquared(c, a, b) <= y * y
                    || SegmentDistanceSquared(d, a, b) <= y * y) return true;
            }
            return false;
        }
        // Separating axes from both rectangles; touching boundaries collide.
        if (Separated(quad, Vector2.UnitX, x, y) || Separated(quad, Vector2.UnitY, x, y)) return false;
        for (int i = 0; i < 2; i++)
        {
            Vector2 edge = quad[i + 1] - quad[i];
            if (Separated(quad, new Vector2(-edge.Y, edge.X), x, y)) return false;
        }
        return true;
    }

    private static bool Separated(ReadOnlySpan<Vector2> quad, Vector2 axis, float x, float y)
    {
        float radius = Math.Abs(axis.X) * x + Math.Abs(axis.Y) * y;
        float low = float.PositiveInfinity, high = float.NegativeInfinity;
        foreach (Vector2 point in quad) { float dot = Vector2.Dot(point, axis); low = Math.Min(low, dot); high = Math.Max(high, dot); }
        return low > radius || high < -radius;
    }
    private static float Cross(Vector2 a, Vector2 b) => a.X * b.Y - a.Y * b.X;
    private static bool QuadContains(ReadOnlySpan<Vector2> quad, Vector2 point)
    {
        bool positive = false, negative = false;
        for (int i = 0; i < 4; i++) { float c = Cross(quad[(i + 1) % 4] - quad[i], point - quad[i]); positive |= c > 0; negative |= c < 0; }
        return !(positive && negative);
    }
    private static float SegmentDistanceSquared(Vector2 point, Vector2 a, Vector2 b)
    {
        Vector2 delta = b - a;
        float t = delta.LengthSquared() <= 1e-12f ? 0 : Math.Clamp(Vector2.Dot(point - a, delta) / delta.LengthSquared(), 0, 1);
        return Vector2.DistanceSquared(point, a + delta * t);
    }
    private static bool SegmentsIntersect(Vector2 a, Vector2 b, Vector2 c, Vector2 d)
    {
        float determinant = Cross(b - a, d - c);
        if (Math.Abs(determinant) < 1e-8f) return false;
        float t = Cross(c - a, d - c) / determinant, u = Cross(c - a, b - a) / determinant;
        return t >= 0 && t <= 1 && u >= 0 && u <= 1;
    }
}
