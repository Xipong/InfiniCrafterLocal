#nullable enable
using System.Collections.Generic;
using System.Globalization;
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Common.UI;

internal static class PlayerEffectDescription
{
    internal static string WithCondition(string text, string? condition, CultureInfo culture)
        => condition == "stationary" ? text + (culture.TwoLetterISOLanguageName == "ru"
            ? " (в покое, без использования предмета)" : " (while stationary, without using an item)") : text;

    internal static string Build(PlayerEffectSpec effect, CultureInfo culture)
    {
        bool ru = culture.TwoLetterISOLanguageName == "ru";
        var lines = new List<string>();
        string Number(double value) => value.ToString("0.##", culture);
        if ((effect.FishingPowerPoints ?? 0) != 0) lines.Add((ru ? "Сила рыбалки: " : "Fishing power: ") + Number((effect.FishingPowerPoints ?? 0) / 1d) + (ru ? " очков" : " points"));
        if (effect.PreventLineBreak == true) lines.Add(ru ? "Защита от обрыва лески" : "Prevent line breaks");
        if (effect.AllowLavaFishing == true) lines.Add(ru ? "Рыбалка в лаве" : "Fishing in lava");
        if (effect.RevealHookedCatch == true) lines.Add(ru ? "Показ улова" : "Reveal hooked catch");
        if ((effect.ExtraCrateChancePercent ?? 0) != 0) lines.Add((ru ? "Дополнительный шанс ящика: " : "Additional crate roll: ") + Number((effect.ExtraCrateChancePercent ?? 0) / 1d) + (ru ? " %" : " %"));
        if ((effect.ItemPickupRangePx ?? 0) != 0) lines.Add((ru ? "Дальность подбора предметов: " : "Item pickup range: ") + Number((effect.ItemPickupRangePx ?? 0) / 16d) + (ru ? " блоков" : " blocks"));
        if ((effect.HeartPickupRangePx ?? 0) != 0) lines.Add((ru ? "Дальность подбора сердец: " : "Heart pickup range: ") + Number((effect.HeartPickupRangePx ?? 0) / 16d) + (ru ? " блоков" : " blocks"));
        if ((effect.ManaPickupRangePx ?? 0) != 0) lines.Add((ru ? "Дальность подбора маны: " : "Mana pickup range: ") + Number((effect.ManaPickupRangePx ?? 0) / 16d) + (ru ? " блоков" : " blocks"));
        if ((effect.CoinPickupRangePx ?? 0) != 0) lines.Add((ru ? "Дальность подбора монет: " : "Coin pickup range: ") + Number((effect.CoinPickupRangePx ?? 0) / 16d) + (ru ? " блоков" : " blocks"));
        if (effect.HighlightDanger == true) lines.Add(ru ? "Подсветка опасностей" : "Danger highlighting");
        if (effect.HighlightCreatures == true) lines.Add(ru ? "Подсветка существ" : "Creature highlighting");
        if (effect.NightVision == true) lines.Add(ru ? "Ночное зрение" : "Night vision");
        if ((effect.HealingPotionCooldownReductionPercent ?? 0) != 0) lines.Add((ru ? "Сокращение базового КД лечебного зелья: " : "Healing potion base cooldown reduction: ") + Number((effect.HealingPotionCooldownReductionPercent ?? 0) / 1d) + (ru ? " %" : " %"));
        if ((effect.HealingPotionCooldownReductionTicks ?? 0) != 0) lines.Add((ru ? "Сокращение базового КД лечебного зелья: " : "Healing potion base cooldown reduction: ") + Number((effect.HealingPotionCooldownReductionTicks ?? 0) / 60d) + (ru ? " с" : " s"));
        if ((effect.HealingPotionCooldownOnHitReductionTicks ?? 0) != 0) lines.Add((ru ? "Сокращение оставшегося КД лечения за удар: " : "Remaining healing cooldown removed per hit: ") + Number((effect.HealingPotionCooldownOnHitReductionTicks ?? 0) / 60d) + (ru ? " с" : " s"));
        if ((effect.AutoManaPotionBelowPercent ?? 0) != 0) lines.Add((ru ? "Маназелье при запасе маны ниже: " : "Use mana potion below: ") + Number((effect.AutoManaPotionBelowPercent ?? 0) / 1d) + (ru ? " %" : " %"));
        if ((effect.HurtInvulnerabilityBonusTicks ?? 0) != 0) lines.Add((ru ? "Дополнительная неуязвимость после урона: " : "Extra immunity after hurt: ") + Number((effect.HurtInvulnerabilityBonusTicks ?? 0) / 60d) + (ru ? " с" : " s"));
        if (effect.Condition == "stationary" && lines.Count > 0) lines.Insert(0, ru ? "В покое, без использования предмета:" : "While stationary, without using an item:");
        return string.Join("; ", lines);
    }
}
