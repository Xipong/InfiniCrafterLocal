#nullable enable
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.Json.Serialization;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;

namespace InfiniCrafterLocal.Common.Models;

public sealed partial class GeneratedItemData
{
    // Persisted v5 is a durable read boundary, not the fresh Author/network grammar.
    // Keep historical positives when changing DTO metadata in a minor release.
    // Only enumerated inert fields can be omitted; executing fields must either
    // lower losslessly from their declared saved owner or fail with an exact path.
    // This projection never writes a cache/save, infers mechanics or dispatches a
    // historical engine. The result still passes the CURRENT strict DTO/Normalize.
    private const string PersistedVfx15 = "infini.vfx.runtime-events.v15";
    private const string PersistedBoundary = "GeneratedItemData.FromLocalCacheJson";
    private static readonly HashSet<string> PersistedOpaqueOwners = new(StringComparer.OrdinalIgnoreCase) {
        "$.debug", "$.concept", "$.realization", "$.llmStageAccounting", "$.contractVersions", "$.recipeHealth",
        "$.canonical", "$.sourceRepresentation", "$.inheritance", "$.lossBudget", "$.itemKnowledge"
    };

    [JsonIgnore]
    public string[] LocalCacheReadReceipt { get; private set; } = Array.Empty<string>();

    public static GeneratedItemData? FromLocalCacheJson(string? json)
    {
        ContractJsonDiagnostics.Clear(PersistedBoundary);
        if (string.IsNullOrWhiteSpace(json)) return null;
        try
        {
            // The wire reader is case-insensitive. Reject ambiguous duplicates
            // before editing, including differently cased aliases of removed keys.
            using var document = JsonDocument.Parse(json);
            RejectPersistedDuplicates(document.RootElement, "$");
            var root = JsonNode.Parse(json, new JsonNodeOptions { PropertyNameCaseInsensitive = true }) as JsonObject
                ?? throw PersistedFailure("$", "persisted definition must be an object");
            if (root["schemaVersion"]?.GetValue<int>() != CurrentSchemaVersion)
                throw PersistedFailure("$.schemaVersion", "only persisted generated item v5 is supported");
            if (PersistedString(root, "runtimeApiVersion", "$") != RuntimeProgramSpec.CurrentApiVersion)
                throw PersistedFailure("$.runtimeApiVersion", "unsupported persisted runtime API");
            var receipt = new List<string>();
            DropPersisted(root, "$", receipt, "canonical", "sourceRepresentation", "inheritance", "lossBudget", "itemKnowledge");
            DropPersistedOwner(root, "generatedParentSummary", receipt, "notableEffects", "runtimePrimaryEntityId", "runtimeEntityIds");
            DropPersistedOwner(root, "gameplay", receipt, "stage", "powerBudget");
            DropPersistedOwner(root, "accessory", receipt, "archetype");
            DropPersistedOwner(root, "armor", receipt, "archetype");
            DropPersistedOwner(root, "visual", receipt, "objectType", "style", "requiredAnchors", "preservationScore", "semanticReviewStatus",
                "visualSoulSignature", "visualSoulArchetype", "dominantColorHex", "accentColorHex", "visualSoulGlow", "visualSoulPulse", "visualSoulCoverage", "visualSoulEdgeDensity");
            if (root["vfxManifest"] is JsonObject manifest && manifest["schema"]?.GetValue<string>() == PersistedVfx15)
                ProjectPersistedVfx15(root, manifest, receipt);
            GeneratedItemData? parsed = JsonSerializer.Deserialize<GeneratedItemData>(receipt.Count == 0 ? json : root.ToJsonString(), Options);
            if (parsed is null) return null;
            parsed.Normalize();
            parsed.LocalCacheReadReceipt = receipt.ToArray();
            return parsed;
        }
        catch (Exception exception)
        {
            ContractJsonDiagnostics.Record(PersistedBoundary, exception);
            return null;
        }
    }

    private static JsonException PersistedFailure(string path, string reason)
        => new($"Persisted definition {path}: {reason}", path, null, null);

    private static void RejectPersistedDuplicates(JsonElement node, string path)
    {
        // Diagnostic blobs and explicitly inert removed owners are opaque JSON,
        // not case-insensitive DTOs. Preserve their legitimate dictionary keys.
        if (PersistedOpaqueOwners.Contains(path)) return;
        if (node.ValueKind == JsonValueKind.Object) {
            var keys = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (JsonProperty property in node.EnumerateObject()) {
                if (!keys.Add(property.Name)) throw PersistedFailure(path + "." + property.Name, "duplicate JSON member");
                RejectPersistedDuplicates(property.Value, path + "." + property.Name);
            }
        } else if (node.ValueKind == JsonValueKind.Array) {
            int index = 0;
            foreach (JsonElement element in node.EnumerateArray()) RejectPersistedDuplicates(element, path + "[" + index++ + "]");
        }
    }

    private static void DropPersistedOwner(JsonObject root, string owner, List<string> receipt, params string[] fields)
    {
        if (root[owner] is JsonObject row) DropPersisted(row, "$." + owner, receipt, fields);
    }

    private static void DropPersisted(JsonObject row, string path, List<string> receipt, params string[] fields)
    {
        foreach (string field in fields)
            if (row.Remove(field)) receipt.Add("persisted:v5:inert " + path + "." + field);
    }

    private static string PersistedString(JsonObject row, string field, string path)
    {
        if (row[field] is JsonValue value && value.TryGetValue<string>(out string? text) && text is not null) return text;
        throw PersistedFailure(path + "." + field, "expected explicit string");
    }

    private static void CheckPersistedKeys(JsonObject row, string path, params string[] allowed)
    {
        var keys = new HashSet<string>(allowed, StringComparer.OrdinalIgnoreCase);
        foreach (var property in row)
            if (!keys.Contains(property.Key)) throw PersistedFailure(path + "." + property.Key, "unknown historical field; not inert metadata");
    }

    private static void ProjectPersistedVfx15(JsonObject root, JsonObject manifest, List<string> receipt)
    {
        // v15's motif and effectColor were real color owners. Validate their exact
        // keys, resolve at the consuming slot, and only THEN omit the old owner.
        var visual = root["visual"] as JsonObject;
        if (visual?.ContainsKey("effectColor") == true)
            _ = PersistedNamedColor(PersistedString(visual, "effectColor", "$.visual"), "$.visual.effectColor", fullWhite: false);
        if (manifest["motif"] is not JsonObject motif)
            throw PersistedFailure("$.vfxManifest.motif", "v15 requires its saved color owner");
        CheckPersistedKeys(motif, "$.vfxManifest.motif", "element", "shapeLanguage", "motionLanguage", "paletteRole", "rhythm", "chaos");
        if (manifest["slots"] is not JsonArray slots)
            throw PersistedFailure("$.vfxManifest.slots", "v15 slots must be an explicit array");
        string itemEntity = root["runtimeProgram"] is JsonObject program ? PersistedString(program, "itemEntityId", "$.runtimeProgram") : "";
        for (int index = 0; index < slots.Count; index++) {
            string path = "$.vfxManifest.slots[" + index + "]";
            var slot = slots[index] as JsonObject ?? throw PersistedFailure(path, "expected slot object");
            string renderer = PersistedString(slot, "rendererKind", path);
            // These exact aliases shared v15's sprite trail/snapshot executors.
            // Decode into the existing primitive; do not add historical dispatch.
            if (renderer is "projectileAfterimage" or "actorAfterimage") {
                receipt.Add("persisted:v15:renderer-alias " + path + ".rendererKind " + renderer + " -> spriteStampTrail");
                renderer = "spriteStampTrail"; slot["rendererKind"] = renderer;
            }
            var kind = VfxRendererRegistry.ParseKind(renderer);
            if (kind == InfiniVfxRendererKind.None)
                throw PersistedFailure(path + ".rendererKind", "unsupported v15 renderer '" + renderer + "'; no lossless current primitive");
            bool item = PersistedString(slot, "entityId", path) == itemEntity;
            bool nested = renderer is "spriteElement" or "texturedPath" or "libraryParticle" or "screenShakeCue";
            bool sound = renderer == "soundCue", light = renderer == "lightCue", impact = renderer == "impactSprite", dust = renderer == "childMotes";
            bool cadenceOnly = sound || light || impact;
            bool sprite = VfxRendererRegistry.ConsumesSpriteTexture(kind);
            if (slot.ContainsKey("color")) throw PersistedFailure(path + ".color", "v15 has no local common RGB owner");
            if (!nested && !sound) {
                // Historical live projectile Draw could take the caller's lighting
                // color when both explicit and finite motif colors were absent.
                // A constant RGB cannot preserve that dependency: refuse, never guess.
                bool historicalLiveDraw = !item && (PersistedString(slot, "event", path).Trim().ToLowerInvariant() == RuntimeEventKind.Periodic
                    || PersistedString(slot, "event", path).Trim().ToLowerInvariant() == RuntimeEventKind.OnSpawn && renderer is "historyRibbon" or "tipTrail");
                Color color = PersistedEffectColor(root, manifest, item && !impact && renderer != "spriteStampTrail", path, receipt,
                    requireConstant: historicalLiveDraw && renderer is not ("impactSprite" or "lightCue" or "childMotes"));
                if (item && renderer == "spriteStampTrail" && PersistedString(slot, "particleSystemId", path) != "none"
                    && color != PersistedEffectColor(root, manifest, item: true, path, receipt))
                    throw PersistedFailure(path + ".color", "v15 item sprite tint and accompanying dust use different saved color sources; cannot lower to one local RGB");
                slot["color"] = PersistedRgb(color);
                receipt.Add("persisted:v15:local-rgb " + path + ".color");
            }
            if (renderer == "libraryParticle") {
                if (slot["particle"] is not JsonObject particle) throw PersistedFailure(path + ".particle", "missing saved library payload");
                ProjectPersistedColorToken(root, manifest, particle, "colorStart", item, path + ".particle", receipt);
                ProjectPersistedColorToken(root, manifest, particle, "colorEnd", item, path + ".particle", receipt);
            }
            if (renderer is "spriteElement" or "texturedPath") {
                string owner = renderer == "spriteElement" ? "element" : "path";
                if (slot[owner] is not JsonObject payload || payload["colorProfile"] is not JsonObject profile)
                    throw PersistedFailure(path + "." + owner + ".colorProfile", "missing saved color profile");
                foreach (string field in new[] { "start", "middle", "end" })
                    ProjectPersistedColorToken(root, manifest, profile, field, item, path + "." + owner + ".colorProfile", receipt);
            }
            // v15 projectile/field selected the bound entity's exact PNG, never
            // a category-wide texture. Current strict admission still validates
            // that producer's readiness and presentation metadata after lowering.
            if (sprite && slot["textureRole"] is JsonValue texture && texture.TryGetValue<string>(out string? role)
                && role is "projectile" or "field") {
                string entityId = PersistedString(slot, "entityId", path);
                var entity = (root["runtimeProgram"]?["entities"] as JsonArray)?.OfType<JsonObject>()
                    .SingleOrDefault(e => e["id"] is JsonValue id && id.TryGetValue<string>(out string? savedId) && savedId == entityId);
                if (entity is null || PersistedString(entity, "visualRole", "$.runtimeProgram.entities") != role)
                    throw PersistedFailure(path + ".textureRole", "v15 texture selector must match the exact bound entity visualRole");
                if (entity["visual"] is not JsonObject entityVisual
                    || PersistedString(entityVisual, "assetMode", "$.runtimeProgram.entities.visual") is not ("baked_sprite" or "reuse_item_icon"))
                    throw PersistedFailure(path + ".textureRole", "v15 texture selector requires its bound entity baked_sprite/reuse_item_icon PNG producer");
                slot["textureRole"] = "entity";
                receipt.Add("persisted:v15:texture-role-alias " + path + ".textureRole " + role + " -> entity");
            }
            // These fields had no executor in v15. The remaining typed payloads,
            // entity/event bindings, opacity, budgets and geometry are not rebuilt.
            DropPersisted(slot, path, receipt, "effectName", "eventGroup", "stage", "backend", "particleRole", "channel", "lane", "source", "emissionMode",
                "fadeIn", "fadeOut", "jitter", "budgetWeight", "visualCost", "signatureWeight", "bakedClipId", "bakedClipHash", "bakedCommandCount", "bakedCommands");
            if (!sprite) DropPersisted(slot, path, receipt, "textureRole");
            if (nested || sound) DropPersisted(slot, path, receipt, "scale", "spread", "particleSystemId", "textureRole");
            else if (light || impact) DropPersisted(slot, path, receipt, "spread", "particleSystemId");
            else {
                string selector = PersistedString(slot, "particleSystemId", path);
                string current = selector switch {
                    "none" => "none", "dust" => "GemDiamond", "pl:glow" => "TintableDustLighted",
                    "pl:shard" => "Glass", "pl:smoke" => "Smoke", "pl:spark" => "Electric",
                    _ => throw PersistedFailure(path + ".particleSystemId", "unknown historical dust selector '" + selector + "'")
                };
                if (current != selector) { slot["particleSystemId"] = current; receipt.Add("persisted:v15:dust-identity " + path + ".particleSystemId " + selector + " -> " + current); }
            }
            if (nested) DropPersisted(slot, path, receipt, "density");
            if (sound || light || dust || renderer == "screenShakeCue") DropPersisted(slot, path, receipt, "alpha", "blend", "layer");
            if ((cadenceOnly && !impact) || dust || renderer is "screenShakeCue" or "texturedPath") DropPersisted(slot, path, receipt, "duration");
            if (renderer is "screenShakeCue" or "texturedPath") DropPersisted(slot, path, receipt, "repeatEvery");
            if (cadenceOnly) {
                string eventName = PersistedString(slot, "event", path).Trim().ToLowerInvariant();
                if (eventName != RuntimeEventKind.Periodic) DropPersisted(slot, path, receipt, "startTick", "repeatEvery", "density");
                else {
                    // Item cues use world clock, not projectile age. Projectile
                    // automatic cadence still consumes density when repeatEvery=0.
                    if (item) DropPersisted(slot, path, receipt, "startTick");
                    if (item || slot["repeatEvery"] is JsonValue repeat && repeat.TryGetValue<int>(out int ticks) && ticks > 0)
                        DropPersisted(slot, path, receipt, "density");
                }
            }
        }
        if (manifest["budget"] is JsonObject budget)
            DropPersisted(budget, "$.vfxManifest.budget", receipt, "effectMagnitude", "visualBudgetClass", "emergencyCap", "spawnRateMultiplier", "enableSoftGlow", "enablePointSparks", "enablePersistentSmoke");
        DropPersisted(manifest, "$.vfxManifest", receipt, "effectName", "inspirationNames", "playbackMode", "seed", "confidence", "effectMagnitude", "visualBudgetClass", "motif", "overlayPolicy", "debug", "hasSlots");
        if (visual?.Remove("effectColor") == true) receipt.Add("persisted:v15:color-owner $.visual.effectColor -> consumed local RGB (or no colored slots)");
        manifest["schema"] = VfxManifestSpec.CurrentSchema;
        receipt.Add("persisted:v15:lossless-current-presentation $.vfxManifest.schema");
    }

    private static void ProjectPersistedColorToken(JsonObject root, JsonObject manifest, JsonObject owner, string field, bool item, string path, List<string> receipt)
    {
        string token = PersistedString(owner, field, path);
        Color color = token == "effect" ? PersistedEffectColor(root, manifest, item, path + "." + field, receipt)
            : PersistedNamedColor(token, path + "." + field, fullWhite: true);
        owner[field] = PersistedRgb(color);
        receipt.Add("persisted:v15:color-token " + path + "." + field + " " + token + " -> RGB");
    }

    private static Color PersistedEffectColor(JsonObject root, JsonObject manifest, bool item, string path, List<string> receipt, bool requireConstant = false)
    {
        if (root["visual"] is JsonObject visual && visual.ContainsKey("effectColor")) {
            receipt.Add("persisted:v15:color-source " + path + " <- $.visual.effectColor");
            return PersistedNamedColor(PersistedString(visual, "effectColor", "$.visual"), "$.visual.effectColor", fullWhite: false);
        }
        if (item) {
            // This is the literal v15 item renderer token owner, not parsing art
            // prose or choosing a palette for a new definition.
            string? token = (root["visual"]?["palette"] as JsonArray)?.FirstOrDefault()?.GetValue<string>();
            receipt.Add("persisted:v15:color-source " + path + " <- saved item palette token (historical white if absent/unrecognized)");
            return TryPersistedNamedColor((token ?? "white").Trim().ToLowerInvariant(), out Color color) ? color : Color.White;
        }
        string element = PersistedString((JsonObject)manifest["motif"]!, "element", "$.vfxManifest.motif").Trim().ToLowerInvariant();
        // Frozen v15 semantic selector, used ONLY to decode a persisted color.
        // It is not a current Author vocabulary or a gameplay/element router.
        Color? selected = element switch {
            "fire" or "heat" => Color.OrangeRed, "ice" or "water" => Color.Cyan,
            "poison" or "nature" => Color.LimeGreen, "shadow" or "void" => Color.MediumPurple,
            "electric" or "lightning" => Color.Yellow, "blood" => Color.Crimson, _ => null
        };
        if (selected is null && requireConstant)
            throw PersistedFailure(path + ".color", "v15 live draw depends on caller lighting without an explicit effectColor/finite motif color; cannot lower to constant RGB");
        receipt.Add("persisted:v15:color-source " + path + " <- $.vfxManifest.motif.element (historical event white if unrecognized)");
        return selected ?? Color.White;
    }

    private static JsonObject PersistedRgb(Color color) => new() { ["r"] = (int)color.R, ["g"] = (int)color.G, ["b"] = (int)color.B };

    private static Color PersistedNamedColor(string token, string path, bool fullWhite)
    {
        if (!TryPersistedNamedColor(token, out Color color)) throw PersistedFailure(path, "unknown exact v15 rendering color token '" + token + "'");
        // v15 LibraryColor / VfxColorRamp used literal Color.White, whereas
        // visual.effectColor used RuntimeColorPolicy's slightly off-white RGB.
        return fullWhite && token == "white" ? Color.White : color;
    }

    private static bool TryPersistedNamedColor(string token, out Color color)
    {
        Color? value = token switch {
            "white" => new Color(235,235,235), "gray" => new Color(170,170,180), "silver" => new Color(192,192,192),
            "brown" => new Color(150,100,65), "tan" => new Color(225,190,120), "red" => new Color(255,85,85),
            "orange" => new Color(255,155,70), "yellow" => new Color(255,235,90), "gold" => new Color(255,205,70),
            "green" => new Color(110,255,145), "cyan" => new Color(90,235,255), "blue" => new Color(120,190,255),
            "purple" => new Color(190,110,255), "pink" => new Color(255,145,215), "black" => new Color(25,25,30), _ => null
        };
        color = value ?? default;
        return value.HasValue;
    }
}
