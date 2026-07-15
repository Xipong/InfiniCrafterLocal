#nullable enable
using System;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Models;

/// <summary>
/// Canonical GeneratedItem/GeneratedProjectile damage-class boundary.
/// Both item and projectile runtime must resolve the same authored exact value here;
/// do not add separate switches in consumers.
/// </summary>
public static class GeneratedDamageClassPolicy
{
    public static DamageClass Resolve(string? raw)
    {
        string value = (raw ?? "").Trim();
        string norm = value.ToLowerInvariant().Replace('-', '_').Replace(' ', '_');
        return norm switch
        {
            "melee" => DamageClass.Melee,
            "melee_no_speed" => DamageClass.MeleeNoSpeed,
            "ranged" => DamageClass.Ranged,
            "magic" => DamageClass.Magic,
            "summon" => DamageClass.Summon,
            "summon_melee_speed" => DamageClass.SummonMeleeSpeed,
            "throwing" or "rogue" => ResolveModded(value) ?? DamageClass.Generic,
            "generic" or "" => DamageClass.Generic,
            _ => ResolveModded(value) ?? DamageClass.Generic,
        };
    }

    private static DamageClass? ResolveModded(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw))
            return null;
        string value = raw.Trim();
        try
        {
            if (ModContent.TryFind<DamageClass>(value, out DamageClass? direct))
                return direct;
        }
        catch
        {
            // A missing optional mod/class is a normal clean-start fallback to Generic.
        }

        foreach (string separator in new[] { "/", ":", "." })
        {
            int index = value.IndexOf(separator, StringComparison.Ordinal);
            if (index <= 0 || index >= value.Length - separator.Length)
                continue;
            string modName = value[..index];
            string className = value[(index + separator.Length)..];
            try
            {
                if (ModLoader.TryGetMod(modName, out Mod? mod)
                    && mod.TryFind<DamageClass>(className, out DamageClass? resolved))
                    return resolved;
            }
            catch
            {
                // Keep optional-mod lookup inert when the target class is unavailable.
            }
        }
        return null;
    }
}
