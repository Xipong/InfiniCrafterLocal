using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.UI;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static readonly MethodInfo Float32BuffTick = typeof(InfiniCraftPlayer)
        .GetMethod("TickGeneratedUtilityBuff", BindingFlags.Instance | BindingFlags.NonPublic)!;

    private static GeneratedItemData Float32BuffData(string field, float value, int duration)
    {
        // Raw JSON is decoded by the canonical strict FromJson consumer. Companion
        // ore-sense keeps the near-neutral example active without masking identity.
        var doc = JsonNode.Parse(GeneratedItemData.Placeholder().ToNetworkJson())!.AsObject();
        var buff = doc["gameplay"]!["generatedBuff"]!.AsObject();
        buff["durationTicks"] = duration;
        buff["miningSpeedMultiplier"] = 1f;
        buff["emitLightStrength"] = 0f;
        buff["lightColorName"] = field == "emitLightStrength" ? "cyan" : "";
        buff["oreSenseRadiusTiles"] = 1;
        buff["movementSpeed"] = 0f;
        buff["jumpBoost"] = 0f;
        buff["manaRegen"] = 0;
        buff["lifeRegen"] = 0;
        buff[field] = value;
        var program = doc["runtimeProgram"]!.AsObject();
        string target = program["itemEntityId"]!.GetValue<string>();
        program["itemUse"]!["configured"] = true;
        program["bindings"] = new JsonArray(new JsonObject {
            ["id"] = "float32_identity_use", ["input"] = "primary_use", ["role"] = "primary",
            ["usePolicy"] = new JsonObject {
                ["action"] = new JsonObject { ["kind"] = "apply_item_effects", ["targetId"] = target },
                ["stackCost"] = 0, ["contactDamage"] = false,
            },
        });
        return GeneratedItemData.FromJson(doc.ToJsonString())
            ?? throw new InvalidOperationException("Real FromJson rejected float32 identity fixture " + field);
    }

    private static void Float32BuffActivate(Player player, GeneratedItemData data)
    {
        var host = MobilityConsumptionHost(data);
        player.inventory[0] = host.Item; player.selectedItem = 0;
        Equal(true, host.CanUseItem(player), "float32 fixture real item admission");
        Equal(true, host.UseItem(player) == true, "float32 fixture actual generated UseItem");
        Equal(1, host.UseCalls, "one real generated effect application");
    }

    private static void NativeFloat32BuffNearNeutralIdentityAndExpiry()
    {
        using var scope = new SwarmRuntimeScope();
        var failures = new List<string>();
        foreach (bool negativeFirst in new[] { false, true })
        {
            try
            {
                WithPlayer((player, generated) => {
                    player.active = true;
                    const float shortValue = .00004f, longValue = -.00004f;
                    var shortBuff = Float32BuffData("movementSpeed", shortValue, 60);
                    var longBuff = Float32BuffData("movementSpeed", longValue, 600);
                    Float32BuffActivate(player, negativeFirst ? longBuff : shortBuff);
                    Float32BuffActivate(player, negativeFirst ? shortBuff : longBuff);
                    var before = generated.CaptureGeneratedUtilityBuffPresentation();
                    Equal(2, before.Entries.Count, "opposite near-neutral float32 values never merge");
                    Equal(shortValue, before.Entries.Single(e => e.RemainingTicks == 60).MovementSpeed, "short exact stored float32 contribution");
                    Equal(longValue, before.Entries.Single(e => e.RemainingTicks == 600).MovementSpeed, "long exact stored float32 contribution");
                    Equal(0f, before.Current.MovementSpeed, "opposite contributions cancel before expiry in either order");
                    player.moveSpeed = 0f; player.pickSpeed = 1f; player.findTreasure = false;
                    generated.PostUpdateEquips();
                    Equal(0f, player.moveSpeed, "real player hook applies the aggregate, not first survivor");
                    Equal(true, player.findTreasure, "ore companion remains independent");
                    // Refresh only the exact negative long contribution with a
                    // shorter duration; it neither stacks nor borrows +short.
                    Float32BuffActivate(player, Float32BuffData("movementSpeed", longValue, 120));
                    Equal(2, generated.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "strict same tiny effect refreshes, never stacks");
                    Equal(600, generated.CaptureGeneratedUtilityBuffPresentation().Entries.Single(e => e.MovementSpeed == longValue).RemainingTicks, "shorter strict repeat never shortens exact long entry");
                    for (int tick = 0; tick < 60; tick++) Float32BuffTick.Invoke(generated, null);
                    var afterShort = generated.CaptureGeneratedUtilityBuffPresentation();
                    Equal(1, afterShort.Entries.Count, "short contribution expires independently");
                    Equal(540, afterShort.Entries[0].RemainingTicks, "long lifetime is not borrowed from the short one");
                    Equal(longValue, afterShort.Current.MovementSpeed, "exact long value after short expiry");
                    player.moveSpeed = 0f; player.pickSpeed = 1f;
                    generated.PostUpdateEquips();
                    Equal(longValue, player.moveSpeed, "real player hook preserves tiny signed survivor");
                    for (int tick = 0; tick < 540; tick++) Float32BuffTick.Invoke(generated, null);
                    Equal(0, generated.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "last contribution expires exactly");
                    player.moveSpeed = 0f; player.pickSpeed = 1f; player.findTreasure = false;
                    generated.PostUpdateEquips();
                    Equal(0f, player.moveSpeed, "no residual movement after all expiries");
                    Equal(false, player.findTreasure, "no residual ore companion after all expiries");
                    Equal(2, before.Entries.Count, "existing presentation snapshot is immutable");
                });
            }
            catch (Exception error) { failures.Add("negativeFirst=" + negativeFirst + ": " + error); }
        }
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }

    private static float Float32IdentityValue(GeneratedUtilityBuffValues value, string field) => field switch {
        "miningSpeedMultiplier" => value.MiningSpeedMultiplier,
        "emitLightStrength" => value.EmitLightStrength,
        "movementSpeed" => value.MovementSpeed,
        "jumpBoost" => value.JumpBoost,
        _ => throw new ArgumentException(field),
    };

    private static void NativeFloat32BuffAllComponentsAndExactRefresh()
    {
        // Server presentation suppression prevents the deliberate tiny light
        // identity from touching graphics. Runtime aggregation/hooks remain real.
        using var scope = new SwarmRuntimeScope(Terraria.ID.NetmodeID.Server, myPlayer: 255);
        var failures = new List<string>();
        foreach ((string field, float first, float second) in new[] {
            ("miningSpeedMultiplier", MathF.BitIncrement(1f), MathF.BitDecrement(1f)),
            ("emitLightStrength", .00004f, .00008f),
            ("movementSpeed", .00004f, -.00004f),
            ("jumpBoost", .00004f, .00008f),
        })
        foreach (bool reverse in new[] { false, true })
        {
            try
            {
                WithPlayer((player, generated) => {
                    player.active = true;
                    var a = Float32BuffData(field, reverse ? second : first, 2).Gameplay.GeneratedBuff;
                    var b = Float32BuffData(field, reverse ? first : second, 4).Gameplay.GeneratedBuff;
                    generated.ApplyGeneratedUtilityBuff(a);
                    generated.ApplyGeneratedUtilityBuff(b);
                    var initial = generated.CaptureGeneratedUtilityBuffPresentation();
                    Equal(2, initial.Entries.Count, field + " exact component identity / reverse=" + reverse);
                    Equal(reverse ? second : first, Float32IdentityValue(initial.Entries.Single(e => e.RemainingTicks == 2), field), field + " exact first stored value");
                    Equal(reverse ? first : second, Float32IdentityValue(initial.Entries.Single(e => e.RemainingTicks == 4), field), field + " exact second stored value");
                    // Duration is intentionally outside effect identity: a strictly
                    // equal decoded value extends its own entry, never double stacks.
                    var refresh = Float32BuffData(field, reverse ? first : second, 6).Gameplay.GeneratedBuff;
                    generated.ApplyGeneratedUtilityBuff(refresh);
                    generated.ApplyGeneratedUtilityBuff(b); // shorter repeat cannot shorten
                    var refreshed = generated.CaptureGeneratedUtilityBuffPresentation();
                    Equal(2, refreshed.Entries.Count, field + " exact repeat refresh keeps two entries");
                    Equal(true, refreshed.Entries.Any(e => e.RemainingTicks == 2) && refreshed.Entries.Any(e => e.RemainingTicks == 6), field + " refresh affects only exact match and uses max duration");
                    for (int tick = 0; tick < 2; tick++) Float32BuffTick.Invoke(generated, null);
                    var survivor = generated.CaptureGeneratedUtilityBuffPresentation();
                    Equal(1, survivor.Entries.Count, field + " independent first expiry");
                    Equal(4, survivor.Entries[0].RemainingTicks, field + " exact refreshed remaining duration");
                    Equal(reverse ? first : second, Float32IdentityValue(survivor.Entries[0], field), field + " exact survivor magnitude");
                    for (int tick = 0; tick < 4; tick++) Float32BuffTick.Invoke(generated, null);
                    Equal(0, generated.CaptureGeneratedUtilityBuffPresentation().Entries.Count, field + " exact refreshed final expiry");
                });
            }
            catch (Exception error) { failures.Add(field + "/reverse=" + reverse + ": " + error); }
        }
        // Equality applies AFTER the existing normalization, including clamps and
        // neutral signed zero, not to authored decimal spelling or duration.
        WithPlayer((_, generated) => {
            generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 2, JumpBoost = 100f });
            generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 4, JumpBoost = 8f });
            var clamped = generated.CaptureGeneratedUtilityBuffPresentation();
            Equal(1, clamped.Entries.Count, "normalized identical clamp endpoint refreshes");
            Equal(8f, clamped.Entries[0].JumpBoost, "canonical normalized magnitude unchanged");
            Equal(4, clamped.Entries[0].RemainingTicks, "normalized exact repeat refresh duration");
        });
        WithPlayer((_, generated) => {
            generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 2, OreSenseRadiusTiles = 1, MovementSpeed = 0f });
            generated.ApplyGeneratedUtilityBuff(new GeneratedBuffSpec { DurationTicks = 4, OreSenseRadiusTiles = 1, MovementSpeed = -0f });
            Equal(1, generated.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "normalized signed neutral zero remains one effect");
        });
        if (failures.Count > 0) throw new InvalidOperationException(string.Join(Environment.NewLine, failures));
    }
}
