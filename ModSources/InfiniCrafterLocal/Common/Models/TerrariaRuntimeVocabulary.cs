#nullable enable
using System;
using System.IO;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>
/// Finite canonical mapping from runtime-program tokens to stable Terraria/tModLoader
/// values. These are technical one-to-one projections, not aliases and not a semantic
/// router. Unknown tokens fail closed; only exact ModType.FullName lookup is allowed; do not add loose spellings, weapon
/// families, or prose-derived fallbacks here.
/// </summary>
public static class TerrariaRuntimeVocabulary
{
    public static DamageClass ResolveDamageClass(string? value)
    {
        string exact = (value ?? "").Trim();
        DamageClass? builtin = exact switch
        {
            "default" => DamageClass.Default,
            "generic" => DamageClass.Generic,
            "melee" => DamageClass.Melee,
            "melee_no_speed" => DamageClass.MeleeNoSpeed,
            "ranged" => DamageClass.Ranged,
            "magic" => DamageClass.Magic,
            "magic_summon_hybrid" => DamageClass.MagicSummonHybrid,
            "summon" => DamageClass.Summon,
            "summon_melee_speed" => DamageClass.SummonMeleeSpeed,
            "throwing" => DamageClass.Throwing,
            _ => null,
        };
        if (builtin is not null)
            return builtin;

        // A modded class is addressed exactly as tModLoader registers ModType.FullName:
        // ModName/ClassName. No loose separators, aliases, name search, or Generic fallback.
        int slash = exact.IndexOf('/');
        bool exactFullName = slash > 0
            && slash == exact.LastIndexOf('/')
            && slash < exact.Length - 1
            && IsContentName(exact.AsSpan(0, slash))
            && IsContentName(exact.AsSpan(slash + 1));
        if (exactFullName && ModContent.TryFind<DamageClass>(exact, out DamageClass? loaded))
            return loaded;
        throw new InvalidDataException($"Unknown exact damageClass '{exact}'");
    }

    public static string CanonicalDamageClassToken(DamageClass? value)
    {
        if (value is null)
            return "";
        if (value == DamageClass.Default) return "default";
        if (value == DamageClass.Generic) return "generic";
        if (value == DamageClass.Melee) return "melee";
        if (value == DamageClass.MeleeNoSpeed) return "melee_no_speed";
        if (value == DamageClass.Ranged) return "ranged";
        if (value == DamageClass.Magic) return "magic";
        if (value == DamageClass.MagicSummonHybrid) return "magic_summon_hybrid";
        if (value == DamageClass.Summon) return "summon";
        if (value == DamageClass.SummonMeleeSpeed) return "summon_melee_speed";
        if (value == DamageClass.Throwing) return "throwing";

        string exact = (value.FullName ?? "").Trim();
        int slash = exact.IndexOf('/');
        bool exactFullName = slash > 0
            && slash == exact.LastIndexOf('/')
            && slash < exact.Length - 1
            && IsContentName(exact.AsSpan(0, slash))
            && IsContentName(exact.AsSpan(slash + 1));
        return exactFullName ? exact : "";
    }

    private static bool IsContentName(ReadOnlySpan<char> value)
    {
        if (value.Length is < 1 or > 64 || !char.IsLetter(value[0]))
            return false;
        for (int i = 1; i < value.Length; i++)
            if (!char.IsLetterOrDigit(value[i]) && value[i] != '_')
                return false;
        return true;
    }

    public static int ResolveItemUseStyle(string? value)
        => value switch
        {
            "swing" => ItemUseStyleID.Swing,
            "eat_food" => ItemUseStyleID.EatFood,
            "thrust" => ItemUseStyleID.Thrust,
            "hold_up" => ItemUseStyleID.HoldUp,
            "shoot" => ItemUseStyleID.Shoot,
            "drink_long" => ItemUseStyleID.DrinkLong,
            "drink_liquid" => ItemUseStyleID.DrinkLiquid,
            "golf_play" => ItemUseStyleID.GolfPlay,
            "hidden_animation" => ItemUseStyleID.HiddenAnimation,
            "mow_the_lawn" => ItemUseStyleID.MowTheLawn,
            "guitar" => ItemUseStyleID.Guitar,
            "rapier" => ItemUseStyleID.Rapier,
            "raise_lamp" => ItemUseStyleID.RaiseLamp,
            _ => throw new InvalidDataException($"Unknown canonical useStyle '{value}'"),
        };

    public static string CanonicalItemUseStyleToken(int value)
        => value switch
        {
            ItemUseStyleID.Swing => "swing",
            ItemUseStyleID.EatFood => "eat_food",
            ItemUseStyleID.Thrust => "thrust",
            ItemUseStyleID.HoldUp => "hold_up",
            ItemUseStyleID.Shoot => "shoot",
            ItemUseStyleID.DrinkLong => "drink_long",
            ItemUseStyleID.DrinkLiquid => "drink_liquid",
            ItemUseStyleID.GolfPlay => "golf_play",
            ItemUseStyleID.HiddenAnimation => "hidden_animation",
            ItemUseStyleID.MowTheLawn => "mow_the_lawn",
            ItemUseStyleID.Guitar => "guitar",
            ItemUseStyleID.Rapier => "rapier",
            ItemUseStyleID.RaiseLamp => "raise_lamp",
            _ => "",
        };

    public static string CanonicalAmmoCategoryToken(int value)
        => value switch
        {
            AmmoID.None => "",
            AmmoID.Arrow => "arrow",
            AmmoID.Bullet => "bullet",
            AmmoID.CandyCorn => "candy_corn",
            AmmoID.Coin => "coin",
            AmmoID.Dart => "dart",
            AmmoID.FallenStar => "fallen_star",
            AmmoID.Flare => "flare",
            AmmoID.Gel => "gel",
            AmmoID.JackOLantern => "jack_o_lantern",
            AmmoID.NailFriendly => "nail_friendly",
            AmmoID.Rocket => "rocket",
            AmmoID.Snowball => "snowball",
            AmmoID.Solution => "solution",
            AmmoID.Stake => "stake",
            AmmoID.StyngerBolt => "stynger_bolt",
            _ => "",
        };

    public static int ResolveAmmoCategory(string? value)
        => value switch
        {
            "" or null => AmmoID.None,
            "arrow" => AmmoID.Arrow,
            "bullet" => AmmoID.Bullet,
            "candy_corn" => AmmoID.CandyCorn,
            "coin" => AmmoID.Coin,
            "dart" => AmmoID.Dart,
            "fallen_star" => AmmoID.FallenStar,
            "flare" => AmmoID.Flare,
            "gel" => AmmoID.Gel,
            "jack_o_lantern" => AmmoID.JackOLantern,
            "nail_friendly" => AmmoID.NailFriendly,
            "rocket" => AmmoID.Rocket,
            "snowball" => AmmoID.Snowball,
            "solution" => AmmoID.Solution,
            "stake" => AmmoID.Stake,
            "stynger_bolt" => AmmoID.StyngerBolt,
            _ => throw new InvalidDataException($"Unknown canonical ammoCategory '{value}'"),
        };
}
