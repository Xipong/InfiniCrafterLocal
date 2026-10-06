#nullable enable
using System;
using System.Reflection;
using InfiniCrafterLocal.Common;
using InfiniCrafterLocal.Common.Services;
using InfiniCrafterLocal.Content.Projectiles;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Systems;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Content.Items;

public partial class GeneratedItem
{

    // Only these fields are temporarily projected. Source identity/crit/armor,
    // accepted DTOs, prefix token, timing, ammo and item ownership stay untouched.
    internal readonly record struct RootCombatTriple(int Damage, float Knockback, DamageClass Class)
    {
        internal static RootCombatTriple Capture(Item item) => new(item.damage, item.knockBack, item.DamageType);
        internal void Apply(Item item) { item.damage = Damage; item.knockBack = Knockback; item.DamageType = Class; }
    }

    private delegate bool NativePrefixStats(Item item, int prefix, out float damage, out float knockback,
        out float speed, out float size, out float shootSpeed, out float mana, out int crit);
    private static readonly NativePrefixStats ReadNativePrefixStats = BindNativePrefixStats();
    private static NativePrefixStats BindNativePrefixStats()
    {
        Type floatRef = typeof(float).MakeByRefType();
        MethodInfo? method = typeof(Item).GetMethod("TryGetPrefixStatMultipliersForItem", BindingFlags.NonPublic | BindingFlags.Instance,
            null, new[] { typeof(int), floatRef, floatRef, floatRef, floatRef, floatRef, floatRef, typeof(int).MakeByRefType() }, null);
        if (method is null || method.ReturnType != typeof(bool))
            throw new InvalidOperationException("Generated root combat: native prefix-stat signature mismatch");
        return method.CreateDelegate<NativePrefixStats>();
    }
    private RootCombatTriple PrefixAppliedRootCombatBase(RootCombatTriple authored)
    {
        int prefix = Item.prefix; // only a prefix native already applied to this exact Item
        if (prefix == 0) return authored;
        // The native getter validates BEFORE-prefix fields, not already-applied
        // ones (small damage/mana/timing values can otherwise look unchanged).
        // Borrow the retained exact base; never replay Prefix or mutate its owner.
        RootCombatTriple before = RootCombatTriple.Capture(Item);
        NativePrefixBase current = NativePrefixBase.Capture(Item);
        try {
            RootCombatTriple source = GeneratedRootCombatSystem.SourceContext(Item);
            if (_nativePrefixBase is not NativePrefixBase baseline)
                throw new InvalidOperationException("Generated root combat: unprefixed native context missing");
            baseline.Restore(Item);
            Item.DamageType = source.Class;
            if (!ReadNativePrefixStats(Item, prefix, out float damage, out float kb, out _, out _, out _, out _, out _))
                throw new InvalidOperationException("Generated root combat: current applied native prefix rejected its stat context");
            return authored with { Damage = (int)Math.Round((float)authored.Damage * damage), Knockback = authored.Knockback * kb };
        }
        finally { current.Restore(Item); Item.prefix = prefix; before.Apply(Item); }
    }

    internal bool TryGetSelectedRootCombat(Player player, out RuntimeEntitySpec? entity, out RootCombatTriple triple)
    {
        RuntimeBindingSpec? binding = ActiveUseBinding(player); // native selector is already resolved here
        entity = binding?.UsePolicy.Action.Kind == RuntimeBindingAction.SpawnEntity
            ? Data.RuntimeProgram.TryGetEntity(binding.UsePolicy.Action.TargetId) : null;
        triple = default;
        if (entity is null || !CanSpawnRoot(player, entity)) return false;
        triple = RootCombatBase(entity);
        return true;
    }

    // Root depth is literally zero and its allowance is RootBindingSpawnCapacity.
    // Reuse the existing canonical owner counter, not a second actor/cache owner.
    private bool CanSpawnRoot(Player player, RuntimeEntitySpec entity)
        => player.active && InfiniRuntimeAuthority.ShouldRunLocalPlayerAction(player)
            && entity.IsProjectileEntity && entity.Spawn.Enabled
            && Data.RuntimeProgram.Limits.MaxChildDepth >= 0
            && GeneratedProjectile.CountActiveGeneratedProjectiles(player.whoAmI)
                < InfiniRuntimeLimits.MaxRuntimeActiveProjectilesPerOwner;

    private RootCombatTriple RootCombatBase(RuntimeEntitySpec entity)
        => PrefixAppliedRootCombatBase(new RootCombatTriple(entity.Damage.Enabled ? entity.Damage.Damage : 0,
            entity.Damage.Knockback, TerrariaRuntimeVocabulary.ResolveDamageClass(entity.Damage.DamageClass)));

    // Call at the start of GeneratedItem.Shoot, before its actual spawn can run
    // Projectile.ApplyStatsFromSource. The source still owns body crit/armor stats.
    private void RestoreRootCombatSource(Player player)
        => GeneratedRootCombatSystem.RestoreSource(player, Item);

    // Hold has no native shooting arguments. The caller must first establish a
    // missing hold root and pass the existing root-spawn preflight; never per-frame.
    private (int Damage, float Knockback) CalculateHoldRootCombat(Player player, RuntimeEntitySpec entity)
    {
        RootCombatTriple before = RootCombatTriple.Capture(Item);
        try {
            RootCombatBase(entity).Apply(Item);
            int damage = player.GetWeaponDamage(Item);
            float knockback = player.GetWeaponKnockback(Item, Item.knockBack);
            return (entity.Damage.Enabled ? damage : 0, knockback);
        }
        finally { before.Apply(Item); }
    }
}
