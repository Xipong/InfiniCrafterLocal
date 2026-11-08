using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Threading;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private sealed class LifecycleSourceFixture : Projectile
    {
        internal static int Executions;
        private static void Hook(Projectile actor) { Executions++; actor.type = 92; }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void UnknownMutation(int child)
        {
            Hook(this);
            if ((type == 91 || type == 92) && owner == Terraria.Main.myPlayer)
            {
                if (ai[0] > 0f)
                {
                    int amount = damage / 3;
                    int index = NewProjectile(null!, position.X, position.Y, velocity.X, velocity.Y, child, amount, knockBack, owner);
                    Terraria.Main.projectile[index].ai[1] = position.Y;
                }
            }
        }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void ExternalLocal()
        {
            int amount = damage;
            if (type == 91) NewProjectile(null!, position.X, position.Y, 0f, 0f, 92, amount, knockBack, owner);
        }
        public void ExceptionRegion()
        {
            if (type == 91)
            {
                try { NewProjectile(null!, position.X, position.Y, 0f, 0f, 92, damage, knockBack, owner); }
                finally { damage++; }
            }
        }
        public void NonlocalControl()
        {
            while (active)
            {
                if (type == 91) { NewProjectile(null!, position.X, position.Y, 0f, 0f, 92, damage, knockBack, owner); break; }
                damage++;
            }
        }
        public void NoSpawn() { if (type == 91) damage++; }
    }

    private static JsonObject LifecycleFixtureSource(string name, out JsonArray calls, int characterLimit = 24000,
        CancellationToken cancellation = default)
    {
        var method = typeof(LifecycleSourceFixture).GetMethod(name)!;
        var moduleType = CSharpOwner.GetNestedType("NativeCSharpModule", CSharpFlags)!;
        var documentType = CSharpOwner.GetNestedType("NativeCSharpDocument", CSharpFlags)!;
        object Create(Type type, params object?[] values) => Activator.CreateInstance(type, CSharpFlags, null, values, null)!;
        using var module = (IDisposable)Create(moduleType, method.Module.FullyQualifiedName,
            File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        using var document = (IDisposable)Create(documentType, method, module, CancellationToken.None);
        calls = new JsonArray();
        return (JsonObject)CSharpOwner.GetMethod("BuildProjectileLifecycleSource", CSharpFlags)!.Invoke(null,
            new object[] { document, 91, 1, calls, cancellation, 16, characterLimit, 64000 })!;
    }

    private static void ProjectileLifecycleKeepsConditionalNativeSource()
    {
        var attack = GeneratorClient.CaptureProjectileAttackReference(new Projectile { type = 91, aiStyle = 1 });
        Equal(true, attack["lifecycle"] is JsonObject, "native Kill source must have explicit lifecycle coverage");
        var lifecycle = attack["lifecycle"]!.AsObject();
        Equal(true, lifecycle["records"]!.AsArray().Count > 0, "HolyArrow retains a closed conditional Kill region");
        string code = string.Join("\n", lifecycle["records"]!.AsArray().Select(row => row!["code"]!.GetValue<string>()));
        foreach (string fragment in new[] { "type == 91", "type == 92", "owner == Main.myPlayer", "ai[0] > 0", "NewProjectile", "/= 3", ".ai[1]", ".ai[0]" })
            Equal(true, code.Contains(fragment, StringComparison.Ordinal), "complete lifecycle source retains " + fragment);
        Equal(false, lifecycle.ToJsonString().Contains("identitySelected", StringComparison.Ordinal), "conditional regions never borrow an entry identity proof");
        foreach (var record in lifecycle["records"]!.AsArray().OfType<JsonObject>())
        {
            Equal(Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(record["code"]!.GetValue<string>()))).ToLowerInvariant(),
                record["codeSha256"]!.GetValue<string>(), "region certificate binds the complete code");
            Equal(true, record["spawnSites"]!.AsArray().OfType<JsonObject>().Any(site => site["projectileTypes"]!.AsArray().Any(id => id!.GetValue<int>() == 92)), "literal child92 has a native source site");
        }
        var cycle = GeneratorClient.CaptureProjectileAttackReference(new Projectile { type = 92, aiStyle = 1 })["lifecycle"]!.AsObject();
        Equal(code, string.Join("\n", cycle["records"]!.AsArray().Select(row => row!["code"]!.GetValue<string>())), "type92 retains the same complete compound source, including its state-dependent cycle");
        Equal(true, cycle["scope"]!.GetValue<string>().Contains("captured-entry identity preservation", StringComparison.Ordinal), "the hook/identity boundary is explicit for cyclic candidates too");
        var arrow = GeneratorClient.CaptureProjectileAttackReference(new Projectile { type = 1, aiStyle = 1 })["lifecycle"]!.AsObject();
        Equal(0, arrow["records"]!.AsArray().Count, "unrelated arrow receives no borrowed HolyArrow source");
        Equal(true, arrow["unresolved"]!.ToJsonString().Contains("absence_not_proved", StringComparison.Ordinal), "no region is not proof of no lifecycle effects");
        string cached = GeneratorClient.CaptureProjectileAttackReference(new Projectile { type = 91, aiStyle = 1 })["lifecycle"]!.ToJsonString();
        Equal(lifecycle.ToJsonString(), cached, "cached native source is deterministic");
        lifecycle["records"]!.AsArray().Clear();
        Equal(cached, GeneratorClient.CaptureProjectileAttackReference(new Projectile { type = 91, aiStyle = 1 })["lifecycle"]!.ToJsonString(), "caller mutation cannot poison the source cache");
        ProjectileLifecycleRecordingKeepsExactProjection();
    }

    private static void ProjectileLifecycleRecordingKeepsExactProjection()
    {
        string directory = Directory.CreateTempSubdirectory("ifc-lifecycle-recording-").FullName;
        string path = Path.Combine(directory, "source.zip");
        var capture = CSharpOwner.GetMethod("CaptureProjectileLifecycleSource", CSharpFlags)!
            .CreateDelegate<Func<int, int, JsonArray, JsonObject>>();
        var method = PackSafetyMethod();
        bool recording = false;
        try
        {
            var references = new JsonArray();
            var expected = capture(91, 1, references);
            string expectedBytes = expected.ToJsonString(), referenceBytes = references.ToJsonString();
            GeneratorClient.BeginNativeSourcePackRecording(path);
            recording = true;
            var recordedReferences = new JsonArray();
            var recorded = capture(91, 1, recordedReferences);
            Equal(expectedBytes, recorded.ToJsonString(), "enabling lifecycle recording preserves exact source bytes");
            Equal(referenceBytes, recordedReferences.ToJsonString(), "enabling lifecycle recording preserves exact source-call order");
            GeneratorClient.CompleteNativeSourcePackRecording();
            recording = false;
            var module = CSharpOwner.GetField("nativeCSharpModule", CSharpFlags)!.GetValue(null)!;
            using var reader = (IDisposable)PackSafetyCreate("NativeSourcePackReader", File.OpenRead(path), module, CancellationToken.None);
            string key = PackSafetyKey(method, new JsonObject { ["type"] = 91, ["style"] = 1 }, "projectile_lifecycle");
            Equal(true, PackSafetyRead(reader, key, CancellationToken.None, out var projection, "projectile_lifecycle"), "the live lifecycle builder records a readable projection");
            Equal(expectedBytes, projection!["result"]!.ToJsonString(), "recorded lifecycle source retains exact bytes");
            Equal(referenceBytes, projection["references"]!.ToJsonString(), "recorded lifecycle calls retain exact bytes");
            recorded["records"]!.AsArray().Clear(); recordedReferences.Clear();
            Equal(true, PackSafetyRead(reader, key, CancellationToken.None, out projection, "projectile_lifecycle"), "recorded projection remains readable after caller mutation");
            Equal(expectedBytes, projection!["result"]!.ToJsonString(), "recording never aliases caller-owned source");
            Equal(referenceBytes, projection["references"]!.ToJsonString(), "recording never aliases caller-owned source calls");
        }
        finally
        {
            if (recording) GeneratorClient.CancelNativeSourcePackRecording();
            Directory.Delete(directory, recursive: true);
        }
    }

    private static void ProjectileLifecycleRefusesIncompleteRegions()
    {
        LifecycleSourceFixture.Executions = 0;
        var dynamic = LifecycleFixtureSource(nameof(LifecycleSourceFixture.UnknownMutation), out var calls);
        Equal(1, dynamic["records"]!.AsArray().Count, "a reached conditional region remains readable after an unknown prior mutation");
        Equal(0, calls.Single()!["projectileTypes"]!.AsArray().Count, "dynamic child type never becomes a literal profile");
        Equal(true, calls.Single()!["unresolved"]!.GetValue<string>().Contains("runtime_expression", StringComparison.Ordinal), "dynamic child gets an explicit diagnostic");
        string code = dynamic["records"]![0]!["code"]!.GetValue<string>();
        foreach (string fragment in new[] { "91", "92", "owner ==", "myPlayer", "ai[0] > 0", "child", ".ai[1]" })
            Equal(true, code.Contains(fragment, StringComparison.Ordinal), "compound guard and post-spawn closure survives: " + fragment);
        Equal(false, dynamic.ToJsonString().Contains("identitySelected", StringComparison.Ordinal), "prior hook is never bypassed by a local identity proof");
        foreach (var (name, reason) in new[] {
            (nameof(LifecycleSourceFixture.ExternalLocal), "external_local_dependency"),
            (nameof(LifecycleSourceFixture.ExceptionRegion), "nonlocal_control_unsupported"),
            (nameof(LifecycleSourceFixture.NonlocalControl), "nonlocal_control_unsupported") })
        {
            var refused = LifecycleFixtureSource(name, out var rejected);
            Equal(0, refused["records"]!.AsArray().Count, "incomplete region is rejected in full: " + name);
            Equal(0, rejected.Count, "refused region cannot leak a child profile: " + name);
            Equal(true, refused["unresolved"]!.ToJsonString().Contains(reason, StringComparison.Ordinal), "specific refusal: " + name);
        }
        var bounded = LifecycleFixtureSource(nameof(LifecycleSourceFixture.UnknownMutation), out calls, characterLimit: 1);
        Equal(0, bounded["records"]!.AsArray().Count, "size bound refuses, never crops a body or guard");
        Equal(0, calls.Count, "bounded region emits no orphan spawn references");
        Equal(true, bounded["unresolved"]!.ToJsonString().Contains("lifecycle_region_character_bound", StringComparison.Ordinal), "exact size refusal retained");
        using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
        CSharpSourceRefuses(() => LifecycleFixtureSource(nameof(LifecycleSourceFixture.UnknownMutation), out _, cancellation: cancelled.Token), "canceled");
        CSharpSourceRefuses(() => LifecycleFixtureSource(nameof(LifecycleSourceFixture.NoSpawn), out _, cancellation: cancelled.Token), "canceled");
        Equal(0, LifecycleSourceFixture.Executions, "read-only native evidence never runs a hook or gameplay source");
    }

    private static void ProjectileLifecycleFingerprintKeepsNativeIdentity()
    {
        var certificate = new JsonObject { ["method"] = "Terraria.Projectile.Kill", ["sourceModuleVersionId"] = "00000000-0000-0000-0000-000000000001", ["sourceMethodSha256"] = new string('a', 64) };
        var projectile = new JsonObject { ["type"] = 91, ["meaningfulNull"] = null,
            ["attackReference"] = new JsonObject { ["source"] = "read_only_native_attack_source", ["version"] = 1,
                ["sourceMethods"] = new JsonArray(certificate.DeepClone()),
                ["lifecycle"] = new JsonObject { ["source"] = "verified_conditional_native_lifecycle_csharp", ["version"] = 1,
                    ["rootCertificate"] = certificate.DeepClone(), ["code"] = "original", ["unresolved"] = "diagnostic" } },
            ["referencedProjectiles"] = new JsonObject { ["sourceCalls"] = new JsonArray(new JsonObject {
                ["method"] = "Terraria.Projectile.Kill", ["at"] = 10, ["projectileTypes"] = new JsonArray(92),
                ["requiredPredicates"] = new JsonArray("b5"), ["unresolved"] = "conditional; hooks unknown" }),
                ["references"] = new JsonArray(new JsonObject { ["type"] = 92 }) } };
        foreach (bool deferred in new[] { false, true })
        {
            var original = FingerprintSourceViewFixture(deferred, projectile);
            var fingerprint = original["fingerprint"]!;
            var formatting = projectile.DeepClone().AsObject();
            formatting["attackReference"]!["lifecycle"]!["code"] = "new formatting";
            formatting["attackReference"]!["lifecycle"]!["unresolved"] = "changed diagnostic presentation";
            Equal(true, JsonNode.DeepEquals(fingerprint, FingerprintSourceViewFixture(deferred, formatting)["fingerprint"]), "lifecycle display formatting/diagnostics do not change fingerprint");
            Equal("original", original["directProjectileRaw"]!["attackReference"]!["lifecycle"]!["code"]!.GetValue<string>(), "root retains complete source display");
            AssertParentFingerprintNativeFacts(original["directProjectileRaw"], fingerprint["directProjectileRaw"], "lifecycle canonical identity observer", true);
            foreach (string change in new[] { "call", "child", "il", "guard", "family", "version", "certificate_missing", "certificate_incomplete", "certificate_wrong_root" })
            {
                var altered = projectile.DeepClone().AsObject();
                if (change == "call") altered["referencedProjectiles"]!["sourceCalls"]![0]!["at"] = 11;
                if (change == "child") altered["referencedProjectiles"]!["references"]![0]!["type"] = 93;
                if (change == "guard") altered["referencedProjectiles"]!["sourceCalls"]![0]!["requiredPredicates"] = new JsonArray("b6");
                if (change == "il") altered["attackReference"]!["sourceMethods"]![0]!["sourceMethodSha256"] = "changed-il";
                if (change == "family") altered["attackReference"]!["lifecycle"]!["source"] = "unknown-source";
                if (change == "version") altered["attackReference"]!["lifecycle"]!["version"] = 2;
                if (change == "certificate_missing") altered["attackReference"]!["sourceMethods"]!.AsArray().Clear();
                if (change == "certificate_incomplete")
                {
                    altered["attackReference"]!["lifecycle"]!["rootCertificate"] = new JsonObject();
                    altered["attackReference"]!["sourceMethods"] = new JsonArray(new JsonObject());
                }
                if (change == "certificate_wrong_root")
                {
                    altered["attackReference"]!["lifecycle"]!["rootCertificate"]!["method"] = "Terraria.Projectile.AI";
                    altered["attackReference"]!["sourceMethods"]![0]!["method"] = "Terraria.Projectile.AI";
                }
                Equal(false, JsonNode.DeepEquals(fingerprint, FingerprintSourceViewFixture(deferred, altered)["fingerprint"]), "native/literal lifecycle identity remains significant: " + change);
                if (change is "family" or "version" or "certificate_missing" or "certificate_incomplete" or "certificate_wrong_root")
                    Equal(true, FingerprintSourceViewFixture(deferred, altered)["fingerprint"]!["directProjectileRaw"]!["attackReference"]!.AsObject().ContainsKey("lifecycle"), "unrecognized or unbacked view is not removed: " + change);
            }
            Equal(true, fingerprint["directProjectileRaw"]!.AsObject().ContainsKey("meaningfulNull") && fingerprint["directProjectileRaw"]!["meaningfulNull"] is null, "native null is retained");
        }
    }
}
