#nullable enable
using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void PersistedV5UnknownExecutableFieldsStillRefuse()
    {
        var source = JsonNode.Parse(NamedItemEffectsFixture().ToJson())!.AsObject();
        Equal(true, GeneratedItemData.FromJson(source.ToJsonString()) is not null, "current definition is admitted before mutations");
        Action<JsonObject>[] corruptions = {
            w => w["futureGameplay"] = new JsonObject(),
            w => { w["Id"] = w["id"]!.DeepClone(); w.Remove("id"); },
            w => w["canonical"] = new JsonObject { ["headNoun"] = "obsolete metadata" },
            w => w["runtimeProgram"]!["futureMechanic"] = 1,
            w => w["gameplay"]!["futureDamage"] = 1,
            w => w["visual"]!["effectColor"] = "effect",
            w => w["schemaVersion"] = 4,
            w => w["runtimeApiVersion"] = "infini.runtime-program.v4",
            w => w["vfxManifest"]!["schema"] = "infini.vfx.runtime-events.v15",
        };
        foreach (var mutate in corruptions) {
            var bad = source.DeepClone().AsObject(); mutate(bad);
            string input = bad.ToJsonString();
            Equal(true, GeneratedItemData.FromJson(input) is null, "retired or unknown contract refuses without migration");
            Equal(true, ContractJsonDiagnostics.TryGet("GeneratedItemData.FromJson", out var error)
                && !string.IsNullOrWhiteSpace(error?.Message), "strict boundary records refusal");
            Equal(input, bad.ToJsonString(), "refusal leaves source unchanged");
        }
        string duplicate = source.ToJsonString().Insert(1, "\"id\":\"duplicate\",");
        Equal(true, GeneratedItemData.FromJson(duplicate) is null, "exact duplicate JSON member refuses");
        string archived = File.ReadAllText(Path.Combine("tests", "generator", "fixtures", "persisted_v5_baseline.json"));
        Equal("f34bc94a29038f341c46c227ba126a024e1f7ce711f4330a305f236ba579cefc",
            Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(archived))).ToLowerInvariant(), "immutable persisted baseline");
        foreach (var entry in JsonNode.Parse(archived)!["cases"]!.AsArray())
            Equal(true, GeneratedItemData.FromJson(entry!["definition"]!.ToJsonString()) is null,
                "archived contract has no local-cache admission exception");
    }

    private static void PersistedV5CurrentFormatIsExactPassThrough()
    {
        foreach (var source in new[] { GeneratedItemData.Placeholder(), NamedItemEffectsFixture(), SentryTargetingFixture() }) {
            source.Debug["A"] = JsonSerializer.SerializeToElement(1); source.Debug["a"] = JsonSerializer.SerializeToElement(2);
            source.Concept = JsonSerializer.SerializeToElement(new JsonObject { ["A"] = 1, ["a"] = 2 });
            string json = source.ToJson();
            var loaded = GeneratedItemData.FromJson(json) ?? throw new InvalidOperationException("current saved JSON rejected");
            Equal(json, loaded.ToJson(), "one current writer/reader preserves exact serialized definition");
            string reference = source.ToPlayerSaveJson();
            Equal(true, GeneratedItemData.FromPlayerSaveJson(reference) is not null, "current compact reference is admitted");
            Equal(true, GeneratedItemData.FromPlayerSaveJson(reference.Insert(1, "\"id\":\"duplicate\",")) is null,
                "compact reference has the same exact duplicate-member boundary");
        }
    }

    private static void PersistedV5RegistryLoadsReadOnlyAndKeepsWorldFence()
    {
        int oldWorld = Terraria.Main.worldID;
        try {
            Terraria.Main.worldID = 43101; using var registry = new GeneratedItemRegistryService();
            var source = AssetOwnerData("persisted_current_synthetic", "never_created.png"); source.Gameplay.Damage = 31;
            string json = source.ToJson();
            Equal(GeneratedDefinitionPersistenceStatus.Written, registry.PersistOne(source).Status, "current writer persists the definition");
            string file = Directory.GetFiles(registry.StoreRoot, "*.json", SearchOption.AllDirectories)
                .Single(path => File.ReadAllText(path) == json);
            byte[] before = File.ReadAllBytes(file);
            try {
                registry.ReloadLocalCacheForCurrentWorld();
                Equal(true, registry.TryGet(source.Id, out var loaded), "registry uses current strict reader");
                Equal(31, loaded.Gameplay.Damage, "registry retains executable values");
                Equal(true, before.SequenceEqual(File.ReadAllBytes(file)), "load does not rewrite definition");
                Terraria.Main.worldID = 43102; registry.ReloadLocalCacheForCurrentWorld();
                Equal(false, registry.TryGet(source.Id, out _), "current reader preserves world ownership");
                Equal(true, before.SequenceEqual(File.ReadAllBytes(file)), "foreign read leaves file byte exact");
            } finally { File.Delete(file); }
        } finally { Terraria.Main.worldID = oldWorld; }
    }
}
