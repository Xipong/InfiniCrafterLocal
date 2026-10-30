using System;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;
using Terraria.ModLoader;

internal static partial class EngineRuntimeChecks
{
    private static int AttackObservationExecutions;
    private static void AttackObservationSource(Projectile projectile)
    {
        AttackObservationExecutions++;
        projectile.localAI[0] += 1f;
        float progress = projectile.localAI[0] / projectile.ai[1];
        float growth = projectile.ai[0] > 0 ? .6f : .2f;
        projectile.scale = (1f + progress * growth) * projectile.ai[2];
        projectile.rotation = progress * 3.1415927f;
        if (progress >= 1f) projectile.Kill();
    }

    private static void ProjectileAttackSourceObservationsKeepExpressionsAndPredicates()
    {
        AttackObservationExecutions = 0;
        var source = GeneratorClient.InspectProjectileAttackSource(typeof(EngineRuntimeChecks).GetMethod(
            nameof(AttackObservationSource), BindingFlags.Static | BindingFlags.NonPublic)!, "motion");
        string json = source.ToJsonString();
        if (Environment.GetEnvironmentVariable("INFINI_DUMP_PARITY_PACKET") is string evidence)
            System.IO.File.WriteAllText(evidence + ".symbolic.json", json);
        foreach (string fragment in new[] { "Projectile.scale", "Projectile.rotation", "Projectile.localAI", "Projectile.ai", "Kill", "requiredPredicates", "0.6", "0.2", "sourceMethodSha256", "sourceModuleVersionId" })
            Equal(true, json.Contains(fragment, StringComparison.Ordinal), "meaningful source dependency retained: " + fragment);
        Equal(0, AttackObservationExecutions, "source observations do not execute the inspected body");
        Equal(true, source["predicates"]!.AsArray().Count >= 2, "opaque ai-dependent alternative and lifetime predicates survive");
    }

    private static void ProjectileAttackNativeDispatchAndSiblingWitnesses()
    {
        // Roster comes from installed SetDefaults2 AI-style assignments; not a production family map.
        foreach (int id in new[] { 982, 983, 984, 997, 972 })
        {
            var projectile = new Projectile();
            projectile.SetDefaults(id); // fixture only; production capture never calls defaults/AI/draw.
            var attack = GeneratorClient.CaptureProjectileAttackReference(projectile);
            string json = attack.ToJsonString();
            Equal(true, attack["motion"] is JsonObject, "native controller source found: " + id);
            foreach (string field in new[] { "Projectile.scale", "Projectile.rotation", "Projectile.localAI", "Projectile.ai", "MountedCenter", "RotatedRelativePoint", "Kill", "IntersectsConeSlowMoreAccurate", "94", "Remap" })
                Equal(true, json.Contains(field, StringComparison.Ordinal), "source semantics " + id + ": " + field);
            Equal(true, attack["draw"] is JsonObject, "source-selected native draw helper: " + id);
            Equal(true, attack["sourceMethods"]!.AsArray().Count >= 4, "each selected root/helper has source certificate");
            if (id == 982)
                foreach (string field in new[] { "DrawProj_Excalibur", "Frame", "1.1", "180", "160", "60", "240", "150" })
                    Equal(true, attack["draw"]!.ToJsonString().Contains(field, StringComparison.Ordinal), "Excalibur render source dependency: " + field);
        }
        var other = new Projectile(); other.SetDefaults(973);
        string negative = GeneratorClient.CaptureProjectileAttackReference(other).ToJsonString();
        Equal(false, negative.Contains("AI_190_NightsEdge", StringComparison.Ordinal), "AI191 primary never borrows secondary AI190 source");
        Equal(false, negative.Contains("DrawProj_Excalibur", StringComparison.Ordinal), "different primary never borrows another renderer");
        var sample = new Projectile(); sample.SetDefaults(982);
        var rejected = GeneratorClient.VerifiedProjectileAttackReference(sample, false);
        Equal(false, rejected.ContainsKey("motion"), "wrong native module remains unknown");
        Equal(true, rejected["coverage"]!.ToJsonString().Contains("module", StringComparison.Ordinal), "certificate refusal is explicit");
        typeof(Projectile).GetProperty(nameof(Projectile.ModProjectile))!.SetValue(sample, new AttackObservationModProjectile());
        Equal(false, GeneratorClient.CaptureProjectileAttackReference(sample).ContainsKey("motion"), "mod projectile does not borrow vanilla source");
    }
    private sealed class AttackObservationModProjectile : ModProjectile
    {
        public override void AI() { AttackObservationExecutions++; }
    }
}
