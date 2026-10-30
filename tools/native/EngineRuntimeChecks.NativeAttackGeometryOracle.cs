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
    // Independent executable rendering of the model-facing helper rules. This
    // deliberately does not call native cone/corner/rotation helpers on the
    // expected side; the actual side invokes those installed native methods.
    private static bool GeometryRulePoint(Vector2 point, Vector2 center, float length, float rotation, float angleLimit)
    {
        Vector2 offset = point - center;
        double rotation64 = 0f - rotation;
        double cosine = Math.Cos(rotation64), sine = Math.Sin(rotation64);
        var rotated = new Vector2((float)(offset.X * cosine - offset.Y * sine), (float)(offset.X * sine + offset.Y * cosine)) + Vector2.Zero;
        float angle = (float)Math.Atan2(rotated.Y, rotated.X);
        float distance = (float)Math.Sqrt(offset.X * offset.X + offset.Y * offset.Y);
        return !(angle < -angleLimit || angle > angleLimit) && distance < length;
    }

    private static bool GeometryRuleRectangle(Rectangle rectangle, Vector2 center, float length, float rotation, float angleLimit)
    {
        Vector2 tip = center + new Vector2((float)Math.Cos(rotation), (float)Math.Sin(rotation)) * length;
        float Clamp(float value, float minimum, float maximum)
        {
            if (value > maximum) value = maximum;
            if (value < minimum) value = minimum;
            return value;
        }
        Vector2[] points = {
            new(Clamp(tip.X, rectangle.X, rectangle.X + rectangle.Width), Clamp(tip.Y, rectangle.Y, rectangle.Y + rectangle.Height)),
            new(rectangle.X, rectangle.Y), new(rectangle.X + rectangle.Width, rectangle.Y),
            new(rectangle.X, rectangle.Y + rectangle.Height), new(rectangle.X + rectangle.Width, rectangle.Y + rectangle.Height),
        };
        foreach (Vector2 point in points)
            if (GeometryRulePoint(point, center, length, rotation, angleLimit)) return true;
        return false;
    }

    private static void ParentNativeGeometryHelperRulesMatchSource()
    {
        MethodInfo pointMethod = typeof(Terraria.Utils).GetMethod("DoesFitInCone", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static)!;
        bool NativePoint(Vector2 point, Vector2 center, float length, float rotation, float limit)
            => (bool)pointMethod.Invoke(null, new object[] { point, center, length, rotation, limit })!;
        int cases = 0;
        void Point(Vector2 point, Vector2 center, float length, float rotation, float limit)
        {
            Equal(NativePoint(point, center, length, rotation, limit), GeometryRulePoint(point, center, length, rotation, limit), $"native point geometry semantic relation p={point} c={center} len={length} rot={rotation} limit={limit}");
            cases++;
        }
        void RectangleCase(Rectangle rectangle, Vector2 center, float length, float rotation, float limit)
        {
            Equal(Terraria.Utils.IntersectsConeSlowMoreAccurate(rectangle, center, length, rotation, limit), GeometryRuleRectangle(rectangle, center, length, rotation, limit), $"native five-point rectangle geometry semantic relation r={rectangle} c={center} len={length} rot={rotation} limit={limit}");
            cases++;
        }
        foreach (float limit in new[] { 0f, MathHelper.PiOver4, MathHelper.Pi, -0.1f, float.NaN })
        foreach (float rotation in new[] { 0f, -0f, MathHelper.PiOver2, MathHelper.Pi, float.NaN })
        foreach (float length in new[] { 0f, 10f, -1f, float.PositiveInfinity, float.NaN })
        {
            foreach (Vector2 point in new[] { Vector2.Zero, new Vector2(1, 1), new Vector2(1, -1), new Vector2(10, 0), new Vector2(float.BitDecrement(10f), 0), new Vector2(float.BitIncrement(10f), 0), new Vector2(-10, 0), new Vector2(float.NaN, 1) })
                Point(point, Vector2.Zero, length, rotation, limit);
            foreach (Rectangle rectangle in new[] { new Rectangle(4, -20, 2, 40), new Rectangle(8, -2, 8, 4), new Rectangle(-10, -1, 2, 2), new Rectangle(10, 0, 0, 0), new Rectangle(-2, -2, 4, 4), new Rectangle(5, 5, -3, -7), new Rectangle(10, 0, 0, 4) })
                RectangleCase(rectangle, Vector2.Zero, length, rotation, limit);
        }
        var random = new Random(76123);
        for (int n = 0; n < 2000; n++)
        {
            Vector2 center = new(random.Next(-80, 81), random.Next(-80, 81));
            float length = random.Next(1, 200), rotation = (float)(random.NextDouble() * 12 - 6), limit = (float)(random.NextDouble() * 3);
            Point(new Vector2(random.Next(-200, 201), random.Next(-200, 201)), center, length, rotation, limit);
            RectangleCase(new Rectangle(random.Next(-200, 201), random.Next(-200, 201), random.Next(0, 80), random.Next(0, 80)), center, length, rotation, limit);
        }
        Equal(true, NativePoint(new Vector2(1, 1), Vector2.Zero, 10, 0, MathHelper.PiOver4), "positive angular boundary included");
        Equal(true, NativePoint(new Vector2(1, -1), Vector2.Zero, 10, 0, MathHelper.PiOver4), "negative angular boundary included");
        Equal(false, NativePoint(new Vector2(10, 0), Vector2.Zero, 10, 0, MathHelper.PiOver4), "radial boundary excluded");
        Equal(true, NativePoint(new Vector2(1, 0), Vector2.Zero, 10, float.NaN, MathHelper.PiOver4), "unordered angle is not abs-angle rejection");
        var closestOnly = new Rectangle(4, -20, 2, 40);
        Equal(true, Terraria.Utils.IntersectsConeSlowMoreAccurate(closestOnly, Vector2.Zero, 10, 0, 0.1f), "forward-tip closest-point witness cannot be replaced by corners only");
        foreach (Vector2 corner in new[] { new Vector2(4, -20), new Vector2(6, -20), new Vector2(4, 20), new Vector2(6, 20) })
            Equal(false, NativePoint(corner, Vector2.Zero, 10, 0, 0.1f), "each corner misses closest-point witness");
        Console.WriteLine($"Native helper geometry comparisons: {cases}");
    }
    private static void ParentNativePositionIntegrationMatchesLiveGuards()
    {
        using var state = new NativeActorState();
        MethodInfo update = typeof(Projectile).GetMethod("UpdatePosition", BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public)!;
        foreach (int type in new[] { ProjectileID.Excalibur, ProjectileID.WoodenArrowFriendly })
        {
            var projectile = new Projectile(); projectile.SetDefaults(type);
            projectile.position = new Vector2(100, 200); projectile.velocity = new Vector2(3, 5);
            projectile.wet = false;
            update.Invoke(projectile, new object[] { new Vector2(7, 11) });
            Equal(new Vector2(103, 205), projectile.position, "dry native integration uses velocity");
            projectile.wet = true;
            update.Invoke(projectile, new object[] { new Vector2(7, 11) });
            Equal(new Vector2(110, 216), projectile.position, "wet native integration uses supplied wetVelocity, not regular velocity");
            projectile.aiStyle = 4;
            update.Invoke(projectile, new object[] { new Vector2(7, 11) });
            Equal(new Vector2(110, 216), projectile.position, "native excluded style bypasses integration");
        }
    }
    private static void ParentNativeArrowMotionMatchesSelectedSource()
    {
        using var state = new NativeActorState();
        Terraria.Main.netMode = NetmodeID.Server;
        Terraria.Main.rand = new UnifiedRandom(73);
        var projectile = new Projectile(); projectile.SetDefaults(ProjectileID.WoodenArrowFriendly);
        projectile.owner = 0; projectile.active = true;
        projectile.velocity = new Vector2(3f, 0f);
        MethodInfo ai = typeof(Projectile).GetMethod("AI_001", BindingFlags.Instance | BindingFlags.NonPublic)!;
        for (int update = 1; update <= 18; update++)
        {
            ai.Invoke(projectile, null);
            float expectedY = update < 15 ? 0f : (update - 14) * 0.1f;
            Equal(true, Math.Abs(projectile.velocity.Y - expectedY) < .00001f, "actual native arrow delayed gravity update " + update);
            Equal((float)Math.Min(update, 15), projectile.ai[0], "actual native arrow timing clock and clamp");
            Equal(true, Math.Abs(projectile.rotation - ((float)Math.Atan2(projectile.velocity.Y, projectile.velocity.X) + 1.57f)) < .00001f,
                "actual native arrow rotation follows velocity");
        }
        projectile.velocity.Y = 16f;
        ai.Invoke(projectile, null);
        Equal(16f, projectile.velocity.Y, "actual native arrow vertical speed cap");
    }
}
