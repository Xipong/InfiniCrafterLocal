#nullable enable
using System;
using InfiniCrafterLocal.Common.Models;
using Microsoft.Xna.Framework;
using Terraria;

namespace InfiniCrafterLocal.Common.Players;

public sealed partial class InfiniCraftPlayer
{
    public readonly record struct GeneratedMovementPreview(Vector2 Destination, string Reason, bool RangeLimited, int CooldownTicks)
    {
        public bool Allowed => Reason.Length == 0 && CooldownTicks <= 0;
    }

    // One geometric decision for preview and execution. Never finds a different
    // landing tile or reserves cooldown merely because the cursor was inspected.
    public GeneratedMovementPreview PreviewGeneratedBlink(IItemEffectsSpec gameplay, Vector2 target)
    {
        GeneratedMovementPreview Refuse(string reason, Vector2 destination = default, bool limited = false)
            => new(destination, reason, limited, _generatedMobilityCooldownTicks);
        if (Player.dead) return Refuse("Dead");
        if (gameplay.MobilityRangeTiles <= 0) return Refuse("RangeMissing");
        if (!float.IsFinite(target.X) || !float.IsFinite(target.Y)
            || !float.IsFinite(Player.Center.X) || !float.IsFinite(Player.Center.Y)) return Refuse("InvalidTarget");
        Vector2 delta = target - Player.Center;
        float range = Math.Clamp(gameplay.MobilityRangeTiles, 1, 120) * 16f;
        bool limited = delta.LengthSquared() > range * range;
        if (limited) target = Player.Center + delta.SafeNormalize(Vector2.UnitX * Player.direction) * range;
        Vector2 destination = target - new Vector2(Player.width / 2f, Player.height / 2f);
        if (!IsBlinkWithinWorld(destination)) return Refuse("WorldEdge", destination, limited);
        if (gameplay.MobilitySafeTileOnly)
        {
            if (Collision.SolidCollision(destination, Player.width, Player.height)) return Refuse("Solid", destination, limited);
            if (Collision.LavaCollision(destination, Player.width, Player.height)) return Refuse("Lava", destination, limited);
        }
        return new(destination, "", limited, _generatedMobilityCooldownTicks);
    }
}
