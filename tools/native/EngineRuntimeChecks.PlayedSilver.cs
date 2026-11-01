using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using ParticleLibrary.Core.V3.Particles;

internal static partial class EngineRuntimeChecks
{
    private static RuntimeRgbSpec Rgb(int r, int g, int b) => new() { R = r, G = g, B = b };
    private static JsonObject RgbWire(int r, int g, int b) => new() { ["r"] = r, ["g"] = g, ["b"] = b };

    private static void PlayedSilverFinalDeliveryAndNativeColorConsumers()
    {
        string wire = File.ReadAllText(Path.Combine("tools", "fixtures", "played-silver-delivered.json"));
        // Frozen historical delivery stays untouched; this test exercises its RGB semantics in the current envelope.
        Equal("ebab278b44ec2938c0341f8c32c9fecf06e9ccb02fafebd8c4c2de5c27a5fda7",
            Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(wire))).ToLowerInvariant(), "immutable played silver source");
        Equal(true, GeneratedItemData.FromJson(wire) is null, "retired original delivery is not silently imported");
        var envelope = JsonNode.Parse(wire)!;
        Equal("immediate", envelope["runtimeProgram"]!["itemUse"]!["releaseTiming"]!.GetValue<string>(), "known saved runtime timing");
        Equal("immediate", envelope["gameplay"]!["releaseTiming"]!.GetValue<string>(), "known saved gameplay timing");
        envelope["runtimeProgram"]!["itemUse"]!.AsObject().Remove("releaseTiming");
        envelope["gameplay"]!.AsObject().Remove("releaseTiming");
        var restoredEnvelope = envelope.DeepClone();
        restoredEnvelope["runtimeProgram"]!["itemUse"]!["releaseTiming"] = "immediate";
        restoredEnvelope["gameplay"]!["releaseTiming"] = "immediate";
        Equal(true, JsonNode.DeepEquals(JsonNode.Parse(wire), restoredEnvelope), "only the two retired envelope fields differ; RGB and mechanics are original");
        wire = envelope.ToJsonString(); // Every later positive and negative RGB control uses this explicit current envelope.
        var data = GeneratedItemData.FromJson(wire)
            ?? throw new InvalidOperationException("RGB final delivery refused: " + ContractJsonDiagnostics.LastError);
        Color silver = new(192, 192, 192);
        var element = data.VfxManifest.Slots.Single(s => s.RendererKind == "spriteElement").Element!;
        var ramp = VfxColorRamp.Copy(element.ColorProfile);
        Equal(silver, ramp.At(0, 1, "alpha"), "local RGB material start knot reaches native color");
        Equal(silver, ramp.At(.5f, 1, "alpha"), "independent middle knot reaches native color");
        Equal(silver, ramp.At(1, 1, "alpha"), "independent end knot reaches native color");
        var slot = data.VfxManifest.Slots.Single(s => s.RendererKind == "libraryParticle");
        object design = LibraryInvoke("CopyLibrary", data, slot, false)!;
        data.Visual.Palette = new[] { "red prose cannot select VFX color" };
        element.ColorProfile.Start.R = 0;
        slot.Particle!.ColorStart.G = 0;
        var info = (ParticleInfo)LibraryInvoke("CreateLibraryInfoCore", design,
            new VfxSourceFrame(Vector2.Zero, Vector2.UnitX, Vector2.Zero), .5f, .5f)!;
        Equal(silver * slot.Alpha, info.Color, "native library CPU particle captures explicit local RGB at emission");
        while (info.Time > 1) InfiniDetachedVfxSystem.AdvanceLibraryInfo(ref info);
        Equal(info.Color.R, info.Color.G, "captured RGB remains immutable after source mutation");
        Equal(info.Color.G, info.Color.B, "captured endpoint remains immutable");
        Equal(silver, ramp.At(0, 1, "alpha"), "material ramp copies mutable DTO RGB by value");
        var accepted = GeneratedItemData.FromJson(wire)!;
        var roundtrip = GeneratedItemData.FromJson(accepted.ToJson())
            ?? throw new InvalidOperationException("RGB definition roundtrip refused");
        Equal(silver, roundtrip.VfxManifest.Slots.Single(s => s.Element is not null).Element!.ColorProfile.Start.ToColor(), "definition serializer preserves exact RGB");
        var snapshot = JsonSerializer.Serialize(accepted);
        var alternate = JsonSerializer.Deserialize<GeneratedItemData>(snapshot)!;
        Equal(silver, alternate.VfxManifest.Slots.Single(s => s.Element is not null).Element!.ColorProfile.Start.ToColor(), "alternate snapshot serializer preserves RGB and omitted common colors");
        foreach (string bad in new[] { "null", "\"silver\"", "\"effect\"", "{\"r\":-1,\"g\":2,\"b\":3}", "{\"r\":256,\"g\":2,\"b\":3}",
            "{\"r\":1.5,\"g\":2,\"b\":3}", "{\"r\":1.0,\"g\":2,\"b\":3}", "{\"r\":true,\"g\":2,\"b\":3}", "{\"r\":\"1\",\"g\":2,\"b\":3}",
            "{\"r\":1,\"g\":2}", "{\"r\":1,\"g\":2,\"b\":3,\"a\":255}", "{\"r\":1,\"r\":2,\"g\":2,\"b\":3}", "{\"R\":1,\"g\":2,\"b\":3}" })
        {
            bool refused = false;
            try { JsonSerializer.Deserialize<RuntimeRgbSpec>(bad); } catch (JsonException) { refused = true; }
            Equal(true, refused, "strict RGB rejects unsupported input " + bad);
        }
        Equal(Color.Black, Rgb(0,0,0).ToColor(), "zero RGB is an explicit valid choice");
        Equal(Color.White, Rgb(255,255,255).ToColor(), "RGB upper bound is exact");
        foreach (string payload in new[] { "element", "particle" })
        {
            var root = JsonNode.Parse(wire)!.AsObject();
            var row = root["vfxManifest"]!["slots"]!.AsArray().Single(s => s![payload] is not null)!;
            if (payload == "element") row[payload]!["colorProfile"]!["start"] = "effect";
            else row[payload]!["colorStart"] = "silver";
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "nested color refuses tokens " + payload);
            Equal(true, ContractJsonDiagnostics.TryGet("GeneratedItemData.FromJson", out _), "unsupported RGB records diagnostics " + payload);
        }
        foreach (var retired in new[] { (Owner: "visual", Field: "visualSoulSignature"), (Owner: "visual", Field: "visualSoulArchetype"),
            (Owner: "visual", Field: "visualSoulGlow"), (Owner: "visual", Field: "visualSoulPulse"), (Owner: "visual", Field: "visualSoulCoverage"),
            (Owner: "visual", Field: "visualSoulEdgeDensity"), (Owner: "visual", Field: "preservationScore"),
            (Owner: "accessory", Field: "archetype"), (Owner: "armor", Field: "archetype") }) {
            var root = JsonNode.Parse(wire)!.AsObject(); root[retired.Owner]![retired.Field] = "retired";
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "inert native metadata refuses " + retired.Owner + "." + retired.Field);
        }
        var oldVisual = JsonNode.Parse(wire)!.AsObject(); oldVisual["visual"]!["effectColor"] = "silver";
        Equal(true, GeneratedItemData.FromJson(oldVisual.ToJsonString()) is null, "retired global Visual color refuses rather than overriding local RGB");
    }
}
