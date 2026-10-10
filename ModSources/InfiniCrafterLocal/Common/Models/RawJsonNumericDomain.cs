#nullable enable
using System;
using System.Globalization;
using System.Numerics;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace InfiniCrafterLocal.Common.Models;

// Property-bound admission only. No global converter registration, semantic
// routing, fallback, clamp, quantization or additional JSON/token/exponent cap.
// Bounds are decimal literals, not binary float/double approximations.
public abstract class RawJsonFloatDomainConverter : JsonConverter<float>
{
    private readonly RawJsonFloatDomain _domain;
    protected RawJsonFloatDomainConverter(string minimum, string maximum, string? neutral = null)
        => _domain = new(minimum, maximum, neutral);
    public override bool HandleNull => true;
    public override float Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        => _domain.Read(ref reader);
    public override void Write(Utf8JsonWriter writer, float value, JsonSerializerOptions options)
        => _domain.Write(writer, value);
}

// Omission never invokes the converter: float? stays absent. Present null is
// invalid even when another serializer does not use the canonical options.
public abstract class RawJsonNullableFloatDomainConverter : JsonConverter<float?>
{
    private readonly RawJsonFloatDomain _domain;
    protected RawJsonNullableFloatDomainConverter(string minimum, string maximum, string? neutral = null)
        => _domain = new(minimum, maximum, neutral);
    public override bool HandleNull => true;
    public override float? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        => _domain.Read(ref reader);
    public override void Write(Utf8JsonWriter writer, float? value, JsonSerializerOptions options)
    {
        if (!value.HasValue) throw new JsonException("present numeric value cannot be null");
        _domain.Write(writer, value.Value);
    }
}

internal sealed class RawJsonFloatDomain
{
    private readonly ExactDecimal _minimum, _maximum;
    private readonly ExactDecimal? _neutral;
    private readonly float _storedNeutral;

    internal RawJsonFloatDomain(string minimum, string maximum, string? neutral)
    {
        _minimum = ExactDecimal.Parse(minimum);
        _maximum = ExactDecimal.Parse(maximum);
        if (_minimum.CompareTo(_maximum) > 0) throw new ArgumentException("numeric domain is reversed");
        if (neutral is not null)
        {
            _neutral = ExactDecimal.Parse(neutral);
            RequireDomain(_neutral.Value);
            _storedNeutral = float.Parse(neutral, NumberStyles.Float, CultureInfo.InvariantCulture);
            if (!float.IsFinite(_storedNeutral)) throw new ArgumentException("neutral must have finite float storage");
        }
    }

    internal float Read(ref Utf8JsonReader reader)
    {
        if (reader.TokenType != JsonTokenType.Number)
            throw new JsonException("present numeric value must be a JSON number");
        // ParseValue preserves the original token, including segmented readers.
        // Admission precedes GetSingle: neither binary64 nor System.Decimal can
        // recover a sufficiently close out-of-domain literal after narrowing.
        using JsonDocument token = JsonDocument.ParseValue(ref reader);
        ExactDecimal source = ExactDecimal.Parse(token.RootElement.GetRawText());
        RequireDomain(source);
        float stored = token.RootElement.GetSingle();
        if (!float.IsFinite(stored)) throw new JsonException("numeric value must have finite float storage");
        if (_neutral.HasValue && stored == _storedNeutral && source.CompareTo(_neutral.Value) != 0)
            throw new JsonException("nonneutral numeric value collapses to declared neutral in float storage");
        return stored; // Ordinary in-domain rounding, including to endpoints, is allowed.
    }

    internal void Write(Utf8JsonWriter writer, float value)
    {
        if (!float.IsFinite(value)) throw new JsonException("numeric value must have finite float storage");
        RequireDomain(ExactDecimal.Parse(value.ToString("R", CultureInfo.InvariantCulture)));
        writer.WriteNumberValue(value);
    }

    private void RequireDomain(ExactDecimal value)
    {
        if (value.CompareTo(_minimum) < 0 || value.CompareTo(_maximum) > 0)
            throw new JsonException("original JSON number is outside the declared property domain");
    }

    // Scientific decimal comparison without exponent expansion or powers of ten.
    // BigInteger is used only for the decimal order; coefficient digits remain
    // literal strings. Work/storage depend on token length, not exponent value.
    private readonly record struct ExactDecimal(int Sign, string Digits, BigInteger Order)
    {
        internal static ExactDecimal Parse(string literal)
        {
            ReadOnlySpan<char> coefficient = literal.AsSpan();
            int sign = 1;
            if (coefficient[0] == '-') { sign = -1; coefficient = coefficient[1..]; }
            BigInteger exponent = BigInteger.Zero;
            int e = coefficient.IndexOfAny('e', 'E');
            if (e >= 0)
            {
                exponent = BigInteger.Parse(coefficient[(e + 1)..], NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture);
                coefficient = coefficient[..e];
            }
            int dot = coefficient.IndexOf('.');
            int fractionDigits = dot < 0 ? 0 : coefficient.Length - dot - 1;
            string digits = coefficient.ToString().Replace(".", "", StringComparison.Ordinal).TrimStart('0');
            if (digits.Length == 0) return new(0, "", BigInteger.Zero);
            BigInteger order = exponent + digits.Length - fractionDigits;
            return new(sign, digits.TrimEnd('0'), order);
        }

        internal int CompareTo(ExactDecimal other)
        {
            if (Sign != other.Sign) return Sign.CompareTo(other.Sign);
            if (Sign == 0) return 0;
            int magnitude = Order.CompareTo(other.Order);
            if (magnitude == 0)
            {
                int length = Math.Max(Digits.Length, other.Digits.Length);
                for (int i = 0; i < length; i++)
                {
                    char left = i < Digits.Length ? Digits[i] : '0';
                    char right = i < other.Digits.Length ? other.Digits[i] : '0';
                    if (left != right) { magnitude = left.CompareTo(right); break; }
                }
            }
            return Sign * magnitude;
        }
    }
}
