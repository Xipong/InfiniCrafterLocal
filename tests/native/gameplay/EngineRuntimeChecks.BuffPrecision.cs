using System;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void GeneratedBuffDurationSurvivesNativeHookOrder()
    {
        using var scope = new MobilityConsumptionNativeScope();
        foreach (bool held in new[] { false, true })
        foreach (int duration in new[] { 1, 2, 60 })
            WithPlayer((player, generated) =>
            {
                PrepareMobilityConsumptionPlayer(player);
                var data = MobilityConsumptionFixture("", 0);
                var buff = new GeneratedBuffSpec {
                    DurationTicks = duration, JumpBoost = .5f,
                    OreSenseRadiusTiles = 1, EmitLightStrength = .5f, LightColorName = "white",
                };
                if (held)
                {
                    data.RuntimeProgram.Bindings[0].UsePolicy.Action.Kind = RuntimeBindingAction.UseItemBody;
                    data.RuntimeProgram.EffectGroups = new[] { new RuntimeItemEffectGroupSpec {
                        Id = "held", GeneratedBuff = buff,
                    } };
                    data.RuntimeProgram.HeldEffectGroupId = "held";
                }
                else data.Gameplay.GeneratedBuff = buff;
                var host = MobilityConsumptionHost(data);
                player.inventory[0] = host.Item;
                int lastRefresh = held ? 2 : 0;
                WithLighting((_, lights) =>
                {
                    for (int tick = 0; tick <= lastRefresh + duration + 1; tick++)
                    {
                        MaterialClock((uint)(5000 + tick));
                        player.jumpSpeedBoost = 0f;
                        player.findTreasure = false;
                        lights.Clear();
                        generated.ResetEffects();
                        // Player.Update applies equipment before ItemCheck/HoldItem;
                        // PostUpdate is the final hook, after the new application.
                        generated.PostUpdateEquips();
                        if (held && tick <= lastRefresh) host.HoldItem(player);
                        else if (!held && tick == 0)
                        {
                            Equal(true, host.CanUseItem(player), "native-order utility admission");
                            host.UseItem(player);
                        }
                        generated.PostUpdate();
                        float expected = tick > 0 && tick <= lastRefresh + duration ? .5f : 0f;
                        Equal(expected, player.jumpSpeedBoost,
                            $"native-order utility held={held} duration={duration} tick={tick}");
                        Equal(expected > 0f, player.findTreasure,
                            $"native-order ore sense held={held} duration={duration} tick={tick}");
                        Equal(expected > 0f ? 1 : 0, lights.Count,
                            $"native-order light held={held} duration={duration} tick={tick}");
                    }
                });
            });
    }

    private static void ReactiveBuffLightSurvivesLateNativeHook()
    {
        using var scope = new SwarmRuntimeScope();
        foreach (int duration in new[] { 1, 2, 60 })
            WithPlayer((player, owner) =>
            {
                player.active = true; player.statLife = 100; player.whoAmI = 0;
                Terraria.Main.player[0] = player;
                var item = ReactiveUtilityItem();
                var buff = item.Data.RuntimeProgram.EffectGroups![0].GeneratedBuff!;
                buff.DurationTicks = duration; buff.EmitLightStrength = .5f; buff.LightColorName = "white";
                Equal(true, GeneratedItemData.FromJson(item.Data.ToNetworkJson()) is not null, "reactive light strict DTO admission");
                WithLighting((_, lights) =>
                {
                    MaterialClock(7000); owner.ResetEffects(); ItemLoader.UpdateAccessory(item.Item, player, false);
                    owner.PostUpdateEquips(); owner.PostUpdate();
                    // Main.DoUpdateInWorld updates projectiles after players;
                    // Projectile.Damage -> Player.Hurt can deliver PostHurt here.
                    owner.PostHurt(new Player.HurtInfo { Damage = 10 });
                    Equal(1, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "equipped on_hurt admits one effect");
                    Equal(0, lights.Count, "late reaction awaits the shared effect phase");
                    for (int tick = 1; tick <= duration + 1; tick++)
                    {
                        MaterialClock((uint)(7000 + tick)); player.moveSpeed = 1f; lights.Clear();
                        owner.ResetEffects(); ItemLoader.UpdateAccessory(item.Item, player, false);
                        owner.PostUpdateEquips(); owner.PostUpdate();
                        bool active = tick <= duration;
                        Equal(active ? 1.25f : 1f, player.moveSpeed, $"late reaction stats duration={duration} tick={tick}");
                        Equal(active ? 1 : 0, lights.Count, $"late reaction light duration={duration} tick={tick}");
                    }
                });
            });
    }

    private static void GeneratedBuffLightKeepsClientServerScope()
    {
        using var scope = new SwarmRuntimeScope();
        foreach (var role in SwarmRoles)
            WithPlayer((player, owner) => WithLighting((_, lights) =>
            {
                player.active = true; player.whoAmI = 0;
                // This scope check starts from an existing accepted utility entry;
                // canonical packet admission/correction has its own native checks.
                Equal(true, owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec {
                    DurationTicks = 1, JumpBoost = .5f, EmitLightStrength = .5f, LightColorName = "white",
                }), "utility light scope entry");
                Terraria.Main.netMode = role.Mode; Terraria.Main.myPlayer = role.Local;
                Terraria.Main.dedServ = role.Mode == Terraria.ID.NetmodeID.Server;
                owner.PostUpdateEquips(); owner.PostUpdate();
                Equal(role.Name == "remote-client" ? 0f : .5f, player.jumpSpeedBoost, role.Name + " gameplay authority unchanged");
                Equal(role.Mode == Terraria.ID.NetmodeID.Server ? 0 : 1, lights.Count, role.Name + " light is client presentation");
                lights.Clear(); player.jumpSpeedBoost = 0f;
                owner.PostUpdateEquips(); owner.PostUpdate();
                Equal(0f, player.jumpSpeedBoost, role.Name + " one-tick effect expires");
                Equal(0, lights.Count, role.Name + " no stale or duplicate light");
            }));
    }

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
                AttachItem(host, item, data);
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
