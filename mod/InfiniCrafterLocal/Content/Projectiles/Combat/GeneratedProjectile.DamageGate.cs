#nullable enable
using InfiniCrafterLocal.Common.Models;

namespace InfiniCrafterLocal.Content.Projectiles;

public sealed partial class GeneratedProjectile
{
    public override bool? CanDamage()
    {
        if (!_configured || _entity is null || !_entity.Damage.Enabled || _activationDelayTicks > 0)
            return false;

        if (_entity.ContactGate is { } gate && MotionWindowActive(gate.Window) && !gate.Enabled)
            return false;
        if (HasBeamGeometry && BeamWarmupProgress() < BeamDamageStart)
            return false;

        // Do not force a hit or bypass native blacklists, NPC immunity, the
        // initial-target exclusion or the independently authored collision shape.
        // Explicit event actions use their own executor, not this contact gate.
        return null;
    }
}
