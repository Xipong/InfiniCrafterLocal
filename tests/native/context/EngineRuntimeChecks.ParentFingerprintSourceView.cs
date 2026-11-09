using System;
using System.IO;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
    private static bool IsReadableNativeView(JsonElement owner, JsonProperty property)
    {
        static bool Named(JsonElement value, string name, string text) => value.ValueKind == JsonValueKind.Object
            && value.TryGetProperty(name, out var field) && field.ValueKind == JsonValueKind.String && field.GetString() == text;
        static bool Version(JsonElement value, int? exact) => value.ValueKind == JsonValueKind.Object
            && value.TryGetProperty("version", out var version) && version.ValueKind == JsonValueKind.Number
            && version.TryGetInt32(out int number) && (exact.HasValue ? number == exact.Value : number > 0);
        if (!Named(owner, "source", "read_only_native_attack_source") || !Version(owner, 1) || !Version(property.Value, null)) return false;
        if (property.Name == "nativeCSharpSource" && Named(property.Value, "source", "verified_decompiled_native_csharp")) return true;
        if (property.Name == "interactionSources")
        {
            if (!Version(property.Value, 1) || !Named(property.Value, "source", "verified_conditional_native_interaction_csharp")
                || !property.Value.TryGetProperty("roots", out var roots) || roots.ValueKind != JsonValueKind.Array || roots.GetArrayLength() != 3
                || !owner.TryGetProperty("sourceMethods", out var interactionMethods) || interactionMethods.ValueKind != JsonValueKind.Array) return false;
            // Independent token-level observer. A readable body is removable
            // only when its original method certificate remains a native fact.
            bool Backed(JsonElement record)
            {
                if (record.ValueKind != JsonValueKind.Object
                    || !record.TryGetProperty("method", out var candidateName) || candidateName.ValueKind != JsonValueKind.String
                    || !record.TryGetProperty("sourceModuleVersionId", out var candidateModule) || candidateModule.ValueKind != JsonValueKind.String || !Guid.TryParse(candidateModule.GetString(), out _)
                    || !record.TryGetProperty("sourceMethodSha256", out var candidateHash) || candidateHash.ValueKind != JsonValueKind.String
                    || candidateHash.GetString() is not { Length: 64 } candidateSha || System.Linq.Enumerable.Any(candidateSha, character => !Uri.IsHexDigit(character))) return false;
                foreach (var candidateMethod in interactionMethods.EnumerateArray())
                    if (candidateMethod.ValueKind == JsonValueKind.Object && System.Linq.Enumerable.Count(candidateMethod.EnumerateObject()) == 3
                        && Named(candidateMethod, "method", candidateName.GetString()!) && Named(candidateMethod, "sourceModuleVersionId", candidateModule.GetString()!)
                        && Named(candidateMethod, "sourceMethodSha256", candidateSha)) return true;
                return false;
            }
            var names = new System.Collections.Generic.HashSet<string>(StringComparer.Ordinal);
            foreach (var root in roots.EnumerateArray())
            {
                if (root.ValueKind != JsonValueKind.Object || !root.TryGetProperty("root", out var rootName)
                    || rootName.ValueKind != JsonValueKind.String || rootName.GetString() is not ("Damage" or "StatusNPC" or "HandleMovement")
                    || !names.Add(rootName.GetString()!) || !root.TryGetProperty("rootCertificate", out var rootCertificate)
                    || rootCertificate.ValueKind != JsonValueKind.Object || System.Linq.Enumerable.Count(rootCertificate.EnumerateObject()) != 3
                    || !Named(rootCertificate, "method", "Terraria.Projectile." + rootName.GetString()) || !Backed(rootCertificate)
                    || !root.TryGetProperty("records", out var records) || records.ValueKind != JsonValueKind.Array
                    || !root.TryGetProperty("helpers", out var helpers) || helpers.ValueKind != JsonValueKind.Array) return false;
                foreach (var record in records.EnumerateArray())
                    if (!Named(record, "method", "Terraria.Projectile." + rootName.GetString()) || !Backed(record)) return false;
                foreach (var helper in helpers.EnumerateArray())
                    if (!Backed(helper)) return false;
            }
            return true;
        }
        if (property.Name != "lifecycle" || !Version(property.Value, 1) || !Named(property.Value, "source", "verified_conditional_native_lifecycle_csharp")
            || !property.Value.TryGetProperty("rootCertificate", out var certificate)
            || !owner.TryGetProperty("sourceMethods", out var methods) || methods.ValueKind != JsonValueKind.Array) return false;
        if (certificate.ValueKind != JsonValueKind.Object || System.Linq.Enumerable.Count(certificate.EnumerateObject()) != 3 || !Named(certificate, "method", "Terraria.Projectile.Kill")
            || !certificate.TryGetProperty("sourceModuleVersionId", out var module) || module.ValueKind != JsonValueKind.String || !Guid.TryParse(module.GetString(), out _)
            || !certificate.TryGetProperty("sourceMethodSha256", out var hash) || hash.ValueKind != JsonValueKind.String
            || hash.GetString() is not { Length: 64 } text || System.Linq.Enumerable.Any(text, character => !Uri.IsHexDigit(character))) return false;
        foreach (var method in methods.EnumerateArray())
            if (CanonicalParentFactJson(method) == CanonicalParentFactJson(certificate)) return true;
        return false;
    }

    // Independent test observer: copy every JSON token through a streaming writer,
    // excluding only the declared display supplement. Do not call production's
    // fingerprint filter or reconstruct native mechanics as expected data.
    private static string NativeFactsWithoutReadableView(JsonElement value)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream)) Write(value, writer);
        using var document = JsonDocument.Parse(stream.ToArray());
        return CanonicalParentFactJson(document.RootElement);

        static void Write(JsonElement node, Utf8JsonWriter writer)
        {
            if (node.ValueKind == JsonValueKind.Object)
            {
                writer.WriteStartObject();
                foreach (var property in node.EnumerateObject())
                {
                    if (IsReadableNativeView(node, property)) continue;
                    writer.WritePropertyName(property.Name); Write(property.Value, writer);
                }
                writer.WriteEndObject();
            }
            else if (node.ValueKind == JsonValueKind.Array)
            {
                writer.WriteStartArray();
                foreach (var child in node.EnumerateArray()) Write(child, writer);
                writer.WriteEndArray();
            }
            else node.WriteTo(writer);
        }
    }

    private static int ReadableNativeViewCount(JsonElement value)
    {
        int count = 0;
        if (value.ValueKind == JsonValueKind.Object)
            foreach (var property in value.EnumerateObject())
                count += (IsReadableNativeView(value, property) ? 1 : 0) + ReadableNativeViewCount(property.Value);
        else if (value.ValueKind == JsonValueKind.Array)
            foreach (var child in value.EnumerateArray()) count += ReadableNativeViewCount(child);
        return count;
    }

    private static void AssertParentFingerprintNativeFacts(JsonElement root, JsonElement fingerprint, string label, bool requireRootView = false)
    {
        if (requireRootView) Equal(true, ReadableNativeViewCount(root) > 0, label + " source view remains in request observations");
        Equal(0, ReadableNativeViewCount(fingerprint), label + " fingerprint excludes recognized display metadata");
        Equal(NativeFactsWithoutReadableView(root), CanonicalParentFactJson(fingerprint), label + " preserves every non-view native fact");
    }

    private static void AssertParentFingerprintNativeFacts(JsonNode? root, JsonNode? fingerprint, string label, bool requireRootView = false)
        => AssertParentFingerprintNativeFacts(JsonSerializer.SerializeToElement(root), JsonSerializer.SerializeToElement(fingerprint), label, requireRootView);

    private static JsonObject FingerprintSourceViewFixture(bool deferred, JsonObject projectile, int damage = 12)
    {
        var facts = new JsonObject {
            ["type"] = 100, ["damage"] = damage, ["literalNull"] = null,
            ["nativeCSharpSource"] = new JsonObject { ["source"] = "different_owner", ["value"] = "keep" },
        };
        var ammo = new JsonObject { ["mode"] = "weapon_uses_ammo", ["nativeReplacementProjectileRaw"] = new JsonArray(projectile.DeepClone()) };
        using var analysis = deferred ? new GeneratorClient.ParentAnalysis() : null;
        JsonObject root;
        using (analysis?.Enter())
        {
            JsonNode Observe(JsonObject source) => analysis is null ? source.DeepClone() : analysis.Defer(() => source.DeepClone());
            JsonNode direct = Observe(projectile), effective = Observe(projectile), ammunition = Observe(ammo);
            const BindingFlags all = BindingFlags.Static | BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public;
            Type nativeFacts = typeof(GeneratorClient).GetNestedType("ParentNativeFacts", all)!;
            object observed = Activator.CreateInstance(nativeFacts, all, null, new object?[] { facts, direct }, null)!;
            var fingerprint = (JsonObject)typeof(GeneratorClient).GetMethod("FingerprintFromFacts", all)!.Invoke(null,
                new object?[] { "Terraria", "FingerprintFixture", Array.Empty<string>(), Array.Empty<string>(), observed,
                    0, true, "Fingerprint fixture", effective.DeepClone(), ammunition.DeepClone() })!;
            root = new JsonObject { ["runtimeFacts"] = facts.DeepClone(), ["directProjectileRaw"] = direct,
                ["effectiveProjectileRaw"] = effective, ["ammoRaw"] = ammunition, ["fingerprint"] = fingerprint };
        }
        return analysis is null ? root : Task.Run(() => analysis.Resolve(root)).GetAwaiter().GetResult()!.AsObject();
    }

    private static void ParentFingerprintExcludesReadableSourceViews()
    {
        ParentFingerprintInteractionSourceViewOracle();
        var attack = new JsonObject {
            ["source"] = "read_only_native_attack_source", ["version"] = 1,
            ["sourceMethods"] = new JsonArray(new JsonObject { ["sourceMethodSha256"] = "native-il-certificate" }),
            ["motion"] = new JsonObject { ["programs"] = new JsonArray(new JsonObject {
                ["observations"] = new JsonArray(new JsonObject { ["at"] = 20,
                    ["requiredPredicates"] = new JsonArray("b10"), ["expression"] = "native_source_write" }),
            }) },
            ["coverage"] = new JsonObject { ["unresolved"] = new JsonArray("callback effects remain unknown") },
        };
        var plain = new JsonObject { ["type"] = 632, ["collisionReference"] = null, ["attackReference"] = attack };
        JsonObject View(string family, int version, string text)
        {
            var raw = plain.DeepClone().AsObject();
            raw["attackReference"]!["nativeCSharpSource"] = new JsonObject {
                ["source"] = family, ["version"] = version,
                ["records"] = new JsonArray(new JsonObject { ["code"] = text,
                    ["decompiler"] = new JsonObject { ["version"] = "display-engine-" + version, ["settings"] = text } }),
            };
            raw["referencedProjectiles"] = new JsonObject { ["references"] = new JsonArray(new JsonObject {
                ["type"] = 601, ["profile"] = new JsonObject { ["type"] = 601, ["attackReference"] = raw["attackReference"]!.DeepClone() },
            }) };
            return raw;
        }
        var firstView = View("verified_decompiled_native_csharp", 1, "first view");
        var changedView = View("verified_decompiled_native_csharp", 2, "different text\nnew formatting and settings");
        // The independent baseline contains every native field and child profile
        // from the view fixture, with only its optional supplement absent.
        var noView = firstView.DeepClone().AsObject();
        noView["attackReference"]!.AsObject().Remove("nativeCSharpSource");
        noView["referencedProjectiles"]!["references"]![0]!["profile"]!["attackReference"]!.AsObject().Remove("nativeCSharpSource");
        Equal(true, JsonNode.DeepEquals(FingerprintSourceViewFixture(false, firstView), FingerprintSourceViewFixture(true, firstView)),
            "immediate and deferred fingerprint projections deliver identical resolved observations");
        foreach (bool deferred in new[] { false, true })
        {
            var baseline = FingerprintSourceViewFixture(deferred, noView);
            var first = FingerprintSourceViewFixture(deferred, firstView);
            var changed = FingerprintSourceViewFixture(deferred, changedView);
            var fingerprint = first["fingerprint"]!;
            AssertParentFingerprintNativeFacts(first["directProjectileRaw"], fingerprint["directProjectileRaw"],
                "independent direct-projectile parity observer", requireRootView: true);
            AssertParentFingerprintNativeFacts(first["effectiveProjectileRaw"], fingerprint["effectiveProjectileRaw"],
                "independent effective-projectile parity observer", requireRootView: true);
            AssertParentFingerprintNativeFacts(first["ammoRaw"], fingerprint["ammoRaw"],
                "independent replacement/child parity observer", requireRootView: true);
            Equal(true, JsonNode.DeepEquals(baseline["fingerprint"], fingerprint), "optional display adds no fingerprint input: " + deferred);
            Equal(true, JsonNode.DeepEquals(fingerprint, changed["fingerprint"]), "display text, settings and format version do not change identity: " + deferred);
            Equal(false, JsonNode.DeepEquals(first["directProjectileRaw"], changed["directProjectileRaw"]), "root retains distinct source displays: " + deferred);
            Equal("first view", first["directProjectileRaw"]!["attackReference"]!["nativeCSharpSource"]!["records"]![0]!["code"]!.GetValue<string>(), "fingerprint projection cannot mutate root source evidence: " + deferred);
            Equal(true, fingerprint["directProjectileRaw"]!.AsObject().ContainsKey("collisionReference") && fingerprint["directProjectileRaw"]!["collisionReference"] is null,
                "meaningful native null remains present: " + deferred);
            Equal(true, fingerprint["runtimeFacts"]!.AsObject().ContainsKey("literalNull") && fingerprint["runtimeFacts"]!["literalNull"] is null,
                "native fact null remains present: " + deferred);
            Equal("keep", fingerprint["runtimeFacts"]!["nativeCSharpSource"]!["value"]!.GetValue<string>(), "same field name under another owner stays literal: " + deferred);
            Equal(false, JsonNode.DeepEquals(fingerprint, FingerprintSourceViewFixture(deferred, firstView, damage: 13)["fingerprint"]), "native stat changes still change fingerprint: " + deferred);
            var changedNative = firstView.DeepClone().AsObject();
            changedNative["attackReference"]!["sourceMethods"]![0]!["sourceMethodSha256"] = "different-native-il";
            Equal(false, NativeFactsWithoutReadableView(JsonSerializer.SerializeToElement(firstView))
                == NativeFactsWithoutReadableView(JsonSerializer.SerializeToElement(changedNative)), "parity observer cannot hide native IL drift: " + deferred);
            Equal(false, JsonNode.DeepEquals(fingerprint, FingerprintSourceViewFixture(deferred, changedNative)["fingerprint"]), "native IL changes still change fingerprint: " + deferred);
            var future = FingerprintSourceViewFixture(deferred, View("unknown_future_source_family", 1, "opaque"));
            AssertParentFingerprintNativeFacts(future["directProjectileRaw"], future["fingerprint"]!["directProjectileRaw"],
                "independent parity observer retains unknown source families");
            Equal("unknown_future_source_family", future["fingerprint"]!["directProjectileRaw"]!["attackReference"]!["nativeCSharpSource"]!["source"]!.GetValue<string>(),
                "unknown source family stays literal: " + deferred);
        }
    }

    private static void ParentFingerprintInteractionSourceViewOracle()
    {
        JsonObject Certificate(string method) => new() { ["method"] = "Terraria.Projectile." + method,
            ["sourceModuleVersionId"] = "11111111-2222-3333-4444-555555555555", ["sourceMethodSha256"] = new string('a', 64) };
        JsonObject Fixture()
        {
            var methods = new JsonArray(); var roots = new JsonArray();
            foreach (string name in new[] { "Damage", "StatusNPC", "HandleMovement" })
            {
                var certificate = Certificate(name); methods.Add(certificate.DeepClone());
                roots.Add(new JsonObject { ["root"] = name, ["rootCertificate"] = certificate,
                    ["records"] = new JsonArray(), ["helpers"] = new JsonArray(), ["unresolved"] = new JsonArray("source_only") });
            }
            var region = Certificate("Damage"); region["code"] = "if (type == 91) { Effect(); }";
            roots[0]!["records"]!.AsArray().Add(region);
            var helper = Certificate("Effect"); methods.Add(helper.DeepClone()); helper["code"] = "void Effect() { }";
            roots[0]!["helpers"]!.AsArray().Add(helper);
            return new JsonObject { ["type"] = 91, ["attackReference"] = new JsonObject {
                ["source"] = "read_only_native_attack_source", ["version"] = 1, ["sourceMethods"] = methods,
                ["sourceCalls"] = new JsonArray(new JsonObject { ["at"] = 20, ["projectileTypes"] = new JsonArray(92), ["unresolved"] = "conditional" }),
                ["interactionSources"] = new JsonObject { ["source"] = "verified_conditional_native_interaction_csharp", ["version"] = 1, ["roots"] = roots } } };
        }
        JsonObject View(JsonObject projectile) => projectile["attackReference"]!["interactionSources"]!.AsObject();
        foreach (bool deferred in new[] { false, true })
        {
            var original = Fixture(); var noView = original.DeepClone().AsObject();
            noView["attackReference"]!.AsObject().Remove("interactionSources");
            var observed = FingerprintSourceViewFixture(deferred, original);
            AssertParentFingerprintNativeFacts(observed["directProjectileRaw"], observed["fingerprint"]!["directProjectileRaw"],
                "independent interaction source observer", requireRootView: true);
            AssertParentFingerprintNativeFacts(observed["ammoRaw"], observed["fingerprint"]!["ammoRaw"],
                "independent interaction replacement observer", requireRootView: true);
            Equal(true, JsonNode.DeepEquals(FingerprintSourceViewFixture(deferred, noView)["fingerprint"], observed["fingerprint"]),
                "certified interaction display alone adds no fingerprint input");
            var changedDisplay = original.DeepClone().AsObject();
            View(changedDisplay)["roots"]![0]!["records"]![0]!["code"] = "if (type == 91) { /* formatting */ Effect(); }";
            Equal(true, JsonNode.DeepEquals(observed["fingerprint"], FingerprintSourceViewFixture(deferred, changedDisplay)["fingerprint"]),
                "interaction display formatting does not change native identity");
            var changedCall = original.DeepClone().AsObject(); changedCall["attackReference"]!["sourceCalls"]![0]!["at"] = 21;
            Equal(false, JsonNode.DeepEquals(observed["fingerprint"], FingerprintSourceViewFixture(deferred, changedCall)["fingerprint"]),
                "interaction observer must not erase native source call drift");
            var mutations = new (string Label, Action<JsonObject> Mutate)[] {
                ("unknown family", p => View(p)["source"] = "future_interaction_family"),
                ("future version", p => View(p)["version"] = 2),
                ("wrong version type", p => View(p)["version"] = true),
                ("unknown owner", p => p["attackReference"]!["source"] = "future_attack_source"),
                ("future owner version", p => p["attackReference"]!["version"] = 2),
                ("missing root", p => View(p)["roots"]!.AsArray().RemoveAt(2)),
                ("duplicate root", p => View(p)["roots"]![2] = View(p)["roots"]![0]!.DeepClone()),
                ("unknown root", p => View(p)["roots"]![0]!["root"] = "FutureHit"),
                ("missing certificate", p => View(p)["roots"]![0]!.AsObject().Remove("rootCertificate")),
                ("extra certificate field", p => View(p)["roots"]![0]!["rootCertificate"]!["future"] = true),
                ("unbacked root", p => p["attackReference"]!["sourceMethods"]!.AsArray().RemoveAt(1)),
                ("unbacked helper", p => p["attackReference"]!["sourceMethods"]!.AsArray().RemoveAt(3)),
                ("region certificate drift", p => View(p)["roots"]![0]!["records"]![0]!["sourceMethodSha256"] = new string('b', 64)),
                ("region wrong method", p => View(p)["roots"]![0]!["records"]![0]!["method"] = "Terraria.Projectile.StatusNPC"),
                ("malformed backed module", p => { View(p)["roots"]![0]!["rootCertificate"]!["sourceModuleVersionId"] = "not-a-guid";
                    p["attackReference"]!["sourceMethods"]![0]!["sourceModuleVersionId"] = "not-a-guid"; }),
                ("malformed backed hash", p => { View(p)["roots"]![0]!["rootCertificate"]!["sourceMethodSha256"] = new string('z', 64);
                    p["attackReference"]!["sourceMethods"]![0]!["sourceMethodSha256"] = new string('z', 64); }),
                ("malformed backed helper", p => { View(p)["roots"]![0]!["helpers"]![0]!["sourceModuleVersionId"] = "not-a-guid";
                    p["attackReference"]!["sourceMethods"]![3]!["sourceModuleVersionId"] = "not-a-guid"; }),
                ("wrong backed root method", p => View(p)["roots"]![0]!["rootCertificate"] = Certificate("StatusNPC")),
                ("missing records", p => View(p)["roots"]![0]!["records"] = null),
                ("missing helpers", p => View(p)["roots"]![0]!["helpers"] = null),
                ("missing source methods", p => p["attackReference"]!["sourceMethods"] = null),
            };
            foreach (var (label, mutate) in mutations)
            {
                var raw = original.DeepClone().AsObject(); mutate(raw);
                Equal(0, ReadableNativeViewCount(JsonSerializer.SerializeToElement(raw)), "unknown/unbacked interaction remains literal: " + label);
                var result = FingerprintSourceViewFixture(deferred, raw);
                AssertParentFingerprintNativeFacts(result["directProjectileRaw"], result["fingerprint"]!["directProjectileRaw"],
                    "independent interaction refusal observer: " + label);
                Equal(true, JsonNode.DeepEquals(raw, result["fingerprint"]!["directProjectileRaw"]),
                    "production retains complete unknown/unbacked interaction: " + label);
                Equal(false, JsonNode.DeepEquals(observed["fingerprint"], result["fingerprint"]),
                    "native certificate or unknown envelope drift remains fingerprint input: " + label);
            }
        }
    }
}
