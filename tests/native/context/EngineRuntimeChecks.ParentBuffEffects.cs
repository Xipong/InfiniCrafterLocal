using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    // Capture-only checks: no Player.UpdateBuffs/NPC.Update/ModBuff hook invocation.
    // Runner registration belongs to the integration owner.
    private static void ParentBuffEffectsAreSourceCertifiedAndParentLocal()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.player[0] = new Player();
        var capture = typeof(GeneratorClient).GetMethod("CaptureNativeBuffEffectReference", BindingFlags.Static | BindingFlags.NonPublic)!;
        JsonObject Read(int id, string receiver)
            => (JsonObject)capture.Invoke(null, new object[] { id, receiver })!;
        foreach (var pair in new[] { (BuffID.Mining, "Terraria.Player.pickSpeed", -0.25),
                                    (BuffID.Poisoned, "Terraria.NPC.lifeRegen", -12.0),
                                    (BuffID.Ichor, "NPC.HitModifiers.Defense.Flat", -15.0) })
        {
            JsonObject fact = Read(pair.Item1, pair.Item1 == BuffID.Mining ? "player" : "npc");
            Equal("partial_native_statement_fragments", fact["completeness"]!.GetValue<string>(), "installed native source must be certified, not silently skipped");
            Equal(true, fact["sourceCertificate"] is JsonObject, "effect carries every dependent method certificate");
            var operations = fact["fragments"]!.AsArray().SelectMany(f => f!["operations"]!.AsArray()).ToArray();
            Equal(true, operations.Any(o => o!["nativeMember"]!.GetValue<string>() == pair.Item2
                && o["value"]!.GetValue<double>() == pair.Item3), "source value is retained without capability preset routing");
            Equal(true, fact["unsupported"]!.AsArray().Count > 0, "partial source coverage is explicit");
        }
        JsonObject spelunker = Read(BuffID.Spelunker, "player");
        Equal(true, spelunker["fragments"]!.AsArray().SelectMany(f => f!["operations"]!.AsArray())
            .Any(o => o!["nativeMember"]!.GetValue<string>() == "Terraria.Player.findTreasure" && o["value"]!.GetValue<bool>()),
            "boolean utility source write is not a copied tooltip");
        var verified = typeof(GeneratorClient).GetMethod("VerifiedNativeBuffEffectReference", BindingFlags.Static | BindingFlags.NonPublic)!;
        foreach (var args in new object?[][] {
            new object?[] { BuffID.Mining, "player", "unknown-binary:unknown-module" },
            new object?[] { BuffID.Count + 900, "player", null },
        })
        {
            JsonObject refused = (JsonObject)verified.Invoke(null, args)!;
            Equal("unsupported", refused["completeness"]!.GetValue<string>(), "unknown binary/modded semantics fail closed");
            Equal(0, refused["fragments"]!.AsArray().Count, "unknown semantics receive no guessed stats");
        }
        var skin = Read(BuffID.ObsidianSkin, "player")["fragments"]!.AsArray()
            .SelectMany(f => f!["operations"]!.AsArray()).ToArray();
        Equal(true, skin.Any(o => o!["nativeMember"]!.GetValue<string>() == "Terraria.Player.buffImmune"
            && o["arrayIndex"]!.GetValue<int>() == BuffID.OnFire && o["value"]!.GetValue<bool>()),
            "array immunity write no longer discards the entire ObsidianSkin branch");
        foreach (var pair in new[] { (BuffID.Ironskin, "Terraria.Player.statDefense", 8.0),
                                    (BuffID.MagicPower, "Terraria.Player.get_magicDamage", (double)0.2f) })
        {
            var ops = Read(pair.Item1, "player")["fragments"]!.AsArray().SelectMany(f => f!["operations"]!.AsArray());
            Equal(true, ops.Any(o => o!["nativeMember"]!.GetValue<string>() == pair.Item2
                && o["operation"]!.GetValue<string>() == "operator_call_and_assign"
                && o["value"]!.GetValue<double>() == pair.Item3), "typed native operator arguments reach parent facts");
        }

        var client = new GeneratorClient();
        using var potions = JsonDocument.Parse(client.Prepare(new Item(ItemID.MiningPotion), new Item(ItemID.SpelunkerPotion), Terraria.Main.player[0]).PayloadJson);
        foreach (string side in new[] { "itemA", "itemB" })
        {
            JsonElement item = potions.RootElement.GetProperty(side);
            Equal(false, item.TryGetProperty("loadedBuffIdentitiesRaw", out _), "no global buff registry in parent packet");
            Equal("player", item.GetProperty("nativeBuffEffectReference").GetProperty("receiver").GetString()!, "self-use facts have player receiver");
            Equal(CanonicalParentFactJson(item.GetProperty("nativeBuffEffectReference")),
                CanonicalParentFactJson(item.GetProperty("runtimeFacts").GetProperty("nativeBuffEffectReference")), "single fact capture projects literally");
        }
        using var swords = JsonDocument.Parse(client.Prepare(new Item(ItemID.BladeofGrass), new Item(ItemID.LightsBane), Terraria.Main.player[0]).PayloadJson);
        var contact = swords.RootElement.GetProperty("itemA").GetProperty("nativeContactHitStatusReference");
        var choice = contact.GetProperty("randomOutcomes").EnumerateArray().Single();
        var proc = choice.GetProperty("alternatives").EnumerateArray().Single(a => a.GetProperty("effects").GetArrayLength() > 0);
        Equal(1, proc.GetProperty("probabilityNumerator").GetInt32(), "Poisoned request probability numerator preserved");
        Equal(4, proc.GetProperty("probabilityDenominator").GetInt32(), "Poisoned request probability denominator preserved");
        var effect = proc.GetProperty("effects")[0];
        Equal(BuffID.Poisoned, effect.GetProperty("buffId").GetInt32(), "contact request keeps source ID20");
        Equal(420, effect.GetProperty("durationTicksMin").GetInt32(), "contact duration stays420 ticks");
        Equal(420, effect.GetProperty("durationTicksMax").GetInt32(), "contact duration maximum stays420 ticks");
        Equal("npc", effect.GetProperty("buffEffectReference").GetProperty("receiver").GetString()!, "on-hit effect describes NPC receiver");
        Equal(false, swords.RootElement.GetProperty("itemA").TryGetProperty("nativeBuffEffectReference", out _), "NPC hit must not become a self buff");
        string? statusExport = Environment.GetEnvironmentVariable("INFINI_PARENT_STATUS_PACKET");
        if (!string.IsNullOrEmpty(statusExport)) File.WriteAllText(statusExport, swords.RootElement.GetRawText());
        string? buffExport = Environment.GetEnvironmentVariable("INFINI_PARENT_BUFF_PACKET");
        if (!string.IsNullOrEmpty(buffExport)) File.WriteAllText(buffExport, potions.RootElement.GetRawText());
    }
}
