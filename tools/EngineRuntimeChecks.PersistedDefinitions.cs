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
        var snapshot = JsonNode.Parse(File.ReadAllText(Path.Combine("LocalGenerator", "tests", "fixtures", "persisted_v5_baseline.json")))!;
        foreach (var entry in snapshot["cases"]!.AsArray()) {
            var definition = entry!["definition"]!;
            var restored = ReadPersistedDefinition(definition.ToJsonString())
                ?? throw new InvalidOperationException("frozen v5 baseline no longer readable: " + entry["case"]);
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

    private static void PersistedV15NonemptyEffectsKeepColorsAndPayloads()
    {
        var source = NamedItemEffectsFixture(); source.SourceMode = "test_fixture"; source.RuntimeProgram.Entities[0].Visual.ImpactCanvasSize = 32;
        var old = PersistedV15Fixture(source); string entity = source.RuntimeProgram.ItemEntityId;
        old["vfxManifest"]!["slots"] = new JsonArray(PersistedV15Slot("soundCue", entity, "on_use"), PersistedV15Slot("impactRing", entity, "on_use"), PersistedV15Slot("impactSprite", entity, "on_use"), PersistedV15Slot("libraryParticle", entity, "on_use"));
        var loaded = ReadPersistedDefinition(old.ToJsonString()) ?? throw new InvalidOperationException("saved nonempty v15 presentation refused");
        Equal(4, loaded.VfxManifest.Slots.Length, "no effect is silently dropped");
        var rows = JsonNode.Parse(loaded.ToLocalCacheJson())!["vfxManifest"]!["slots"]!.AsArray();
        for (int i = 0; i < rows.Count; i++) {
            var before = old["vfxManifest"]!["slots"]![i]!; var after = rows[i]!;
            foreach (string field in new[] { "id", "entityId", "event", "anchor", "slotSeed", "phaseOffset" }) Equal(before[field]!.ToJsonString(), after[field]!.ToJsonString(), "exact effect identity " + field);
        }
        Equal(old["vfxManifest"]!["slots"]![0]!["sound"]!.ToJsonString(), rows[0]!["sound"]!.ToJsonString(), "exact sound playback choices");
        Equal("Item1", (string)rows[0]!["soundId"]!, "exact sound selector");
        foreach (int i in new[] { 1, 2 }) Equal(RgbWire(255,155,70).ToJsonString(), rows[i]!["color"]!.ToJsonString(), "visual.effectColor wins over motif ice");
        Equal(RgbWire(255,205,70).ToJsonString(), rows[3]!["particle"]!["colorStart"]!.ToJsonString(), "independent named gold ramp start");
        Equal(RgbWire(255,155,70).ToJsonString(), rows[3]!["particle"]!["colorEnd"]!.ToJsonString(), "effect ramp end uses saved effectColor");
        foreach (string field in old["vfxManifest"]!["slots"]![3]!["particle"]!.AsObject().Select(p => p.Key).Where(k => k is not ("colorStart" or "colorEnd")))
            Equal(old["vfxManifest"]!["slots"]![3]!["particle"]![field]!.ToJsonString(), rows[3]!["particle"]![field]!.ToJsonString(), "literal particle payload " + field);
        Equal(10, (int)rows[3]!["startTick"]!, "delayed library timing preserved");
        Equal(true, GeneratedItemData.FromJson(loaded.ToNetworkJson()) is not null, "projected definition uses existing strict network DTO");
    }

    private static void PersistedV15NamedColorSemanticsAreFrozen()
    {
        var historical = new (string Token, int R, int G, int B)[] {
            ("white",235,235,235),("gray",170,170,180),("silver",192,192,192),("brown",150,100,65),
            ("tan",225,190,120),("red",255,85,85),("orange",255,155,70),("yellow",255,235,90),
            ("gold",255,205,70),("green",110,255,145),("cyan",90,235,255),("blue",120,190,255),
            ("purple",190,110,255),("pink",255,145,215),("black",25,25,30)
        };
        foreach (var color in historical) {
            var old = PersistedV15Fixture(); old["visual"]!["effectColor"] = color.Token;
            old["vfxManifest"]!["slots"] = new JsonArray(PersistedV15Slot("libraryParticle", "unavailable_item", "on_use"));
            var particle = old["vfxManifest"]!["slots"]![0]!["particle"]!;
            particle["colorStart"] = "white"; particle["colorEnd"] = "effect";
            var loaded = ReadPersistedDefinition(old.ToJsonString()) ?? throw new InvalidOperationException("saved color refused: " + color.Token);
            var row = JsonNode.Parse(loaded.ToLocalCacheJson())!["vfxManifest"]!["slots"]![0]!["particle"]!;
            Equal(RgbWire(255,255,255).ToJsonString(), row["colorStart"]!.ToJsonString(), "nested white historically means full white, not effect white");
            Equal(RgbWire(color.R,color.G,color.B).ToJsonString(), row["colorEnd"]!.ToJsonString(), "frozen named effect RGB " + color.Token);
        }
    }

    private static void PersistedV15ColorSourcesAndMaterialProfilesStayLocal()
    {
        var source = NamedItemEffectsFixture(); source.SourceMode = "test_fixture";
        source.RuntimeProgram.Entities[0].Visual.ImpactCanvasSize = 32;
        var old = PersistedV15Fixture(source); old["visual"]!.AsObject().Remove("effectColor");
        old["visual"]!["palette"] = new JsonArray("red");
        old["vfxManifest"]!["slots"] = new JsonArray(PersistedV15Slot("impactRing", "unavailable_item", "on_use"), PersistedV15Slot("impactSprite", "unavailable_item", "on_use"));
        var loaded = ReadPersistedDefinition(old.ToJsonString()) ?? throw new InvalidOperationException("saved item/motif color sources refused");
        var slots = JsonNode.Parse(loaded.ToLocalCacheJson())!["vfxManifest"]!["slots"]!;
        Equal(RgbWire(255,85,85).ToJsonString(), slots[0]!["color"]!.ToJsonString(), "historical item primitive takes saved palette token, not motif");
        Equal(RgbWire(0,255,255).ToJsonString(), slots[1]!["color"]!.ToJsonString(), "historical dedicated impact takes saved motif ice, not item palette");

        var materialSource = ParseMaterialElement(MaterialElementWire());
        var material = PersistedV15Fixture(materialSource);
        var row = PersistedV15Slot("spriteElement", "unavailable_item", "periodic");
        row["element"] = material["vfxManifest"]!["slots"]![0]!["element"]!.DeepClone();
        row["startTick"] = 0; row["repeatEvery"] = 1; row["scale"] = 1; row["density"] = 0; row["visualCost"] = 0;
        var profile = row["element"]!["colorProfile"]!; profile["start"] = "white"; profile["middle"] = "effect"; profile["end"] = "gold";
        material["vfxManifest"]!["slots"] = new JsonArray(row);
        var materialLoaded = ReadPersistedDefinition(material.ToJsonString()) ?? throw new InvalidOperationException("saved independent material color profile refused");
        var current = JsonNode.Parse(materialLoaded.ToLocalCacheJson())!["vfxManifest"]!;
        Equal(material["vfxManifest"]!["assets"]!.ToJsonString(), current["assets"]!.ToJsonString(), "authored material asset identity/prompt retained");
        var result = current["slots"]![0]!["element"]!["colorProfile"]!;
        Equal(RgbWire(255,255,255).ToJsonString(), result["start"]!.ToJsonString(), "material white stays full white");
        Equal(RgbWire(255,155,70).ToJsonString(), result["middle"]!.ToJsonString(), "material effect uses saved explicit effectColor");
        Equal(RgbWire(255,205,70).ToJsonString(), result["end"]!.ToJsonString(), "material independent gold end retained");
        foreach (string field in row["element"]!.AsObject().Select(p => p.Key).Where(k => k != "colorProfile"))
            Equal(row["element"]![field]!.ToJsonString(), current["slots"]![0]!["element"]![field]!.ToJsonString(), "material payload retained: " + field);

        foreach (var selector in new[] { ("dust","GemDiamond"), ("pl:glow","TintableDustLighted"), ("pl:shard","Glass"), ("pl:smoke","Smoke"), ("pl:spark","Electric"), ("none","none") }) {
            var saved = PersistedV15Fixture(); var ring = PersistedV15Slot("impactRing", "unavailable_item", "on_use");
            ring["particleSystemId"] = selector.Item1; saved["vfxManifest"]!["slots"] = new JsonArray(ring);
            var accepted = ReadPersistedDefinition(saved.ToJsonString()) ?? throw new InvalidOperationException("historical dust identity refused: " + selector.Item1);
            Equal(selector.Item2, accepted.VfxManifest.Slots[0].ParticleSystemId!, "exact historical native DustID lowering");
        }
        foreach (string alias in new[] { "projectileAfterimage", "actorAfterimage" }) {
            var spriteSource = SentryTargetingFixture(); spriteSource.SourceMode = "test_fixture";
            spriteSource.Visual.RenderSizePx = 32; spriteSource.Visual.ForwardAngleDegrees = 0;
            spriteSource.RuntimeProgram.TryGetEntity("root")!.Visual.AssetMode = "reuse_item_icon";
            spriteSource.RuntimeProgram.TryGetEntity("root")!.Damage.Enabled = true;
            spriteSource.RuntimeProgram.TryGetEntity("root")!.Damage.Damage = 8;
            var saved = PersistedV15Fixture(spriteSource); var sprite = PersistedV15Slot(alias, "root", "on_hit");
            sprite["textureRole"] = "entity"; saved["vfxManifest"]!["slots"] = new JsonArray(sprite);
            var accepted = ReadPersistedDefinition(saved.ToJsonString()) ?? throw new InvalidOperationException("lossless historical sprite alias refused: " + alias);
            Equal("spriteStampTrail", accepted.VfxManifest.Slots[0].RendererKind, "identical historical renderer branch lowers to existing primitive");
            Equal("entity", accepted.VfxManifest.Slots[0].TextureRole!, "sprite alias keeps exact asset owner");
            Equal(true, GeneratedItemData.FromJson(saved.ToJsonString()) is null, "historical alias stays out of fresh/network grammar");
        }
        foreach (string role in new[] { "projectile", "field" })
        foreach (string renderer in new[] { "spriteStampTrail", "projectileAfterimage" })
        foreach (string assetMode in new[] { "reuse_item_icon", "baked_sprite" }) {
            var spriteSource = RootSpawnFixture(0, 1); spriteSource.SourceMode = "offline_contract_fixture";
            spriteSource.Visual.SpritePath = "saved_item.png"; spriteSource.Visual.SpriteStatus = "generated";
            spriteSource.Visual.RenderSizePx = 32; spriteSource.Visual.ForwardAngleDegrees = 0;
            var entity = spriteSource.RuntimeProgram.TryGetEntity("root")!;
            entity.Kind = role == "field" ? RuntimeEntityKind.Field : RuntimeEntityKind.FreeProjectile;
            entity.VisualRole = entity.Visual.Role = role; entity.Visual.AssetMode = assetMode;
            entity.Damage.Enabled = true; entity.Damage.Damage = 8;
            entity.Movement = new RuntimeMovementSpec { Name = "move_straight", Code = 0 };
            if (assetMode == "baked_sprite") {
                entity.Visual.SpritePath = "saved_entity.png"; entity.Visual.SpriteStatus = "generated";
                entity.Visual.RenderSizePx = 48; entity.Visual.ForwardAngleDegrees = 90;
            }
            var saved = PersistedV15Fixture(spriteSource); var sprite = PersistedV15Slot(renderer, "root", "on_hit");
            sprite["textureRole"] = role; saved["vfxManifest"]!["slots"] = new JsonArray(sprite);
            string before = saved.ToJsonString();
            var accepted = ReadPersistedDefinition(before) ?? throw new InvalidOperationException("lossless historical texture role refused: " + role + "/" + renderer + "/" + assetMode);
            Equal("entity", accepted.VfxManifest.Slots[0].TextureRole!, "exact saved role lowers to canonical entity selector");
            var selected = SpritePresentation.Resolve(accepted, "root", accepted.VfxManifest.Slots[0].TextureRole!);
            Equal(assetMode == "reuse_item_icon" ? "saved_item.png" : "saved_entity.png", selected.Path, "alias keeps exact selected PNG producer");
            Equal(assetMode == "reuse_item_icon" ? 32 : 48, selected.RenderSizePx!.Value, "alias keeps selected producer size");
            Equal(assetMode == "reuse_item_icon" ? 0f : 90f, selected.ForwardAngleDegrees!.Value, "alias keeps selected producer axis");
            Equal(true, accepted.LocalCacheReadReceipt.Any(s => s == "persisted:v15:texture-role-alias $.vfxManifest.slots[0].textureRole " + role + " -> entity"), "texture role lowering has exact receipt");
            Equal(before, saved.ToJsonString(), "saved alias input remains unchanged");
            var currentAlias = JsonNode.Parse(accepted.ToLocalCacheJson())!;
            currentAlias["vfxManifest"]!["slots"]![0]!["textureRole"] = role;
            Equal(true, ReadPersistedDefinition(currentAlias.ToJsonString()) is null, "texture alias is v15-only, not current persisted grammar");
            Equal(true, GeneratedItemData.FromJson(currentAlias.ToJsonString()) is null, "texture alias stays out of fresh/network grammar");
            foreach (string wrongRole in new[] { role == "field" ? "projectile" : "field", "invented_role" }) {
                var bad = saved.DeepClone(); bad["vfxManifest"]!["slots"]![0]!["textureRole"] = wrongRole;
                Equal(true, ReadPersistedDefinition(bad.ToJsonString()) is null, "mismatched/unknown saved role cannot select another PNG");
                if (wrongRole != "invented_role")
                    Equal(true, ContractJsonDiagnostics.TryGet("GeneratedItemData.FromLocalCacheJson", out var roleError) && roleError?.Path == "$.vfxManifest.slots[0].textureRole", "role mismatch has exact boundary diagnostic");
            }
            var noProducer = saved.DeepClone();
            var bound = noProducer["runtimeProgram"]!["entities"]!.AsArray().Single(e => (string?)e!["id"] == "root")!;
            bound["visual"]!["assetMode"] = "no_asset";
            Equal(true, ReadPersistedDefinition(noProducer.ToJsonString()) is null, "matching role without exact PNG producer still refuses");
            Equal(true, ContractJsonDiagnostics.TryGet("GeneratedItemData.FromLocalCacheJson", out var producerError) && producerError?.Path == "$.vfxManifest.slots[0].textureRole", "missing producer has exact alias diagnostic");
            var noPng = saved.DeepClone();
            var pngOwner = assetMode == "reuse_item_icon" ? noPng["visual"]! : noPng["runtimeProgram"]!["entities"]!.AsArray().Single(e => (string?)e!["id"] == "root")!["visual"]!;
            pngOwner["spritePath"] = "";
            Equal(true, ReadPersistedDefinition(noPng.ToJsonString()) is null, "lowering never bypasses selected producer PNG readiness");
        }
        var dynamicDraw = PersistedV15Fixture(SentryTargetingFixture()); dynamicDraw["visual"]!.AsObject().Remove("effectColor");
        var dynamicRoot = dynamicDraw["runtimeProgram"]!["entities"]!.AsArray().Single(e => (string?)e!["id"] == "root")!;
        dynamicRoot["damage"]!["enabled"] = true; dynamicRoot["damage"]!["damage"] = 8;
        dynamicDraw["vfxManifest"]!["motif"]!["element"] = "unrecognized saved prose";
        dynamicDraw["vfxManifest"]!["slots"] = new JsonArray(PersistedV15Slot("impactRing", "root", "on_hit"));
        Equal(true, ReadPersistedDefinition(dynamicDraw.ToJsonString()) is not null, "historical nonperiodic projectile white is deterministic");
        dynamicDraw["vfxManifest"]!["slots"]![0]!["event"] = "periodic";
        Equal(true, ReadPersistedDefinition(dynamicDraw.ToJsonString()) is null, "caller-light-dependent live color cannot become invented constant");
        Equal(true, ContractJsonDiagnostics.TryGet("GeneratedItemData.FromLocalCacheJson", out var error) && error?.Path == "$.vfxManifest.slots[0].color", "unrepresentable live color refusal has exact path");
        dynamicDraw["visual"]!["effectColor"] = "cyan";
        Equal(true, ReadPersistedDefinition(dynamicDraw.ToJsonString()) is not null, "explicit saved color removes live ambiguity");
    }

    private static void PersistedV5UnknownExecutableFieldsStillRefuse()
    {
        Action<JsonObject>[] corruptions = {
            w => w["futureGameplay"] = new JsonObject(),
            w => w["runtimeProgram"]!["futureMechanic"] = 1,
            w => { w["runtimeProgram"]!["entities"]![0]!["movement"]!["name"] = "unsupported_move"; w["runtimeProgram"]!["entities"]![0]!["movement"]!["code"] = 987654; },
            w => w["gameplay"]!["futureDamage"] = 1,
            w => w["visual"]!["futureColor"] = "red",
            w => w["vfxManifest"]!["futureRenderer"] = 1,
            w => w["vfxManifest"]!["budget"]!["futureBudget"] = 1,
            w => w["vfxManifest"]!["motif"]!["futureMotion"] = 1,
            w => w["vfxManifest"]!["slots"]![0]!["futureBehavior"] = 1,
            w => w["vfxManifest"]!["slots"]![0]!["rendererKind"] = "unsupportedRealPrimitive",
            w => w["vfxManifest"]!["slots"]![0]!["sound"]!.AsObject().Remove("volume"),
            w => w["schemaVersion"] = 4,
            w => w["runtimeApiVersion"] = "infini.runtime-program.v4",
            w => w["vfxManifest"]!["schema"] = "infini.vfx.runtime-events.v999"
        };
        foreach (var mutate in corruptions) {
            var bad = PersistedV15Fixture(); bad["vfxManifest"]!["slots"] = new JsonArray(PersistedV15Slot("soundCue", "unavailable_item", "on_use")); mutate(bad);
            Equal(true, ReadPersistedDefinition(bad.ToJsonString()) is null, "persisted projection is not a general unknown-field skip");
            Equal(true, ContractJsonDiagnostics.TryGet("GeneratedItemData.FromLocalCacheJson", out var error) && !string.IsNullOrWhiteSpace(error?.Message), "failure keeps precise persisted-boundary diagnostic");
        }
        var unsupportedRuntime = PersistedV15Fixture(SentryTargetingFixture());
        unsupportedRuntime["runtimeProgram"]!["entities"]!.AsArray().Single(e => (string?)e!["id"] == "root")!["movement"]!["code"] = 987654;
        Equal(true, ReadPersistedDefinition(unsupportedRuntime.ToJsonString()) is null, "actual projectile unknown opcode remains fail-closed");
        var unsupported = PersistedV15Fixture(); unsupported["visual"]!["effectColor"] = "invented prose";
        Equal(true, ReadPersistedDefinition(unsupported.ToJsonString()) is null, "invalid saved authored color cannot choose replacement");
        string ambiguous = PersistedV15Fixture().ToJsonString();
        ambiguous = ambiguous.Insert(1, "\"Canonical\":{},");
        Equal(true, ReadPersistedDefinition(ambiguous) is null, "case-insensitive duplicate historical owner cannot bypass projection");
        var unknownParticle = PersistedV15Fixture();
        unknownParticle["vfxManifest"]!["slots"] = new JsonArray(PersistedV15Slot("libraryParticle", "unavailable_item", "on_use"));
        unknownParticle["vfxManifest"]!["slots"]![0]!["particle"]!["futureMotion"] = 1;
        Equal(true, ReadPersistedDefinition(unknownParticle.ToJsonString()) is null, "nested particle is not an opaque metadata blob");
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
