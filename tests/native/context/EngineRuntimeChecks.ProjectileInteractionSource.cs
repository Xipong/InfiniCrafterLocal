using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private sealed class InteractionSourceFixture : Projectile
    {
        internal static int Executions;
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void ExternalDamage(int target)
        {
            Executions++;
            int amount = damage + target;
            if (type == 91) damage = amount;
        }
        public void SharedStyle()
        {
            if (aiStyle == 8 && type != 96) { velocity.X = -velocity.X; velocity.Y = -velocity.Y; }
        }
        public void ExternalBreak()
        {
            int amount = damage;
            while (active) { if (type == 91) { damage = amount; break; } damage++; }
        }
        public void ExceptionRegion()
        {
            if (type == 91) { try { damage++; } finally { damage--; } }
        }
        public void ForeignActor(Projectile other) { if (other.type == 91) damage++; }
        public void NegatedGuard() { if (!(type == 91 && damage > 0)) damage++; }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void SwitchSource()
        {
            switch (type)
            {
                case 91: case 92: damage++; break;
                case 93: damage += 200; break;
                case 94: damage += 300; break;
                case 95: damage += 400; break;
                default: damage = 999; break;
            }
        }
        public void SwitchGoto()
        {
            switch (type)
            {
                case 91: damage++; goto case 93;
                case 92: damage += 100; break;
                case 93: damage += 200; break;
                case 94: damage += 300; break;
                case 95: damage += 400; break;
            }
        }
        public void DynamicSpawn(int child)
        {
            if (type == 91) NewProjectile(null!, position.X, position.Y, 0f, 0f, child, damage, knockBack, owner);
        }
    }

    private class InteractionVirtualFixture { public virtual void Effect() { } }
    private class InteractionGenericFixture<T> { public void Effect() { } }

    private static JsonObject InteractionFixtureSource(string name, int type = 91, int style = 8,
        int characterLimit = 16000, CancellationToken cancellation = default)
    {
        var method = typeof(InteractionSourceFixture).GetMethod(name)!;
        var moduleType = CSharpOwner.GetNestedType("NativeCSharpModule", CSharpFlags)!;
        var documentType = CSharpOwner.GetNestedType("NativeCSharpDocument", CSharpFlags)!;
        object Create(Type target, params object?[] values) => Activator.CreateInstance(target, CSharpFlags, null, values, null)!;
        using var module = (IDisposable)Create(moduleType, method.Module.FullyQualifiedName,
            File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        using var document = (IDisposable)Create(documentType, method, module, CancellationToken.None);
        return (JsonObject)CSharpOwner.GetMethod("BuildProjectileInteractionSource", CSharpFlags)!.Invoke(null,
            new object[] { document, type, style, cancellation, 12, characterLimit, 48000 })!;
    }

    private static void ProjectileInteractionSourceKeepsExplicitUnknowns()
    {
        InteractionSourceFixture.Executions = 0;
        var value = InteractionFixtureSource(nameof(InteractionSourceFixture.ExternalDamage));
        Equal(1, value["records"]!.AsArray().Count, "hit source keeps region even when hit result is an external local");
        var record = value["records"]![0]!;
        Equal(false, record.AsObject().ContainsKey("at"), "coarse AST ranges are never presented as exact guard IL offsets");
        Equal(1, record["regionIndex"]!.GetValue<int>(), "region metadata is an explicit local ordinal");
        Equal(true, record["externalInputs"]!.AsArray().Any(input => input!["kind"]!.GetValue<string>() == "external_local"), "external damage is an explicit unknown entry local");
        Equal(false, record["coverage"]!.GetValue<string>().Contains("closed", StringComparison.Ordinal), "open source never claims complete local closure");
        Equal(false, value.ToJsonString().Contains("identitySelected", StringComparison.Ordinal), "relevance is not execution or identity preservation");
        var unrelated = InteractionFixtureSource(nameof(InteractionSourceFixture.ExternalDamage), type: 92);
        Equal(0, unrelated["records"]!.AsArray().Count, "unrelated type receives no borrowed hit source");
        Equal(0, InteractionFixtureSource(nameof(InteractionSourceFixture.ForeignActor))["records"]!.AsArray().Count, "foreign receiver cannot witness captured actor relevance");
        Equal(0, InteractionFixtureSource(nameof(InteractionSourceFixture.NegatedGuard))["records"]!.AsArray().Count, "negated equality is not a positive relevance witness");
        var positive = new ICSharpCode.Decompiler.CSharp.Syntax.BinaryOperatorExpression(
            new ICSharpCode.Decompiler.CSharp.Syntax.IdentifierExpression("type"),
            ICSharpCode.Decompiler.CSharp.Syntax.BinaryOperatorType.Equality,
            new ICSharpCode.Decompiler.CSharp.Syntax.PrimitiveExpression(91));
        var negated = new ICSharpCode.Decompiler.CSharp.Syntax.UnaryOperatorExpression(
            ICSharpCode.Decompiler.CSharp.Syntax.UnaryOperatorType.Not, positive);
        Equal(false, (bool)CSharpOwner.GetMethod("PositiveInteractionEquality", CSharpFlags)!.Invoke(null, new object[] { positive, negated })!, "an equality nested under boolean negation cannot qualify even if the decompiler retains that AST");
        var style = InteractionFixtureSource(nameof(InteractionSourceFixture.SharedStyle));
        Equal(1, style["records"]!.AsArray().Count, "style family source remains discoverable without item ID rules");
        Equal(true, style["records"]![0]!["code"]!.GetValue<string>().Contains("type != 96", StringComparison.Ordinal), "negative type guard is retained literally, not evaluated or dropped");
        foreach (var name in new[] { nameof(InteractionSourceFixture.ExternalBreak), nameof(InteractionSourceFixture.ExceptionRegion) })
        {
            var refused = InteractionFixtureSource(name);
            Equal(0, refused["records"]!.AsArray().Count, "external locals do not mask unsupported control: " + name);
            Equal(true, refused["unresolved"]!.ToJsonString().Contains("nonlocal_control", StringComparison.Ordinal), "control refusal is explicit: " + name);
        }
        var switched = InteractionFixtureSource(nameof(InteractionSourceFixture.SwitchSource));
        Equal(1, switched["records"]!.AsArray().Count, "native switch section is an independent source region");
        string switchCode = switched["records"]![0]!["code"]!.GetValue<string>();
        Equal(true, switchCode.StartsWith("switch (type)", StringComparison.Ordinal), "original switch selector is not rewritten to if");
        Equal(true, switchCode.Contains("case 91:", StringComparison.Ordinal) && switchCode.Contains("case 92:", StringComparison.Ordinal), "all labels sharing the admitted section stay together");
        Equal(false, switchCode.Contains("case 93:", StringComparison.Ordinal), "unrelated switch sections are not borrowed");
        Equal(0, InteractionFixtureSource(nameof(InteractionSourceFixture.SwitchGoto))["records"]!.AsArray().Count, "goto another case refuses the whole partial section");
        var dispatch = CSharpOwner.GetMethod("InteractionHelperDispatchExact", CSharpFlags)!;
        foreach (var method in new[] { typeof(InteractionVirtualFixture).GetMethod("Effect")!, typeof(InteractionGenericFixture<>).GetMethod("Effect")! })
            Equal(false, (bool)dispatch.Invoke(null, new object[] { method })!, "virtual/open-generic helper dispatch remains unknown");
        var dynamic = InteractionFixtureSource(nameof(InteractionSourceFixture.DynamicSpawn));
        Equal(1, dynamic["records"]![0]!["spawnSites"]!.AsArray().Count, "runtime child callsite is retained");
        Equal(0, dynamic["records"]![0]!["spawnSites"]![0]!["projectileTypes"]!.AsArray().Count, "runtime child expression never becomes a guessed identity");
        Equal(true, dynamic["records"]![0]!["spawnSites"]![0]!["unresolved"]!.GetValue<string>().Contains("runtime_expression", StringComparison.Ordinal), "unknown dynamic child reason retained");
        var bounded = InteractionFixtureSource(nameof(InteractionSourceFixture.ExternalDamage), characterLimit: 1);
        Equal(0, bounded["records"]!.AsArray().Count, "oversize region is refused whole");
        Equal(true, bounded["unresolved"]!.ToJsonString().Contains("interaction_region_character_bound", StringComparison.Ordinal), "exact bound retained");
        using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
        CSharpSourceRefuses(() => InteractionFixtureSource(nameof(InteractionSourceFixture.ExternalDamage), cancellation: cancelled.Token), "canceled");
        Equal(0, InteractionSourceFixture.Executions, "source inspection never executes fixture/gameplay");
        var roots = new JsonArray(); var methods = new JsonArray();
        foreach (string root in new[] { "Damage", "StatusNPC", "HandleMovement" })
        {
            var certificate = new JsonObject { ["method"] = "Terraria.Projectile." + root,
                ["sourceModuleVersionId"] = "00000000-0000-0000-0000-000000000001", ["sourceMethodSha256"] = new string('a', 64) };
            methods.Add(certificate.DeepClone());
            var sourceRecord = certificate.DeepClone().AsObject(); sourceRecord["code"] = "original";
            roots.Add(new JsonObject { ["root"] = root, ["rootCertificate"] = certificate, ["helpers"] = new JsonArray(),
                ["records"] = new JsonArray(sourceRecord) });
        }
        var projectile = new JsonObject { ["type"] = 91, ["attackReference"] = new JsonObject {
            ["source"] = "read_only_native_attack_source", ["version"] = 1, ["sourceMethods"] = methods,
            ["interactionSources"] = new JsonObject { ["source"] = "verified_conditional_native_interaction_csharp", ["version"] = 1, ["roots"] = roots } } };
        var original = FingerprintSourceViewFixture(false, projectile);
        Equal(false, original["fingerprint"]!["directProjectileRaw"]!["attackReference"]!.AsObject().ContainsKey("interactionSources"), "backed source display omitted only from fingerprint");
        Equal(true, original["directProjectileRaw"]!["attackReference"]!.AsObject().ContainsKey("interactionSources"), "raw source display retained");
        methods.Clear();
        Equal(true, FingerprintSourceViewFixture(false, projectile)["fingerprint"]!["directProjectileRaw"]!["attackReference"]!.AsObject().ContainsKey("interactionSources"), "unbacked source cannot disappear from fingerprint");
    }

    private static JsonObject NativeInteractionSource(int type, int style)
        => NativeInteractionCapture(type, style, out _);

    private static JsonObject NativeInteractionCapture(int type, int style, out JsonArray calls)
    {
        calls = new JsonArray();
        return (JsonObject)CSharpOwner.GetMethod("CaptureProjectileInteractionSource", CSharpFlags)!.Invoke(null,
            new object[] { type, style, (Action<MethodBase>)(_ => { }), calls })!;
    }

    private static void ProjectileInteractionSourceKeepsNativeHitAndBounce()
    {
        var vampire = NativeInteractionCapture(ProjectileID.VampireKnife, 2, out var vampireCalls);
        var water = NativeInteractionSource(ProjectileID.WaterBolt, 8);
        var cool = NativeInteractionCapture(ProjectileID.CoolWhip, 165, out var coolCalls);
        var fire = NativeInteractionSource(ProjectileID.FireWhip, 165);
        static string Code(JsonObject value) => string.Join("\n", value["roots"]!.AsArray().SelectMany(root =>
            root!["records"]!.AsArray().Concat(root["helpers"]!.AsArray())).Select(record => record!["code"]!.GetValue<string>()));
        Equal(true, Code(vampire).Contains("vampireHeal", StringComparison.Ordinal), "native hit source retains VampireHeal call/body");
        Equal(true, Code(vampire).Contains("lifeSteal", StringComparison.Ordinal), "one-hop lifesteal resource limit is visible");
        Equal(true, vampireCalls.Any(call => call!["method"]!.GetValue<string>() == "Terraria.Projectile.vampireHeal"
            && call["projectileTypes"]!.AsArray().Any(id => id!.GetValue<int>() == ProjectileID.VampireHeal)), "native vampire helper contributes literal heal child305");
        Equal(true, coolCalls.Any(call => call!["projectileTypes"]!.AsArray().Any(id => id!.GetValue<int>() == ProjectileID.CoolWhipProj)), "native CoolWhip hit contributes literal child917");
        foreach (var calls in new[] { vampireCalls, coolCalls })
        {
            var graph = GeneratorClient.BuildReferencedProjectileSnapshots(calls, (id, allowed) =>
                (true, allowed ? new JsonObject { ["type"] = id } : null, null));
            Equal(true, graph!["references"]!.AsArray().Count > 0, "exact admitted source calls reach existing bounded descendant owner");
            Equal(calls.ToJsonString(), graph["sourceCalls"]!.ToJsonString(), "bounded owner preserves callsite conditions and multiplicity");
        }
        Equal(true, Code(water).Contains("velocity.X = 0f -", StringComparison.Ordinal) || Code(water).Contains("velocity.X = -", StringComparison.Ordinal), "native movement collision retains x reflection");
        Equal(true, Code(water).Contains("type != 96", StringComparison.Ordinal), "Water Bolt shares a guarded style branch; no exclusion is erased");
        Equal(true, Code(cool).Contains("NewProjectile", StringComparison.Ordinal), "Cool Whip conditional hit source retains spawn");
        Equal(true, Code(fire).Contains("AddBuff", StringComparison.Ordinal), "Firecracker conditional hit source retains status");
        foreach (var value in new[] { vampire, water, cool, fire })
        {
            foreach (var root in value["roots"]!.AsArray())
            {
                var records = root!["records"]!.AsArray().Concat(root["helpers"]!.AsArray());
                int size = 0;
                foreach (var record in records)
                {
                    string code = record!["code"]!.GetValue<string>(); size += code.Length;
                    Equal(Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(code))).ToLowerInvariant(), record["codeSha256"]!.GetValue<string>(), "native code certificate binds complete text");
                    Equal(true, code.Length <= 16000, "per-record bound");
                }
                Equal(true, size <= 48000, "total source bound per native root");
            }
        }
        var arrow = NativeInteractionSource(ProjectileID.WoodenArrowFriendly, 1);
        Equal(false, Code(arrow).Contains("vampireHeal", StringComparison.Ordinal), "ordinary arrow never borrows lifesteal source");
        Equal(vampire.ToJsonString(), NativeInteractionSource(ProjectileID.VampireKnife, 2).ToJsonString(), "native interaction source repeat deterministic");
    }
}
