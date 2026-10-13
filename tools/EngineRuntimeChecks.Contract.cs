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

}
