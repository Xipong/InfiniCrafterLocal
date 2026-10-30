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
            var snapshot = System.Text.Json.JsonSerializer.SerializeToNode(
                GeneratorClient.ProjectileRawSnapshot(id, 0f, "native_cpu_fixture", null, -1))!.AsObject();
            Equal(true, snapshot["attackReference"] is JsonObject, "real native snapshot includes attack reference");
            Equal(projectile.penetrate, snapshot["penetrate"]!.GetValue<int>(), "literal native penetration retained");
            Equal(projectile.maxPenetrate, snapshot["maxPenetrate"]!.GetValue<int>(), "literal native maximum penetration retained");
            Equal(projectile.usesLocalNPCImmunity, snapshot["usesLocalNPCImmunity"]!.GetValue<bool>(), "literal local immunity retained");
            Equal(projectile.localNPCHitCooldown, snapshot["localNPCHitCooldown"]!.GetValue<int>(), "literal local repeat cooldown retained");
            Equal(projectile.usesIDStaticNPCImmunity, snapshot["usesIDStaticNPCImmunity"]!.GetValue<bool>(), "literal static immunity retained");
            Equal(projectile.idStaticNPCHitCooldown, snapshot["idStaticNPCHitCooldown"]!.GetValue<int>(), "literal static cooldown retained");
            Equal(projectile.stopsDealingDamageAfterPenetrateHits, snapshot["stopsDealingDamageAfterPenetrateHits"]!.GetValue<bool>(), "damage-stop distinct from visual lifetime");
            if (id == 982 && Environment.GetEnvironmentVariable("INFINI_DUMP_ATTACK_REFERENCE") is string output)
                System.IO.File.WriteAllText(output, snapshot.ToJsonString(new System.Text.Json.JsonSerializerOptions { WriteIndented = true }));
            Equal(true, attack["motion"] is JsonObject, "native controller source found: " + id);
            foreach (string field in new[] { "Projectile.scale", "Projectile.rotation", "Projectile.localAI", "Projectile.ai", "MountedCenter", "RotatedRelativePoint", "Kill", "IntersectsConeSlowMoreAccurate", "94", "Remap" })
                Equal(true, json.Contains(field, StringComparison.Ordinal), "source semantics " + id + ": " + field);
            Equal(true, attack["draw"] is JsonObject, "source-selected native draw helper: " + id);
            Equal(true, attack["sourceMethods"]!.AsArray().Count >= 4, "each selected root/helper has source certificate");
            if (id == 982)
            {
                var cone = attack["collision"]!["predicateSources"]!.AsArray().Select(n => n!.AsObject())
                    .Single(n => n["method"]!.GetValue<string>().EndsWith(".DoesFitInCone", StringComparison.Ordinal));
                var bounds = cone["predicates"]!.AsArray();
                Equal(2, bounds.Count, "native cone retains both angular bounds");
                Equal(bounds[0]!["inputs"]![0]!.GetValue<string>(), bounds[1]!["inputs"]![0]!.GetValue<string>(), "both angular bounds read the same named angle");
                Equal(false, cone.ToJsonString().Contains("loop_or_alias", StringComparison.Ordinal), "acyclic cone helper has no false recursive marker");
            }
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
    private static Projectile? AttackOtherProjectile = null;
    private static void AttackIdentitySource(Projectile projectile)
    {
        if (projectile.type == 982) projectile.scale = 1.25f;
        else projectile.scale = 2.5f;
        if (projectile.ai[0] > 0f) projectile.rotation = 0.2f;
        else projectile.rotation = 0.6f;
    }
    private static void AttackIdentityDirectCall(Projectile projectile) => AttackIdentitySource(projectile);
    private static void AttackIdentityForeignCall(Projectile projectile) => AttackIdentitySource(AttackOtherProjectile!);
    private static void AttackIdentityChangedBeforeCall(Projectile projectile) { projectile.type = 983; AttackIdentitySource(projectile); }
    private static void AttackIdentityEscapedBeforeCall(Projectile projectile) { AttackMutateActor(projectile); AttackIdentitySource(projectile); }
    private static void AttackIdentityExceptionBeforeCall(Projectile projectile)
    {
        try { AttackMutateActor(projectile); } catch (InvalidOperationException) { }
        AttackIdentitySource(projectile);
    }
    private static void AttackIdentityExceptionAfterCall(Projectile projectile)
    {
        AttackIdentitySource(projectile);
        try { AttackMutateActor(projectile); } catch (InvalidOperationException) { }
    }
    private static void AttackIdentityIndirectStore(Projectile projectile, ref Projectile sink)
    {
        sink = projectile;
        if (projectile.type == 982) projectile.scale = 1.25f;
        else projectile.scale = 2.5f;
    }
    private static void AttackIdentityWrongReceiver(Projectile projectile)
    {
        if (AttackOtherProjectile!.type == 982) projectile.scale = 1.25f;
        else projectile.scale = 2.5f;
    }
    private static void AttackIdentityMutable(Projectile projectile)
    {
        projectile.type = 983;
        if (projectile.type == 982) projectile.scale = 1.25f;
        else projectile.scale = 2.5f;
    }
    private static void AttackIdentityEscape(Projectile projectile)
    {
        AttackMutateIdentity(ref projectile.type);
        if (projectile.type == 982) projectile.scale = 1.25f;
        else projectile.scale = 2.5f;
    }
    private static void AttackIdentityCallEscape(Projectile projectile)
    {
        AttackMutateActor(projectile);
        if (projectile.type == 982) projectile.scale = 1.25f;
        else projectile.scale = 2.5f;
    }
    private static void AttackIdentityConditionalEscape(Projectile projectile)
    {
        var alias = projectile.ai[0] > 0f ? projectile : AttackOtherProjectile!;
        AttackMutateActor(alias);
        if (projectile.type == 982) projectile.scale = 1.25f;
        else projectile.scale = 2.5f;
    }
    private static void AttackIdentityLocalAddressEscape(Projectile projectile)
    {
        var alias = projectile;
        AttackMutateActorAddress(ref alias);
        if (projectile.type == 982) projectile.scale = 1.25f;
        else projectile.scale = 2.5f;
    }
    private static void AttackMutateActorAddress(ref Projectile projectile) { projectile.type = 983; }
    private static void AttackMutateActor(Projectile projectile) { projectile.type = 983; }
    private static void AttackIdentityDominatingWrite(Projectile projectile)
    {
        float growth = 0.2f;
        if (projectile.type == 982) growth = 0.6f;
        projectile.scale = growth;
    }
    private static void AttackMutateIdentity(ref int identity) { identity = 983; }
    private static void ProjectileAttackIdentitySelectionKeepsUnknownConditions()
    {
        JsonObject Inspect(string name) => GeneratorClient.InspectProjectileAttackIdentitySource(
            typeof(EngineRuntimeChecks).GetMethod(name, BindingFlags.NonPublic | BindingFlags.Static)!, 982, 190);
        MethodInfo Method(string name) => typeof(EngineRuntimeChecks).GetMethod(name, BindingFlags.NonPublic | BindingFlags.Static)!;
        Equal(true, GeneratorClient.InspectProjectileAttackCallBinding(Method(nameof(AttackIdentityDirectCall)), Method(nameof(AttackIdentitySource))), "direct helper receives the captured actor");
        Equal(false, GeneratorClient.InspectProjectileAttackCallBinding(Method(nameof(AttackIdentityForeignCall)), Method(nameof(AttackIdentitySource))), "foreign helper actor cannot borrow captured identity");
        foreach (string caller in new[] { nameof(AttackIdentityChangedBeforeCall), nameof(AttackIdentityEscapedBeforeCall), nameof(AttackIdentityExceptionBeforeCall) })
            Equal(false, GeneratorClient.InspectProjectileAttackCallBinding(Method(caller), Method(nameof(AttackIdentitySource))), "caller must preserve actor identity before helper: " + caller);
        Equal(true, GeneratorClient.InspectProjectileAttackCallBinding(Method(nameof(AttackIdentityExceptionAfterCall)), Method(nameof(AttackIdentitySource))), "unrelated later exception arm does not hide complete call prefix");
        var selected = Inspect(nameof(AttackIdentitySource));
        string json = selected.ToJsonString();
        Equal(true, json.Contains("1.25", StringComparison.Ordinal), "matching identity assignment remains");
        Equal(false, json.Contains("2.5", StringComparison.Ordinal), "other identity assignment is unreachable");
        Equal(true, json.Contains("0.2", StringComparison.Ordinal) && json.Contains("0.6", StringComparison.Ordinal), "both runtime AI alternatives remain");
        var reaching = Inspect(nameof(AttackIdentityDominatingWrite)).ToJsonString();
        Equal(true, reaching.Contains("0.6", StringComparison.Ordinal), "identity selected reaching definition remains");
        Equal(false, reaching.Contains("0.2", StringComparison.Ordinal), "overwritten initialization is not a reaching alternative");
        foreach (string name in new[] { nameof(AttackIdentityWrongReceiver), nameof(AttackIdentityMutable), nameof(AttackIdentityEscape), nameof(AttackIdentityCallEscape), nameof(AttackIdentityConditionalEscape), nameof(AttackIdentityLocalAddressEscape), nameof(AttackIdentityIndirectStore) })
        {
            var refused = Inspect(name);
            Equal(0, refused["identitySelection"]!["selectedEdges"]!.AsArray().Count, "uncertified identity cannot select: " + name);
            Equal(true, refused.ToJsonString().Contains("2.5", StringComparison.Ordinal), "uncertified alternative retained: " + name);
        }
        foreach (int type in new[] { 982, 983, 984, 997, 972 })
        {
            var projectile = new Projectile(); projectile.SetDefaults(type);
            var programs = GeneratorClient.CaptureProjectileAttackReference(projectile)["motion"]!["programs"]!.AsArray();
            var raw = programs[0]!.AsObject();
            Equal(true, raw["identitySelected"] is JsonObject, "native identity specialization exists: " + type);
            var native = raw["identitySelected"]!;
            Equal(type, native["identitySelection"]!["identityPredicates"]!["Projectile.type"]!.GetValue<int>(), "specialized identity never borrowed from sibling");
            Equal(true, raw["predicates"]!.ToJsonString().Contains("972", StringComparison.Ordinal), "full raw source retains excluded sibling branch");
            if (type == 982)
                Equal(false, native["symbols"]!.AsObject().ContainsKey("Entity.position"), "Excalibur excludes sibling position controller");
            if (type == 972)
                Equal(true, native["symbols"]!.AsObject().ContainsKey("Entity.position"), "matching sibling retains its own position controller");
        }
    }
    private static void AttackIdentityUnreachableMutation(Projectile projectile)
    {
        if (projectile.type == 983) AttackMutateActor(projectile);
        if (projectile.type == 982) projectile.scale = 1.25f;
        else projectile.scale = 2.5f;
    }
    private static void AttackIdentityUnknownMutation(Projectile projectile)
    {
        if (projectile.ai[0] > 0f) AttackMutateActor(projectile);
        if (projectile.type == 982) projectile.scale = 1.25f;
        else projectile.scale = 2.5f;
    }
    private static void AttackIdentityUnsignedRange(Projectile projectile)
    {
        if ((uint)(projectile.type - 10) <= 2) projectile.scale = 1.25f;
        else projectile.scale = 2.5f;
    }
    private static void AttackMotionVectorComponents(Projectile projectile)
    {
        projectile.velocity.Y += 0.1f;
        if (projectile.velocity.Y > 16f) projectile.velocity.Y = 16f;
        projectile.position.X += projectile.velocity.X;
        var unrelated = new Microsoft.Xna.Framework.Vector2(); unrelated.Y = 999f;
        var copied = projectile.velocity; copied.Y = 777f;
        AttackOtherProjectile!.velocity.Y = 888f;
    }
    private static void ProjectileSharedAiCaptureSelectsBeforeSourceBudgets()
    {
        MethodInfo Method(string name) => typeof(EngineRuntimeChecks).GetMethod(name, BindingFlags.Static | BindingFlags.NonPublic)!;
        string selected = GeneratorClient.InspectProjectileAttackIdentitySource(Method(nameof(AttackIdentityUnreachableMutation)), 982, 190).ToJsonString();
        Equal(false, selected.Contains("2.5", StringComparison.Ordinal), "excluded foreign identity mutation cannot block later proven identity");
        var unknown = GeneratorClient.InspectProjectileAttackIdentitySource(Method(nameof(AttackIdentityUnknownMutation)), 982, 190);
        Equal(0, unknown["identitySelection"]!["selectedEdges"]!.AsArray().Count, "runtime-conditioned mutation still blocks selection");
        foreach (int type in new[] { 1, 10, 11, 12, 13 })
        {
            string range = GeneratorClient.InspectProjectileAttackIdentitySource(Method(nameof(AttackIdentityUnsignedRange)), type, 1).ToJsonString();
            Equal(type is >= 10 and <= 12, range.Contains("1.25", StringComparison.Ordinal), "unsigned subtraction range preserves underflow semantics");
            Equal(type is < 10 or > 12, range.Contains("2.5", StringComparison.Ordinal), "unsigned subtraction rejects outside range");
        }
        string components = GeneratorClient.InspectProjectileAttackSource(Method(nameof(AttackMotionVectorComponents)), "motion").ToJsonString();
        foreach (string fact in new[] { "Vector2.Y", "Entity.velocity", "Entity.position", "0.1", "16" })
            Equal(true, components.Contains(fact, StringComparison.Ordinal), "native vector component sink captured: " + fact);
        foreach (string excluded in new[] { "999", "777", "888" })
            Equal(false, components.Contains(excluded, StringComparison.Ordinal), "local/foreign vector is not captured actor motion: " + excluded);
        foreach (int type in new[] { ProjectileID.WoodenArrowFriendly, ProjectileID.FireArrow, ProjectileID.UnholyArrow })
        {
            var projectile = new Projectile(); projectile.SetDefaults(type);
            var reference = GeneratorClient.CaptureProjectileAttackReference(projectile);
            var raw = reference["motion"]!["programs"]![0]!.AsObject();
            var actual = raw["identitySelected"]!.AsObject();
            Equal(type, actual["identitySelection"]!["identityPredicates"]!["Projectile.type"]!.GetValue<int>(), "shared controller selected for exact native identity");
            Equal(true, actual["observations"]!.AsArray().Count > 0, "source budget cannot erase successful selected behavior");
            Equal(false, actual.ToJsonString().Contains("character_bound", StringComparison.Ordinal), "source length is not a rejection threshold");
            Equal(true, actual["symbols"]!.AsObject().ContainsKey("Entity.velocity"), "native actual projectile movement exposed");
            if (raw["coverage"]!.GetValue<string>() == "unknown")
            {
                string reason = raw["unresolved"]!.GetValue<string>();
                Equal(true, reason.StartsWith("connected_source_", StringComparison.Ordinal), "unselected audit retains exact resource refusal");
                Equal(true, reference["coverage"]!["unresolved"]!.AsArray().Any(gap => gap!.GetValue<string>().Contains(reason, StringComparison.Ordinal)), "resource refusal survives root coverage");
            }
            if (type == ProjectileID.WoodenArrowFriendly)
                foreach (string fact in new[] { "Projectile.ai", "Vector2.Y", "0.1", "15", "16", "Math.Atan2" })
                    Equal(true, actual.ToJsonString().Contains(fact, StringComparison.Ordinal), "actual arrow source dependency retained: " + fact);
        }
    }
    private sealed class AttackObservationModProjectile : ModProjectile
    {
        public override void AI() { AttackObservationExecutions++; }
    }
}
