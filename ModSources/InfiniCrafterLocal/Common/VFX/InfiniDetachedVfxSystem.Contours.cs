#nullable enable
using System;
using System.Collections.Generic;
using System.Linq;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Terraria;

namespace InfiniCrafterLocal.Common.VFX;
public sealed partial class InfiniDetachedVfxSystem
{
    private readonly record struct ContourTransform(Vector2 Translate, Vector2 Scale, float Rotation);
    private sealed record ContourDraw(
        VfxContourGeometry.Triangle[] Triangles,
        string TexturePath,
        string? LibraryTextureId,
        VfxTextureUv TextureUv,
        string Sampling,
        Vector3 ColorStart,
        Vector3 ColorEnd,
        float OpacityStart,
        float OpacityEnd,
        bool Planar,
        Vector2 Origin,
        Vector2 Size,
        bool Repeat,
        float RepeatLength,
        float Scroll,
        float Length,
        VfxNumberRamp? LengthOpacity,
        Vector2[]? StrokePath,
        float StrokeWidth,
        string StrokeJoin,
        string StrokeCap,
        float MiterLimit);
    private sealed record ContourDesign(
        ContourDraw[] Draws,
        string Attachment,
        string RotationFrame,
        ContourTransform Start,
        ContourTransform End,
        string Layer,
        string Blend,
        int Duration,
        int MaxDraw);
    private sealed class ContourEmission
    {
        internal required ContourDesign Design;
        internal required string SourceKey, Anchor;
        internal VfxSourceFrame Frame;
        internal VfxSourceBinding? Binding;
        internal Vector2 SourceAnchorOffset;
        internal ulong Due;
        internal bool ReportedInvalid;
    }

    private static readonly List<ContourEmission> ContourEmissions = new();
    private static ContourTransform CopyContourTransform(VfxContourTransform t) => new(VfxContourGeometry.Point(t.Translate), VfxContourGeometry.Point(t.Scale), t.RotationRadians);
    private static ContourDesign CopyContours(GeneratedItemData data, VfxSlotSpec slot)
    {
        var geometry = slot.Geometry!;
        geometry.Validate();
        var paths = VfxContourGeometry.Resolve(geometry.Contours);
        var draws = new List<ContourDraw>();
        foreach (var d in geometry.Draws)
        {
            var p = paths[d.Op == "band" ? d.First! : d.Contour!];
            var triangles = d.Op switch
            {
                "fill" => VfxContourGeometry.Fill(p),
                "band" => VfxContourGeometry.Band(p, paths[d.Second!]),
                _ => VfxContourGeometry.Stroke(p, d.WidthPx!.Value, d.Join!, d.Cap!, d.MiterLimit!.Value)};
            float length = 0;
            for (int i = 1; i < p.Length; i++)
                length += Vector2.Distance(p[i - 1], p[i]);
            var m = d.Material;
            var map = d.Mapping;
            var texture = m.Texture;
            string path = ResolveMaterialTexture(data, slot.EntityId, texture);
            draws.Add(new(triangles, path, texture.Source == "library" ? texture.AssetId : null, VfxTextureUv.Copy(texture.Uv), m.Sampling, m.ColorStart.ToColor().ToVector3(), m.ColorEnd.ToColor().ToVector3(), m.OpacityStart, m.OpacityEnd, d.Op == "fill", map.Origin is null ? Vector2.Zero : VfxContourGeometry.Point(map.Origin), map.Size is null ? Vector2.One : VfxContourGeometry.Point(map.Size), (d.Op == "fill" ? map.AddressMode == "repeat" : map.Mode == "repeat"), map.RepeatLengthPx ?? 1, map.ScrollPxPerTick ?? 0, length, d.OpacityProfile is null ? null : VfxNumberRamp.Copy(d.OpacityProfile), d.Op == "stroke" ? p.ToArray() : null, d.WidthPx ?? 0, d.Join ?? "", d.Cap ?? "", d.MiterLimit ?? 1));
        }

        return new(draws.ToArray(), geometry.Attachment, geometry.RotationFrame, CopyContourTransform(geometry.TransformStart), CopyContourTransform(geometry.TransformEnd), slot.Layer!, slot.Blend!, slot.Duration!.Value, data.VfxManifest.Budget.MaxDrawCalls);
    }

    internal static bool EnqueueContours(GeneratedItemData data, VfxSlotSpec slot, string sourceKey, VfxSourceFrame frame, VfxSourceBinding? binding) => EnqueueCopiedContours(CopyContours(data, slot), sourceKey, frame, binding, slot.Anchor, slot.Event == RuntimeEventKind.Periodic ? 0 : slot.StartTick!.Value);
    private static bool EnqueueCopiedContours(ContourDesign design, string sourceKey, VfxSourceFrame frame, VfxSourceBinding? binding, string anchor, int delay)
    {
        if (Main.dedServ || !frame.Valid || string.IsNullOrEmpty(sourceKey) || OwnedRecordCount >= MaxEmissions)
            return false;
        bool attached = design.Attachment == "source";
        if (attached && (binding is null || !binding.IsLive))
            return false;
        var emission = new ContourEmission
        {
            Design = design,
            SourceKey = sourceKey,
            Anchor = anchor,
            Frame = frame,
            Binding = attached ? binding : null,
            Due = Main.GameUpdateCount + (ulong)delay
        };
        if (attached && anchor == "hitPoint")
        {
            if (!binding!.TryFrame("self", out var source))
                return false;
            emission.SourceAnchorOffset = frame.Inverse(frame.Position - (frame.SourceCenter ?? source.Position));
            emission.Anchor = "self";
        }

        ContourEmissions.Add(emission);
        return true;
    }

    private static void UpdateContours(ulong now) => ContourEmissions.RemoveAll(e => now >= e.Due + (ulong)e.Design.Duration || e.Binding is not null && !e.Binding.IsLive);
    private static void DrawContours(string layer, GraphicsDevice device)
    {
        ulong now = Main.GameUpdateCount;
        foreach (var e in ContourEmissions)
        {
            var d = e.Design;
            if (d.Layer != layer || now < e.Due || now - e.Due >= (ulong)d.Duration)
                continue;
            if (e.Binding is not null && !e.Binding.TryFrame(e.Anchor, out e.Frame))
                continue;
            var frame = e.Frame with
            {
                Position = e.Frame.Position + e.Frame.Rotate(e.SourceAnchorOffset)
            };
            float t = (float)(now - e.Due) / d.Duration;
            foreach (var draw in d.Draws)
            {
                var texture = MaterialTexture(draw.TexturePath, draw.LibraryTextureId);
                if (texture is null)
                    continue;
                VertexPositionColorTexture[] mesh;
                try
                {
                    mesh = BuildContourMesh(draw, d.Start, d.End, d.RotationFrame, frame, t, now, d.Blend);
                }
                catch (System.IO.InvalidDataException error)
                {
                    if (!e.ReportedInvalid)
                    {
                        ContractJsonDiagnostics.Record("VFX.contour.runtimeGeometry", error);
                        e.ReportedInvalid = true;
                    }

                    continue;
                }

                // Filled topology is indivisible: a depleted budget skips this whole draw, never amputates triangles.
                if (mesh.Length == 0 || !TrySpendSourceDraw(e.SourceKey, d.MaxDraw, (mesh.Length / 3 + 1) / 2))
                    continue;
                DrawMaterialPathMesh(device, texture, mesh, draw.Repeat, draw.Sampling == "linear");
            }
        }
    }

    private static VertexPositionColorTexture[] BuildContourMesh(ContourDraw d, ContourTransform start, ContourTransform end, string rotationFrame, VfxSourceFrame frame, float t, ulong now, string blend)
    {
        var scale = Vector2.Lerp(start.Scale, end.Scale, t);
        float opacity = MathHelper.Lerp(d.OpacityStart, d.OpacityEnd, t);
        if (scale.X == 0 || scale.Y == 0 || opacity <= 0 || d.Triangles.Length == 0)
            return Array.Empty<VertexPositionColorTexture>();
        var translate = Vector2.Lerp(start.Translate, end.Translate, t);
        float frameRotation = rotationFrame == "source" ? frame.Forward.ToRotation() : 0;
        if (rotationFrame == "source")
            translate = VfxContourGeometry.Transform(translate, Vector2.Zero, Vector2.One, frameRotation);
        float rotation = MathHelper.Lerp(start.Rotation, end.Rotation, t) + frameRotation;
        var triangles = d.Triangles;
        float pathLength = d.Length;
        if (d.StrokePath is { } centerline)
        {
            var transformed = centerline.Select(p => VfxContourGeometry.Transform(p, translate, scale, rotation)).ToArray();
            triangles = VfxContourGeometry.Stroke(transformed, d.StrokeWidth, d.StrokeJoin, d.StrokeCap, d.MiterLimit);
            pathLength = 0;
            for (int k = 1; k < transformed.Length; k++)
                pathLength += Vector2.Distance(transformed[k - 1], transformed[k]);
        }

        var color = InfiniVfxRuntime.ApplyBlend(new Color(Vector3.Lerp(d.ColorStart, d.ColorEnd, t)) * opacity, blend);
        double scroll = d.Repeat ? now * (double)d.Scroll / d.RepeatLength : 0;
        scroll -= Math.Floor(scroll);
        VertexPositionColorTexture Vertex(Vector2 p, Vector2 uv)
        {
            float alongOpacity = d.LengthOpacity?.At(uv.X) ?? 1;
            if (d.Planar)
                uv = (p - d.Origin) / d.Size;
            else if (d.Repeat)
                uv.X = uv.X * pathLength / d.RepeatLength + (float)scroll;
            var pos = d.StrokePath is not null ? frame.Position + p : frame.Position + VfxContourGeometry.Transform(p, translate, scale, rotation);
            return new(new Vector3(pos, 0), color * alongOpacity, d.TextureUv.Map(uv));
        }

        var result = new VertexPositionColorTexture[triangles.Length * 3];
        int i = 0;
        foreach (var tri in triangles)
        {
            result[i++] = Vertex(tri.A, tri.UvA);
            result[i++] = Vertex(tri.B, tri.UvB);
            result[i++] = Vertex(tri.C, tri.UvC);
        }

        return result;
    }
}
