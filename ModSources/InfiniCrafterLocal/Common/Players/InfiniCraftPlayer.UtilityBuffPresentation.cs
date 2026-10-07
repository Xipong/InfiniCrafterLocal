#nullable enable
using System;
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
                active.MovementSpeed, active.JumpBoost, active.ManaRegen, active.LifeRegen);
        }
        var current = new GeneratedUtilityBuffValues(_generatedBuffTicks,
            _generatedMiningSpeedMultiplier, _generatedLightStrength, _generatedLightColorName,
            _generatedOreSenseRadiusTiles, _generatedMovementSpeed, _generatedJumpBoost,
            _generatedManaRegen, _generatedLifeRegen);
        return new(current, Array.AsReadOnly(entries));
    }
}
