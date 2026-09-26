using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Models;

internal static partial class EngineRuntimeChecks
{
    private static void NeutralItemOmissionsPreserveProjection()
    {
        // Build an actual wire document first; ToJson normalizes its source and
        // would erase a missing-key test if called after removing fields.
        foreach (string damageClass in new[] { "melee", "magic" })
        {
            var source = GeneratedItemData.Placeholder();
            source.Gameplay.DamageClass = damageClass;
            source.Gameplay.Damage = 17;
            JsonObject full = JsonNode.Parse(source.ToJson())!.AsObject();
            JsonObject gameplay = full["gameplay"]!.AsObject();
            JsonObject itemUse = full["runtimeProgram"]!["itemUse"]!.AsObject();
            gameplay["manaCost"] = 0;
            gameplay["holdoutOffsetX"] = 0;
            itemUse["holdoutOffsetX"] = 0;
            gameplay["holdoutOffsetY"] = 0;
            itemUse["holdoutOffsetY"] = 0;

            // Test each omission and the whole approved group, with no class
            // inference (melee and magic must both retain the same zero mana).
            string[][] omissions = {
                new[] { "manaCost" }, new[] { "holdoutOffsetX" }, new[] { "holdoutOffsetY" },
                new[] { "manaCost", "holdoutOffsetX", "holdoutOffsetY" },
            };
            foreach (string[] missing in omissions)
            {
                var sparse = (JsonObject)full.DeepClone();
                foreach (string key in missing)
                {
                    sparse["gameplay"]!.AsObject().Remove(key);
                    if (key != "manaCost") sparse["runtimeProgram"]!["itemUse"]!.AsObject().Remove(key);
                }
                var explicitData = GeneratedItemData.FromJson(full.ToJsonString())
                    ?? throw new InvalidOperationException("explicit neutral item wire rejected");
                var sparseData = GeneratedItemData.FromJson(sparse.ToJsonString())
                    ?? throw new InvalidOperationException("sparse neutral item wire rejected");
                string label = damageClass + "/" + string.Join(",", missing);
                Equal(explicitData.ToJson(), sparseData.ToJson(), label + " complete normalized DTO");
                var expected = new Terraria.Item();
                var actual = new Terraria.Item();
                explicitData.ApplyToItem(expected);
                sparseData.ApplyToItem(actual);
                Equal(expected.mana, actual.mana, label + " actual Item.mana");
                Equal(0, actual.mana, label + " zero cost irrespective of class");
                Equal(expected.DamageType.Name, actual.DamageType.Name, label + " actual Item.DamageType");
                Equal(damageClass + "damageclass", actual.DamageType.Name.ToLowerInvariant(), label + " selected class");
                Equal(17, actual.damage, label + " damage remains active");
                Equal(0, sparseData.RuntimeProgram.ItemUse.HoldoutOffsetX, label + " draw X");
                Equal(0, sparseData.RuntimeProgram.ItemUse.HoldoutOffsetY, label + " draw Y");
                var host = new InfiniCrafterLocal.Content.Items.GeneratedItem();
                typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(host, sparseData);
                Equal(0f, host.HoldoutOffset()!.Value.X, label + " real item draw X");
                Equal(0f, host.HoldoutOffset()!.Value.Y, label + " real item draw Y");
            }

            // Non-neutral costs/offsets must never be silently erased while
            // independently omitted neutral neighbors are completed.
            gameplay["manaCost"] = 13;
            gameplay["holdoutOffsetX"] = 7;
            itemUse["holdoutOffsetX"] = 7;
            gameplay["holdoutOffsetY"] = -3;
            itemUse["holdoutOffsetY"] = -3;
            foreach (string retained in new[] { "manaCost", "holdoutOffsetX", "holdoutOffsetY" })
            {
                var sparse = (JsonObject)full.DeepClone();
                foreach (string key in new[] { "manaCost", "holdoutOffsetX", "holdoutOffsetY" })
                    if (key != retained)
                    {
                        sparse["gameplay"]!.AsObject().Remove(key);
                        if (key != "manaCost") sparse["runtimeProgram"]!["itemUse"]!.AsObject().Remove(key);
                    }
                var parsed = GeneratedItemData.FromJson(sparse.ToJsonString())
                    ?? throw new InvalidOperationException("non-neutral item wire rejected: " + retained);
                var item = new Terraria.Item();
                parsed.ApplyToItem(item);
                Equal(retained == "manaCost" ? 13 : 0, item.mana, damageClass + "/" + retained + " cost");
                Equal(retained == "holdoutOffsetX" ? 7 : 0, parsed.RuntimeProgram.ItemUse.HoldoutOffsetX, retained + " X");
                Equal(retained == "holdoutOffsetY" ? -3 : 0, parsed.RuntimeProgram.ItemUse.HoldoutOffsetY, retained + " Y");
                Equal(damageClass + "damageclass", item.DamageType.Name.ToLowerInvariant(), retained + " damage class");
                var host = new InfiniCrafterLocal.Content.Items.GeneratedItem();
                typeof(InfiniCrafterLocal.Content.Items.GeneratedItem).GetProperty("Data")!.SetValue(host, parsed);
                Equal(retained == "holdoutOffsetX" ? 7f : 0f, host.HoldoutOffset()!.Value.X, retained + " real draw X");
                Equal(retained == "holdoutOffsetY" ? -3f : 0f, host.HoldoutOffset()!.Value.Y, retained + " real draw Y");
            }
        }
    }

    private static void NeutralBuffOmissionsReachRealPlayerEffects()
    {
        var source = GeneratedItemData.Placeholder();
        JsonObject full = JsonNode.Parse(source.ToJson())!.AsObject();
        JsonObject buff = full["gameplay"]!["generatedBuff"]!.AsObject();
        buff["durationTicks"] = 60;
        buff["emitLightStrength"] = 0f;
        buff["lightColorName"] = "";
        string[] neutralKeys = {
            "miningSpeedMultiplier", "oreSenseRadiusTiles", "movementSpeed",
            "jumpBoost", "manaRegen", "lifeRegen",
        };
        // Each effect alone must keep its meaning when all other approved
        // neutral fields disappear. Ore sense and jump are deliberately sole
        // effects, not merely passengers of a different active buff.
        foreach (string? active in new string?[] {
            null, "miningSpeedMultiplier", "oreSenseRadiusTiles", "movementSpeed",
            "jumpBoost", "manaRegen", "lifeRegen",
        })
        {
            foreach (string key in neutralKeys)
                buff[key] = key == "miningSpeedMultiplier" ? JsonValue.Create(1f)
                    : key == "movementSpeed" || key == "jumpBoost" ? JsonValue.Create(0f)
                    : JsonValue.Create(0);
            if (active is not null)
                buff[active] = active switch {
                    "miningSpeedMultiplier" => JsonValue.Create(2f),
                    "movementSpeed" => JsonValue.Create(0.5f),
                    "jumpBoost" => JsonValue.Create(2f),
                    "oreSenseRadiusTiles" => JsonValue.Create(1),
                    _ => JsonValue.Create(3),
                };
            var sparse = (JsonObject)full.DeepClone();
            foreach (string key in neutralKeys)
                if (key != active) sparse["gameplay"]!["generatedBuff"]!.AsObject().Remove(key);
            var explicitData = GeneratedItemData.FromJson(full.ToJsonString())
                ?? throw new InvalidOperationException("explicit generated buff rejected: " + active);
            var sparseData = GeneratedItemData.FromJson(sparse.ToJsonString())
                ?? throw new InvalidOperationException("sparse generated buff rejected: " + active);
            string label = active ?? "no active effects";
            Equal(explicitData.ToJson(), sparseData.ToJson(), label + " complete normalized DTO");
            GeneratedBuffSpec spec = sparseData.Gameplay.GeneratedBuff;
            Equal(active is not null, spec.HasAnyEffect, label + " effect gate");
            WithPlayer((player, generated) =>
            {
                player.active = true;
                player.pickSpeed = 1f;
                player.moveSpeed = 1f;
                generated.ApplyGeneratedUtilityBuff(spec);
                generated.PostUpdateEquips(); // Real ModPlayer application hook, no world/game loop.
                Equal(active == "miningSpeedMultiplier" ? 0.5f : 1f, player.pickSpeed, label + " mining");
                Equal(active == "movementSpeed" ? 1.5f : 1f, player.moveSpeed, label + " movement");
                Equal(active == "jumpBoost" ? 2f : 0f, player.jumpSpeedBoost, label + " jump");
                Equal(active == "manaRegen" ? 3 : 0, player.manaRegenBonus, label + " mana regen");
                Equal(active == "lifeRegen" ? 3 : 0, player.lifeRegen, label + " life regen");
                Equal(active == "oreSenseRadiusTiles", player.findTreasure, label + " ore sense");
                int ticks = (int)typeof(InfiniCrafterLocal.Common.Players.InfiniCraftPlayer)
                    .GetField("_generatedBuffTicks", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!
                    .GetValue(generated)!;
                Equal(active is null ? 0 : 60, ticks, label + " admitted active entries only");
            });
        }
    }

    private static int ReplayGeneratedContracts(string path)
    {
        int passed = 0, failed = 0;
        foreach (string line in File.ReadLines(path))
        {
            if (string.IsNullOrWhiteSpace(line)) continue;
            using JsonDocument row = JsonDocument.Parse(line);
            string caseId = row.RootElement.GetProperty("case").GetString() ?? "unknown";
            string json = row.RootElement.GetProperty("data").GetRawText();
            GeneratedItemData? parsed = GeneratedItemData.FromJson(json);
            if (parsed is not null)
            {
                passed++;
                continue;
            }
            failed++;
            ContractJsonDiagnostics.TryGet("GeneratedItemData.FromJson", out ContractJsonError? error);
            Console.WriteLine($"REPLAY FAIL {caseId}: {error?.ErrorType ?? "unknown"}: {error?.Message ?? "no diagnostics"}");
        }
        Console.WriteLine($"Live contract replay: {passed} passed, {failed} failed");
        return failed == 0 && passed > 0 ? 0 : 1;
    }

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
