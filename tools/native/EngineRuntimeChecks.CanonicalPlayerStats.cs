using System;
using System.Text.Json;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void ExistingPlayerStatsShareEquipmentConsumer()
    {
        using var actors = new NativeActorState();
        WithPlayer((player, owner) => {
            player.active = true; player.statLife = 50; player.velocity = Vector2.Zero; player.itemAnimation = 0;
            var conditional = NativeUtilityItem("\"lifeRegen\":4,\"lifeRegenCondition\":\"stationary\",\"treasureSense\":true,\"treasureSenseCondition\":\"stationary\"");
            void Sample(Vector2 velocity, int animation)
            {
                owner.ResetEffects(); player.velocity = velocity; player.itemAnimation = animation;
                player.lifeRegen = 0; player.findTreasure = false;
                conditional.UpdateAccessory(player, true);
            }
            Sample(Vector2.Zero, 0);
            Equal(4, player.lifeRegen, "one existing regeneration value contributes once");
            Equal(true, player.findTreasure, "gear uses the native treasure flag");
            Sample(Vector2.UnitX, 0);
            Equal(0, player.lifeRegen, "moving makes the explicit regeneration condition inactive");
            Equal(false, player.findTreasure, "moving makes the explicit treasure condition inactive");
            Sample(Vector2.Zero, 1);
            Equal(0, player.lifeRegen, "active item animation is not stationary recovery");
            Equal(false, player.findTreasure, "active item animation also gates conditional treasure sense");

            var oldWire = NativeUtilityItem("\"lifeRegen\":4,\"treasureSense\":true");
            Equal<string?>(null, oldWire.Data.Accessory.LifeRegenCondition, "old wire retains absent regen condition");
            Equal<string?>(null, oldWire.Data.Accessory.TreasureSenseCondition, "old wire retains absent treasure condition");
            using (var json = JsonDocument.Parse(oldWire.Data.ToNetworkJson()))
            {
                var accessory = json.RootElement.GetProperty("accessory");
                Equal(false, accessory.TryGetProperty("lifeRegenCondition", out _), "serialization preserves old condition absence");
                Equal(false, accessory.TryGetProperty("treasureSenseCondition", out _), "serialization does not invent a treasure condition");
            }
            player.lifeRegen = 0; player.findTreasure = false; player.velocity = Vector2.UnitX;
            oldWire.UpdateAccessory(player, true);
            Equal(4, player.lifeRegen, "old root regeneration remains unconditional");
            Equal(true, player.findTreasure, "ordinary root treasure flag remains unconditional");

            conditional.Data.Accessory.Enabled = false;
            conditional.Data.Armor = new ArmorSpec { Enabled = true, Slot = "head", LifeRegen = 4,
                LifeRegenCondition = "stationary", TreasureSense = true, TreasureSenseCondition = "stationary" };
            player.velocity = Vector2.Zero; player.itemAnimation = 0; player.lifeRegen = 0; player.findTreasure = false;
            conditional.UpdateEquip(player);
            Equal(4, player.lifeRegen, "armor reaches the same regeneration consumer");
            Equal(true, player.findTreasure, "armor reaches the same treasure consumer");
            player.velocity = Vector2.UnitX; player.lifeRegen = 0; player.findTreasure = false;
            conditional.UpdateEquip(player);
            Equal(0, player.lifeRegen, "armor preserves the same conditional behavior");
            Equal(false, player.findTreasure, "armor cannot bypass the treasure condition");
        });
        foreach (string fields in new[] {
            "\"treasureSense\":null", "\"treasureSense\":\"true\"",
            "\"lifeRegenCondition\":null", "\"lifeRegenCondition\":\"unknown\"",
            "\"treasureSenseCondition\":null", "\"treasureSenseCondition\":\"unknown\"",
            "\"playerEffect\":{\"lifeRegenUnits\":4}", "\"playerEffect\":{\"highlightTreasure\":true}",
        })
        {
            bool rejected = false;
            try { NativeUtilityItem("\"defense\":1," + fields); }
            catch (InvalidOperationException) { rejected = true; }
            Equal(true, rejected, "null/unknown conditions and duplicate nested stat inputs are rejected");
        }
    }

    private static void ExistingBuffStatsFilterBeforeTheirAggregateCap()
    {
        using var actors = new NativeActorState();
        WithPlayer((player, owner) => {
            player.active = true; player.statLife = 50; player.velocity = Vector2.Zero; player.itemAnimation = 0;
            owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, LifeRegen = 120 });
            owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, LifeRegen = 120, LifeRegenCondition = "stationary",
                OreSenseRadiusTiles = 1, TreasureSenseCondition = "stationary" });
            owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, LifeRegen = -100 });
            Equal(3, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "conditioned and unconditional equal-rate buffs stay distinct");
            player.lifeRegen = 0; player.findTreasure = false; owner.ResetEffects(); owner.PostUpdateEquips();
            Equal(120, player.lifeRegen, "eligible contributions use the original generated-buff cap");
            Equal(true, player.findTreasure, "stationary buff enables treasure highlighting");
            player.velocity = Vector2.UnitX; player.lifeRegen = 0; player.findTreasure = false;
            owner.ResetEffects(); owner.PostUpdateEquips();
            Equal(20, player.lifeRegen, "inactive contribution is removed before the cap, not after it");
            Equal(false, player.findTreasure, "inactive conditional treasure does not leak through raw aggregate");
            var view = owner.CaptureGeneratedUtilityBuffPresentation();
            Equal(20, view.Current.LifeRegen, "read-only presentation sees actual eligible aggregate");
            Equal(0, view.Current.OreSenseRadiusTiles, "read-only treasure state follows actual condition");
        });
        WithPlayer((player, owner) => {
            player.active = true; player.statLife = 50; player.velocity = Vector2.UnitX;
            owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, LifeRegen = 100 });
            owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, LifeRegen = -100, LifeRegenCondition = "stationary" });
            player.lifeRegen = 0; owner.ResetEffects(); owner.PostUpdateEquips();
            Equal(100, player.lifeRegen, "raw aggregate cancellation cannot suppress an eligible contribution");
        });
        WithPlayer((player, owner) => {
            player.active = true; player.statLife = 50; player.velocity = Vector2.Zero;
            owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 1, LifeRegen = 4,
                LifeRegenCondition = "stationary", OreSenseRadiusTiles = 1, TreasureSenseCondition = "stationary" });
            player.lifeRegen = 0; player.findTreasure = false; owner.ResetEffects(); owner.PostUpdateEquips();
            Equal(4, player.lifeRegen, "last buff tick still applies the existing regeneration");
            Equal(true, player.findTreasure, "last buff tick still applies the existing treasure sense");
            player.lifeRegen = 0; player.findTreasure = false; owner.ResetEffects(); owner.PostUpdateEquips();
            Equal(0, player.lifeRegen, "expiration retires regeneration without another stat channel");
            Equal(false, player.findTreasure, "expiration retires treasure sense");
            owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 60, MiningSpeedMultiplier = 1.5f });
            owner.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 90, MiningSpeedMultiplier = 1.5f,
                LifeRegenCondition = "stationary", TreasureSenseCondition = "stationary" });
            Equal(1, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "conditions on zero stats do not split identical mechanics");
        });
    }
}
