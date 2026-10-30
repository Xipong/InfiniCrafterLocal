#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Xna.Framework;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>Authored presentation only. Dimensions are world pixels, independent of hitbox and sprite scale.</summary>
[JsonConverter(typeof(RuntimeBodyGeometrySpec.Converter))]
public sealed class RuntimeBodyGeometrySpec
{
    public string Schema { get; set; } = "";
    public string Source { get; set; } = "";
    public float WidthPx { get; set; } = float.NaN;
    public string Color { get; set; } = "";
    public float Opacity { get; set; } = float.NaN;
    public float? LengthPx { get; set; }
    public string? Axis { get; set; }

    public void Validate()
    {
        if (Schema != "infini.body-geometry.v1" || Source is not ("body_segment" or "collision_path"))
            throw new InvalidDataException("Unknown body geometry schema/source");
        if (!float.IsFinite(WidthPx) || WidthPx <= 0 || WidthPx > 1024 || !float.IsFinite(Opacity) || Opacity < 0 || Opacity > 1)
            throw new InvalidDataException("Body geometry requires widthPx in (0,1024] and opacity in [0,1]");
        if (Color is null || Color.Length != 7 || Color[0] != '#') throw new InvalidDataException("Body geometry color must be #RRGGBB");
        for (int i = 1; i < 7; i++) if (!Uri.IsHexDigit(Color[i])) throw new InvalidDataException("Body geometry color must be #RRGGBB");
        if (Source == "body_segment") {
            if (LengthPx is not { } length || !float.IsFinite(length) || length <= 0 || length > 4096 || Axis is not ("velocity" or "rotation" or "aim"))
                throw new InvalidDataException("Body segment requires lengthPx in (0,4096] and explicit axis");
        } else if (LengthPx.HasValue || Axis is not null) throw new InvalidDataException("Collision path forbids lengthPx/axis");
    }

    public Microsoft.Xna.Framework.Color ToColor()
    {
        Validate();
        return new Color(Convert.ToInt32(Color.Substring(1, 2), 16), Convert.ToInt32(Color.Substring(3, 2), 16), Convert.ToInt32(Color.Substring(5, 2), 16)) * Opacity;
    }

    public sealed class Converter : JsonConverter<RuntimeBodyGeometrySpec>
    {
        public override bool HandleNull => true;
        public override RuntimeBodyGeometrySpec Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options)
        {
            using var doc = JsonDocument.ParseValue(ref reader);
            if (doc.RootElement.ValueKind != JsonValueKind.Object) throw new JsonException("Body geometry must be an object");
            var result = new RuntimeBodyGeometrySpec(); var seen = new HashSet<string>(StringComparer.Ordinal);
            foreach (var p in doc.RootElement.EnumerateObject()) {
                if (!seen.Add(p.Name)) throw new JsonException("Duplicate body geometry field: " + p.Name);
                switch (p.Name) {
                    case "schema": result.Schema = p.Value.GetString()!; break;
                    case "source": result.Source = p.Value.GetString()!; break;
                    case "color": result.Color = p.Value.GetString()!; break;
                    case "widthPx": result.WidthPx = p.Value.GetSingle(); break;
                    case "opacity": result.Opacity = p.Value.GetSingle(); break;
                    case "lengthPx": result.LengthPx = p.Value.GetSingle(); break;
                    case "axis": result.Axis = p.Value.GetString() ?? throw new JsonException("Null axis"); break;
                    default: throw new JsonException("Unknown body geometry field: " + p.Name);
                }
            }
            result.Validate(); return result;
        }
        public override void Write(Utf8JsonWriter writer, RuntimeBodyGeometrySpec value, JsonSerializerOptions options)
        {
            value.Validate(); writer.WriteStartObject();
            writer.WriteString("schema", value.Schema); writer.WriteString("source", value.Source);
            writer.WriteNumber("widthPx", value.WidthPx); writer.WriteString("color", value.Color); writer.WriteNumber("opacity", value.Opacity);
            if (value.Source == "body_segment") { writer.WriteNumber("lengthPx", value.LengthPx!.Value); writer.WriteString("axis", value.Axis); }
            writer.WriteEndObject();
        }
    }
}
