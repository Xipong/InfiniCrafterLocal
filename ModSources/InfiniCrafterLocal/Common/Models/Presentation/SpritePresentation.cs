#nullable enable
using System;
using System.Globalization;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

namespace InfiniCrafterLocal.Common.Models;

// Technical execution of explicitly authored final-frame units, not gameplay
// normalization. No alpha/PCA/name inference and no physics or pose mutation.
internal readonly record struct SpritePresentationSelection(string Path, int? RenderSizePx, float? ForwardAngleDegrees, ItemGripSpec? Grip = null, bool FrontHandBody = false, bool ImpactTexture = false)
{
    internal float FrameScale(int width, int height) => ImpactTexture ? 1f : SpritePresentation.FrameScale(RenderSizePx, width, height);
    internal Vector2 ProjectileOrigin(RuntimeEntitySpec? entity, int width, int height, float scale, SpriteEffects effects)
    {
        if (!FrontHandBody || entity?.Movement.Code != 20) return new(width * .5f, height * .5f);
        if (Grip is null || !RenderSizePx.HasValue || !ForwardAngleDegrees.HasValue || !float.IsFinite(scale) || scale <= 0f)
            throw new InvalidDataException("front-hand sprite pose has no admitted selected grip/size/axis/scale");
        Grip.Validate();
        return new InfiniCrafterLocal.Common.VFX.InfiniVfxSpriteAnchor((float)Grip.NormalizedX, (float)Grip.NormalizedY,
            ForwardAngleDegrees.Value, entity.Movement.Params.HitboxOffsetPx!.Value).Origin(width, height, scale, effects);
    }
    internal float ProjectileRotation(RuntimeEntitySpec? entity, float rotation, SpriteEffects effects)
    {
        // Explicit spinning poses and whip are native, not motion-aimed sprites.
        if (ImpactTexture || entity is null || entity.Movement.Code is 14 or 16 or 17 or 18)
            return rotation;
        return SpritePresentation.AlignForward(rotation - MathF.PI / 2f, SpritePresentation.RequireForwardAngle(ForwardAngleDegrees), effects);
    }
}

internal static class SpritePresentation
{
    // Exact opaque pixel-edge support geometry, measured once with the selected
    // texture generation. This is presentation normalization, not an inferred
    // material/decoration classification or a change to the native item collider.
    internal static Vector2[] MeasureAlphaHull(Color[] pixels, int width, int height)
    {
        var points = new List<Vector2>();
        for (int y = 0; y < height; y++)
        {
            int left = width, right = -1;
            for (int x = 0; x < width; x++)
                if (pixels[y * width + x].A > 0) { left = Math.Min(left, x); right = x; }
            if (right < left) continue;
            points.Add(new(left, y)); points.Add(new(right + 1, y));
            points.Add(new(left, y + 1)); points.Add(new(right + 1, y + 1));
        }
        points.Sort((a, b) => a.X != b.X ? a.X.CompareTo(b.X) : a.Y.CompareTo(b.Y));
        if (points.Count == 0) return Array.Empty<Vector2>();
        var hull = new List<Vector2>();
        static float Cross(Vector2 a, Vector2 b, Vector2 c)
            => (b.X-a.X)*(c.Y-a.Y) - (b.Y-a.Y)*(c.X-a.X);
        foreach (Vector2 p in points)
        {
            while (hull.Count >= 2 && Cross(hull[^2], hull[^1], p) <= 0) hull.RemoveAt(hull.Count-1);
            hull.Add(p);
        }
        int lowerCount = hull.Count;
        for (int i = points.Count - 2; i >= 0; i--)
        {
            Vector2 p = points[i];
            while (hull.Count > lowerCount && Cross(hull[^2], hull[^1], p) <= 0) hull.RemoveAt(hull.Count-1);
            hull.Add(p);
        }
        hull.RemoveAt(hull.Count-1);
        return hull.ToArray();
    }

    internal static Vector2 DroppedBodyPosition(Vector2 bottom, Vector2 origin, float rotation,
        float scale, Vector2[]? alphaHull)
    {
        // Unknown geometry is possible only for borrowed/headless cache fixtures;
        // retain their old frame placement. A measured alpha-empty image stays empty.
        if (alphaHull is null || alphaHull.Length == 0) return bottom - new Vector2(0, origin.Y * scale);
        float cosine = MathF.Cos(rotation), sine = MathF.Sin(rotation);
        float minX = float.PositiveInfinity, maxX = float.NegativeInfinity, maxY = float.NegativeInfinity;
        foreach (Vector2 point in alphaHull)
        {
            Vector2 p = (point - origin) * scale;
            float x = p.X * cosine - p.Y * sine, y = p.X * sine + p.Y * cosine;
            minX = Math.Min(minX, x); maxX = Math.Max(maxX, x); maxY = Math.Max(maxY, y);
        }
        return bottom - new Vector2((minX + maxX) * .5f, maxY);
    }

    // Property-local admission: keep nullable-float storage and direct setter
    // guards, but reject out-of-domain JSON before GetSingle can round it in.
    public sealed class ForwardAngleJsonConverter : JsonConverter<float?>
    {
        public override bool HandleNull => true;
        public override float? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            if (reader.TokenType != JsonTokenType.Number)
                throw new JsonException("forwardAngleDegrees must be a number in -180..180 when present");
            double source = reader.GetDouble();
            if (!double.IsFinite(source) || source is < -180d or > 180d)
                throw new JsonException("forwardAngleDegrees must be finite in -180..180 when present");
            if (source is -180d or 180d)
            {
                // Even double/decimal can round a very close outside number to
                // an endpoint. Compare its exact decimal magnitude, no powers
                // or arbitrary-precision expansion of the exponent required.
                using JsonDocument number = JsonDocument.ParseValue(ref reader);
                if (!BoundaryMagnitudeWithinDomain(number.RootElement.GetRawText()))
                    throw new JsonException("forwardAngleDegrees JSON number is outside -180..180");
                return RequireForwardAngle(number.RootElement.GetSingle());
            }
            return RequireForwardAngle(reader.GetSingle());
        }
        public override void Write(Utf8JsonWriter writer, float? value, JsonSerializerOptions options)
            => writer.WriteNumberValue(RequireForwardAngle(value));

        private static bool BoundaryMagnitudeWithinDomain(string literal)
        {
            ReadOnlySpan<char> coefficient = literal.AsSpan();
            if (coefficient[0] == '-') coefficient = coefficient[1..];
            int exponent = 0, e = coefficient.IndexOfAny('e', 'E');
            if (e >= 0)
            {
                if (!int.TryParse(coefficient[(e + 1)..], NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out exponent))
                    return false; // an exponent larger than the token length cannot be near 180
                coefficient = coefficient[..e];
            }
            int dot = coefficient.IndexOf('.');
            int fractionDigits = dot < 0 ? 0 : coefficient.Length - dot - 1;
            string digits = coefficient.ToString().Replace(".", "", StringComparison.Ordinal).TrimStart('0');
            long integerDigits = (long)digits.Length + exponent - fractionDigits;
            if (integerDigits != 3) return integerDigits < 3;
            return string.CompareOrdinal(digits.TrimEnd('0').PadRight(3, '0'), "180") <= 0;
        }
    }

    internal static int RequireRenderSize(int? value)
        => value is >= 1 and <= 512 ? value.Value
            : throw new InvalidDataException("renderSizePx must be an integer in 1..512 when present");
    internal static float RequireForwardAngle(float? value)
        => value.HasValue && float.IsFinite(value.Value) && value.Value is >= -180f and <= 180f ? value.Value
            : throw new InvalidDataException("forwardAngleDegrees must be finite in -180..180 when present");
    internal static float FrameScale(int? size, int width, int height)
    {
        if (!size.HasValue) throw new InvalidDataException("selected main PNG requires explicit renderSizePx");
        if (width <= 0 || height <= 0) throw new InvalidDataException("main sprite frame has no extent");
        return size.Value / (float)Math.Max(width, height);
    }
    internal static float AlignForward(float bodyAngle, float axisDegrees, SpriteEffects effects)
    {
        float radians = axisDegrees * (MathF.PI / 180f);
        float x = MathF.Cos(radians), y = MathF.Sin(radians);
        if ((effects & SpriteEffects.FlipHorizontally) != 0) x = -x;
        if ((effects & SpriteEffects.FlipVertically) != 0) y = -y;
        return bodyAngle - MathF.Atan2(y, x);
    }
    internal static SpritePresentationSelection Root(GeneratedItemData data)
        => new(data.Visual.SpritePath ?? "", data.Visual.RenderSizePx, data.Visual.ForwardAngleDegrees, data.Visual.Grip);
    internal static SpritePresentationSelection Entity(GeneratedItemData data, RuntimeEntitySpec entity)
        => entity.Visual.AssetMode switch {
            "reuse_item_icon" => Root(data) with { FrontHandBody = entity.Movement.Code == 20 },
            "baked_sprite" when entity.Kind == RuntimeEntityKind.ItemBody => Root(data),
            "baked_sprite" => new(entity.Visual.SpritePath ?? "", entity.Visual.RenderSizePx, entity.Visual.ForwardAngleDegrees, entity.Visual.Grip, entity.Movement.Code == 20),
            _ => new("", null, null),
        };
    internal static SpritePresentationSelection Resolve(GeneratedItemData data, string entityId, string textureRole)
    {
        string role = (textureRole ?? "").Trim().ToLowerInvariant();
        if (role == "none") return new("", null, null);
        RuntimeEntitySpec? entity = data.RuntimeProgram.TryGetEntity(entityId);
        if (role == "item") return entity?.Movement.Code == 20 && entity.Visual.AssetMode == "reuse_item_icon"
            ? Entity(data, entity) : Root(data);
        if (entity is null) return new("", null, null);
        if (role == "impact") return new(entity.Visual.ImpactSpritePath ?? "", null, null, ImpactTexture: true);
        if (role != "entity") return new("", null, null);
        return Entity(data, entity);
    }
}
