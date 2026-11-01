#nullable enable
// Repository-owned historical-format fixtures; no private cache, DLL or PNG input.
// The reflection fallback intentionally runs the original strict reader on baseline
// so RED is a refused valid persisted definition, not a compile-time missing API.
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static GeneratedItemData? ReadPersistedDefinition(string json)
    {
        var reader = typeof(GeneratedItemData).GetMethod("FromLocalCacheJson", new[] { typeof(string) });
        return reader is null ? GeneratedItemData.FromJson(json) : (GeneratedItemData?)reader.Invoke(null, new object[] { json });
    }

    private static JsonObject PersistedV15Fixture(GeneratedItemData? source = null)
    {
        var wire = JsonNode.Parse((source ?? NamedItemEffectsFixture()).ToLocalCacheJson())!.AsObject();
        wire["canonical"] = new JsonObject { ["headNoun"] = "NOT A GAMEPLAY ROUTER" };
        wire["sourceRepresentation"] = new JsonArray(); wire["inheritance"] = new JsonArray();
        wire["lossBudget"] = new JsonObject(); wire["itemKnowledge"] = new JsonObject();
        wire["gameplay"]!["stage"] = "early"; wire["gameplay"]!["powerBudget"] = 1;
        wire["accessory"]!["archetype"] = "NOT AN EFFECT"; wire["armor"]!["archetype"] = "NOT AN EFFECT";
        wire["generatedParentSummary"]!["notableEffects"] = new JsonArray("advisory only");
        wire["generatedParentSummary"]!["runtimePrimaryEntityId"] = "not_authority";
        wire["generatedParentSummary"]!["runtimeEntityIds"] = new JsonArray("not_authority");
        var visual = wire["visual"]!.AsObject();
        foreach (string field in new[] { "objectType", "style", "semanticReviewStatus", "visualSoulSignature", "visualSoulArchetype", "dominantColorHex", "accentColorHex" }) visual[field] = "inert";
        visual["requiredAnchors"] = new JsonArray();
        foreach (string field in new[] { "preservationScore", "visualSoulGlow", "visualSoulPulse", "visualSoulCoverage", "visualSoulEdgeDensity" }) visual[field] = .5;
        visual["effectColor"] = "orange";
        var vfx = wire["vfxManifest"]!.AsObject(); vfx["schema"] = "infini.vfx.runtime-events.v15";
        vfx["effectName"] = "diagnostic"; vfx["inspirationNames"] = new JsonArray(); vfx["playbackMode"] = "Realtime";
        vfx["seed"] = 123; vfx["confidence"] = 1; vfx["effectMagnitude"] = .3; vfx["visualBudgetClass"] = "small";
        vfx["motif"] = new JsonObject { ["element"] = "ice", ["shapeLanguage"] = "literal saved prose", ["motionLanguage"] = "literal saved prose", ["paletteRole"] = "primary", ["rhythm"] = 1, ["chaos"] = 0 };
        vfx["overlayPolicy"] = "LocalOnly"; vfx["debug"] = new JsonObject(); vfx["hasSlots"] = false;
        var budget = vfx["budget"]!.AsObject();
        foreach (string field in new[] { "effectMagnitude", "spawnRateMultiplier" }) budget[field] = 1;
        budget["visualBudgetClass"] = "small";
        foreach (string field in new[] { "emergencyCap", "enableSoftGlow", "enablePointSparks", "enablePersistentSmoke" }) budget[field] = true;
        return wire;
    }

    private static JsonObject PersistedV15Slot(string renderer, string entity, string eventName)
    {
        var slot = new JsonObject {
            ["id"] = "saved_" + renderer.ToLowerInvariant(), ["entityId"] = entity, ["event"] = eventName, ["rendererKind"] = renderer,
            ["effectName"] = "", ["eventGroup"] = "auto", ["stage"] = "loop", ["backend"] = "Auto",
            ["textureRole"] = renderer == "impactSprite" ? "impact" : "none", ["particleRole"] = "none",
            ["anchor"] = "self", ["blend"] = "additive", ["layer"] = "AfterProjectiles", ["channel"] = "impactShape", ["lane"] = "accent",
            ["source"] = "llm_vfx_director", ["emissionMode"] = "none", ["particleSystemId"] = "none",
            ["fadeIn"] = 0, ["fadeOut"] = 0, ["slotSeed"] = 12345, ["startTick"] = 0, ["repeatEvery"] = 0,
            ["scale"] = .8, ["density"] = .2, ["duration"] = 9, ["alpha"] = .55, ["spread"] = 0, ["jitter"] = 0,
            ["phaseOffset"] = 0, ["budgetWeight"] = 1, ["visualCost"] = .2, ["signatureWeight"] = 0,
            ["bakedClipId"] = "", ["bakedClipHash"] = "", ["bakedCommandCount"] = 0, ["bakedCommands"] = new JsonArray()
        };
        if (renderer == "soundCue") {
            slot["soundId"] = "Item1"; slot["sound"] = new JsonObject { ["volume"] = .45, ["pitch"] = .15, ["pitchVariance"] = .08 };
            slot["channel"] = "sound"; slot["lane"] = "cue";
        }
        if (renderer == "libraryParticle") {
            slot["particle"] = LibrarySlotWire()["particle"]!.DeepClone();
            slot["particle"]!["colorStart"] = "gold"; slot["particle"]!["colorEnd"] = "effect";
            slot["scale"] = 1; slot["density"] = 0; slot["visualCost"] = 0;
            slot["startTick"] = 10; slot["duration"] = 12; slot["channel"] = "impactParticles"; slot["backend"] = "Particle";
        }
        return slot;
    }

    private static void PersistedV5MetadataDoesNotOwnGameplay()
    {
        // Frozen baseline bytes, deliberately NOT regenerated by today's writer.
        // Otherwise adding a newly required field to both DTO and fixture would
        // hide the very minor-update regression this boundary must prevent.
        string archived = File.ReadAllText(Path.Combine("LocalGenerator", "tests", "fixtures", "persisted_v5_baseline.json"));
        Equal("f34bc94a29038f341c46c227ba126a024e1f7ce711f4330a305f236ba579cefc",
            Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(archived))).ToLowerInvariant(), "immutable persisted baseline");
        var snapshot = JsonNode.Parse(archived)!;
        foreach (var entry in snapshot["cases"]!.AsArray()) {
            var definition = entry!["definition"]!;
            Equal(true, ReadPersistedDefinition(definition.ToJsonString()) is null, "retired pose fields are not a production compatibility fallback");
            // Metadata compatibility remains covered on an explicit current test envelope.
            // User-approved removal of the old pose contract does not change these saved mechanics.
            var current = definition.DeepClone();
            Equal("", current["runtimeProgram"]!["itemUse"]!["releaseTiming"]!.GetValue<string>(), "known saved empty runtime timing");
            Equal("", current["gameplay"]!["releaseTiming"]!.GetValue<string>(), "known saved empty gameplay timing");
            current["runtimeProgram"]!["itemUse"]!.AsObject().Remove("releaseTiming");
            current["gameplay"]!.AsObject().Remove("releaseTiming");
            var roundtrip = current.DeepClone();
            roundtrip["runtimeProgram"]!["itemUse"]!["releaseTiming"] = "";
            roundtrip["gameplay"]!["releaseTiming"] = "";
            Equal(true, JsonNode.DeepEquals(definition, roundtrip), "historical metadata and executable semantics are unchanged");
            var restored = ReadPersistedDefinition(current.ToJsonString())
                ?? throw new InvalidOperationException("explicit current envelope of frozen v5 baseline refused: " + entry["case"]);
            Equal((int)definition["gameplay"]!["damage"]!, restored.Gameplay.Damage, "frozen damage preserved");
            Equal((int)definition["gameplay"]!["useTime"]!, restored.Gameplay.UseTime, "frozen native cadence preserved");
            Equal(definition["runtimeProgram"]!["entities"]!.AsArray().Count, restored.RuntimeProgram.Entities.Length, "frozen entity topology retained");
            Equal(definition["runtimeProgram"]!["bindings"]!.AsArray().Count, restored.RuntimeProgram.Bindings.Length, "frozen input topology retained");
        }
        foreach (var source in new[] { NamedItemEffectsFixture(), SentryTargetingFixture(), GeneratedItemData.Placeholder() }) {
            string canonical = source.ToLocalCacheJson();
            var old = PersistedV15Fixture(source); string input = old.ToJsonString();
            var loaded = ReadPersistedDefinition(input) ?? throw new InvalidOperationException("historical v5 item refused before executable validation");
            var actual = JsonNode.Parse(loaded.ToLocalCacheJson())!; var expected = JsonNode.Parse(canonical)!;
            foreach (string owner in new[] { "runtimeProgram", "gameplay", "accessory", "armor", "visual", "recipeMeta", "generatedParentSummary" })
                Equal(expected[owner]!.ToJsonString(), actual[owner]!.ToJsonString(), "persisted metadata never reauthors " + owner);
            Equal(input, old.ToJsonString(), "projection does not mutate caller JSON");
            Equal(true, GeneratedItemData.FromJson(input) is null, "fresh/network reader stays strict");
            var receipt = typeof(GeneratedItemData).GetProperty("LocalCacheReadReceipt")?.GetValue(loaded) as string[];
            Equal(true, receipt is { Length: > 0 } && receipt.Any(s => s.Contains("$.canonical")), "inert omission has path-specific receipt");
            Equal(false, actual.AsObject().ContainsKey("localCacheReadReceipt"), "receipt is not executable wire");
        }
    }

    private static void PersistedV15ExecutableSlotsRefuseWithoutReconstruction()
    {
        // A saved v15 effect is not a request to re-run old semantic color
        // selection, even when its historical tokens happen to be familiar.
        foreach (string renderer in new[] {
            "soundCue", "impactRing", "impactSprite", "libraryParticle",
            "projectileAfterimage", "actorAfterimage", "spriteElement", "texturedPath"
        }) {
            var saved = PersistedV15Fixture();
            var slot = PersistedV15Slot(renderer, "unavailable_item", "on_use");
            if (renderer == "impactRing") slot["color"] = RgbWire(255, 155, 70);
            saved["vfxManifest"]!["slots"] = new JsonArray(slot);
            string original = saved.ToJsonString();
            Equal(true, ReadPersistedDefinition(original) is null,
                "v15 executable " + renderer + " cannot be historically reinterpreted");
            Equal(true, ContractJsonDiagnostics.TryGet("GeneratedItemData.FromLocalCacheJson", out var error)
                && error?.Path == "$.vfxManifest.slots",
                "nonempty v15 refuses at its executable slot boundary");
            Equal(original, saved.ToJsonString(), "rejecting v15 does not mutate saved bytes");
        }
    }

    private static void PersistedV15EmptyMotifAndEffectColorAreOpaque()
    {
        // Even malformed old metadata must be irrelevant when no VFX slots
        // execute. Nobody should ever consult motif.element at load time.
        foreach (JsonNode? motif in new JsonNode?[] {
            null, JsonValue.Create("not even an object"), JsonValue.Create(123),
            new JsonArray("arbitrary", "prose"),
            new JsonObject { ["element"] = "fire", ["futureUnknown"] = new JsonArray(1, 2) }
        }) {
            var saved = PersistedV15Fixture();
            saved["vfxManifest"]!["motif"] = motif?.DeepClone();
            saved["visual"]!["effectColor"] = new JsonObject { ["notAColor"] = true };
            saved["vfxManifest"]!["debug"] = new JsonObject { ["arbitrary"] = new JsonArray("debug") };
            string input = saved.ToJsonString();
            var restored = ReadPersistedDefinition(input)
                ?? throw new InvalidOperationException("empty saved VFX unexpectedly depends on motif or effectColor");
            var serialized = JsonNode.Parse(restored.ToLocalCacheJson())!;
            Equal(0, restored.VfxManifest.Slots.Length, "empty VFX remains empty");
            Equal(false, serialized["vfxManifest"]!.AsObject().ContainsKey("motif"), "motif not persisted as authority");
            Equal(false, serialized["visual"]!.AsObject().ContainsKey("effectColor"), "retired effectColor never resolved");
            Equal(true, restored.LocalCacheReadReceipt.Any(x => x.Contains("motif")), "opaque omission documented");
            Equal(input, saved.ToJsonString(), "no rewrite of original historical cache");
        }
    }

    private static void PersistedV16BakedColorsStayAuthoritative()
    {
        var source = ParseMaterialElement(MaterialElementWire());
        string canonical = source.ToLocalCacheJson();
        var saved = JsonNode.Parse(canonical)!.AsObject();
        // This is NOT an invitation to recalculate already-baked RGB.
        saved["vfxManifest"]!["motif"] = new JsonObject {
            ["element"] = "fire", ["futureLegacyAdvisory"] = new JsonArray("no interpreter")
        };
        saved["visual"]!["effectColor"] = "not-a-supported-color-token";
        string savedBytes = saved.ToJsonString();
        var restored = ReadPersistedDefinition(savedBytes)
            ?? throw new InvalidOperationException("current baked-RGB VFX refused because of dead metadata");
        var actual = JsonNode.Parse(restored.ToLocalCacheJson())!;
        var expected = JsonNode.Parse(canonical)!;
        foreach (string field in new[] { "slots", "assets", "budget" })
            Equal(expected["vfxManifest"]![field]!.ToJsonString(), actual["vfxManifest"]![field]!.ToJsonString(),
                "persisted current VFX " + field + " stays byte-semantically unchanged");
        Equal(expected["runtimeProgram"]!.ToJsonString(), actual["runtimeProgram"]!.ToJsonString(),
            "loading inert presentation metadata cannot alter executable runtime");
        Equal(true, GeneratedItemData.FromJson(savedBytes) is null, "fresh/network grammar remains strict");
        Equal(savedBytes, saved.ToJsonString(), "local normalization never edits original cache");
    }

    private static void PersistedV5UnknownExecutableFieldsStillRefuse()
    {
        var source = JsonNode.Parse(GeneratedItemData.Placeholder().ToLocalCacheJson())!.AsObject();
        Action<JsonObject>[] corruptions = {
            w => w["futureGameplay"] = new JsonObject(),
            w => w["runtimeProgram"]!["futureMechanic"] = 1,
            w => { w["runtimeProgram"]!["entities"]![0]!["movement"]!["name"] = "unsupported_move";
                   w["runtimeProgram"]!["entities"]![0]!["movement"]!["code"] = 987654; },
            w => w["gameplay"]!["futureDamage"] = 1,
            w => w["visual"]!["futureColor"] = "red",
            w => w["vfxManifest"]!["futureRenderer"] = 1,
            w => w["vfxManifest"]!["budget"]!["futureBudget"] = 1,
            w => w["schemaVersion"] = 4,
            w => w["runtimeApiVersion"] = "infini.runtime-program.v4",
            w => w["vfxManifest"]!["schema"] = "infini.vfx.runtime-events.v999"
        };
        foreach (var mutate in corruptions) {
            var bad = JsonNode.Parse(source.ToJsonString())!.AsObject();
            mutate(bad);
            Equal(true, ReadPersistedDefinition(bad.ToJsonString()) is null,
                "unknown actual executable/contract fields fail closed");
            Equal(true, ContractJsonDiagnostics.TryGet("GeneratedItemData.FromLocalCacheJson", out var error)
                && !string.IsNullOrWhiteSpace(error?.Message), "refusal has persisted-boundary diagnostic");
        }
        var unknownSlot = MaterialElementWire();
        unknownSlot["vfxManifest"]!["slots"]![0]!["futureBehavior"] = 1;
        Equal(true, ReadPersistedDefinition(unknownSlot.ToJsonString()) is null,
            "current executable renderer fields remain strict");
        var historicalColor = MaterialElementWire();
        historicalColor["vfxManifest"]!["slots"]![0]!["element"]!["colorProfile"]!["start"] = "effect";
        Equal(true, ReadPersistedDefinition(historicalColor.ToJsonString()) is null,
            "named semantic color tokens never enter current color profiles");
        var unsupportedRuntime = PersistedV15Fixture(SentryTargetingFixture());
        unsupportedRuntime["runtimeProgram"]!["entities"]!.AsArray().Single(e => (string?)e!["id"] == "root")!["movement"]!["code"] = 987654;
        Equal(true, ReadPersistedDefinition(unsupportedRuntime.ToJsonString()) is null,
            "actual old projectile unknown opcode stays refused");
        string ambiguous = PersistedV15Fixture().ToJsonString();
        ambiguous = ambiguous.Insert(1, "\"Canonical\":{},");
        Equal(true, ReadPersistedDefinition(ambiguous) is null,
            "case-insensitive duplicate metadata owner cannot bypass projection");
    }

    private static void PersistedV5CurrentFormatIsExactPassThrough()
    {
        foreach (var source in new[] { GeneratedItemData.Placeholder(), NamedItemEffectsFixture(), SentryTargetingFixture() }) {
            source.Debug["A"] = JsonSerializer.SerializeToElement(1); source.Debug["a"] = JsonSerializer.SerializeToElement(2);
            source.Concept = JsonSerializer.SerializeToElement(new JsonObject { ["A"] = 1, ["a"] = 2 });
            string json = source.ToLocalCacheJson();
            var loaded = ReadPersistedDefinition(json) ?? throw new InvalidOperationException("current saved JSON rejected");
            Equal(json, loaded.ToLocalCacheJson(), "current writer/reader exact serialized parity");
            var receipt = typeof(GeneratedItemData).GetProperty("LocalCacheReadReceipt")?.GetValue(loaded) as string[];
            Equal(true, receipt is { Length: 0 }, "current input receives no historical projection");
        }
    }

    private static void PersistedV5RegistryLoadsReadOnlyAndKeepsWorldFence()
    {
        int oldWorld = Terraria.Main.worldID;
        try {
            Terraria.Main.worldID = 43101; using var registry = new GeneratedItemRegistryService();
            var source = AssetOwnerData("persisted_v15_synthetic", "never_created.png"); source.Gameplay.Damage = 31;
            var old = PersistedV15Fixture(source); string json = old.ToJsonString();
            Directory.CreateDirectory(registry.StoreRoot); string file = Path.Combine(registry.StoreRoot, source.Id + ".json");
            File.WriteAllText(file, json); byte[] before = File.ReadAllBytes(file);
            try {
                registry.ReloadLocalCacheForCurrentWorld();
                Equal(true, registry.TryGet(source.Id, out var loaded), "actual registry saved-reader path hydrates old definition");
                Equal(31, loaded.Gameplay.Damage, "registry retains executable values");
                Equal(true, before.SequenceEqual(File.ReadAllBytes(file)), "read projection never rewrites source file");
                Terraria.Main.worldID = 43102; registry.ReloadLocalCacheForCurrentWorld();
                Equal(false, registry.TryGet(source.Id, out _), "projection does not weaken world ownership");
                Equal(true, before.SequenceEqual(File.ReadAllBytes(file)), "foreign read leaves file byte exact");
            } finally { File.Delete(file); }
        } finally { Terraria.Main.worldID = oldWorld; }
    }
}
