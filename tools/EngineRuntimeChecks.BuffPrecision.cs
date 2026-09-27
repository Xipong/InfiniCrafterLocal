using System;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void SmallGeneratedBuffsReachRealHooks()
    {
        foreach (string companion in new[] { "sole", "healing", "ore" })
        foreach ((string field, float value) in new[] {
            ("movementSpeed", .0005f), ("movementSpeed", -.0005f),
            ("jumpBoost", .0005f), ("miningSpeedMultiplier", 1.0005f),
            ("miningSpeedMultiplier", .9995f),
            ("miningSpeedMultiplier", MathF.BitIncrement(1f)),
            ("miningSpeedMultiplier", MathF.BitDecrement(1f)),
        })
        {
            JsonObject doc = JsonNode.Parse(GeneratedItemData.Placeholder().ToJson())!.AsObject();
            JsonObject gameplay = doc["gameplay"]!.AsObject();
            JsonObject buff = gameplay["generatedBuff"]!.AsObject();
            buff["durationTicks"] = 60;
            buff["miningSpeedMultiplier"] = 1f;
            buff["movementSpeed"] = 0f;
            buff["jumpBoost"] = 0f;
            buff["emitLightStrength"] = 0f;
            buff["lightColorName"] = "";
            buff["manaRegen"] = 0;
            buff["lifeRegen"] = 0;
            buff["oreSenseRadiusTiles"] = companion == "ore" ? 1 : 0;
            buff[field] = value;
            gameplay["healLife"] = companion == "healing" ? 1 : 0;
            string target = doc["runtimeProgram"]!["entities"]![0]!["id"]!.GetValue<string>();
            doc["runtimeProgram"]!["bindings"] = new JsonArray(new JsonObject {
                ["id"] = "buff_use", ["input"] = "primary_use", ["role"] = "primary",
                ["usePolicy"] = new JsonObject {
                    ["action"] = new JsonObject { ["kind"] = "apply_item_effects", ["targetId"] = target },
                    ["stackCost"] = 0, ["contactDamage"] = false,
                },
            });
            doc["runtimeProgram"]!["itemUse"]!["configured"] = true;
            GeneratedItemData data = GeneratedItemData.FromJson(doc.ToJsonString())
                ?? throw new InvalidOperationException($"small buff DTO rejected: {field}/{value:R}/{companion}");
            Equal(true, data.Gameplay.GeneratedBuff.HasAnyEffect, "small buff effect gate");
            WithPlayer((player, generated) =>
            {
                player.active = true;
                player.moveSpeed = player.pickSpeed = 1f;
                var item = new Item { type = 1, stack = 1 };
                var host = new GeneratedItem();
                typeof(ModType<Item>).GetProperty("Entity", BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic)!.SetValue(host, item);
                typeof(Item).GetProperty("ModItem")!.SetValue(item, host);
                typeof(GeneratedItem).GetProperty("Data")!.SetValue(host, data);
                data.ApplyToItem(item);
                Equal(true, host.CanUseItem(player), "small buff CanUseItem");
                host.UseItem(player);
                generated.PostUpdateEquips();
                // Exact float equality: epsilon assertions would hide the original bug.
                Equal(field == "movementSpeed" ? 1f + value : 1f, player.moveSpeed, "small movement");
                Equal(field == "jumpBoost" ? value : 0f, player.jumpSpeedBoost, "small jump");
                Equal(field == "miningSpeedMultiplier" ? 1f / value : 1f, player.pickSpeed, "small mining");
                Equal(companion == "ore", player.findTreasure, "ore companion");
            });
        }
        var neutral = new GeneratedBuffSpec { DurationTicks = 60 };
        Equal(false, neutral.HasAnyEffect, "exact neutral stays inert");
    }
}
