#nullable enable
using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using InfiniCrafterLocal.Common.UI;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    /// <summary>
    /// Read-only interface adapter over the existing live entries and aggregate.
    /// No normalization, lifetime advancement, AddBuff or aggregation occurs here.
    /// Kept outside Mobility.cs so gameplay storage and UI have separate owners.
    /// </summary>
    internal GeneratedUtilityBuffPresentation CaptureGeneratedUtilityBuffPresentation()
    {
        var entries = new GeneratedUtilityBuffValues[_activeGeneratedUtilityBuffs.Count];
        for (int index = 0; index < entries.Length; index++)
        {
            ActiveGeneratedUtilityBuff active = _activeGeneratedUtilityBuffs[index];
            entries[index] = new(active.Ticks, active.MiningSpeedMultiplier,
                active.EmitLightStrength, active.LightColorName, active.OreSenseRadiusTiles,
                active.MovementSpeed, active.JumpBoost, active.ManaRegen, active.LifeRegen,
                active.Combat?.DefensePoints ?? 0, active.Combat?.AttackSpeedPercent ?? 0, active.Combat?.CritChancePoints ?? 0,
                active.Combat is { } combat ? new ReadOnlyDictionary<string, float>(new Dictionary<string, float>
                    { [combat.DamageClass] = combat.DamagePercent }) : null, active.PlayerEffect is { } effect ? effect with { } : null,
                active.LifeRegenCondition, active.TreasureSenseCondition);
        }
        var current = new GeneratedUtilityBuffValues(_generatedBuffTicks,
            _generatedMiningSpeedMultiplier, _generatedLightStrength, _generatedLightColorName,
            HasActiveGeneratedTreasureSense ? 1 : 0, _generatedMovementSpeed, _generatedJumpBoost,
            _generatedManaRegen, CurrentGeneratedLifeRegen, _generatedDefense, _generatedAttackSpeed, _generatedCrit,
            new ReadOnlyDictionary<string, float>(new Dictionary<string, float>(_generatedDamage)));
        return new(current, Array.AsReadOnly(entries));
    }
}
