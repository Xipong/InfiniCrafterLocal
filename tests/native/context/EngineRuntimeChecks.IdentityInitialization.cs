using System;
using System.Linq;
using System.Reflection;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    // Inspection only. The opaque initializer and fixture bodies never run.
    private static class IdentityInitializationTable
    {
        internal static int Value = 1;
        static IdentityInitializationTable() { IdentityInitializerHost.Unknown(); }
        internal static int Read(Projectile actor) => Value + actor.owner;
    }
    private static int IdentityInitializationBefore(Projectile actor)
    {
        int value = IdentityInitializationTable.Value;
        int other = IdentityInitializationTable.Read(actor);
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
        return value + other;
    }
    private static int IdentityInitializationBothBranches(Projectile actor)
    {
        int value;
        if (actor.wet) value = IdentityInitializationTable.Value;
        else value = IdentityInitializationTable.Value + 1;
        int other = IdentityInitializationTable.Read(actor);
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
        return value + other;
    }
    private static int IdentityInitializationOneBranch(Projectile actor)
    {
        int value = actor.wet ? IdentityInitializationTable.Value : 0;
        int other = IdentityInitializationTable.Read(actor);
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
        return value + other;
    }
    private static int IdentityInitializationAfter(Projectile actor)
    {
        int other = IdentityInitializationTable.Read(actor);
        int value = IdentityInitializationTable.Value;
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
        return value + other;
    }
    private static int IdentityInitializationLoop(Projectile actor)
    {
        int value = 0;
        while (actor.wet) value += IdentityInitializationTable.Value;
        int other = IdentityInitializationTable.Read(actor);
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
        return value + other;
    }
    private static int IdentityInitializationContextCache(Projectile actor)
    {
        int value = 0;
        if (actor.wet)
        {
            value = IdentityInitializationTable.Value;
            value += IdentityInitializationTable.Read(actor);
        }
        value += IdentityInitializationTable.Read(actor);
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
        return value;
    }
    private static class IdentityInitializationForeignTable
    {
        internal static int Value = 1;
        static IdentityInitializationForeignTable() { IdentityInitializerHost.Unknown(); }
    }
    private static int IdentityInitializationMutatingGetter(Projectile actor)
    { actor.type = 983; return IdentityInitializationTable.Value; }
    private static int IdentityInitializationEscapingGetter(Projectile actor)
    { IdentityInitializerHost.Actor = actor; return IdentityInitializationTable.Value; }
    private static int IdentityInitializationOpaqueGetter(Projectile actor)
    { IdentityInitializerHost.Unknown(); return IdentityInitializationTable.Value + actor.owner; }
    private static int IdentityInitializationForeignGetter(Projectile actor)
    { return IdentityInitializationForeignTable.Value + actor.owner; }
    private static int IdentityInitializationMutating(Projectile actor)
    {
        int value = IdentityInitializationTable.Value + IdentityInitializationMutatingGetter(actor);
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
        return value;
    }
    private static int IdentityInitializationEscaping(Projectile actor)
    {
        int value = IdentityInitializationTable.Value + IdentityInitializationEscapingGetter(actor);
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
        return value;
    }
    private static int IdentityInitializationOpaque(Projectile actor)
    {
        int value = IdentityInitializationTable.Value + IdentityInitializationOpaqueGetter(actor);
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
        return value;
    }
    private static int IdentityInitializationForeign(Projectile actor)
    {
        int value = IdentityInitializationTable.Value + IdentityInitializationForeignGetter(actor);
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
        return value;
    }
    private static int IdentityInitializationPriorMutation(Projectile actor)
    {
        IdentityInitializationMutatingGetter(actor);
        int value = IdentityInitializationTable.Value + IdentityInitializationTable.Read(actor);
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
        return value;
    }
    private static void ProjectileIdentityInitializationContinuationIsContextual()
    {
        foreach (var name in new[] { nameof(IdentityInitializationBefore), nameof(IdentityInitializationBothBranches) })
        {
            var proof = GeneratorClient.InspectProjectileAttackIdentitySource(
                typeof(EngineRuntimeChecks).GetMethod(name, BindingFlags.NonPublic | BindingFlags.Static)!, 982, 190);
            Equal(true, proof["identitySelection"]!["selectedEdges"]!.AsArray().Count > 0,
                "prior static access on every path prevents another initializer invocation: " + name);
            Equal(0, proof["identitySelection"]!["blockedIdentityReads"]!.AsArray().Count,
                "later pure getter has no new initializer effect: " + name);
            Equal(true, proof["identitySelection"]!["scope"]!.GetValue<string>().Contains("hidden global effects"),
                "prior field access is not a claim to model hidden global mutation");
        }
        foreach (var name in new[] { nameof(IdentityInitializationOneBranch), nameof(IdentityInitializationAfter),
            nameof(IdentityInitializationLoop), nameof(IdentityInitializationContextCache),
            nameof(IdentityInitializationMutating), nameof(IdentityInitializationEscaping),
            nameof(IdentityInitializationOpaque), nameof(IdentityInitializationForeign), nameof(IdentityInitializationPriorMutation) })
        {
            var proof = GeneratorClient.InspectProjectileAttackIdentitySource(
                typeof(EngineRuntimeChecks).GetMethod(name, BindingFlags.NonPublic | BindingFlags.Static)!, 982, 190);
            Equal(0, proof["identitySelection"]!["selectedEdges"]!.AsArray().Count,
                "uncovered path or another callsite must retain initializer barrier: " + name);
            Equal(true, proof["identitySelection"]!["blockedIdentityReads"]!.AsArray().Count > 0,
                "initializer uncertainty has exact refusal witness: " + name);
        }
        const BindingFlags flags = BindingFlags.NonPublic | BindingFlags.Public | BindingFlags.Static | BindingFlags.Instance;
        var owner = typeof(GeneratorClient);
        var fixture = typeof(EngineRuntimeChecks).GetMethod(nameof(IdentityInitializationBefore), flags)!;
        var code = owner.GetMethod("AttackCode", flags)!.Invoke(null, new object[] { fixture });
        var sliced = Activator.CreateInstance(owner.GetNestedType("ParentSourceMethod", flags)!, flags, null,
            new object?[] { fixture, code, null, null }, null)!;
        var selection = Activator.CreateInstance(owner.GetNestedType("AttackIdentitySelection", flags)!, flags, null,
            new object[] { sliced, 982, 190, true }, null)!;
        var receipt = (System.Text.Json.Nodes.JsonObject)selection.GetType().GetField("Receipt", flags)!.GetValue(selection)!;
        Equal(0, receipt["selectedEdges"]!.AsArray().Count, "a slice cannot certify its own apparent initialization prefix");
        Equal(true, receipt["blockedIdentityReads"]!.AsArray().Count > 0, "slice initialization boundary stays explicit");
        var method = typeof(Projectile).GetMethod("AI_062", BindingFlags.NonPublic | BindingFlags.Instance)!;
        var native = GeneratorClient.InspectProjectileAttackIdentitySource(method, 613, 62);
        var blocked = native["identitySelection"]!["blockedIdentityReads"]!.AsArray();
        Equal(false, blocked.OfType<System.Text.Json.Nodes.JsonObject>().Any(row =>
            row["hazardMember"]!.GetValue<string>().Contains("get_OwnerMinionAttackTargetNPC")),
            "real Cell minion getter cannot rerun Main initializer after earlier Main field access");
        var spawn = GeneratorClient.InspectProjectileSpawnSource(method, 613, 62);
        Equal("614", string.Join(",", HelperSpawnTypes(spawn)), "real Cell source keeps only its native child identity");
        Equal(true, spawn["sourceCalls"]!.AsArray().All(row => row!["requiredPredicates"]!.AsArray().Count > 0),
            "Cell child is still conditional on runtime targeting and attack state");
        Equal(true, native["identitySelection"]!["priorStaticAccesses"]!.AsArray().Count > 0,
            "static-access premise is recorded without claiming completed initialization");
    }
}
