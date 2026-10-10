#nullable enable
using InfiniCrafterLocal.Common.Models;
using System;
using Terraria;
using Terraria.DataStructures;

namespace InfiniCrafterLocal.Common.Runtime;

// Immutable event-time values, separate from damageDone (a post-defense hit)
// and from the authored source entity. A terminal parent need not remain active.
internal readonly record struct RuntimeParentCombat(int Damage, float Knockback, bool HasProjectile)
{
    internal static RuntimeParentCombat Capture(IEntitySource source, Player owner)
        => source is EntitySource_Parent { Entity: Projectile projectile }
            && source.GetType() == typeof(EntitySource_Parent)
            && projectile.owner == owner.whoAmI
            ? new RuntimeParentCombat(projectile.damage, projectile.knockBack, true)
            : default;
}

internal static class RuntimeChildCombat
{
    internal static bool TryResolve(
        string? damageBasis, string? knockbackBasis, float damageMultiplier,
        RuntimeParentCombat parent, out int? damageOverride, out float? knockbackOverride)
    {
        damageOverride = null;
        knockbackOverride = null;
        // Null is only the old saved-wire meaning. Fresh Author must select both.
        if (damageBasis is not (null or RuntimeChildCombatBasis.AuthoredChild or RuntimeChildCombatBasis.LiveParent)
            || knockbackBasis is not (null or RuntimeChildCombatBasis.AuthoredChild or RuntimeChildCombatBasis.LiveParent)
            || !float.IsFinite(damageMultiplier) || damageMultiplier < 0f || damageMultiplier > 10f)
            return false;
        if ((damageBasis == RuntimeChildCombatBasis.LiveParent || knockbackBasis == RuntimeChildCombatBasis.LiveParent)
            && !parent.HasProjectile)
            return false;
        if (damageBasis == RuntimeChildCombatBasis.LiveParent)
        {
            // Resolve the selected final damage once. Never reapply class/player
            // modifiers and never substitute authored damage when it is zero.
            double scaled = Math.Round(parent.Damage * (double)damageMultiplier);
            if (parent.Damage < 0 || scaled > int.MaxValue)
                return false;
            damageOverride = (int)scaled;
        }
        if (knockbackBasis == RuntimeChildCombatBasis.LiveParent)
        {
            if (!float.IsFinite(parent.Knockback) || parent.Knockback < 0f)
                return false;
            knockbackOverride = parent.Knockback;
        }
        return true;
    }
}
