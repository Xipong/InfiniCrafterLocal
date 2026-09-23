using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void AppliedTraceObservesProjectionWithoutChangingDefinition()
    {
        var hash = typeof(InfiniCrafterLocal.Common.Services.GeneratedItemRegistryService)
            .GetMethod("ComputeDefinitionHash", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        foreach (bool passive in new[] { false, true })
        {
            var data = GeneratedItemData.Placeholder();
            data.Id = "applied_trace_probe";
            data.Gameplay.Damage = 37;
            if (passive)
            {
                data.Accessory = new AccessorySpec { Enabled = true, Defense = -7, MaxLife = 1 };
                data.RuntimeProgram.Bindings = new[] {
                    new RuntimeBindingSpec { Id = "equip", Input = RuntimeInputKind.Equipped,
                        Role = RuntimeEntityRole.Primary, UsePolicy = new RuntimeBindingUsePolicySpec {
                            Action = new RuntimeBindingActionSpec { Kind = RuntimeBindingAction.EquipPassive, TargetId = data.RuntimeProgram.ItemEntityId },
                        } },
                };
            }
            data.Normalize();
            string json = data.ToJson(), network = data.ToNetworkJson(), save = data.ToPlayerSaveJson();
            string definitionHash = (string)hash.Invoke(null, new object[] { data })!;
            var item = new Terraria.Item();
            for (int pass = 0; pass < 2; pass++)
            {
                data.ApplyToItem(item);
                string trace = data.LastAppliedTrace ?? throw new InvalidOperationException("successful ApplyToItem left trace empty");
                string[] fields = trace.Split(" | ");
                Equal(true, fields.Contains("damage=" + item.damage), "trace uses applied damage, not authored damage");
                Equal(true, fields.Contains("useStyle=" + item.useStyle), "trace uses applied useStyle");
                Equal(true, fields.Contains("defense=" + item.defense), "trace includes signed defense");
                Equal(true, fields.Contains("shoot=" + item.shoot), "trace uses actual projectile proxy ID");
                foreach (string field in new[] {
                    "damageClass=" + item.DamageType.Name, "useTime=" + item.useTime,
                    "useAnimation=" + item.useAnimation, "shootSpeed=" + item.shootSpeed,
                    "knockback=" + item.knockBack, "rare=" + item.rare, "value=" + item.value,
                    "accessory=" + item.accessory, "ammo=" + item.ammo, "noMelee=" + item.noMelee,
                    "noUseGraphic=" + item.noUseGraphic, "channel=" + item.channel,
                    "maxStack=" + item.maxStack,
                }) Equal(true, fields.Contains(field), "exact applied field " + field);
                if (passive) Equal(false, fields.Contains("damage=37"), "passive trace cannot masquerade as authored damage");
                Equal(json, data.ToJson(), "diagnostic does not change full DTO");
                Equal(network, data.ToNetworkJson(), "diagnostic does not change wire DTO");
                Equal(save, data.ToPlayerSaveJson(), "diagnostic does not change save reference");
                Equal(definitionHash, (string)hash.Invoke(null, new object[] { data })!, "definition hash unchanged");
                item.damage = 999; // LastAppliedTrace is a projection snapshot, not current/prefixed combat stats.
                Equal(trace, data.LastAppliedTrace!, "snapshot remains historical until next ApplyToItem");
            }
            Equal(37, data.Gameplay.Damage, "diagnostic preserves authored damage");
            var received = GeneratedItemData.FromJson(network)!;
            Equal(true, received.LastAppliedTrace is null, "wire clone has no historical local trace");
            string prior = data.LastAppliedTrace!;
            data.Gameplay.Rarity = 2;
            Equal(prior, data.LastAppliedTrace!, "authored edit does not rewrite historical projection");
            data.ApplyToItem(item);
            Equal(true, data.LastAppliedTrace!.Split(" | ").Contains("rare=2"), "reapplication replaces snapshot");
            Equal(false, prior == data.LastAppliedTrace, "updated projection is not stale");
        }
    }

    private static void PlayerSaveReferenceRequiresVersionMarkers()
    {
        const string boundary = "GeneratedItemData.FromPlayerSaveJson";
        var source = GeneratedItemData.Placeholder();
        source.Id = "save_contract_probe";
        source.Name = "Saved reference probe";
        source.RecipeKey = "saved_recipe_probe";
        source.RecipeMeta.WorldScoped = true;
        source.RecipeMeta.WorldId = "world_probe";
        source.Gameplay.Damage = 37;
        InfiniCrafterLocal.Content.Items.GeneratedItem Host(GeneratedItemData? data = null)
        {
            var host = new InfiniCrafterLocal.Content.Items.GeneratedItem();
            typeof(Terraria.ModLoader.ModType<Terraria.Item>).GetProperty("Entity",
                System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.NonPublic)!
                .SetValue(host, new Terraria.Item());
            if (data is not null) typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(host, data);
            return host;
        }
        var tag = new Terraria.ModLoader.IO.TagCompound();
        Host(source).SaveData(tag);
        string valid = tag.GetString("infiniJson");
        void CheckValid()
        {
            var parsed = GeneratedItemData.FromPlayerSaveJson(valid) ?? throw new InvalidOperationException("writer output rejected");
            Equal(true, GeneratedItemData.IsPlayerSaveReferenceOnly(parsed), "valid save is reference-only");
            Equal(false, ContractJsonDiagnostics.TryGet(boundary, out _), "valid reference clears its parse diagnostic");
            var loaded = Host();
            loaded.LoadData(tag);
            Equal(source.Id, loaded.Data.Id, "actual LoadData retains identity");
            Equal(source.RecipeKey, loaded.Data.RecipeKey, "actual LoadData retains recipe");
            Equal(source.Name, loaded.Data.Name, "actual LoadData retains display name");
            Equal(source.RecipeMeta.WorldId, loaded.Data.RecipeMeta.WorldId, "actual LoadData retains world scope");
            Equal(0, loaded.Item.damage, "reference does not restore unverified gameplay");
            var savedAgain = new Terraria.ModLoader.IO.TagCompound();
            loaded.SaveData(savedAgain);
            Equal(valid, savedAgain.GetString("infiniJson"), "reference load/save round trip is exact");
            Equal(37, source.Gameplay.Damage, "save/load does not mutate source definition");
        }
        CheckValid();
        var cases = new System.Collections.Generic.List<(string Name, string Json)>();
        foreach (string field in new[] { "infiniSaveKind", "version", "runtimeApiVersion" })
        {
            var node = System.Text.Json.Nodes.JsonNode.Parse(valid)!.AsObject();
            node.Remove(field);
            cases.Add(("missing " + field, node.ToJsonString()));
        }
        foreach (string version in new[] { "0", "4", "6", "-1", "2147483647", "null", "\"5\"", "true", "[]" })
        {
            var node = System.Text.Json.Nodes.JsonNode.Parse(valid)!.AsObject();
            node["version"] = System.Text.Json.Nodes.JsonNode.Parse(version);
            cases.Add(("version=" + version, node.ToJsonString()));
        }
        foreach (string field in new[] { "infiniSaveKind", "runtimeApiVersion" })
        foreach (string value in new[] { "null", "\"legacy\"" })
        {
            var node = System.Text.Json.Nodes.JsonNode.Parse(valid)!.AsObject();
            node[field] = System.Text.Json.Nodes.JsonNode.Parse(value);
            cases.Add((field + "=" + value, node.ToJsonString()));
        }
        cases.Add(("empty object", "{}"));
        var failures = new System.Collections.Generic.List<string>();
        foreach (var test in cases)
        {
            try
            {
                Equal(true, GeneratedItemData.FromPlayerSaveJson(test.Json) is null, test.Name + " rejected");
                Equal(true, ContractJsonDiagnostics.TryGet(boundary, out _), test.Name + " records parse diagnostic");
                var loaded = Host();
                loaded.LoadData(new Terraria.ModLoader.IO.TagCompound { ["infiniJson"] = test.Json });
                Equal("corrupt_reference", loaded.Data.SourceMode, test.Name + " actual LoadData remains inert");
                Equal(0, loaded.Item.damage, test.Name + " grants no gameplay");
                CheckValid();
            }
            catch (Exception error) { failures.Add(test.Name + ": " + error.Message); }
        }
        ContractJsonDiagnostics.Clear(boundary);
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static RuntimeProgramSpec ContractProgram(int entityCount, int limit)
    {
        var program = GeneratedItemData.Placeholder().RuntimeProgram;
        var item = program.Entities.Single();
        program.Entities = Enumerable.Range(0, entityCount).Select(index => index == 0 ? item : new RuntimeEntitySpec
        {
            Id = "helper_" + index,
            Kind = RuntimeEntityKind.TemporaryHelper,
            VisualRole = "helper",
            Visual = new RuntimeEntityVisualSpec { Role = "helper", AssetMode = "no_asset" },
            Spawn = new RuntimeSpawnSpec { Enabled = true },
            LifetimeTicks = 60,
        }).ToArray();
        program.Limits.MaxEntityCount = limit;
        return JsonSerializer.Deserialize<RuntimeProgramSpec>(JsonSerializer.Serialize(program))!;
    }

    private static void RuntimeEntityCountRespectsDeclaredLimit()
    {
        int engineCap = InfiniRuntimeLimits.MaxRuntimeEntities;
        foreach (int limit in new[] { 1, 2, engineCap })
        {
            var program = ContractProgram(limit, limit);
            program.NormalizeAndValidate();
            Equal(limit, program.Entities.Length, "exact-limit entity count remains intact");
            Equal(limit, program.Limits.MaxEntityCount, "declared limit remains intact");
            string[] ids = program.Entities.Select(entity => entity.Id).ToArray();
            program.NormalizeAndValidate();
            Equal(true, ids.SequenceEqual(program.Entities.Select(entity => entity.Id)), "repeat validation preserves identities");
        }
        foreach (int limit in new[] { 1, 2, engineCap })
        {
            var program = ContractProgram(limit + 1, limit);
            bool rejected = false;
            try { program.NormalizeAndValidate(); }
            catch (InvalidDataException error) when (error.Message.Contains("runtimeProgram.entities", StringComparison.Ordinal))
            {
                rejected = true;
            }
            Equal(true, rejected, "entity count above declared limit " + limit + " is rejected");
            Equal(limit + 1, program.Entities.Length, "rejection must not truncate entities");
        }
        // Preserve the existing engine-level cap normalization, not a new policy.
        var aboveCap = ContractProgram(engineCap, int.MaxValue);
        aboveCap.NormalizeAndValidate();
        Equal(engineCap, aboveCap.Limits.MaxEntityCount, "engine cap cannot be raised by wire");
        var empty = ContractProgram(0, engineCap);
        bool emptyRejected = false;
        try { empty.NormalizeAndValidate(); }
        catch (InvalidDataException error) when (error.Message.Contains("runtimeProgram.entities", StringComparison.Ordinal))
        {
            emptyRejected = true;
        }
        Equal(true, emptyRejected, "empty entity list remains invalid");
    }
}
