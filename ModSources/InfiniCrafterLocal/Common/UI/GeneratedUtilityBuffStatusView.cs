#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Text;
using Microsoft.Xna.Framework;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.UI;

// Immutable copies of existing live fields; no authored DTO, recipe or gameplay owner.
internal readonly record struct GeneratedUtilityBuffValues(
    int RemainingTicks, float MiningSpeedMultiplier, float EmitLightStrength,
    string LightColorName, int OreSenseRadiusTiles, float MovementSpeed,
    float JumpBoost, int ManaRegen, int LifeRegen, int Defense = 0, float AttackSpeed = 0,
    float CritChance = 0, IReadOnlyDictionary<string, float>? DamageBonuses = null, global::InfiniCrafterLocal.Common.Models.PlayerEffectSpec? PlayerEffect = null);

internal sealed record GeneratedUtilityBuffPresentation(
    GeneratedUtilityBuffValues Current, IReadOnlyList<GeneratedUtilityBuffValues> Entries);

internal enum GeneratedUtilityBuffField
{
    MiningSpeedMultiplier, EmitLightStrength, OreSenseRadiusTiles,
    MovementSpeed, JumpBoost, ManaRegen, LifeRegen, Defense, AttackSpeed, CritChance, Damage, PlayerEffect,
}

internal sealed record GeneratedUtilityBuffStatus(
    GeneratedUtilityBuffField Field, int IconBuffType, string Label,
    int RemainingTicks, string Tooltip);

/// <summary>
/// Direct-field UI mapping only. Buff IDs are texture references, never
/// Player.buffType entries. Current values come from the canonical aggregate;
/// presentation must not recalculate its clamp/product/sum rules.
/// </summary>
internal static class GeneratedUtilityBuffStatusView
{
    private static readonly (GeneratedUtilityBuffField Field, int Icon, string Label, string RussianLabel)[] Map = {
        (GeneratedUtilityBuffField.MiningSpeedMultiplier, BuffID.Mining, "Generated mining speed", "Скорость добычи"),
        (GeneratedUtilityBuffField.EmitLightStrength, BuffID.Shine, "Generated light", "Свет"),
        (GeneratedUtilityBuffField.OreSenseRadiusTiles, BuffID.Spelunker, "Generated ore sense", "Обнаружение руды"),
        (GeneratedUtilityBuffField.MovementSpeed, BuffID.Swiftness, "Generated movement speed", "Скорость передвижения"),
        (GeneratedUtilityBuffField.JumpBoost, BuffID.Featherfall, "Generated jump boost", "Усиление прыжка"),
        (GeneratedUtilityBuffField.ManaRegen, BuffID.ManaRegeneration, "Generated mana regeneration", "Восстановление маны"),
        (GeneratedUtilityBuffField.LifeRegen, BuffID.Regeneration, "Generated life regeneration", "Восстановление здоровья"),
        (GeneratedUtilityBuffField.Defense, BuffID.Ironskin, "Generated defense", "Защита"),
        (GeneratedUtilityBuffField.AttackSpeed, BuffID.Tipsy, "Generated attack speed", "Скорость атаки"),
        (GeneratedUtilityBuffField.CritChance, BuffID.Rage, "Generated critical chance", "Шанс критического удара"),
        (GeneratedUtilityBuffField.Damage, BuffID.Wrath, "Generated damage", "Урон"),
    };

    internal static IReadOnlyList<GeneratedUtilityBuffStatus> Build(
        GeneratedUtilityBuffPresentation snapshot, CultureInfo culture)
    {
        bool russian = culture.TwoLetterISOLanguageName == "ru";
        var statuses = new List<GeneratedUtilityBuffStatus>(Map.Length);
        foreach (var mapping in Map)
        {
            int remaining = 0;
            var contributions = new StringBuilder();
            foreach (GeneratedUtilityBuffValues entry in snapshot.Entries)
            {
                if (entry.RemainingTicks <= 0 || !IsActive(entry, mapping.Field)) continue;
                remaining = Math.Max(remaining, entry.RemainingTicks);
                contributions.Append('\n').Append(russian ? "Активный модификатор: " : "Active contribution: ")
                    .Append(Effect(entry, mapping.Field, culture)).Append(" — ")
                    .Append(Duration(entry.RemainingTicks, culture));
            }
            if (remaining <= 0) continue;
            string tooltip = (russian ? "Действующий эффект: " : "Current generated effect: ") + Effect(snapshot.Current, mapping.Field, culture)
                + (russian ? "\nДо окончания последнего модификатора: " : "\nRemaining until last contribution expires: ") + Duration(remaining, culture)
                + contributions;
            statuses.Add(new(mapping.Field, mapping.Icon, russian ? mapping.RussianLabel : mapping.Label, remaining, tooltip));
        }
        foreach (var entry in snapshot.Entries)
            if (entry.RemainingTicks > 0 && entry.PlayerEffect is { HasEffect: true } effect)
                statuses.Add(new(GeneratedUtilityBuffField.PlayerEffect, BuffID.WellFed,
                    russian ? "Модификатор игрока" : "Player modifier", entry.RemainingTicks,
                    PlayerEffectDescription.Build(effect, culture) + " — " + Duration(entry.RemainingTicks, culture)));
        return statuses.AsReadOnly();
    }

    private static bool IsActive(GeneratedUtilityBuffValues value, GeneratedUtilityBuffField field) => field switch
    {
        GeneratedUtilityBuffField.MiningSpeedMultiplier => float.IsFinite(value.MiningSpeedMultiplier) && value.MiningSpeedMultiplier != 1f,
        GeneratedUtilityBuffField.EmitLightStrength => float.IsFinite(value.EmitLightStrength) && value.EmitLightStrength > 0f,
        GeneratedUtilityBuffField.OreSenseRadiusTiles => value.OreSenseRadiusTiles > 0,
        GeneratedUtilityBuffField.MovementSpeed => float.IsFinite(value.MovementSpeed) && value.MovementSpeed != 0f,
        GeneratedUtilityBuffField.JumpBoost => float.IsFinite(value.JumpBoost) && value.JumpBoost != 0f,
        GeneratedUtilityBuffField.ManaRegen => value.ManaRegen != 0,
        GeneratedUtilityBuffField.LifeRegen => value.LifeRegen != 0,
        GeneratedUtilityBuffField.Defense => value.Defense != 0,
        GeneratedUtilityBuffField.AttackSpeed => value.AttackSpeed != 0,
        GeneratedUtilityBuffField.CritChance => value.CritChance != 0,
        GeneratedUtilityBuffField.Damage => value.DamageBonuses?.Any(pair => pair.Value != 0) == true,
        _ => false,
    };

    private static string Effect(GeneratedUtilityBuffValues value, GeneratedUtilityBuffField field, CultureInfo culture)
    {
        bool russian = culture.TwoLetterISOLanguageName == "ru";
        string Number(float number) => float.IsFinite(number) ? GeneratedStatusTooltipView.Number(number, culture) : "unavailable";
        string Signed(float number) => (number >= 0f ? "+" : "") + Number(number);
        return field switch
        {
            GeneratedUtilityBuffField.MiningSpeedMultiplier => (russian ? "множитель скорости добычи ×" : "pickSpeed divisor ×") + Number(value.MiningSpeedMultiplier),
            GeneratedUtilityBuffField.EmitLightStrength => Number(value.EmitLightStrength) + (russian ? " — интенсивность света (" : " RGB coefficient (") + value.LightColorName + ")",
            // Existing runtime sets findTreasure, not an enforced authored radius.
            GeneratedUtilityBuffField.OreSenseRadiusTiles => russian ? (value.OreSenseRadiusTiles > 0 ? "обнаружение сокровищ включено" : "обнаружение сокровищ выключено") : "findTreasure = " + (value.OreSenseRadiusTiles > 0 ? "true" : "false"),
            GeneratedUtilityBuffField.MovementSpeed => Signed(value.MovementSpeed) + (russian ? " к коэффициенту скорости передвижения" : " moveSpeed factor"),
            GeneratedUtilityBuffField.JumpBoost => Signed(PlayerDisplayUnits.BlocksPerSecond(value.JumpBoost)) + (russian ? " блоков/с к скорости прыжка" : " blocks/s jump-speed bonus"),
            GeneratedUtilityBuffField.ManaRegen => Signed(value.ManaRegen) + (russian ? " единиц manaRegenBonus" : " manaRegenBonus points"),
            GeneratedUtilityBuffField.LifeRegen => Signed(value.LifeRegen / 2f) + (russian ? " ОЗ/с — вклад в регенерацию" : " HP/s contribution"),
            GeneratedUtilityBuffField.Defense => Signed(value.Defense) + (russian ? " защиты" : " defense"),
            GeneratedUtilityBuffField.AttackSpeed => Signed(value.AttackSpeed) + (russian ? "% скорости атаки" : "% attack speed"),
            GeneratedUtilityBuffField.CritChance => Signed(value.CritChance) + (russian ? " п.п. шанса критического удара" : " percentage points critical chance"),
            GeneratedUtilityBuffField.Damage => string.Join(", ", (value.DamageBonuses ?? new Dictionary<string, float>())
                .Where(pair => pair.Value != 0).OrderBy(pair => pair.Key, StringComparer.Ordinal)
                .Select(pair => pair.Key + " " + Signed(pair.Value) + "%")),
            _ => "",
        };
    }

    private static string Duration(int ticks, CultureInfo culture)
    {
        if (ticks == int.MaxValue) return "∞";
        return GeneratedStatusTooltipView.CountdownSeconds(ticks, culture)
            + (culture.TwoLetterISOLanguageName == "ru" ? " с" : " s");
    }

    // Native HUD uses slot indices, but the equipment grid compacts nonzero slots.
    internal static int GetAppendIndex(IReadOnlyList<int> buffTypes, bool inventory)
    {
        int append = 0;
        for (int index = 0; index < buffTypes.Count; index++)
        {
            if (inventory) { if (buffTypes[index] != 0) append++; }
            else if (buffTypes[index] > 0) append = index + 1;
        }
        return append;
    }

    // Exact installed Main.DrawInterface_Resources_Buffs / DrawInventory geometry.
    // The enclosing UI layer already adjusts screen/mouse coordinates for UI scale.
    internal static Point IconPosition(int index, bool inventory, int screenWidth,
        int screenHeight, int inventoryTopOffset, int mapStyle)
    {
        if (!inventory) return new Point(32 + index % 11 * 38, 76 + index / 11 * 50);
        int rows = 3;
        int mapOffset = mapStyle == 1 ? 260 : 0;
        if (screenHeight > 630 + mapOffset) rows++;
        if (screenHeight > 680 + mapOffset) rows++;
        if (screenHeight > 730 + mapOffset) rows++;
        return new Point(screenWidth - 84 - index / rows * 46,
            inventoryTopOffset + 421 + index % rows * 46);
    }
}
