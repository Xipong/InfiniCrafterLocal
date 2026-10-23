#nullable enable
using System;
using Terraria;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    public readonly record struct GeneratedUtilityRetirement(string Reason, uint Tick, int Contributions, int ExhaustionEntries);
    private uint? _generatedUtilityRetiredAt;
    private GeneratedUtilityRetirement? _lastGeneratedUtilityRetirement;
    public GeneratedUtilityRetirement? LastGeneratedUtilityRetirement => _lastGeneratedUtilityRetirement;

    internal bool IsGeneratedUtilityActivationCurrent(uint? activationTick)
    {
        if (!activationTick.HasValue || !_generatedUtilityRetiredAt.HasValue) return true;
        uint sinceRetirement = unchecked(activationTick.Value - _generatedUtilityRetiredAt.Value);
        // Same/dead tick or an earlier activation belongs to the retired life.
        // Unsigned half-range comparison remains valid through the native wrap.
        return sinceRetirement is > 0 and <= int.MaxValue;
    }

    private uint _generatedUtilityLifeGeneration;
    private uint _minimumGeneratedUtilityLifeGeneration;
    private uint? _lastNativeUtilityDeathGeneration;
    private bool _generatedUtilityDeathObserved;
    private bool _lastGeneratedUtilitySnapshotWasDead;

    private static bool UtilityGenerationBefore(uint candidate, uint minimum)
        => unchecked((int)(candidate - minimum)) < 0;

    private bool ObserveGeneratedUtilityDeath()
    {
        if (_generatedUtilityDeathObserved) return false;
        _generatedUtilityDeathObserved = true;
        if (Main.netMode != Terraria.ID.NetmodeID.MultiplayerClient)
            _generatedUtilityLifeGeneration = unchecked(_generatedUtilityLifeGeneration + 1);
        // A trusted server-dead snapshot may arrive before the native death
        // hook. Count that acknowledgement once, never require another epoch.
        bool acknowledged = _lastGeneratedUtilitySnapshotWasDead
            && (!_lastNativeUtilityDeathGeneration.HasValue
                || UtilityGenerationBefore(_lastNativeUtilityDeathGeneration.Value, _generatedUtilityLifeGeneration));
        _minimumGeneratedUtilityLifeGeneration = Main.netMode != Terraria.ID.NetmodeID.MultiplayerClient || acknowledged
            ? _generatedUtilityLifeGeneration : unchecked(_generatedUtilityLifeGeneration + 1);
        _lastNativeUtilityDeathGeneration = _minimumGeneratedUtilityLifeGeneration;
        return true;
    }

    private void ResetGeneratedUtilityNetworkLife()
    {
        _generatedUtilityLifeGeneration = _minimumGeneratedUtilityLifeGeneration = 0;
        _lastNativeUtilityDeathGeneration = null;
        _generatedUtilityDeathObserved = _lastGeneratedUtilitySnapshotWasDead = false;
    }

    public override void OnRespawn() => _generatedUtilityDeathObserved = false;

    internal void RetireGeneratedUtilityState(string reason, bool syncNetwork = false)
    {
        bool newDeath = reason == "death" && ObserveGeneratedUtilityDeath();
        int contributions = _activeGeneratedUtilityBuffs.Count;
        int exhaustion = _generatedItemExhaustion.Count;
        bool changed = contributions > 0 || exhaustion > 0 || _generatedBuffTicks > 0;
        _generatedUtilityRetiredAt = Main.GameUpdateCount;
        if (changed || _lastGeneratedUtilityRetirement is null || _lastGeneratedUtilityRetirement.Value.Reason != reason)
            _lastGeneratedUtilityRetirement = new(reason, Main.GameUpdateCount, contributions, exhaustion);
        _activeGeneratedUtilityBuffs.Clear();
        ClearGeneratedItemExhaustion();
        ResetGeneratedUtilityBuffAggregate();
        if ((changed || newDeath) && syncNetwork) CorrectGeneratedBuffPrediction();
    }
}
