#nullable enable
using Terraria;
using Terraria.ModLoader;

namespace ResonanceLattice.Content.Buffs;

/// <summary>
/// Granted by the Lattice Probe when a nearby network is sufficiently charged.
/// Faster mana regeneration while attuned to the lattice.
/// </summary>
public sealed class LatticeAttunementBuff : ModBuff
{
    public override void Update(Player player, ref int buffIndex)
    {
        player.manaRegen += Core.LatticeLimits.AttunementManaRegen;
    }
}
