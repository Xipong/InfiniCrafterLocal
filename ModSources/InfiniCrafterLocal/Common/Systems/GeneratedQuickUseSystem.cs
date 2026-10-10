#nullable enable
using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
using InfiniCrafterLocal.Common.Runtime;
using InfiniCrafterLocal.Content.Items;
using MonoMod.RuntimeDetour;
using Terraria;
using Terraria.ModLoader;

namespace InfiniCrafterLocal.Common.Systems;

// Native quick-use executes effects, not Shoot or alternate input. Carry that
// literal consumer context through its existing CanUseItem/UseItem/ConsumeItem calls.
public sealed class GeneratedQuickUseSystem : ModSystem
{
    private enum QuickUseKind { Heal, Mana }
    private readonly List<Hook> _hooks = new();
    [ThreadStatic] private static Player? _player;
    [ThreadStatic] private static QuickUseKind _kind;
    [ThreadStatic] private static bool _executing, _published;

    public override void Load()
    {
        if (_hooks.Count != 0) throw new InvalidOperationException("Generated quick-use bridge already installed");
        try
        {
            Install(nameof(Player.QuickHeal), typeof(void), (Action<Action<Player>, Player>)QuickHeal);
            Install(nameof(Player.QuickMana), typeof(void), (Action<Action<Player>, Player>)QuickMana);
            Install(nameof(Player.QuickHeal_GetItemToUse), typeof(Item), (Func<Func<Player, Item?>, Player, Item?>)QuickHealCandidate);
            Install(nameof(Player.QuickMana_GetItemToUse), typeof(Item), (Func<Func<Player, Item?>, Player, Item?>)QuickManaCandidate);
            MethodInfo use = typeof(ItemLoader).GetMethod(nameof(ItemLoader.UseItem),
                BindingFlags.Static | BindingFlags.Public, null, new[] { typeof(Item), typeof(Player) }, null)
                ?? throw new InvalidOperationException("Generated quick-use ItemLoader.UseItem boundary missing");
            if (use.ReturnType != typeof(bool?))
                throw new InvalidOperationException("Generated quick-use ItemLoader.UseItem return contract changed");
            _hooks.Add(new Hook(use, (Func<Func<Item, Player, bool?>, Item, Player, bool?>)AfterNativeUseItem));
        }
        catch { Unload(); throw; }
    }

    private void Install(string name, Type returnType, Delegate detour)
    {
        MethodInfo method = typeof(Player).GetMethod(name, BindingFlags.Instance | BindingFlags.Public, null, Type.EmptyTypes, null)
            ?? throw new InvalidOperationException("Generated quick-use native signature missing: " + name);
        if (method.ReturnType != returnType)
            throw new InvalidOperationException("Generated quick-use native return contract mismatch: " + name);
        _hooks.Add(new Hook(method, detour));
    }

    public override void Unload()
    {
        for (int i = _hooks.Count - 1; i >= 0; i--) _hooks[i].Dispose();
        _hooks.Clear(); _player = null; _executing = _published = false;
        GeneratedQuickUtilityActivation.Clear();
    }

    internal static bool IsNativeQuickUse(Player player) => ReferenceEquals(_player, player);

    internal static bool AcceptsBinding(Player player, RuntimeBindingSpec binding, IItemEffectsSpec gameplay)
        => !IsNativeQuickUse(player)
            || binding.UsePolicy.Action.Kind == RuntimeBindingAction.ApplyItemEffects
                && (_kind == QuickUseKind.Heal ? gameplay.HealLife > 0 : gameplay.HealMana > 0);

    private static T Within<T>(Player player, QuickUseKind kind, Func<T> invoke)
    {
        Player? previousPlayer = _player; QuickUseKind previousKind = _kind;
        _player = player; _kind = kind;
        try
        {
            // Native selectors may inspect healLife/healMana before CanUseItem.
            // A previous manual alternate use must not hide the primary group.
            ProjectPrimaryEffectCandidates(player.inventory);
            if (player.useVoidBag()) ProjectPrimaryEffectCandidates(player.bank4.item);
            return invoke();
        }
        finally { _player = previousPlayer; _kind = previousKind; }
    }

    private static void ProjectPrimaryEffectCandidates(Item[] items)
    {
        foreach (Item item in items)
        {
            if (item?.ModItem is not GeneratedItem generated || generated.Data.RuntimeProgram.EffectGroups is null)
                continue;
            RuntimeBindingSpec? primary = generated.Data.RuntimeProgram.BindingForInput(RuntimeInputKind.PrimaryUse);
            generated.Data.ApplyUseEffectFields(item, primary?.UsePolicy.Action.Kind == RuntimeBindingAction.ApplyItemEffects, primary);
        }
    }

    private static bool? AfterNativeUseItem(Func<Item, Player, bool?> orig, Item item, Player player)
    {
        bool? result = orig(item, player); // unchanged native + all GlobalItem/ModItem consumers
        if (_executing && !_published && IsNativeQuickUse(player) && item.ModItem is GeneratedItem generated)
        {
            _published = true; // one notification per real quick-use call, never candidate scans
            // Transport/definition failure must never interrupt the native heal/consume tail.
            try { GeneratedQuickUtilityActivation.Send(player, generated, (byte)(_kind == QuickUseKind.Heal ? 1 : 2)); }
            catch (Exception error)
            {
                try { global::InfiniCrafterLocal.InfiniCrafterLocalMod.Instance?.Logger?.Warn("Quick utility activation refused: " + error.GetType().Name); }
                catch { }
            }
        }
        return result;
    }
    private static void Execute(Action<Player> orig, Player player, QuickUseKind kind)
    {
        bool previousExecuting = _executing, previousPublished = _published;
        _executing = true; _published = false;
        try { Within(player, kind, () => { orig(player); return true; }); }
        finally { _executing = previousExecuting; _published = previousPublished; }
    }
    private static void QuickHeal(Action<Player> orig, Player player) => Execute(orig, player, QuickUseKind.Heal);
    private static void QuickMana(Action<Player> orig, Player player) => Execute(orig, player, QuickUseKind.Mana);
    private static Item? QuickHealCandidate(Func<Player, Item?> orig, Player player)
        => Within(player, QuickUseKind.Heal, () => orig(player));
    private static Item? QuickManaCandidate(Func<Player, Item?> orig, Player player)
        => Within(player, QuickUseKind.Mana, () => orig(player));
}
