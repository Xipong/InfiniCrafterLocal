#nullable enable
using Terraria;
using Terraria.ModLoader;

namespace ResonanceLattice.Core;

/// <summary>
/// Cross-system NPC integration: any NPC marked by lattice energy (currently Stormcaller
/// bolts) takes bonus damage from every damage source for a short time. Demonstrates that
/// the library can plug into the native combat pipeline via a plain GlobalNPC.
/// </summary>
public sealed class LatticeMarkGlobalNPC : GlobalNPC
{
    public override bool InstancePerEntity => true;

    public int MarkTicks;

    public void Mark(int ticks)
    {
        if (ticks > MarkTicks)
            MarkTicks = ticks;
    }

    public override void PostAI(NPC npc)
    {
        if (MarkTicks > 0)
            MarkTicks--;
    }

    public override void ModifyHitByProjectile(NPC npc, Projectile projectile, ref NPC.HitModifiers modifiers)
    {
        if (MarkTicks > 0)
            modifiers.FinalDamage *= LatticeLimits.MarkedDamageMultiplier;
    }

    public override void ModifyHitByItem(NPC npc, Player player, Item item, ref NPC.HitModifiers modifiers)
    {
        if (MarkTicks > 0)
            modifiers.FinalDamage *= LatticeLimits.MarkedDamageMultiplier;
    }
}
