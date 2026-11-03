#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.RegularExpressions;
using Microsoft.Xna.Framework;
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Common.VFX;
// Bounded cosmetic geometry only. No gameplay/collision authority, generated code or GPU indices in wire.
internal static class VfxContourGeometry
{
    internal readonly record struct Triangle(Vector2 A, Vector2 B, Vector2 C)
    {
        internal Vector2 UvA { get; init; }
        internal Vector2 UvB { get; init; }
        internal Vector2 UvC { get; init; }
    }

    internal const int MaxPoints = 128, MaxTotalPoints = 512, MaxTriangles = 4096;
    private const double Epsilon = 1e-7;
    internal static double Cross(Vector2 a, Vector2 b, Vector2 c) => ((double)b.X - a.X) * ((double)c.Y - a.Y) - ((double)b.Y - a.Y) * ((double)c.X - a.X);
    internal static bool Same(Vector2 a, Vector2 b) => Math.Abs(a.X - b.X) <= 1e-6f && Math.Abs(a.Y - b.Y) <= 1e-6f;
    internal static bool Closed(Vector2[] p) => p.Length > 2 && Same(p[0], p[^1]);
    private static InvalidDataException Error(string message) => new("geometry: " + message);
    internal static Dictionary<string, Vector2[]> Resolve(VfxContourNode[] nodes)
    {
        if (nodes is null || nodes.Length is < 1 or > 16)
            throw Error("contours count must be 1..16");
        var byId = new Dictionary<string, VfxContourNode>(StringComparer.Ordinal);
        foreach (var n in nodes)
        {
            if (n is null || n.Id is null || !Regex.IsMatch(n.Id, @"\A[a-z][a-z0-9_]{0,47}\z") || !byId.TryAdd(n.Id, n))
                throw Error("contour IDs must be unique lowercase identifiers up to 48 characters");
            n.Validate();
        }

        var result = new Dictionary<string, Vector2[]>(StringComparer.Ordinal);
        var visiting = new HashSet<string>();
        int total = 0;
        Vector2[] Get(string id)
        {
            if (result.TryGetValue(id, out var found))
                return found;
            if (!byId.TryGetValue(id, out var n))
                throw Error("unknown contour '" + id + "'");
            if (!visiting.Add(id))
                throw Error("contour reference cycle at '" + id + "'");
            Vector2[] points;
            switch (n.Kind)
            {
                case "line":
                    points = new[]
                    {
                        Point(n.From!),
                        Point(n.To!)
                    };
                    break;
                case "polyline":
                    points = n.Points!.Select(Point).ToArray();
                    break;
                case "ellipseArc":
                    points = new Vector2[n.Segments!.Value + 1];
                    for (int i = 0; i < points.Length; i++)
                    {
                        float a = n.StartRadians!.Value + n.SweepRadians!.Value * i / (points.Length - 1);
                        points[i] = Point(n.Center!) + new Vector2(MathF.Cos(a) * n.RadiusX!.Value, MathF.Sin(a) * n.RadiusY!.Value);
                    }

                    // The full-turn constructor's last endpoint is mathematically identical, not a near-closed polygon.
                    if (Math.Abs(Math.Abs(n.SweepRadians!.Value) - MathF.Tau) < 1e-6f)
                        points[^1] = points[0];
                    break;
                case "transform":
                    points = Get(n.Source!).Select(p => Transform(p, Point(n.Translate!), Point(n.Scale!), n.RotationRadians!.Value)).ToArray();
                    break;
                case "concat":
                    var joined = new List<Vector2>();
                    foreach (var reference in n.Sources!)
                    {
                        var part = Get(reference);
                        if (part.Length == 0)
                            continue;
                        if (joined.Count > 0 && !Same(joined[^1], part[0]))
                            throw Error("concat endpoints do not coincide");
                        joined.AddRange(joined.Count == 0 ? part : part.Skip(1));
                        if (joined.Count > MaxPoints)
                            throw Error("concat exceeds resolved point limit");
                    }

                    points = joined.ToArray();
                    break;
                case "trim":
                    points = Trim(Get(n.Source!), n.Start!.Value, n.End!.Value);
                    break;
                case "close":
                    var source = Get(n.Source!);
                    var list = new List<Vector2>(source);
                    foreach (var p in n.Via!)
                        list.Add(Point(p));
                    if (!Same(list[0], list[^1]))
                        list.Add(list[0]);
                    points = list.ToArray();
                    break;
                default:
                    throw Error("unknown contour kind");
            }

            // Consecutive identical points add no line or area. Only this exact lossless representation normalization is performed.
            points = points.Where((p, i) => i == 0 || !Same(p, points[i - 1])).ToArray();
            if (points.Length > MaxPoints || points.Any(p => !float.IsFinite(p.X) || !float.IsFinite(p.Y) || Math.Abs(p.X) > 8192 || Math.Abs(p.Y) > 8192))
                throw Error("resolved contour exceeds coordinate or point bounds");
            total += points.Length;
            if (total > MaxTotalPoints)
                throw Error("total resolved contour points exceed 512");
            visiting.Remove(id);
            result.Add(id, points);
            return points;
        }

        foreach (var n in nodes)
            Get(n.Id);
        return result;
    }

    internal static Vector2 Point(float[] p) => new(p[0], p[1]);
    internal static Vector2 Transform(Vector2 p, Vector2 translate, Vector2 scale, float rotation)
    {
        p *= scale;
        float c = MathF.Cos(rotation), s = MathF.Sin(rotation);
        return translate + new Vector2(c * p.X - s * p.Y, s * p.X + c * p.Y);
    }

    private static bool On(Vector2 a, Vector2 b, Vector2 p) => Math.Abs(Cross(a, b, p)) <= Epsilon && p.X >= Math.Min(a.X, b.X) - Epsilon && p.X <= Math.Max(a.X, b.X) + Epsilon && p.Y >= Math.Min(a.Y, b.Y) - Epsilon && p.Y <= Math.Max(a.Y, b.Y) + Epsilon;
    private static bool Intersects(Vector2 a, Vector2 b, Vector2 c, Vector2 d)
    {
        double x = Cross(a, b, c), y = Cross(a, b, d), z = Cross(c, d, a), w = Cross(c, d, b);
        return (x > Epsilon && y < -Epsilon || x < -Epsilon && y > Epsilon) && (z > Epsilon && w < -Epsilon || z < -Epsilon && w > Epsilon) || Math.Abs(x) <= Epsilon && On(a, b, c) || Math.Abs(y) <= Epsilon && On(a, b, d) || Math.Abs(z) <= Epsilon && On(c, d, a) || Math.Abs(w) <= Epsilon && On(c, d, b);
    }

    internal static double Area(IReadOnlyList<Vector2> p)
    {
        double a = 0;
        for (int i = 0; i < p.Count; i++)
        {
            var q = p[(i + 1) % p.Count];
            a += (double)p[i].X * q.Y - (double)q.X * p[i].Y;
        }

        return a * .5;
    }

    private static List<Vector2> Polygon(Vector2[] input)
    {
        if (!Closed(input))
            throw Error("fill requires an explicitly closed contour");
        var p = input.Take(input.Length - 1).ToList();
        if (p.Count < 3)
            throw Error("fill needs at least three distinct points");
        for (int i = 0; i < p.Count; i++)
            for (int j = i + 1; j < p.Count; j++)
            {
                if (j == i + 1 || i == 0 && j == p.Count - 1)
                    continue;
                if (Intersects(p[i], p[(i + 1) % p.Count], p[j], p[(j + 1) % p.Count]))
                    throw Error("fill contour intersects or touches itself");
            }

        // Remove only collinear vertices lying between their neighbours; not backtracking edges.
        bool changed = true;
        while (changed && p.Count > 3)
        {
            changed = false;
            for (int i = 0; i < p.Count; i++)
                if (On(p[(i + p.Count - 1) % p.Count], p[(i + 1) % p.Count], p[i]))
                {
                    p.RemoveAt(i);
                    changed = true;
                    break;
                }
        }

        if (Math.Abs(Area(p)) <= Epsilon)
            throw Error("fill contour has zero or numerically ambiguous area");
        if (Area(p) < 0)
            p.Reverse();
        return p;
    }

    private static bool Inside(Vector2 p, Vector2 a, Vector2 b, Vector2 c, bool strict = false)
    {
        double x = Cross(a, b, p), y = Cross(b, c, p), z = Cross(c, a, p);
        return strict ? x > Epsilon && y > Epsilon && z > Epsilon : x >= -Epsilon && y >= -Epsilon && z >= -Epsilon;
    }

    internal static Triangle[] Fill(Vector2[] input)
    {
        input = input.Where((p, i) => i == 0 || !Same(p, input[i - 1])).ToArray();
        if (input.Length <= 1)
            return Array.Empty<Triangle>();
        if (Closed(input) && input.Skip(2).All(p => Math.Abs(Cross(input[0], input[1], p)) <= Epsilon))
            return Array.Empty<Triangle>();
        var p = Polygon(input);
        var triangles = new List<Triangle>();
        while (p.Count > 3)
        {
            bool clipped = false;
            for (int i = 0; i < p.Count; i++)
            {
                int prev = (i + p.Count - 1) % p.Count, next = (i + 1) % p.Count;
                var a = p[prev];
                var b = p[i];
                var c = p[next];
                if (Cross(a, b, c) <= Epsilon)
                    continue;
                bool contains = false;
                for (int j = 0; j < p.Count; j++)
                    if (j != prev && j != i && j != next && Inside(p[j], a, b, c))
                    {
                        contains = true;
                        break;
                    }

                if (contains)
                    continue;
                triangles.Add(new(a, b, c));
                p.RemoveAt(i);
                clipped = true;
                break;
            }

            if (!clipped)
                throw Error("fill triangulation is numerically ambiguous");
        }

        triangles.Add(new(p[0], p[1], p[2]));
        return triangles.ToArray();
    }

    private static float[] Fractions(Vector2[] p)
    {
        if (p.Length < 2)
            throw Error("band contours need nonzero length");
        var f = new float[p.Length];
        for (int i = 1; i < p.Length; i++)
            f[i] = f[i - 1] + Vector2.Distance(p[i - 1], p[i]);
        if (f[^1] <= 0)
            throw Error("band contours need nonzero length");
        float total = f[^1];
        for (int i = 1; i < f.Length; i++)
            f[i] /= total;
        return f;
    }

    private static Vector2 Sample(Vector2[] p, float[] f, float t)
    {
        int i = Array.BinarySearch(f, t);
        if (i >= 0)
            return p[i];
        i = ~i;
        if (i <= 0)
            return p[0];
        if (i >= p.Length)
            return p[^1];
        if (Math.Abs(t - f[i]) <= 1e-6f)
            return p[i];
        if (Math.Abs(t - f[i - 1]) <= 1e-6f)
            return p[i - 1];
        return Vector2.Lerp(p[i - 1], p[i], (t - f[i - 1]) / (f[i] - f[i - 1]));
    }

    internal static Vector2[] Trim(Vector2[] path, float start, float end)
    {
        if (path.Length <= 1)
            return path.ToArray();
        var fractions = Fractions(path);
        bool reverse = start > end;
        float low = Math.Min(start, end), high = Math.Max(start, end);
        var result = new List<Vector2>
        {
            Sample(path, fractions, low)
        };
        for (int i = 1; i < path.Length - 1; i++)
            if (fractions[i] > low && fractions[i] < high)
                result.Add(path[i]);
        var last = Sample(path, fractions, high);
        if (!Same(result[^1], last))
            result.Add(last);
        if (reverse)
            result.Reverse();
        return result.ToArray();
    }

    internal static Triangle[] Band(Vector2[] a, Vector2[] b)
    {
        if (Closed(a) != Closed(b))
            throw Error("band contours must both be open or both closed");
        SimpleBoundary(a);
        SimpleBoundary(b);
        var fa = Fractions(a);
        var fb = Fractions(b);
        var fractions = fa.Concat(fb).Append(.5f).Distinct().OrderBy(x => x).ToArray();
        var triangles = new List<Triangle>();
        double sign = 0;
        for (int i = 1; i < fractions.Length; i++)
        {
            var q = new[]
            {
                Sample(a, fa, fractions[i - 1]),
                Sample(a, fa, fractions[i]),
                Sample(b, fb, fractions[i]),
                Sample(b, fb, fractions[i - 1])
            };
            var cell = Fill(new[] { q[0], q[1], q[2], q[3], q[0] });
            if (cell.Length == 0)
                continue;
            double area = Area(q);
            if (sign == 0)
                sign = Math.Sign(area);
            else if (sign != Math.Sign(area))
                throw Error("band correspondence reverses orientation");
            var uv = new[]
            {
                new Vector2(fractions[i - 1], 0),
                new Vector2(fractions[i], 0),
                new Vector2(fractions[i], 1),
                new Vector2(fractions[i - 1], 1)
            };
            Vector2 Map(Vector2 point) => uv[Array.FindIndex(q, p => Same(p, point))];
            triangles.AddRange(cell.Select(t => t with { UvA = Map(t.A), UvB = Map(t.B), UvC = Map(t.C) }));
        }

        // Ruled bands can be locally valid yet globally overlap. Reject crossings and strict containment.
        for (int i = 0; i < triangles.Count; i++)
            for (int j = i + 1; j < triangles.Count; j++)
                if (Overlap(triangles[i], triangles[j]))
                    throw Error("band triangles overlap");
        return triangles.ToArray();
    }

    private static void SimpleBoundary(Vector2[] p)
    {
        for (int i = 0; i < p.Length - 1; i++)
            for (int j = i + 1; j < p.Length - 1; j++)
            {
                if (j == i + 1 || Closed(p) && i == 0 && j == p.Length - 2)
                    continue;
                if (Intersects(p[i], p[i + 1], p[j], p[j + 1]))
                    throw Error("band boundary intersects or touches itself");
            }
    }

    private static bool Overlap(Triangle a, Triangle b)
    {
        var x = new[]
        {
            a.A,
            a.B,
            a.C
        };
        var y = new[]
        {
            b.A,
            b.B,
            b.C
        };
        if (Inside((a.A + a.B + a.C) / 3, b.A, b.B, b.C, true) || Inside((b.A + b.B + b.C) / 3, a.A, a.B, a.C, true))
            return true;
        if (x.Any(p => Inside(p, b.A, b.B, b.C, true)) || y.Any(p => Inside(p, a.A, a.B, a.C, true)))
            return true;
        for (int i = 0; i < 3; i++)
            for (int j = 0; j < 3; j++)
            {
                var p = x[i];
                var q = x[(i + 1) % 3];
                var r = y[j];
                var s = y[(j + 1) % 3];
                if (Same(p, r) || Same(p, s) || Same(q, r) || Same(q, s))
                    continue;
                double a1 = Cross(p, q, r), a2 = Cross(p, q, s), b1 = Cross(r, s, p), b2 = Cross(r, s, q);
                if ((a1 > Epsilon && a2 < -Epsilon || a1 < -Epsilon && a2 > Epsilon) && (b1 > Epsilon && b2 < -Epsilon || b1 < -Epsilon && b2 > Epsilon))
                    return true;
            }

        return false;
    }

    internal static Triangle[] Stroke(Vector2[] p, float width, string join, string cap, float miterLimit)
    {
        p = p.Where((point, i) => i == 0 || !Same(point, p[i - 1])).ToArray();
        if (width <= 0 || p.Length < 2)
            return Array.Empty<Triangle>();
        var distances = Fractions(p);
        if (!distances.Any(f => Math.Abs(f - .5f) < 1e-7))
        {
            int split = Array.FindIndex(distances, f => f > .5f);
            var points = p.ToList();
            var middle = Sample(p, distances, .5f);
            if (!Same(middle, p[split - 1]) && !Same(middle, p[split]))
                points.Insert(split, middle);
            p = points.ToArray();
        }

        bool closed = Closed(p);
        int count = p.Length - 1;
        var triangles = new List<Triangle>();
        float half = width * .5f;
        var directions = new Vector2[count];
        var normals = new Vector2[count];
        var lengths = Fractions(p);
        var leftStart = new Vector2[count];
        var leftEnd = new Vector2[count];
        var rightStart = new Vector2[count];
        var rightEnd = new Vector2[count];
        for (int i = 0; i < count; i++)
        {
            directions[i] = Vector2.Normalize(p[i + 1] - p[i]);
            normals[i] = new(-directions[i].Y, directions[i].X);
            var a = p[i];
            var b = p[i + 1];
            if (!closed && cap == "square")
            {
                if (i == 0)
                    a -= directions[i] * half;
                if (i == count - 1)
                    b += directions[i] * half;
            }

            leftStart[i] = a + normals[i] * half;
            leftEnd[i] = b + normals[i] * half;
            rightStart[i] = a - normals[i] * half;
            rightEnd[i] = b - normals[i] * half;
        }

        var bevels = new List<(Vector2 a, Vector2 b, Vector2 c, float u, Vector2 normal)>();
        for (int i = closed ? 0 : 1; i < count; i++)
        {
            int before = (i + count - 1) % count;
            var pos = p[i];
            float turn = (float)Cross(Vector2.Zero, directions[before], directions[i]);
            if (Math.Abs(turn) < 1e-7)
                continue;
            var m = Vector2.Normalize(normals[before] + normals[i]);
            float denominator = Vector2.Dot(m, normals[i]);
            float length = half / denominator;
            if (!float.IsFinite(length))
                continue;
            var left = pos + m * length;
            var right = pos - m * length;
            bool bevel = join == "bevel" || Math.Abs(length) > half * miterLimit;
            if (!bevel)
            {
                leftEnd[before] = leftStart[i] = left;
                rightEnd[before] = rightStart[i] = right;
            }
            else if (turn > 0)
            {
                leftEnd[before] = leftStart[i] = left;
                bevels.Add((rightEnd[before], rightStart[i], left, lengths[i], normals[i]));
            }
            else
            {
                rightEnd[before] = rightStart[i] = right;
                bevels.Add((leftEnd[before], leftStart[i], right, lengths[i], normals[i]));
            }
        }

        for (int i = 0; i < count; i++)
        {
            var q = new[]
            {
                leftStart[i],
                leftEnd[i],
                rightEnd[i],
                rightStart[i]
            };
            var uv = new[]
            {
                new Vector2(lengths[i], 0),
                new Vector2(lengths[i + 1], 0),
                new Vector2(lengths[i + 1], 1),
                new Vector2(lengths[i], 1)
            };
            // Literal bounded strip coverage: true self-crossings can blend twice; no hidden polygon union.
            foreach (var ids in new[]
            {
                new[]
                {
                    0,
                    1,
                    2
                },
                new[]
                {
                    0,
                    2,
                    3
                }
            }

            )
            {
                int a = ids[0], b = ids[1], c = ids[2];
                double area = Cross(q[a], q[b], q[c]);
                if (Math.Abs(area) <= Epsilon)
                    continue;
                if (area < 0)
                    (b, c) = (c, b);
                triangles.Add(new(q[a], q[b], q[c]) { UvA = uv[a], UvB = uv[b], UvC = uv[c] });
            }
        }

        foreach (var b in bevels)
        {
            var a = b.a;
            var c = b.c;
            var d = b.b;
            if (Cross(a, d, c) < 0)
                (d, c) = (c, d);
            Vector2 Map(Vector2 v) => new(b.u, .5f - Vector2.Dot(v - b.c, b.normal) / width);
            triangles.Add(new(a, d, c) { UvA = Map(a), UvB = Map(d), UvC = Map(c) });
        }

        return triangles.ToArray();
    }
}
