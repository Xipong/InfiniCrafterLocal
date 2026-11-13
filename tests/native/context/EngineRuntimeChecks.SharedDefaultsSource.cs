using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using System.Threading;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private sealed class SharedDefaultsFixture : Projectile
    {
        internal static int Executions;
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void Shared(bool allowed)
        {
            if (allowed && (type == 177 || type == 178))
            {
                Executions++;
                if (type == 177) minionSlots = 0.5f;
                else minionSlots = 1f;
            }
            if (type == 179) minionSlots = 2f;
            if (type >= 280 && type <= 283)
            {
                if (type == 281 || type == 282) minionSlots = 0.5f;
                width = 24;
            }
            if (type >= 900) width = 99;
            if (allowed || type == 270 || type == 271) width = 88;
            if (300 <= type && 303 >= type) width = 77;
            if (type >= 310 && type <= 313 && type <= 308) width = 66;
        }
    }

    private static void SharedDefaultsRemainConditionalSource()
    {
        var method = typeof(SharedDefaultsFixture).GetMethod(nameof(SharedDefaultsFixture.Shared))!;
        object Create(Type type, params object?[] values) => Activator.CreateInstance(type, CSharpFlags, null, values, null)!;
        using var module = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpModule", CSharpFlags)!, method.Module.FullyQualifiedName,
            File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        using var document = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpDocument", CSharpFlags)!, method, module, CancellationToken.None);
        JsonObject? Read(int type, int bound = 24000, CancellationToken token = default)
            => (JsonObject?)CSharpOwner.GetMethod("BuildSharedProjectileDefaults", CSharpFlags)!.Invoke(null, new object[] { document, type, token, bound });
        SharedDefaultsFixture.Executions = 0;
        object declaration = document.GetType().GetField("Declaration", CSharpFlags)!.GetValue(document)!;
        string original = declaration.ToString()!;
        var first = Read(177)!; var second = Read(178)!;
        Equal(first["records"]!.ToJsonString(), second["records"]!.ToJsonString(), "shared source keeps alternative identities, not specialized profiles");
        string code = first["records"]![0]!["code"]!.GetValue<string>();
        foreach (string fact in new[] { "allowed", "177", "178", "0.5f", "1f", "else" })
            Equal(true, code.Contains(fact, StringComparison.Ordinal), "whole shared arm retains " + fact);
        Equal(true, Read(179) is null, "single identity defaults are already available as native snapshot");
        Equal(true, Read(180) is null, "unrelated type receives no guessed source");
        var range = Read(280)!;
        Equal(1, range["records"]!.AsArray().Count, "one whole shared range, no duplicate nested region");
        string rangeCode = range["records"]![0]!["code"]!.GetValue<string>();
        foreach (string fact in new[] { "280", "283", "281", "282", "minionSlots", "width" })
            Equal(true, rangeCode.Contains(fact, StringComparison.Ordinal), "shared range retains alternate body " + fact);
        Equal(true, Read(900) is null, "open ended domain is not a shared identity witness");
        Equal(true, Read(270) is null, "unknown disjunction cannot establish finite relevance");
        Equal(true, Read(301) is not null, "reversed finite inequalities are supported");
        Equal(true, Read(311) is null, "disjoint interval intersection has no relevance");
        var bounded = Read(177, 1)!;
        Equal(0, bounded["records"]!.AsArray().Count, "bound never truncates a conditional body");
        Equal(1, bounded["unresolved"]!.AsArray().Count, "bound remains explicitly unknown");
        Equal(original, declaration.ToString()!, "shared cached syntax is unchanged");
        Equal(0, SharedDefaultsFixture.Executions, "source inspection never executes hooks or fixture body");
        bool cancelled = false;
        try { Read(177, token: new CancellationToken(true)); }
        catch (TargetInvocationException error) when (error.InnerException is OperationCanceledException) { cancelled = true; }
        Equal(true, cancelled, "source inspection honors cancellation");
    }

    private static void SharedDefaultsReachCompositeParent()
    {
        using var state = new NativeActorState();
        var packet = JsonNode.Parse(new InfiniCrafterLocal.Common.Services.GeneratorClient().Prepare(
            new Item(ItemID.StardustDragonStaff), new Item(ItemID.StardustCellStaff), new Player()).PayloadJson)!;
        var profile = packet["itemA"]!["directProjectileRaw"]!;
        var conditional = profile["mechanicsSource"]!["conditionalDefaults"]!;
        Equal("conditional_shared_projectile_defaults", conditional["source"]!.GetValue<string>(), "conditional provenance travels with source");
        var roots = conditional["roots"]!.AsArray();
        Equal(true, roots.All(root => root!["unresolved"]!.AsArray().Count == 0), "shared defaults fit source budget");
        string code = string.Join("\n", roots.SelectMany(root => root!["records"]!.AsArray()).Select(row => row!["code"]!.GetValue<string>()));
        Equal(true, code.Contains("minionSlots", StringComparison.Ordinal), "native shared segment cost is visible");
        Equal(true, profile["conditionalDefaults"] is null, "conditional source is not a native default property");
    }
    private static void SharedDefaultsRecordingPreservesSource()
    {
        string directory = Directory.CreateTempSubdirectory("ifc-defaults-recording-").FullName;
        string path = Path.Combine(directory, "source.zip");
        var capture = CSharpOwner.GetMethod("CaptureSharedProjectileDefaults", CSharpFlags)!
            .CreateDelegate<Func<int, JsonObject?>>();
        bool recording = false;
        try
        {
            var projectile = new Projectile(); projectile.SetDefaults(ProjectileID.StardustDragon1);
            int type = projectile.type;
            string expected = capture(type)!.ToJsonString();
            GeneratorClient.BeginNativeSourcePackRecording(path); recording = true;
            Equal(expected, capture(type)!.ToJsonString(), "recording preserves conditional defaults bytes");
            GeneratorClient.CompleteNativeSourcePackRecording(); recording = false;
            var module = CSharpOwner.GetField("nativeCSharpModule", CSharpFlags)!.GetValue(null)!;
            using var reader = (IDisposable)PackSafetyCreate("NativeSourcePackReader", File.OpenRead(path), module, CancellationToken.None);
            using var scope = new PackSafetyScope(module, reader);
            var cached = capture(type)!;
            Equal(expected, cached.ToJsonString(), "packed and unpacked shared defaults are identical");
            cached["roots"]!.AsArray().Clear();
            Equal(expected, capture(type)!.ToJsonString(), "caller mutation cannot change cached defaults source");
        }
        finally
        {
            if (recording) GeneratorClient.CancelNativeSourcePackRecording();
            Directory.Delete(directory, recursive: true);
        }
    }

}
