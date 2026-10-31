#nullable enable
using ResonanceLattice.Content.Buffs;
using Terraria.ModLoader;

namespace ResonanceLattice.Core;

/// <summary>
/// Player-side lattice integration: while the attunement buff is active (granted by the
/// Lattice Probe when a nearby network is well charged), the player regenerates mana
/// faster. Runs locally per player, so it is multiplayer-safe through vanilla buff sync.
/// </summary>
public sealed class LatticePlayer : ModPlayer
{
    public override void PostUpdate()
    {
        if (Player.HasBuff<LatticeAttunementBuff>())
            Player.manaRegen += LatticeLimits.AttunementManaRegen;
    }
}
