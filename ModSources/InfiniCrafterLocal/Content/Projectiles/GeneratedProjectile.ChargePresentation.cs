#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Terraria;

namespace InfiniCrafterLocal.Content.Projectiles;

// Read-only observation of the existing controller clock, including extraUpdates.
// Source is the physical projectile generation, not the item ID or projectile slot.
internal readonly record struct GeneratedChargeStatus(object Source, int ChargeUpdates, int DurationUpdates)
{
    internal float Progress => Math.Clamp(ChargeUpdates / (float)Math.Max(1, DurationUpdates), 0f, 1f);
    internal bool Ready => ChargeUpdates >= DurationUpdates;
}

public sealed partial class GeneratedProjectile
{
    internal bool TryCaptureChargeStatus(Player owner, out GeneratedChargeStatus status)
    {
        status = default;
        if (!_configured || _runtimePayloadRejected || !Projectile.active || _presentationRetired
            || _activationDelayTicks > 0 || _age <= 0 || _released || _data is null
            || _entity?.Controller.Code != RuntimeControllerCode.ChargeThenRelease
            || _entity.Controller.Params.ChargeTicks <= 0 || owner is not { active: true, dead: false, channel: true }
            || Projectile.owner != owner.whoAmI || !HoldingGeneratedItem(owner))
            return false;
        int duration = AuthoredTicksToProjectileUpdates(_entity.Controller.Params.ChargeTicks);
        status = new(_presentationGeneration, Math.Clamp(_chargeTicks, 0, duration), duration);
        return true;
    }
}
