using System;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using ParticleLibrary.Core.V3.Particles;

internal static partial class EngineRuntimeChecks
{
    // Exact Python Visual -> VFX -> sanitized delivery fixture. The paired
    // pytest checks the full retained JSON value, not a reconstructed DTO.
    private static void PlayedSilverFinalDeliveryAndNativeColorConsumers()
    {
        string wire = File.ReadAllText(Path.Combine("tools", "fixtures", "played-silver-delivered.json"));
        var data = GeneratedItemData.FromJson(wire)
            ?? throw new InvalidOperationException("silver final delivery refused: " + ContractJsonDiagnostics.LastError);
        Color silver = new(192, 192, 192);
        Equal("silver", data.Visual.EffectColor!, "silver remains explicit, never repaired to gray");
        Equal("silver", RuntimeColorPolicy.RequireRenderingToken("silver"), "exact rendering admission");
        Equal(silver, RuntimeColorPolicy.Resolve("silver", Color.Magenta), "finite RGB is not fallback or gray");
        Equal(false, silver == RuntimeColorPolicy.Resolve("gray", Color.Magenta), "silver and gray are distinct RGB tokens");
        Equal(silver, InfiniVfxRuntime.PresentationColor(data, Color.Magenta), "shared item/projectile/detached effect consumer");
        var element = data.VfxManifest.Slots.Single(s => s.RendererKind == "spriteElement").Element!;
        var ramp = VfxColorRamp.Copy(element.ColorProfile, InfiniVfxRuntime.PresentationColor(data, Color.Magenta));
        Equal(silver, ramp.At(0, 1, "alpha"), "explicit material start knot reaches RGB");
        Equal(silver, ramp.At(.5f, 1, "alpha"), "captured effect knot reaches RGB");
        Equal(silver, ramp.At(1, 1, "alpha"), "explicit material end knot reaches RGB");
        var slot = data.VfxManifest.Slots.Single(s => s.RendererKind == "libraryParticle");
        object design = LibraryInvoke("CopyLibrary", data, slot, false)!;
        data.Visual.EffectColor = "red";
        element.ColorProfile.Start = "blue";
        slot.Particle!.ColorStart = "green";
        var info = (ParticleInfo)LibraryInvoke("CreateLibraryInfoCore", design,
            new VfxSourceFrame(Vector2.Zero, Vector2.UnitX, Vector2.Zero), .5f, .5f)!;
        Equal(silver * slot.Alpha, info.Color, "native library CPU particle captures explicit silver at emission");
        while (info.Time > 1) InfiniDetachedVfxSystem.AdvanceLibraryInfo(ref info);
        Equal(info.Color.R, info.Color.G, "captured silver remains achromatic after source mutation");
        Equal(info.Color.G, info.Color.B, "captured effect endpoint remains achromatic");
        Equal(silver, ramp.At(0, 1, "alpha"), "material ramp is immutable after source mutation");
        var accepted = GeneratedItemData.FromJson(wire)!;
        var roundtrip = GeneratedItemData.FromJson(accepted.ToJson())
            ?? throw new InvalidOperationException("silver definition roundtrip refused");
        Equal("silver", roundtrip.Visual.EffectColor!, "native definition roundtrip retains token");
        foreach (string bad in new[] { "Silver", " silver", "silver ", "#C0C0C0", "silver gray", "effect" })
        {
            var root = JsonNode.Parse(wire)!.AsObject(); root["visual"]!["effectColor"] = bad;
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "exact Visual color refusal " + bad);
        }
        foreach (string payload in new[] { "element", "particle" })
        {
            var root = JsonNode.Parse(wire)!.AsObject();
            var row = root["vfxManifest"]!["slots"]!.AsArray().Single(s => s![payload] is not null)!;
            if (payload == "element") row[payload]!["colorProfile"]!["start"] = "silver gray";
            else row[payload]!["colorStart"] = "silver gray";
            Equal(true, GeneratedItemData.FromJson(root.ToJsonString()) is null, "nested color rejects prose " + payload);
        }
        var absent = JsonNode.Parse(wire)!.AsObject(); absent["visual"]!.AsObject().Remove("effectColor");
        var legacy = GeneratedItemData.FromJson(absent.ToJsonString())!;
        Equal(Color.Magenta, InfiniVfxRuntime.PresentationColor(legacy, Color.Magenta), "absence retains caller-owned legacy color");
    }
}
