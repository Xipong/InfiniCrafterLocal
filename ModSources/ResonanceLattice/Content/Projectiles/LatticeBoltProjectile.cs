#nullable enable
using Microsoft.Xna.Framework;
using ResonanceLattice.Core;
using Terraria;
using Terraria.Audio;
using Terraria.ID;
using Terraria.ModLoader;

namespace ResonanceLattice.Content.Projectiles;

/// <summary>
/// Charge bolt fired by the Stormcaller. Flies straight, arcs visually, and on tile or NPC
/// impact feeds <see cref="LatticeLimits.BoltChargeAmount"/> into the nearest network
/// (authoritative side only) and marks the victim. Demonstrates projectile integration with
/// the lattice: the projectile never touches the graph directly, only the public facade.
/// </summary>
public sealed class LatticeBoltProjectile : ModProjectile
{
    public override void SetDefaults()
    {
        Projectile.width = 12;
        Projectile.height = 12;
        Projectile.friendly = true;
        Projectile.hostile = false;
        Projectile.penetrate = 1;
        Projectile.timeLeft = 240;
        Projectile.tileCollide = true;
        Projectile.ignoreWater = true;
        Projectile.DamageType = DamageClass.Magic;
        Projectile.light = 0.4f;
    }

    public override void AI()
    {
        Projectile.rotation = Projectile.velocity.ToRotation();
        if (Main.rand.NextBool(2))
        {
            Dust dust = Dust.NewDust(Projectile.position, Projectile.width, Projectile.height, DustID.Electric, 0f, 0f, 100, default, 1f);
            dust.noGravity = true;
            dust.velocity *= 0.3f;
        }
    }

    public override bool OnTileCollide(Vector2 oldVelocity)
    {
        if (ResonanceLattice.IsAuthoritative)
        {
            float applied = ResonanceLattice.InjectCharge(Projectile.Center, LatticeLimits.BoltChargeAmount);
            if (applied > 0f)
            {
                Burst(Projectile.Center, 10);
                SoundEngine.PlaySound(SoundID.Item12, Projectile.Center);
            }
        }
        return true; // let vanilla tile collision kill the projectile
    }

    public override void OnHitNPC(NPC target, NPC.HitInfo hit, int damageDone)
    {
        if (ResonanceLattice.IsAuthoritative)
            ResonanceLattice.InjectCharge(target.Center, LatticeLimits.BoltChargeAmount * 0.5f);
        target.GetGlobalNPC<LatticeMarkGlobalNPC>().Mark(LatticeLimits.MarkDurationTicks);
        Burst(target.Center, 8);
    }

    private static void Burst(Vector2 center, int count)
    {
        for (int i = 0; i < count; i++)
        {
            Dust dust = Dust.NewDust(center, 0, 0, DustID.Electric, 0f, 0f, 100, default, 1.2f);
            dust.velocity = Main.rand.NextVector2Circular(4f, 4f);
            dust.noGravity = true;
        }
    }
}
