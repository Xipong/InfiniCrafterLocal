#nullable enable
using System;
using System.IO;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Xna.Framework;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>Local authored RGB only. Opacity belongs to the consuming renderer.</summary>
[JsonConverter(typeof(RuntimeRgbSpec.JsonConverter))]
public sealed class RuntimeRgbSpec
{
    public int R { get; set; }
    public int G { get; set; }
    public int B { get; set; }

    public void Validate()
    {
        if (R is < 0 or > 255 || G is < 0 or > 255 || B is < 0 or > 255)
            throw new InvalidDataException("VFX RGB requires integer r, g and b in 0..255");
    }

    public Color ToColor()
    {
        Validate();
        return new Color(R, G, B);
    }

    public sealed class JsonConverter : JsonConverter<RuntimeRgbSpec>
    {
        public override bool HandleNull => true;
        public override RuntimeRgbSpec Read(ref Utf8JsonReader reader, Type type, JsonSerializerOptions options)
        {
            if (reader.TokenType != JsonTokenType.StartObject)
                throw new JsonException("VFX RGB requires a closed {r,g,b} object");
            int mask = 0;
            var rgb = new RuntimeRgbSpec();
            while (reader.Read() && reader.TokenType != JsonTokenType.EndObject)
            {
                if (reader.TokenType != JsonTokenType.PropertyName) throw new JsonException("Invalid VFX RGB member");
                string? name = reader.GetString();
                int bit = name switch { "r" => 1, "g" => 2, "b" => 4, _ => 0 };
                if (bit == 0 || (mask & bit) != 0) throw new JsonException("Unknown or duplicate VFX RGB member '" + name + "'");
                if (!reader.Read() || reader.TokenType != JsonTokenType.Number || !reader.TryGetInt32(out int value) || value is < 0 or > 255)
                    throw new JsonException("VFX RGB '" + name + "' requires an integer in 0..255");
                if (bit == 1) rgb.R = value;
                else if (bit == 2) rgb.G = value;
                else rgb.B = value;
                mask |= bit;
            }
            if (reader.TokenType != JsonTokenType.EndObject || mask != 7) throw new JsonException("VFX RGB requires exactly r, g and b");
            return rgb;
        }
        public override void Write(Utf8JsonWriter writer, RuntimeRgbSpec value, JsonSerializerOptions options)
        {
            if (value is null) throw new JsonException("VFX RGB cannot be null");
            value.Validate();
            writer.WriteStartObject();
            writer.WriteNumber("r", value.R);
            writer.WriteNumber("g", value.G);
            writer.WriteNumber("b", value.B);
            writer.WriteEndObject();
        }
    }
}
