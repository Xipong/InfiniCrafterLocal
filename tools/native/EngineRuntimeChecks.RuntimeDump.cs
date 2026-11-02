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
        if (Environment.GetEnvironmentVariable("INFINI_DUMP_ATTACK_PARENT") is string output)
            System.IO.File.WriteAllText(output, request.RootElement.GetRawText());
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
    private static void RuntimeDumpPublishesImmutablePairAndPreservesPreviousOnFailure()
    {
        string root = System.IO.Directory.CreateTempSubdirectory("ifc-dump-pair-").FullName;
        try
        {
            var captureEnvironment = typeof(InfiniDumpCommand).GetMethod("CaptureDumpEnvironment", BindingFlags.Static | BindingFlags.NonPublic)!;
            var environment = (JsonObject)captureEnvironment.Invoke(null, null)!;
            Equal(Terraria.Main.versionNumber, environment["gameVersion"]!.GetValue<string>(), "manifest game version comes from loaded native constants");
            Equal(typeof(Terraria.ModLoader.ModLoader).Module.ModuleVersionId.ToString(),
                environment["tModLoader"]!["mvid"]!.GetValue<string>(), "loaded tML module identity is observed, not inferred from game version");
            Equal(typeof(InfiniDumpCommand).Module.ModuleVersionId.ToString(),
                environment["exporter"]!["mvid"]!.GetValue<string>(), "manifest identifies the actual exporter build");
            JsonObject Publish(bool fail) => InfiniDumpCommand.PublishSnapshot(root,
                writer => writer.WriteLine("{\"type\":1,\"damage\":0}"),
                writer =>
                {
                    writer.WriteLine("{\"type\":2,\"unavailable\":true}");
                    if (fail) throw new System.IO.IOException("test interruption before manifest publication");
                }, environment);
            JsonObject first = Publish(false);
            string manifestPath = System.IO.Path.Combine(root, InfiniDumpCommand.DumpManifestName);
            string original = System.IO.File.ReadAllText(manifestPath);
            string oldItem = System.IO.Path.Combine(root, first["files"]!["items"]!["path"]!.GetValue<string>());
            string oldProjectile = System.IO.Path.Combine(root, first["files"]!["projectiles"]!["path"]!.GetValue<string>());
            Equal(1, first["files"]!["items"]!["rows"]!.GetValue<int>(), "manifest counts literal item rows");
            Equal(1, first["files"]!["projectiles"]!["unavailableRows"]!.GetValue<int>(), "capture refusals are counted, not hidden");
            foreach (string kind in new[] { "items", "projectiles" })
            {
                var entry = first["files"]![kind]!;
                byte[] bytes = System.IO.File.ReadAllBytes(System.IO.Path.Combine(root, entry["path"]!.GetValue<string>()));
                Equal((long)bytes.Length, entry["bytes"]!.GetValue<long>(), "manifest binds exact byte length");
                Equal(Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)).ToLowerInvariant(),
                    entry["sha256"]!.GetValue<string>(), "manifest binds exact SHA-256");
            }
            bool failed = false;
            try { Publish(true); } catch (System.IO.IOException) { failed = true; }
            Equal(true, failed, "I/O failure remains terminal, never successful partial export");
            Equal(original, System.IO.File.ReadAllText(manifestPath), "failed second capture cannot replace the previous manifest");
            Equal(true, System.IO.File.Exists(oldItem) && System.IO.File.Exists(oldProjectile), "previous complete pair survives");
            Equal(1, System.IO.Directory.GetDirectories(System.IO.Path.Combine(root, "runtime_dump_snapshots")).Length,
                "only unpublished failed attempt is removed");
            JsonObject second = Publish(false);
            Equal(false, first["snapshotId"]!.GetValue<string>() == second["snapshotId"]!.GetValue<string>(), "new snapshot has a separate immutable identity");
            Equal(true, System.IO.File.Exists(oldItem) && System.IO.File.Exists(oldProjectile), "successful publication also retains previous pair");
            Equal(false, System.IO.File.Exists(System.IO.Path.Combine(root, "items_runtime_dump.jsonl")), "no mutable legacy alias recreates mixed-pair risk");
            string current = System.IO.File.ReadAllText(manifestPath);
            try
            {
                InfiniDumpCommand.PublishSnapshot(root, writer =>
                {
                    for (int n = 0; n <= InfiniDumpCommand.DumpRowLimit; n++) writer.WriteLine("{\"type\":1}");
                }, _ => { }, environment);
                throw new Exception("row bound did not refuse export");
            }
            catch (System.IO.InvalidDataException) { }
            Equal(current, System.IO.File.ReadAllText(manifestPath), "bounded failure leaves accepted manifest unchanged");
            if (Environment.GetEnvironmentVariable("INFINI_DUMP_MANIFEST_TEST_OUTPUT") is string output)
            {
                System.IO.Directory.CreateDirectory(output);
                // Synthetic rows only; enables reader interoperability verification.
                InfiniDumpCommand.PublishSnapshot(output,
                    writer => writer.WriteLine("{\"type\":1}"),
                    writer => writer.WriteLine("{\"type\":2,\"sourceMod\":\"Synthetic\",\"internalName\":\"Bolt\"}"),
                    environment);
            }
        }
        finally { System.IO.Directory.Delete(root, recursive: true); }
    }

    private static void RuntimeDumpNebulaRainbowAvailableContentRoundTrip()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.SinglePlayer;
        Terraria.Main.dedServ = true; // No GPU/world simulation is part of this content check.
        var rows = new List<JsonObject>();
        foreach (int type in new[] { ItemID.NebulaArcanum, ItemID.RainbowCrystalStaff })
        {
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
            var item = new Item(type);
            using var request = JsonDocument.Parse(new GeneratorClient().Prepare(item, item, new Player()).PayloadJson);
            var live = JsonNode.Parse(request.RootElement.GetProperty("itemA").GetRawText())!.AsObject();
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
            JsonObject dump = InfiniDumpCommand.CaptureItemSnapshot(item);
            foreach (string field in new[] { "useTime", "useAnimation", "reuseDelay", "tooltipLines", "tooltipSource",
                "nativeShootReference", "nativeEquipmentReference", "nativeContactHitStatusReference", "parentSourceGraph" })
                Equal(true, JsonNode.DeepEquals(live[field], dump[field]), "bounded parent live/dump literal content parity: " + field);
            var direct = dump["directProjectileRaw"]!.AsObject();
            var standalone = InfiniDumpCommand.CaptureProjectileSnapshot(item.shoot);
            foreach (string field in new[] { "timeLeft", "extraUpdates", "framesRaw", "setsRaw", "attackReference",
                "motionReference", "collisionReference", "onHitStatusReference", "spriteReferenceRaw" })
                Equal(true, JsonNode.DeepEquals(direct[field], standalone[field]), "item/standalone projectile available observation parity: " + field);
            Equal(true, direct["attackReference"] is JsonObject, "bounded source coverage, including unknowns, reaches dump");
            rows.Add(dump);
        }
        if (Environment.GetEnvironmentVariable("INFINI_DUMP_CONTENT_TEST_OUTPUT") is string output)
        {
            var captureEnvironment = typeof(InfiniDumpCommand).GetMethod("CaptureDumpEnvironment", BindingFlags.Static | BindingFlags.NonPublic)!;
            var environment = (JsonObject)captureEnvironment.Invoke(null, null)!;
            InfiniDumpCommand.PublishSnapshot(output,
                writer => { foreach (var row in rows) writer.WriteLine(row.ToJsonString()); },
                writer =>
                {
                    // Catalog rows exist independently of any proved spawn edge.
                    foreach (int type in new[] { ProjectileID.NebulaArcanum, ProjectileID.NebulaArcanumSubshot,
                        ProjectileID.RainbowCrystal, ProjectileID.RainbowCrystalExplosion })
                        writer.WriteLine(InfiniDumpCommand.CaptureProjectileSnapshot(type).ToJsonString());
                }, environment);
        }
    }

}
