using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Players;
using InfiniCrafterLocal.Common.UI;
using InfiniCrafterLocal.Content.Items;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static void GeneratedBuffLongAndPermanentLifetimes()
    {
        using var state = new SwarmRuntimeScope();
        Equal(false, new GeneratedBuffSpec().HasAnyEffect, "default neutral DTO remains inactive");
        var boundary = Float32BuffData("lifeRegen", 4f, int.MaxValue - 1);
        Equal(int.MaxValue - 1, boundary.Gameplay.GeneratedBuff.DurationTicks, "strict reader accepts full finite Int32 storage range");
        foreach (string invalid in new[] { "missing", "negative", "overflow", "null", "string" })
        {
            var document = JsonNode.Parse(boundary.ToNetworkJson())!.AsObject();
            var buff = document["gameplay"]!["generatedBuff"]!.AsObject();
            if (invalid == "missing") buff.Remove("durationTicks");
            else if (invalid == "negative") buff["durationTicks"] = -1;
            else if (invalid == "overflow") buff["durationTicks"] = int.MaxValue;
            else if (invalid == "null") buff["durationTicks"] = null;
            else buff["durationTicks"] = "0";
            Equal(true, GeneratedItemData.FromJson(document.ToJsonString()) is null,
                "strict reader rejects " + invalid + " duration instead of inventing permanence");
        }
        foreach (int duration in new[] { 45 * 60 * 60, 0 })
        WithPlayer((player, owner) =>
        {
            PrepareMobilityConsumptionPlayer(player);
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            var data = Float32BuffData("lifeRegen", 4f, duration);
            Equal(duration, data.Gameplay.GeneratedBuff.DurationTicks, "strict item reader preserves authored duration");
            Float32BuffActivate(player, data);
            int expectedTicks = duration == 0 ? int.MaxValue : duration;
            Equal(expectedTicks, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Single().RemainingTicks,
                "real item use activates the long or permanent contribution");
            Float32BuffTick.Invoke(owner, null); Float32BuffTick.Invoke(owner, null);
            if (duration > 0) expectedTicks -= 2;
            Equal(expectedTicks, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Single().RemainingTicks,
                "finite timer counts down and permanent timer never counts down");
            Float32BuffActivate(player, Float32BuffData("lifeRegen", 4f, 60));
            Equal(1, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Count, "short refresh does not stack the same effect");
            Equal(expectedTicks, owner.CaptureGeneratedUtilityBuffPresentation().Entries.Single().RemainingTicks,
                "short refresh cannot shorten long or permanent lifetime");

            var receiver = NativeDtoBindPlayer(new Player { whoAmI = 1, active = true });
            using var stream = new MemoryStream(ExhaustionSnapshot(owner));
            var reader = new BinaryReader(stream);
            reader.ReadByte();
            typeof(InfiniCraftPlayer).GetMethod("ReadGeneratedBuffState", MobilityConsumptionFlags)!.Invoke(receiver, new object[] { reader });
            Equal(stream.Length, stream.Position, "real utility codec consumes current snapshot exactly");
            Equal(expectedTicks, receiver.CaptureGeneratedUtilityBuffPresentation().Entries.Single().RemainingTicks,
                "network roundtrip preserves full long or permanent lifetime");
            Float32BuffTick.Invoke(receiver, null);
            Equal(duration == 0 ? int.MaxValue : expectedTicks - 1,
                receiver.CaptureGeneratedUtilityBuffPresentation().Entries.Single().RemainingTicks,
                "received contribution uses the same finite or permanent clock");
            receiver.Player.dead = true; receiver.UpdateDead();
            Equal(0, receiver.CaptureGeneratedUtilityBuffPresentation().Entries.Count,
                "network roundtrip preserves initial long/permanent death policy");

            var rows = GeneratedUtilityBuffStatusView.Build(owner.CaptureGeneratedUtilityBuffPresentation(), CultureInfo.InvariantCulture);
            Equal(duration == 0, rows.Any(row => row.Tooltip.Contains("∞", StringComparison.Ordinal)),
                "live status honestly distinguishes permanent from long finite duration");
        });
    }

    private static void GeneratedBuffDurationPresentation()
    {
        using var state = new SwarmRuntimeScope();
        WithForgePresentationLanguages(locale =>
        {
            foreach (int duration in new[] { 45 * 60 * 60, 0 })
            {
                var data = Float32BuffData("lifeRegen", 4f, duration);
                var item = AttachItem(new GeneratedItem(), new Item { type = ItemID.Wood, stack = 1 }, data);
                typeof(ModType).GetProperty("Mod", TestInstance)!.SetValue(item, new TooltipProbeMod());
                var lines = new List<TooltipLine>();
                item.ModifyRuntimeTooltips(lines, expanded: true);
                string text = lines.Single(row => row.Name == "InfiniLifeRegenPrimary").Text;
                Equal(duration == 0, text.Contains("∞", StringComparison.Ordinal),
                    locale + " actual item tooltip distinguishes permanent duration");
                if (duration > 0) Equal(true, text.Contains("2700", StringComparison.Ordinal),
                    locale + " actual item tooltip does not truncate forty-five minutes");
            }
            var value = new GeneratedUtilityBuffValues(int.MaxValue - 1, 1f, 0f, "", 0, 0f, 0f, 0, 4);
            var presentation = new GeneratedUtilityBuffPresentation(value, new[] { value });
            string tooltip = GeneratedUtilityBuffStatusView.Build(presentation, CultureInfo.InvariantCulture).Single().Tooltip;
            Equal(true, tooltip.Contains("35791395", StringComparison.Ordinal), "largest finite status duration stays positive without integer overflow");
            Equal(false, tooltip.Contains("∞", StringComparison.Ordinal), "largest finite duration is not confused with permanent sentinel");
        });
    }
}
