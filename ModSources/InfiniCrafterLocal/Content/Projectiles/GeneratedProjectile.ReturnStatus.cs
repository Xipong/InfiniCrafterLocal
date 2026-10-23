#nullable enable
using System;
using Microsoft.Xna.Framework;

namespace InfiniCrafterLocal.Content.Projectiles;

internal sealed record GeneratedReturnStatus(string ItemId, string Name, string SpritePath,
    string Phase, int ReturnInTicks, int RemainingTicks, float DistanceBlocks);

public sealed partial class GeneratedProjectile
{
    private void BeginReturn()
    {
        if (_returning) return;
        _returning = true;
        Projectile.netUpdate = true;
    }

    internal GeneratedReturnStatus? CaptureReturnStatus(int owner, Vector2 ownerCenter)
    {
        if (!_configured || _data is null || _entity is null || !Projectile.active || Projectile.owner != owner
            || _entity.Movement.Code is not (5 or 14 or 16 or 17)) return null;
        int updates = Math.Max(1, Projectile.extraUpdates + 1);
        int returnIn = !_returning && _entity.Movement.Code is 5 or 14
            ? Math.Max(0, _entity.Movement.Params.ReturnAfterTicks - _age / updates) : 0;
        return new(_data.Id, _data.Name, _data.Visual.SpritePath,
            _activationDelayTicks > 0 ? "waiting" : _returning ? "returning" : _entity.Movement.Code is 16 or 17 ? "held" : "outbound",
            returnIn, (int)Math.Min(int.MaxValue, (Math.Max(0, (long)Projectile.timeLeft) + updates - 1) / updates),
            Vector2.Distance(Projectile.Center, ownerCenter) / 16f);
    }
}
