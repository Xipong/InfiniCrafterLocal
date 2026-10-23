#nullable enable
using System;
using Terraria;
namespace InfiniCrafterLocal.Common.Runtime;
// Resource reservation belongs to one exact captured player object. It never
// reads HeldItem, guesses another player, consumes potions, or grants spawn rights.
internal sealed class RuntimeVolleyManaPayment
{
    private readonly Player _owner;
    private readonly int _baseCost, _requested, _charged;
    private readonly bool _perShot;
    private readonly float _multiplier;
    private bool _settled;
    private RuntimeVolleyManaPayment(Player owner, int baseCost, bool perShot, int requested, int charged, float multiplier)
    { _owner = owner; _baseCost = baseCost; _perShot = perShot; _requested = requested; _charged = charged; _multiplier = multiplier; }
    internal static bool TryReserve(Player owner, int baseCost, bool perShot, int requested, int reserve, out RuntimeVolleyManaPayment? payment)
    {
        payment = null;
        if (owner is null || !owner.active || owner.dead || baseCost < 0 || baseCost > 200 || requested < 1 || requested > 4 || reserve < 0 || reserve > 400) return false;
        float multiplier = owner.manaCost;
        float raw = baseCost * (perShot ? requested : 1) * multiplier;
        if (!float.IsFinite(multiplier) || multiplier < 0f || !float.IsFinite(raw) || raw >= int.MaxValue) return false;
        int charge = (int)raw;
        if ((long)owner.statMana - charge < reserve || !owner.CheckMana(baseCost * (perShot ? requested : 1), pay: true, blockQuickMana: true)) return false;
        payment = new(owner, baseCost, perShot, requested, charge, multiplier);
        return true;
    }
    internal void Complete(int spawned)
    {
        if (_settled) return;
        if (spawned < 0 || spawned > _requested) throw new ArgumentOutOfRangeException(nameof(spawned));
        _settled = true;
        int paid = spawned == 0 ? 0 : (int)(_baseCost * (_perShot ? spawned : 1) * _multiplier);
        _owner.statMana += _charged - paid;
        if (paid > 0) _owner.manaRegenDelay = Math.Max(_owner.manaRegenDelay, _owner.maxRegenDelay);
    }
}
