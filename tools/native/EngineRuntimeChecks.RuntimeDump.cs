using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Commands;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void RuntimeDumpSharesCompleteParentAndProjectileCapture()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
        MethodInfo? itemCapture = typeof(InfiniDumpCommand).GetMethod("CaptureItemSnapshot", BindingFlags.Static | BindingFlags.NonPublic);
        MethodInfo? projectileCapture = typeof(InfiniDumpCommand).GetMethod("CaptureProjectileSnapshot", BindingFlags.Static | BindingFlags.NonPublic);
        Equal(true, itemCapture is not null && projectileCapture is not null,
            "dump must expose and actually use the same complete capture as a prepared craft, not a parallel SetDefaults field list");
        var packets = new List<JsonNode>();
        foreach (int type in new[] { ItemID.Excalibur, ItemID.TrueExcalibur, ItemID.TerraBlade,
            ItemID.WoodenArrow, ItemID.BladeofGrass, ItemID.BandofRegeneration, ItemID.Boomstick })
        {
            var item = new Item(type);
            var player = new Player();
            // Some native projectile defaults (e.g. Blade of Grass) sample scale.
            // Compare captures under identical RNG state, not different samples.
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
            using var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, item, player).PayloadJson);
            JsonObject live = JsonNode.Parse(request.RootElement.GetProperty("itemA").GetRawText())!.AsObject();
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
            // Compare actual serialized JSONL semantics, not JsonValue<float>
            // nodes against already-parsed native float JSON from Prepare.
            JsonObject dump = JsonNode.Parse(((JsonObject)itemCapture!.Invoke(null, new object[] { item })!).ToJsonString())!.AsObject();
            Equal(item.type, dump["type"]!.GetValue<int>(), "historical dump type remains a native identity");
            foreach (string key in new[] { "runtimeFacts", "fingerprint", "nativeShootReference", "nativeContactHitStatusReference",
                "nativeEquipmentReference", "nativeEnvironmentReference", "nativeBuffEffectReference", "parentSourceGraph", "tooltipLines", "tooltipSource" })
            {
                if (!JsonNode.DeepEquals(live[key], dump[key]) && Environment.GetEnvironmentVariable("INFINI_DUMP_PARITY_PACKET") is string evidence)
                    System.IO.File.WriteAllText(evidence + ".diff.json", JsonSerializer.Serialize(new { type, key, live = live[key], dump = dump[key] }));
                Equal(true, JsonNode.DeepEquals(live[key], dump[key]), type + " exact live/dump source observation " + key);
            }
            JsonNode? direct = dump["directProjectileRaw"];
            if (direct is JsonObject directObject)
            {
                var withoutMetrics = (JsonObject)directObject.DeepClone();
                withoutMetrics.Remove("textureMetrics");
                Equal(true, JsonNode.DeepEquals(live["directProjectileRaw"], withoutMetrics), "nested dump projectile preserves every canonical source observation");
                JsonObject projectile = (JsonObject)projectileCapture!.Invoke(null, new object[] { item.shoot })!;
                foreach (string key in new[] { "motionReference", "collisionReference", "onHitStatusReference", "attackReference", "armorPenetration", "aiStyle" })
                    Equal(true, JsonNode.DeepEquals(direct[key], projectile[key]), "standalone projectile and item projectile share source facts: " + key);
            }
            Equal(item.damage, dump["damage"]!.GetValue<int>(), "capture does not rebalance parent");
            Equal(item.damage, live["damage"]!.GetValue<int>(), "capture does not mutate consumed item");
            packets.Add(dump);
        }
        Equal(true, packets.Single(p => p["type"]!.GetValue<int>() == ItemID.WoodenArrow)["directProjectileRaw"]!["motionReference"] is not null,
            "existing verified arrow motion is no longer lost only in dump");
        Equal(true, packets.Single(p => p["type"]!.GetValue<int>() == ItemID.BandofRegeneration)["lifeRegen"] is not null,
            "non-attack native facts also follow the canonical capture");
        string? path = Environment.GetEnvironmentVariable("INFINI_DUMP_PARITY_PACKET");
        if (!string.IsNullOrEmpty(path)) System.IO.File.WriteAllText(path, JsonSerializer.Serialize(packets));
    }

    private static void ParentProjectileAttackSemanticsReachPrepareAndDump()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        var item = new Item(ItemID.Excalibur);
        using var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, item, new Player()).PayloadJson);
        var projectile = request.RootElement.GetProperty("itemA").GetProperty("directProjectileRaw");
        Equal(true, projectile.TryGetProperty("attackReference", out var attack) && attack.ValueKind == JsonValueKind.Object,
            "native Excalibur needs actual motion/collision/draw source observations, not only 16x16 defaults and an AI number");
        JsonObject dump = InfiniDumpCommand.CaptureItemSnapshot(item);
        Equal(true, dump["directProjectileRaw"]!["attackReference"] is JsonObject,
            "the same attack observation reaches dump without a second field map");
    }

    private static void RuntimeDumpKeepsCaptureFailuresAsExplicitRows()
    {
        var method = typeof(InfiniDumpCommand).GetMethod("WriteSnapshot", BindingFlags.Static | BindingFlags.NonPublic);
        Equal(true, method is not null, "dump capture failures need explicit rows instead of silent disappearance");
        using var writer = new System.IO.StringWriter();
        var options = new JsonSerializerOptions();
        Func<JsonObject?> valid = () => new JsonObject { ["type"] = 42, ["damage"] = 0 };
        Func<JsonObject?> failed = () => throw new InvalidOperationException("private runtime detail must not be exported");
        method!.Invoke(null, new object[] { writer, 42, valid, options });
        method.Invoke(null, new object[] { writer, 43, failed, options });
        method.Invoke(null, new object[] { writer, 42, valid, options });
        var rows = writer.ToString().Split('\n', StringSplitOptions.RemoveEmptyEntries).Select(line => JsonNode.Parse(line)!).ToArray();
        Equal(3, rows.Length, "failed definition does not vanish or hide the next definition");
        Equal(0, rows[0]["damage"]!.GetValue<int>(), "zero source facts remain literal");
        Equal(43, rows[1]["type"]!.GetValue<int>(), "failed identity is retained");
        Equal(true, rows[1]["unavailable"]!.GetValue<bool>(), "capture is unavailable, not an empty healthy definition");
        Equal(nameof(InvalidOperationException), rows[1]["captureError"]!.GetValue<string>(), "bounded diagnostic is exception type only");
        Equal(false, rows[1].ToJsonString().Contains("private runtime detail", StringComparison.Ordinal), "exception content is not exposed");
    }
}
