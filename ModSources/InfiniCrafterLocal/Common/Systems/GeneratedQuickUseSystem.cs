#nullable enable
using System;
using System.Collections.Generic;
using System.Reflection;
using InfiniCrafterLocal.Common.Models;
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

    public override void Load()
    {
        if (_hooks.Count != 0) throw new InvalidOperationException("Generated quick-use bridge already installed");
        try
        {
            Install(nameof(Player.QuickHeal), typeof(void), (Action<Action<Player>, Player>)QuickHeal);
            Install(nameof(Player.QuickMana), typeof(void), (Action<Action<Player>, Player>)QuickMana);
            Install(nameof(Player.QuickHeal_GetItemToUse), typeof(Item), (Func<Func<Player, Item?>, Player, Item?>)QuickHealCandidate);
            Install(nameof(Player.QuickMana_GetItemToUse), typeof(Item), (Func<Func<Player, Item?>, Player, Item?>)QuickManaCandidate);
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
        _hooks.Clear(); _player = null;
    }

    internal static bool IsNativeQuickUse(Player player) => ReferenceEquals(_player, player);

    internal static bool AcceptsBinding(Player player, RuntimeBindingSpec binding, GameplaySpec gameplay)
        => !IsNativeQuickUse(player)
            || binding.UsePolicy.Action.Kind == RuntimeBindingAction.ApplyItemEffects
                && (_kind == QuickUseKind.Heal ? gameplay.HealLife > 0 : gameplay.HealMana > 0);

    private static T Within<T>(Player player, QuickUseKind kind, Func<T> invoke)
    {
        Player? previousPlayer = _player; QuickUseKind previousKind = _kind;
        _player = player; _kind = kind;
        try { return invoke(); }
        finally { _player = previousPlayer; _kind = previousKind; }
    }

    private static void QuickHeal(Action<Player> orig, Player player)
        => Within(player, QuickUseKind.Heal, () => { orig(player); return true; });
    private static void QuickMana(Action<Player> orig, Player player)
        => Within(player, QuickUseKind.Mana, () => { orig(player); return true; });
    private static Item? QuickHealCandidate(Func<Player, Item?> orig, Player player)
        => Within(player, QuickUseKind.Heal, () => orig(player));
    private static Item? QuickManaCandidate(Func<Player, Item?> orig, Player player)
        => Within(player, QuickUseKind.Mana, () => orig(player));
}
