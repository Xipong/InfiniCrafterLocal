#nullable enable
using System;
using System.IO;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;
using Terraria.ModLoader.IO;

namespace InfiniCrafterLocal.Content.Items;

public partial class GeneratedItem
{
    private const string NativePrefixSaveKey = "infiniNativePrefix";
    private int? _pendingNativePrefix;
    private NativePrefixBase? _nativePrefixBase;
    private bool _hasNativePrefixDefaults;
    private int _nativeDefaultCrit;
    private int _nativeDefaultReuseDelay;
    private int _nativeDefaultAnimationCompensation;
    private static readonly FieldInfo NativeAnimationCompensation = typeof(Item).GetField(
        "currentUseAnimationCompensation", BindingFlags.Instance | BindingFlags.NonPublic)
        ?? throw new MissingFieldException(typeof(Item).FullName, "currentUseAnimationCompensation");

    // Instance-only technical state. Neither a prefix nor these materialized
    // fields belong to GeneratedItemData/the canonical definition or craft input.
    private readonly record struct NativePrefixBase(
        int Damage, float Knockback, int Crit, int UseTime, int UseAnimation,
        int ReuseDelay, float ShootSpeed, float Scale, int Value, int Rarity, int Mana, int AnimationCompensation)
    {
        public static NativePrefixBase Capture(Item item) => new(
            item.damage, item.knockBack, item.crit, item.useTime, item.useAnimation,
            item.reuseDelay, item.shootSpeed, item.scale, item.value, item.rare, item.mana,
            (int)NativeAnimationCompensation.GetValue(item)!);

        public void Restore(Item item)
        {
            item.prefix = 0;
            item.damage = Damage; item.knockBack = Knockback; item.crit = Crit;
            item.useTime = UseTime; item.useAnimation = UseAnimation; item.reuseDelay = ReuseDelay;
            item.shootSpeed = ShootSpeed; item.scale = Scale; item.value = Value;
            item.rare = Rarity; item.mana = Mana;
            // Prefix first undoes this native adjustment. Restoring animation
            // without its paired state changes the next application by a tick.
            NativeAnimationCompensation.SetValue(item, AnimationCompensation);
        }
    }

    private int InstanceNativePrefix => _pendingNativePrefix ?? Item.prefix;

    // Call only after native ResetStats/SetDefaults has supplied unprefixed fields.
    // Do not call ResetPrefix here: the installed implementation uses ItemIO.Refresh.
    private void ResetNativePrefixLifecycle()
    {
        _pendingNativePrefix = null;
        _nativePrefixBase = null;
        _hasNativePrefixDefaults = true;
        _nativeDefaultCrit = Item.crit;
        _nativeDefaultReuseDelay = Item.reuseDelay;
        _nativeDefaultAnimationCompensation = (int)NativeAnimationCompensation.GetValue(Item)!;
    }

    private void CopyNativePrefixLifecycleTo(GeneratedItem clone)
    {
        clone._pendingNativePrefix = _pendingNativePrefix;
        clone._nativePrefixBase = _nativePrefixBase; // nullable value snapshot, never shared mutable state
        clone._hasNativePrefixDefaults = _hasNativePrefixDefaults;
        clone._nativeDefaultCrit = _nativeDefaultCrit;
        clone._nativeDefaultReuseDelay = _nativeDefaultReuseDelay;
        clone._nativeDefaultAnimationCompensation = _nativeDefaultAnimationCompensation;
    }

    private static int ValidateNativePrefixToken(int prefix)
    {
        // Native Item.prefix/ItemIO.Send use an integer; mod prefixes are not bytes.
        // Refuse roll sentinels and out-of-roster values, rather than rolling a replacement.
        if (prefix < 0 || prefix >= PrefixLoader.PrefixCount)
            throw new InvalidDataException($"Unsupported native prefix token {prefix}");
        return prefix;
    }

    private void RetainNativePrefixForHydration(int prefix)
        => _pendingNativePrefix = ValidateNativePrefixToken(prefix);

    private void SaveNativePrefixLifecycle(TagCompound tag)
    {
        int prefix = ValidateNativePrefixToken(InstanceNativePrefix);
        tag[NativePrefixSaveKey] = prefix;
        // Preserve native mod-prefix identity across changes to load-order IDs.
        if (PrefixLoader.GetPrefix(prefix) is ModPrefix modPrefix)
        {
            tag[NativePrefixSaveKey + "Mod"] = modPrefix.Mod.Name;
            tag[NativePrefixSaveKey + "Name"] = modPrefix.Name;
        }
    }

    private void LoadNativePrefixLifecycle(TagCompound tag)
    {
        _pendingNativePrefix = null;
        if (!tag.ContainsKey(NativePrefixSaveKey)) return; // legacy native Item.prefix still works
        if (tag.ContainsKey(NativePrefixSaveKey + "Mod") || tag.ContainsKey(NativePrefixSaveKey + "Name"))
        {
            if (!tag.ContainsKey(NativePrefixSaveKey + "Mod") || !tag.ContainsKey(NativePrefixSaveKey + "Name"))
                throw new InvalidDataException("Incomplete native mod-prefix identity");
            if (!ModContent.TryFind<ModPrefix>(tag.GetString(NativePrefixSaveKey + "Mod"),
                tag.GetString(NativePrefixSaveKey + "Name"), out var modPrefix))
                throw new InvalidDataException("Unavailable native mod-prefix identity");
            RetainNativePrefixForHydration(modPrefix.Type);
        }
        else RetainNativePrefixForHydration(tag.GetInt(NativePrefixSaveKey));
    }

    private void ApplyDataWithNativePrefix()
    {
        int prefix = InstanceNativePrefix;
        if (!_hasNativePrefixDefaults)
        {
            // Normal production initialization is SetDefaults; this also supports
            // explicitly attached, native-defaulted hosts without a loader bootstrap.
            _hasNativePrefixDefaults = true;
            _nativeDefaultCrit = Item.crit;
            _nativeDefaultReuseDelay = Item.reuseDelay;
            _nativeDefaultAnimationCompensation = (int)NativeAnimationCompensation.GetValue(Item)!;
        }
        // ApplyToItem deliberately doesn't own crit/reuseDelay. Reset those native
        // base fields too before reapplying, or repeated hydration adds crit again.
        Item.crit = _nativeDefaultCrit;
        Item.reuseDelay = _nativeDefaultReuseDelay;
        NativeAnimationCompensation.SetValue(Item, _nativeDefaultAnimationCompensation);
        Item.prefix = 0;
        Data.ApplyToItem(Item);
        _nativePrefixBase = NativePrefixBase.Capture(Item);
        if (GeneratedItemData.IsPlayerSaveReferenceOnly(Data))
        {
            // ItemIO.Load applies native prefix after LoadData; Receive applies it
            // before NetReceive. Both can reject an inert host, so retain the token
            // outside Item.prefix until authoritative full-definition hydration.
            RetainNativePrefixForHydration(prefix);
            return;
        }
        ReapplyNativePrefix(prefix);
    }

    private int BeginNativePrefixProjection()
    {
        int prefix = InstanceNativePrefix;
        if (_nativePrefixBase is not NativePrefixBase baseline)
        {
            ApplyDataWithNativePrefix();
            baseline = _nativePrefixBase!.Value;
        }
        baseline.Restore(Item);
        return prefix;
    }

    private void ReapplyNativePrefix(int prefix)
    {
        _pendingNativePrefix = null;
        Item.prefix = 0;
        // Use the real native category/AllowPrefix/stat-effect checks, modifiers,
        // rounding, value/rarity and mod-prefix Apply hooks. Prefix(0) is a no-op,
        // not a reset. A refusal stays unprefixed; never force a token or reroll.
        if (prefix != 0) Item.Prefix(ValidateNativePrefixToken(prefix));
    }

    private void FinishNativePrefixProjection(int prefix, bool placing)
    {
        // Prefix validation sees the real nonzero authored body damage. Placement
        // is only a temporary use projection, not a different prefixable identity.
        ReapplyNativePrefix(prefix);
        if (placing) Item.damage = 0;
    }
}
