using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private static void VerifyNativeSourcePackTarget(string manifestPath)
    {
        var manifest = JsonNode.Parse(File.ReadAllText(manifestPath))!.AsObject();
        if (manifest["schema"]!.GetValue<string>() != "ifc_native_target_staging_v1"
            || manifest["runtimeVersion"]!.GetValue<string>() != Environment.Version.ToString()
            || manifest["runtimeIdentifier"]!.GetValue<string>() != RuntimeInformation.RuntimeIdentifier)
            throw new InvalidDataException("Native target runtime differs from the official staging manifest.");
        string trusted = AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES") as string
            ?? throw new InvalidOperationException("The CLR trusted platform assembly roster is unavailable.");
        var paths = new Dictionary<string, string>(StringComparer.OrdinalIgnoreCase);
        foreach (string path in trusted.Split(Path.PathSeparator, StringSplitOptions.RemoveEmptyEntries))
        {
            string name = Path.GetFileName(path);
            if (paths.TryGetValue(name, out string? prior) && prior != path)
                throw new InvalidDataException("Ambiguous trusted platform assembly: " + name);
            paths[name] = path;
        }
        int verified = 0;
        foreach (var row in manifest["assets"]!.AsArray().OfType<JsonObject>())
        {
            string name = row["fileName"]!.GetValue<string>();
            if (!paths.TryGetValue(name, out string? path)
                || new FileInfo(path).Length != row["bytes"]!.GetValue<long>()
                || NativeSourcePackFileHash(path) != row["sha256"]!.GetValue<string>())
                throw new InvalidDataException("CLR selected different bytes for " + name + ": " + path);
            verified++;
        }
        if (verified == 0) throw new InvalidDataException("The target staging manifest contains no managed assets.");
        Console.WriteLine("NATIVE_TARGET_VERIFIED " + new JsonObject {
            ["runtimeVersion"] = Environment.Version.ToString(), ["runtimeIdentifier"] = RuntimeInformation.RuntimeIdentifier,
            ["assemblies"] = verified, ["stagingManifestSha256"] = NativeSourcePackFileHash(manifestPath)
        }.ToJsonString());
    }

    // Offline build input enumeration uses the complete native identity ranges.
    // SetDefaults supplies the real type/aiStyle pair; no AI, world or draw runs.
    // An ordinary craft never enters this collector or constructs this catalog.
    private static void BuildNativeSourcePack(string outputPath)
    {
        string output = Path.GetFullPath(outputPath);
        Directory.CreateDirectory(Path.GetDirectoryName(output)!);
        string reportPath = output + ".report.json";
        var timer = Stopwatch.StartNew();
        var identities = new JsonArray();
        var errors = new JsonArray();
        var gaps = new SortedDictionary<string, int>(StringComparer.Ordinal);
        var report = new JsonObject
        {
            ["schema"] = "ifc_native_source_pack_build_v1", ["status"] = "incomplete",
            ["scope"] = "Offline source projections for every positive vanilla ProjectileID and ItemID. Projectile.SetDefaults supplies identities; item dispatcher roots depend only on Item.type. No game/world/AI/draw, provider calls, benchmark roster or saved player state.",
            ["nativeMvid"] = typeof(Projectile).Module.ModuleVersionId.ToString(),
            ["nativeAssemblySha256"] = NativeSourcePackFileHash(typeof(Projectile).Assembly.Location),
            ["decompilerAssemblySha256"] = NativeSourcePackFileHash(typeof(ICSharpCode.Decompiler.CSharp.CSharpDecompiler).Assembly.Location),
            ["collectorAssemblySha256"] = NativeSourcePackFileHash(typeof(EngineRuntimeChecks).Assembly.Location),
            ["projectionSha256"] = NativeSourcePackBuild.ProjectionSha256,
            ["runtimeVersion"] = Environment.Version.ToString(),
            ["projectileCount"] = ProjectileID.Count - 1, ["itemCount"] = ItemID.Count - 1,
            ["excludedIdentities"] = "0 is None/inactive; every positive ID below the corresponding native Count is visited",
            ["identities"] = identities, ["errors"] = errors
        };
        using var cancellation = new CancellationTokenSource();
        ConsoleCancelEventHandler interrupt = (_, args) => { args.Cancel = true; cancellation.Cancel(); };
        Console.CancelKeyPress += interrupt;
        bool recording = false;
        try
        {
            using var state = new NativeActorState();
            Terraria.Main.netMode = NetmodeID.SinglePlayer;
            Terraria.Main.rand = new Terraria.Utilities.UnifiedRandom(91);
            // Clear once so no earlier harness call can hide a recording entry.
            // Reuse bounded source/IL/AST caches throughout the exhaustive pass.
            GeneratorClient.ParentAnalysis.Invalidate();
            using var sourceCache = new GeneratorClient.ParentSourceGraphCache(shared: true);
            using var scope = sourceCache.Enter();
            var itemCapture = typeof(GeneratorClient).GetMethod("CaptureNativeItemDispatchReference",
                BindingFlags.Static | BindingFlags.NonPublic)!.CreateDelegate<Func<int, JsonObject>>();
            GeneratorClient.BeginNativeSourcePackRecording(output);
            recording = true;
            Console.WriteLine("NATIVE_SOURCE_PACK start=" + output);
            for (int id = 1; id < ProjectileID.Count; id++)
            {
                cancellation.Token.ThrowIfCancellationRequested();
                try
                {
                    var projectile = new Projectile();
                    projectile.SetDefaults(id);
                    if (projectile.type != id || projectile.ModProjectile is not null)
                        throw new InvalidOperationException("Native defaults changed the requested projectile identity.");
                    Record("projectile", id, projectile.aiStyle,
                        GeneratorClient.VerifiedProjectileAttackReference(projectile, moduleVerified: true));
                }
                catch (Exception error) when (error is not OperationCanceledException and not OutOfMemoryException)
                { Failure("projectile", id, error); }
                Progress("projectile", id, ProjectileID.Count - 1);
            }
            for (int id = 1; id < ItemID.Count; id++)
            {
                cancellation.Token.ThrowIfCancellationRequested();
                try { Record("item", id, null, itemCapture(id)); }
                catch (Exception error) when (error is not OperationCanceledException and not OutOfMemoryException)
                { Failure("item", id, error); }
                Progress("item", id, ItemID.Count - 1);
            }
            cancellation.Token.ThrowIfCancellationRequested();
            if (errors.Count != 0)
                throw new InvalidOperationException("Native source pack has failed identity captures; inspect " + reportPath);
            GeneratorClient.CompleteNativeSourcePackRecording();
            recording = false;
            report["status"] = "complete";
            report["packSha256"] = NativeSourcePackFileHash(output);
            report["packBytes"] = new FileInfo(output).Length;
        }
        catch (OperationCanceledException)
        {
            report["status"] = "cancelled";
            throw;
        }
        finally
        {
            if (recording) GeneratorClient.CancelNativeSourcePackRecording();
            Console.CancelKeyPress -= interrupt;
            report["elapsedMs"] = timer.Elapsed.TotalMilliseconds;
            report["capturedIdentities"] = identities.Count;
            report["gapIdentityCounts"] = JsonSerializer.SerializeToNode(gaps);
            File.WriteAllText(reportPath, report.ToJsonString(new JsonSerializerOptions { WriteIndented = true }));
            Console.WriteLine("NATIVE_SOURCE_PACK report=" + reportPath + " status=" + report["status"]!.GetValue<string>());
        }

        void Record(string kind, int id, int? style, JsonObject value)
        {
            byte[] bytes = JsonSerializer.SerializeToUtf8Bytes(value);
            string[] found = NativeSourcePackGaps(value).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray();
            foreach (string gap in found) gaps[gap] = gaps.GetValueOrDefault(gap) + 1;
            var row = new JsonObject
            {
                ["kind"] = kind, ["type"] = id,
                ["referenceSha256"] = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(),
                ["referenceBytes"] = bytes.Length,
                ["gaps"] = new JsonArray(found.Select(gap => (JsonNode?)JsonValue.Create(gap)).ToArray())
            };
            if (style.HasValue) row["aiStyle"] = style.Value;
            identities.Add(row);
        }

        void Failure(string kind, int id, Exception error)
        {
            var row = new JsonObject { ["kind"] = kind, ["type"] = id,
                ["errorType"] = error.GetType().FullName, ["message"] = error.Message };
            errors.Add(row);
            Console.Error.WriteLine("NATIVE_SOURCE_PACK error=" + row.ToJsonString());
        }

        void Progress(string kind, int completed, int total)
        {
            if (completed % 32 == 0 || completed == total)
                Console.WriteLine(FormattableString.Invariant(
                    $"NATIVE_SOURCE_PACK kind={kind} completed={completed}/{total} errors={errors.Count} elapsed_ms={timer.Elapsed.TotalMilliseconds:F1}"));
        }
    }

    private static string NativeSourcePackFileHash(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static IEnumerable<string> NativeSourcePackGaps(JsonNode? value)
    {
        if (value is JsonObject obj)
            foreach (var pair in obj)
            {
                if (pair.Key is "unknowns" or "unresolved" or "unavailable")
                {
                    if (pair.Value is JsonValue text && text.TryGetValue<string>(out string? message) && message is not null)
                        yield return message;
                    else if (pair.Value is JsonArray messages)
                        foreach (var entry in messages.OfType<JsonValue>())
                            if (entry.TryGetValue<string>(out string? entryText) && entryText is not null) yield return entryText;
                }
                foreach (string gap in NativeSourcePackGaps(pair.Value)) yield return gap;
            }
        else if (value is JsonArray array)
            foreach (var entry in array)
                foreach (string gap in NativeSourcePackGaps(entry)) yield return gap;
    }
}
