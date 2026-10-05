#nullable enable
using System;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Xna.Framework.Graphics;

namespace InfiniCrafterLocal.Common.Models;

// Technical execution of explicitly authored final-frame units, not gameplay
// normalization. No alpha/PCA/name inference and no physics or pose mutation.
internal readonly record struct SpritePresentationSelection(string Path, int? RenderSizePx, float? ForwardAngleDegrees)
{
    internal float FrameScale(int width, int height) => SpritePresentation.FrameScale(RenderSizePx, width, height);
    internal float ProjectileRotation(RuntimeEntitySpec? entity, float rotation, SpriteEffects effects)
    {
        // Explicit spinning poses and whip are native, not motion-aimed sprites.
        if (!ForwardAngleDegrees.HasValue || entity is null || entity.Movement.Code is 14 or 16 or 17 or 18)
            return rotation;
        return SpritePresentation.AlignForward(rotation - MathF.PI / 2f, ForwardAngleDegrees.Value, effects);
    }
}

internal static class SpritePresentation
{
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
        if (!size.HasValue) return 1f; // exact declared saved-wire compatibility
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
        => new(data.Visual.SpritePath ?? "", data.Visual.RenderSizePx, data.Visual.ForwardAngleDegrees);
    internal static SpritePresentationSelection Entity(GeneratedItemData data, RuntimeEntitySpec entity)
        => entity.Visual.AssetMode switch {
            "reuse_item_icon" => Root(data),
            "baked_sprite" when entity.Kind == RuntimeEntityKind.ItemBody => Root(data),
            "baked_sprite" => new(entity.Visual.SpritePath ?? "", entity.Visual.RenderSizePx, entity.Visual.ForwardAngleDegrees),
            _ => new("", null, null),
        };
    internal static SpritePresentationSelection Resolve(GeneratedItemData data, string entityId, string textureRole)
    {
        string role = (textureRole ?? "").Trim().ToLowerInvariant();
        if (role == "none") return new("", null, null);
        if (role == "item") return Root(data);
        RuntimeEntitySpec? entity = data.RuntimeProgram.TryGetEntity(entityId);
        if (entity is null) return new("", null, null);
        if (role == "impact") return new(entity.Visual.ImpactSpritePath ?? "", null, null);
        if (role != "entity" && !string.Equals(entity.VisualRole, role, StringComparison.Ordinal)) return new("", null, null);
        return Entity(data, entity);
    }
}
