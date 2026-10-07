#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using Microsoft.Xna.Framework;
using Terraria.ID;

namespace InfiniCrafterLocal.Common.UI;

// Immutable copies of existing live fields; no authored DTO, recipe or gameplay owner.
internal readonly record struct GeneratedUtilityBuffValues(
    int RemainingTicks, float MiningSpeedMultiplier, float EmitLightStrength,
    string LightColorName, int OreSenseRadiusTiles, float MovementSpeed,
    float JumpBoost, int ManaRegen, int LifeRegen);

internal sealed record GeneratedUtilityBuffPresentation(
    GeneratedUtilityBuffValues Current, IReadOnlyList<GeneratedUtilityBuffValues> Entries);

internal enum GeneratedUtilityBuffField
{
    MiningSpeedMultiplier, EmitLightStrength, OreSenseRadiusTiles,
    MovementSpeed, JumpBoost, ManaRegen, LifeRegen,
}

internal sealed record GeneratedUtilityBuffStatus(
    GeneratedUtilityBuffField Field, int IconBuffType, string Label,
    int RemainingTicks, string Tooltip);

/// <summary>
/// Finite direct-field UI mapping only. Buff IDs are texture references, never
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
        return statuses.AsReadOnly();
    }

    private static bool IsActive(GeneratedUtilityBuffValues value, GeneratedUtilityBuffField field) => field switch
    {
        GeneratedUtilityBuffField.MiningSpeedMultiplier => float.IsFinite(value.MiningSpeedMultiplier) && value.MiningSpeedMultiplier != 1f,
        GeneratedUtilityBuffField.EmitLightStrength => float.IsFinite(value.EmitLightStrength) && value.EmitLightStrength > 0f,
        GeneratedUtilityBuffField.OreSenseRadiusTiles => value.OreSenseRadiusTiles > 0,
        GeneratedUtilityBuffField.MovementSpeed => float.IsFinite(value.MovementSpeed) && value.MovementSpeed != 0f,
        GeneratedUtilityBuffField.JumpBoost => float.IsFinite(value.JumpBoost) && value.JumpBoost > 0f,
        GeneratedUtilityBuffField.ManaRegen => value.ManaRegen > 0,
        GeneratedUtilityBuffField.LifeRegen => value.LifeRegen > 0,
        _ => false,
    };

    private static string Effect(GeneratedUtilityBuffValues value, GeneratedUtilityBuffField field, CultureInfo culture)
    {
        bool russian = culture.TwoLetterISOLanguageName == "ru";
        string Number(float number) => float.IsFinite(number) ? number.ToString("R", culture) : "unavailable";
        string Signed(float number) => (number >= 0f ? "+" : "") + Number(number);
        return field switch
        {
            GeneratedUtilityBuffField.MiningSpeedMultiplier => (russian ? "множитель скорости добычи ×" : "pickSpeed divisor ×") + Number(value.MiningSpeedMultiplier),
            GeneratedUtilityBuffField.EmitLightStrength => Number(value.EmitLightStrength) + (russian ? " — интенсивность света (" : " RGB coefficient (") + value.LightColorName + ")",
            // Existing runtime sets findTreasure, not an enforced authored radius.
            GeneratedUtilityBuffField.OreSenseRadiusTiles => russian ? (value.OreSenseRadiusTiles > 0 ? "обнаружение сокровищ включено" : "обнаружение сокровищ выключено") : "findTreasure = " + (value.OreSenseRadiusTiles > 0 ? "true" : "false"),
            GeneratedUtilityBuffField.MovementSpeed => Signed(value.MovementSpeed) + (russian ? " к коэффициенту скорости передвижения" : " moveSpeed factor"),
            GeneratedUtilityBuffField.JumpBoost => Signed(value.JumpBoost) + (russian ? " пикс./тик к скорости прыжка" : " px/world tick (jumpSpeedBoost)"),
            GeneratedUtilityBuffField.ManaRegen => "+" + value.ManaRegen.ToString(culture) + (russian ? " к регенерации маны" : " manaRegenBonus points"),
            GeneratedUtilityBuffField.LifeRegen => "+" + value.LifeRegen.ToString(culture) + (russian ? " к регенерации здоровья" : " lifeRegen points"),
            _ => "",
        };
    }

    private static string Duration(int ticks, CultureInfo culture)
        => ticks.ToString(culture) + (culture.TwoLetterISOLanguageName == "ru" ? " тиков (" : " ticks (")
            + (ticks / 60d).ToString("0.###", culture) + (culture.TwoLetterISOLanguageName == "ru" ? " с)" : " s)");

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
