using System;
using System.Buffers;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    // Inject the literal as bytes after fixture serialization: JsonNode/float/double
    // fixture conversion must not erase the counterexample before FromJson sees it.
    private static string HitboxRawNumber(string json, string property, string literal)
    {
        JsonObject root = JsonNode.Parse(json)!.AsObject();
        root["runtimeProgram"]!["entities"]![1]!["hitboxCurve"]![property] = "RAW_HITBOX_NUMBER";
        return root.ToJsonString().Replace("\"RAW_HITBOX_NUMBER\"", literal, StringComparison.Ordinal);
    }

    private static string HitboxNumericFixture()
    {
        var source = RootSpawnFixture(8, 1);
        source.RuntimeProgram.Entities[1].HitboxCurve = HitboxCurve();
        return source.ToJson();
    }

    private static void HitboxRawNumericDomainRefusesOutsideBeforeNarrowing()
    {
        string json = HitboxNumericFixture();
        foreach (string field in new[] { "startScale", "endScale" })
        foreach (string literal in new[] {
            "0.24999999999999997", "8.000000000000002",
            "0.2499999999999999999999999999999999999999999999999999999999",
            "8.0000000000000000000000000000000000000000000000000000000001",
            "2499999999999999999999999999999999999999999999999999999999e-58",
            "8000000000000000000000000000000000000000000000000000000001e-57",
            "1e99999999999999999999999999999999999999999999999999999",
            "1e-99999999999999999999999999999999999999999999999999999",
            "-1e-99999999999999999999999999999999999999999999999999999",
        })
            Equal(true, GeneratedItemData.FromJson(HitboxRawNumber(json, field, literal)) is null,
                "original hitbox domain refuses " + field + "=" + literal);
    }

    private static void HitboxRawNumericEndpointsSurviveSerializationCacheNetwork()
    {
        string json = HitboxNumericFixture();
        foreach (string field in new[] { "startScale", "endScale" })
        foreach ((string literal, float expected) in new[] {
            ("0.25", .25f), ("8", 8f), ("25e-2", .25f), ("800e-2", 8f),
            ("0.2500000000000000000000000000000000000000000000000000000001", .25f),
            ("7.9999999999999999999999999999999999999999999999999999999999", 8f),
            ("2500000000000000000000000000000000000000000000000000000001e-58", .25f),
            ("7999999999999999999999999999999999999999999999999999999999e-57", 8f),
            ("1.0000000000000000000000000000000000000000000000000000000001", 1f),
            ("1.5", 1.5f),
        })
        {
            var data = GeneratedItemData.FromJson(HitboxRawNumber(json, field, literal))
                ?? throw new InvalidOperationException("in-domain literal rejected: " + literal);
            foreach ((string route, string payload) in new[] {
                ("full", data.ToJson()), ("cache", data.ToLocalCacheJson()), ("network", data.ToNetworkJson()),
            })
            {
                var copy = GeneratedItemData.FromJson(payload) ?? throw new InvalidOperationException(route + " rejected");
                RuntimeHitboxCurveSpec curve = copy.RuntimeProgram.Entities[1].HitboxCurve!;
                Equal(expected, field == "startScale" ? curve.StartScale : curve.EndScale, route + " exact float storage");
                Equal(5, curve.StartDelayTicks, route + " retains authored clock");
                Equal(false, curve.MirrorToSprite, route + " retains independent visual policy");
                foreach (string outside in new[] { "0.24999999999999997", "8.000000000000002" })
                    Equal(true, GeneratedItemData.FromJson(HitboxRawNumber(payload, field, outside)) is null,
                        route + " re-admission refuses raw outside " + field);
            }
        }
    }

    private static void HitboxRawNumericPresenceAndInvalidTypesStayStrict()
    {
        string json = HitboxNumericFixture();
        foreach (string field in new[] { "startScale", "endScale" })
        {
            foreach (string invalid in new[] { "null", "true", "false", "\"1\"", "[]", "{}" })
                Equal(true, GeneratedItemData.FromJson(HitboxRawNumber(json, field, invalid)) is null, field + " rejects " + invalid);
            var missing = JsonNode.Parse(json)!;
            missing["runtimeProgram"]!["entities"]![1]!["hitboxCurve"]!.AsObject().Remove(field);
            Equal(true, GeneratedItemData.FromJson(missing.ToJsonString()) is null, field + " remains required");
        }
        foreach (string invalid in new[] { "null", "[]", "true", "\"curve\"", "0", "{}" })
        {
            var malformed = JsonNode.Parse(json)!;
            malformed["runtimeProgram"]!["entities"]![1]!["hitboxCurve"] = JsonNode.Parse(invalid);
            Equal(true, GeneratedItemData.FromJson(malformed.ToJsonString()) is null, "invalid curve container " + invalid);
        }
        var absent = JsonNode.Parse(json)!;
        absent["runtimeProgram"]!["entities"]![1]!.AsObject().Remove("hitboxCurve");
        var legacy = GeneratedItemData.FromJson(absent.ToJsonString()) ?? throw new InvalidOperationException("absence rejected");
        foreach (string payload in new[] { legacy.ToJson(), legacy.ToLocalCacheJson(), legacy.ToNetworkJson() })
        {
            Equal(false, payload.Contains("hitboxCurve", StringComparison.Ordinal), "absence stays omitted");
            Equal(true, GeneratedItemData.FromJson(payload)!.RuntimeProgram.Entities[1].HitboxCurve is null, "absence stays nullable");
        }
    }

    // Test-only explicit domains exercise reusable mechanics, not semantic routing.
    public sealed class SignedRawProbe
    {
        public sealed class ValueConverter : RawJsonFloatDomainConverter
        {
            public ValueConverter() : base("-0.9", "0.9", "0") { }
        }
        [JsonConverter(typeof(ValueConverter))] public float Value { get; set; }
    }
    public sealed class PiRawProbe
    {
        public sealed class ValueConverter : RawJsonFloatDomainConverter
        {
            public ValueConverter() : base("0", "3.141592653589793") { }
        }
        [JsonConverter(typeof(ValueConverter))] public float Value { get; set; }
    }
    public sealed class NullableRawProbe
    {
        public sealed class ValueConverter : RawJsonNullableFloatDomainConverter
        {
            public ValueConverter() : base("0", "4", "1") { }
        }
        [JsonConverter(typeof(ValueConverter))]
        [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
        public float? Value { get; set; }
    }

    private static void RawNumericHelperSignedNullableAndNeutralDomains()
    {
        static T Parse<T>(string literal) => JsonSerializer.Deserialize<T>("{\"Value\":" + literal + "}")!;
        static void Refused<T>(string literal)
        {
            try { _ = Parse<T>(literal); }
            catch (JsonException) { return; }
            throw new InvalidOperationException("raw numeric helper accepted " + typeof(T).Name + ": " + literal);
        }
        foreach (string literal in new[] { "-0.9", "0.9", "-9e-1", "9e-1", "-0.89999999999999999999999999999999999999999999999999", "0.89999999999999999999999999999999999999999999999999" })
            Equal(literal[0] == '-' ? -.9f : .9f, Parse<SignedRawProbe>(literal).Value, "signed decimal endpoint rounding");
        foreach (string literal in new[] { "-0.90000000000000000000000000000000000000000000000001", "0.90000000000000000000000000000000000000000000000001", "-1e-1000", "1e-1000", "1e-999999999999999999999999999999999999999999999", "true", "\"0\"", "null", "[]", "{}" })
            Refused<SignedRawProbe>(literal);
        foreach (string literal in new[] { "0", "-0", "0e999999999999999999999999999999999999999999999", "-0e-999999999999999999999999999999999999999999999" })
            Equal(0f, Parse<SignedRawProbe>(literal).Value, "exact zero has no exponent cap");
        foreach (string literal in new[] { "1e-44", "-1e-44" })
            Equal(true, Parse<SignedRawProbe>(literal).Value != 0f, "nonzero subnormal stays admitted");
        foreach (string literal in new[] { "1.00000000000000000000000000000000000000000000000001", "0.99999999999999999999999999999999999999999999999999", "null", "true", "\"1\"", "-1e-1000", "4.00000000000000000000000000000000000000000000000001" })
            Refused<NullableRawProbe>(literal);
        foreach (string literal in new[] { "0", "1", "1e0", "4", "1.00000011920928955078125", "0.999999940395355224609375", "1e-1000" })
        {
            NullableRawProbe parsed = Parse<NullableRawProbe>(literal);
            string json = JsonSerializer.Serialize(parsed);
            Equal(parsed.Value!.Value, JsonSerializer.Deserialize<NullableRawProbe>(json)!.Value!.Value, "nullable float storage roundtrip");
        }
        // Nonzero collapsing to 0 is allowed when the only declared neutral is 1.
        Equal(0f, Parse<NullableRawProbe>("1e-1000").Value!.Value, "no undeclared neutral policy");
        var absent = JsonSerializer.Deserialize<NullableRawProbe>("{}")!;
        Equal(false, absent.Value.HasValue, "nullable omission is not present null");
        Equal("{}", JsonSerializer.Serialize(absent), "alternate serializer keeps omission");

        var endpoint = Parse<PiRawProbe>("3.141592653589793");
        string endpointWire = JsonSerializer.Serialize(endpoint);
        Equal(endpoint.Value, JsonSerializer.Deserialize<PiRawProbe>(endpointWire)!.Value, "nonexact decimal endpoint retains identical stored float roundtrip");
        Equal(true, endpointWire.Contains("3.141592653589793", StringComparison.Ordinal), "writer uses exact declared endpoint representative");
        Refused<PiRawProbe>("3.141592653589793000000000001");

        const string splitLiteral = "0.90000000000000000000000000000000000000000000000001";
        var first = new RawNumericSegment(Encoding.UTF8.GetBytes(splitLiteral[..18]));
        RawNumericSegment last = first.Append(Encoding.UTF8.GetBytes(splitLiteral[18..]));
        var reader = new Utf8JsonReader(new ReadOnlySequence<byte>(first, 0, last, last.Memory.Length));
        Equal(true, reader.Read(), "segmented reader has number");
        Equal(true, reader.HasValueSequence, "fixture really splits numeric token");
        bool refused = false;
        try { _ = new SignedRawProbe.ValueConverter().Read(ref reader, typeof(float), new JsonSerializerOptions()); }
        catch (JsonException) { refused = true; }
        Equal(true, refused, "segmented original token retains exact boundary");
    }

    private sealed class RawNumericSegment : ReadOnlySequenceSegment<byte>
    {
        internal RawNumericSegment(byte[] bytes) => Memory = bytes;
        internal RawNumericSegment Append(byte[] bytes)
        {
            var next = new RawNumericSegment(bytes) { RunningIndex = RunningIndex + Memory.Length };
            Next = next;
            return next;
        }
    }
}
