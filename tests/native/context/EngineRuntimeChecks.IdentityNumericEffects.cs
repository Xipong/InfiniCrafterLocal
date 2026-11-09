using System;
using System.Reflection;
using Microsoft.Xna.Framework;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    // These bodies are inspected, never invoked. The assertions exercise the
    // same producer used by real capture, including its continuation proof.
    private static class IdentityNumericEffects
    {
        private static float epsilon;
        static IdentityNumericEffects() { epsilon = Epsilon(); }
        private static float Epsilon() { float value = 1f; value *= 0.5f; return value; }
        private static float Reassign(float value) { value *= 0.5f; return value; }
        internal static void Write(Projectile actor)
        {
            actor.alpha = (int)Reassign(epsilon + 1f);
            actor.rotation = (float)((double)(actor.damage + 1234567890123L) + 0.5d);
        }
    }
    private static class IdentityReferenceSlotEffects
    {
        internal static void Write(Projectile actor)
        {
            actor = actor.active ? actor : null!;
            if (actor is not null) actor.alpha = 1;
        }
    }
    private static class IdentityByRefSlotEffects
    {
        internal static void Write(Projectile actor) { Set(ref actor.alpha); }
        private static void Set(ref int value) { value = 123; }
    }
    private static class IdentityStructStoreEffects
    {
        private static Vector2 slot;
        internal static void Write(Projectile actor) { Store(actor.velocity); }
        private static void Store(Vector2 value) { slot = value; }
    }
    private static class IdentityReferenceStoreEffects
    {
        private static Projectile slot = null!;
        internal static void Write(Projectile actor) { slot = actor; }
    }
    private static class IdentityInitializerHost
    {
        internal static Projectile Actor = null!;
        internal static Action Unknown = null!;
    }
    private static class IdentityMutatingInitializer
    {
        static IdentityMutatingInitializer() { IdentityInitializerHost.Actor.type = 983; }
        internal static void Write(Projectile actor) { actor.alpha = 1; }
    }
    private static class IdentityOpaqueInitializer
    {
        static IdentityOpaqueInitializer() { IdentityInitializerHost.Unknown(); }
        internal static void Write(Projectile actor) { actor.alpha = 1; }
    }
    private static class IdentityEscapingInitializer
    {
        private static Projectile escaped = null!;
        static IdentityEscapingInitializer() { escaped = IdentityInitializerHost.Actor; }
        internal static void Write(Projectile actor) { actor.alpha = 1; }
    }
    private static class IdentityRecursiveEffects
    {
        internal static void Write(Projectile actor) { Write(actor); }
    }
    private static class IdentityCyclicInitializerA
    {
        static IdentityCyclicInitializerA() { IdentityCyclicInitializerB.Value(); }
        internal static int Value() => 1;
        internal static void Write(Projectile actor) { actor.alpha = 1; }
    }
    private static class IdentityCyclicInitializerB
    {
        static IdentityCyclicInitializerB() { IdentityCyclicInitializerA.Value(); }
        internal static int Value() => 1;
    }
    private static class IdentityFailedInitializerCache
    {
        static IdentityFailedInitializerCache() { Pure(); PureWithActor(null!); IdentityInitializerHost.Actor.type = 983; }
        internal static int Pure() => 1;
        internal static void PureWithActor(Projectile actor) { actor.alpha = 1; }
        internal static void Write(Projectile actor) { actor.alpha = 1; }
    }
    private static void IdentityNumericContinuation(Projectile actor)
    { IdentityNumericEffects.Write(actor); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }
    private static void IdentityReferenceSlotContinuation(Projectile actor)
    { IdentityReferenceSlotEffects.Write(actor); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }
    private static void IdentityByRefSlotContinuation(Projectile actor)
    { IdentityByRefSlotEffects.Write(actor); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }
    private static void IdentityStructStoreContinuation(Projectile actor)
    { IdentityStructStoreEffects.Write(actor); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }
    private static void IdentityReferenceStoreContinuation(Projectile actor)
    { IdentityReferenceStoreEffects.Write(actor); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }
    private static void IdentityMutatingInitializerContinuation(Projectile actor)
    { IdentityMutatingInitializer.Write(actor); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }
    private static void IdentityOpaqueInitializerContinuation(Projectile actor)
    { IdentityOpaqueInitializer.Write(actor); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }
    private static void IdentityEscapingInitializerContinuation(Projectile actor)
    { IdentityEscapingInitializer.Write(actor); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }
    private static void IdentityRecursiveContinuation(Projectile actor)
    { IdentityRecursiveEffects.Write(actor); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }
    private static void IdentityCyclicInitializerContinuation(Projectile actor)
    { IdentityCyclicInitializerA.Write(actor); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }
    private static void IdentityFailedInitializerContinuation(Projectile actor)
    { IdentityFailedInitializerCache.Write(actor); actor.alpha = IdentityFailedInitializerCache.Pure(); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }

    private static void IdentityConditionalCacheContinuation(Projectile actor)
    {
        if (actor.type == 999) IdentityFailedInitializerCache.Write(actor);
        IdentityFailedInitializerCache.PureWithActor(actor);
        if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f;
    }
    private static void IdentitySourceWrapperContinuation(Projectile actor)
    { actor.GetSource_FromThis(); if (actor.type == 982) actor.scale = 1.25f; else actor.scale = 2.5f; }

    private static void ProjectileIdentityNumericEffectsPreserveBarriers()
    {
        foreach (var name in new[] { nameof(IdentityNumericContinuation), nameof(AttackIdentityOpacitySetter) })
        {
            var proof = GeneratorClient.InspectProjectileAttackIdentitySource(
                typeof(EngineRuntimeChecks).GetMethod(name, BindingFlags.NonPublic | BindingFlags.Static)!, 982, 190);
            Equal(true, proof["identitySelection"]!["selectedEdges"]!.AsArray().Count > 0,
                "closed numeric effects preserve captured identity: " + name);
            Equal(0, proof["identitySelection"]!["blockedIdentityReads"]!.AsArray().Count,
                "numeric effects have no stale refusal: " + name);
            Equal(false, proof.ToJsonString().Contains("2.5", StringComparison.Ordinal), "certified branch is absent: " + name);
        }
        var cacheProof = GeneratorClient.InspectProjectileAttackIdentitySource(
            typeof(EngineRuntimeChecks).GetMethod(nameof(IdentityConditionalCacheContinuation), BindingFlags.NonPublic | BindingFlags.Static)!, 982, 190);
        Equal(true, cacheProof["identitySelection"]!["selectedEdges"]!.AsArray().Count > 0, "foreign first call is excluded");
        Equal(true, cacheProof["identitySelection"]!["blockedIdentityReads"]!.AsArray().Count > 0,
            "failed initializer cannot publish conditional helper as globally safe");
        Equal(true, cacheProof.ToJsonString().Contains("2.5", StringComparison.Ordinal),
            "unsafe initializer on surviving call retains later alternatives");
        foreach (var name in new[] { nameof(IdentityReferenceSlotContinuation), nameof(IdentityByRefSlotContinuation),
            nameof(IdentityStructStoreContinuation), nameof(IdentityReferenceStoreContinuation),
            nameof(IdentityMutatingInitializerContinuation), nameof(IdentityOpaqueInitializerContinuation),
            nameof(IdentityEscapingInitializerContinuation), nameof(IdentityRecursiveContinuation),
            nameof(IdentityCyclicInitializerContinuation), nameof(IdentityFailedInitializerContinuation),
            nameof(IdentitySourceWrapperContinuation) })
        {
            var proof = GeneratorClient.InspectProjectileAttackIdentitySource(
                typeof(EngineRuntimeChecks).GetMethod(name, BindingFlags.NonPublic | BindingFlags.Static)!, 982, 190);
            Equal(0, proof["identitySelection"]!["selectedEdges"]!.AsArray().Count,
                "alias/initialization/recursion barrier is retained: " + name);
            Equal(true, proof["identitySelection"]!["blockedIdentityReads"]!.AsArray().Count > 0,
                "refused numeric extension reports a witness: " + name);
            Equal(true, proof.ToJsonString().Contains("2.5", StringComparison.Ordinal), "uncertain branch remains: " + name);
        }
    }
}
