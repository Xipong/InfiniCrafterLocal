using System;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using InfiniCrafterLocal.Common.Services;

internal static partial class EngineRuntimeChecks
{
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
            Equal(false, JsonNode.DeepEquals(fingerprint, FingerprintSourceViewFixture(deferred, changedNative)["fingerprint"]), "native IL changes still change fingerprint: " + deferred);
            var future = FingerprintSourceViewFixture(deferred, View("unknown_future_source_family", 1, "opaque"));
            Equal("unknown_future_source_family", future["fingerprint"]!["directProjectileRaw"]!["attackReference"]!["nativeCSharpSource"]!["source"]!.GetValue<string>(),
                "unknown source family stays literal: " + deferred);
        }
    }
}
