using System;
using System.Reflection;
using Microsoft.Xna.Framework;
using Terraria;
using Terraria.ID;
using Terraria.Utilities;

internal static partial class EngineRuntimeChecks
{
    // Independent oracle: executes the real native method/collision on isolated
    // CPU actors, not the extractor's formulas or a generated weapon controller.
    private static void ParentNativeGrowingArcMatchesRealMotionAndConeUnion()
    {
        using var state = new NativeActorState();
        Dust[] oldDust = Terraria.Main.dust;
        try
        {
            Terraria.Main.dedServ = true;
            Terraria.Main.netMode = NetmodeID.Server;
            Terraria.Main.rand = new UnifiedRandom(41);
            Terraria.Main.dust = new Dust[6001];
            for (int i = 0; i < Terraria.Main.dust.Length; i++) Terraria.Main.dust[i] = new Dust();
            var player = new Player { whoAmI = 0, active = true, dead = false, direction = 1, gravDir = 1f, fullRotation = 0f };
            player.Center = new Vector2(800, 700);
            Terraria.Main.player[0] = player;
            var projectile = new Projectile();
            projectile.SetDefaults(ProjectileID.Excalibur);
            projectile.owner = 0; projectile.active = true;
            projectile.velocity = Vector2.UnitX;
            projectile.ai[0] = 1f; projectile.ai[1] = 20f; projectile.ai[2] = 1f;
            MethodInfo ai = typeof(Projectile).GetMethod("AI_190_NightsEdge", BindingFlags.Instance | BindingFlags.NonPublic)!;
            projectile.localAI[0] = 9f;
            ai.Invoke(projectile, null);
            Equal(10f, projectile.localAI[0], "native AI advances its local clock");
            void Near(float expected, float actual, string label) => Equal(true, Math.Abs(expected - actual) < .001f, label);
            Near(1.3f, projectile.scale, "native AI live scale grows independently from 16px defaults");
            Equal(true, Vector2.DistanceSquared(player.MountedCenter - projectile.velocity, projectile.Center) < .001f,
                "native AI owner anchor compensates later position integration");
            float middleAngle = projectile.rotation + MathHelper.TwoPi / 25f * projectile.ai[0];
            Rectangle Target(float angle, float distance)
            {
                Vector2 center = projectile.Center + new Vector2(MathF.Cos(angle), MathF.Sin(angle)) * distance;
                return new Rectangle((int)center.X - 1, (int)center.Y - 1, 2, 2);
            }
            Rectangle distant = Target(middleAngle, 100f);
            Equal(false, projectile.Hitbox.Intersects(distant), "small SetDefaults AABB alone misses native damaging area");
            Equal(true, projectile.Colliding(projectile.Hitbox, distant), "actual native cone reaches far beyond default AABB");
            Equal(false, projectile.Colliding(projectile.Hitbox, Target(middleAngle + MathHelper.Pi, 100f)), "native cone does not hit behind its accepted direction");
            projectile.localAI[0] = 3f;
            ai.Invoke(projectile, null);
            Near(1.12f, projectile.scale, "early native scale uses actual progress");
            float earlyAngle = projectile.rotation + MathHelper.TwoPi / 25f * projectile.ai[0];
            Rectangle trailOnly = Target(earlyAngle - MathHelper.ToRadians(70f), 75f);
            Equal(false, Terraria.Utils.IntersectsConeSlowMoreAccurate(trailOnly, projectile.Center, 94f * projectile.scale, earlyAngle, MathHelper.PiOver4),
                "early target is outside the primary native cone");
            Equal(true, projectile.Colliding(projectile.Hitbox, trailOnly), "actual Colliding retains the second conditional early-cycle cone");
        }
        finally { Terraria.Main.dust = oldDust; }
    }
}
