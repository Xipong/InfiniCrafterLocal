#nullable enable
using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using InfiniCrafterLocal.Common.Analysis;

namespace InfiniCrafterLocal.Common.Services;

public sealed partial class GeneratorClient
{
    // Build-time memoization of the existing read-only source builders. Keys
    // contain their complete inputs, never item names, pairs or weapon classes.
    // A miss runs the same live reader; it cannot replace missing evidence.
    private const int NativeSourcePackVersion = 2;
    private const int NativeSourcePackMinimumIlBytes = 1;
    private const int NativeSourcePackEntryLimit = 30000;
    private const int NativeSourcePackEntryBytes = 4 * 1024 * 1024;
    private const int NativeSourcePackArchiveBytes = 128 * 1024 * 1024;
    private const string NativeSourcePackPath = "Data/native-source-pack.zip";
    private static NativeSourcePackReader? nativeSourcePackReader;
    private static bool nativeSourcePackReadAttempted;
    private static NativeSourcePackRecorder? nativeSourcePackRecorder;

    private static string NativeSourceProjectionKey(string kind, MethodInfo method, JsonObject input)
    {
        string identity = kind + "\n" + method.Module.ModuleVersionId + "\n"
            + method.MetadataToken.ToString(CultureInfo.InvariantCulture) + "\n"
            + CSharpHash(method.GetMethodBody()!.GetILAsByteArray()!) + "\n" + input.ToJsonString();
        return SourceAnalysisBuffers.HashUtf8(identity);
    }

    private static bool TryReadNativeSourceProjection(string kind, MethodInfo method,
        JsonObject input, CancellationToken cancellation, out JsonObject projection)
    {
        cancellation.ThrowIfCancellationRequested();
        projection = null!;
        if (nativeSourcePackRecorder is not null
            || (method.GetMethodBody()?.GetILAsByteArray()?.Length ?? 0) < NativeSourcePackMinimumIlBytes)
            return false;
        var module = GetVerifiedNativeCSharpModule(method, cancellation);
        if (!nativeSourcePackReadAttempted)
        {
            // An absent/incompatible bundle is a cache miss, not a source
            // refusal. Cancellation is retryable and never poisons this state.
            NativeSourcePackReader? opened = null;
            try
            {
                Stream? stream = null;
                if (Terraria.ModLoader.ModLoader.TryGetMod("InfiniCrafterLocal", out var mod))
                {
                    if (mod.FileExists(NativeSourcePackPath))
                        stream = mod.GetFileStream(NativeSourcePackPath, newFileStream: true);
                }
                else
                {
                    string path = System.IO.Path.Combine(AppContext.BaseDirectory, NativeSourcePackPath);
                    if (System.IO.File.Exists(path)) stream = System.IO.File.OpenRead(path);
                }
                if (stream is not null) opened = new NativeSourcePackReader(stream, module, cancellation);
                cancellation.ThrowIfCancellationRequested();
                nativeSourcePackReader = opened;
                nativeSourcePackReadAttempted = true;
            }
            catch (OperationCanceledException) { opened?.Dispose(); throw; }
            catch (Exception error) when (error is not OutOfMemoryException)
            {
                opened?.Dispose(); nativeSourcePackReadAttempted = true;
                if (ParentAnalysis.ProfileJobs)
                    Console.Error.WriteLine("PARENT_SOURCE_PACK unavailable=" + error.GetType().Name);
            }
        }
        if (nativeSourcePackReader is null) return false;
        bool found = nativeSourcePackReader.TryRead(NativeSourceProjectionKey(kind, method, input), kind, cancellation, out projection);
        cancellation.ThrowIfCancellationRequested();
        if (ParentAnalysis.ProfileJobs)
            Console.Error.WriteLine("PARENT_SOURCE_PACK action=" + (found ? "hit" : "miss")
                + " kind=" + kind + " method=" + SourceMember(method));
        return found;
    }

    private static void RecordNativeSourceProjection(string kind, MethodInfo method,
        JsonObject input, JsonObject projection, CancellationToken cancellation)
    {
        cancellation.ThrowIfCancellationRequested();
        if (nativeSourcePackRecorder is null
            || (method.GetMethodBody()?.GetILAsByteArray()?.Length ?? 0) < NativeSourcePackMinimumIlBytes) return;
        try { nativeSourcePackRecorder.Add(NativeSourceProjectionKey(kind, method, input), kind, projection, cancellation); }
        catch (Exception error)
        {
            // Existing source readers keep per-method diagnostics on failure.
            // Recording must still fail atomically if one of those readers
            // catches a collision or a write error before it reaches the CLI.
            nativeSourcePackRecorder.Fail(error);
            throw;
        }
    }

    internal static void BeginNativeSourcePackRecording(string outputPath)
    {
        lock (nativeCSharpGate)
        {
            if (nativeSourcePackRecorder is not null) throw new InvalidOperationException("native_source_pack_recording_already_active");
            nativeSourcePackRecorder = new NativeSourcePackRecorder(outputPath);
        }
    }

    internal static void CompleteNativeSourcePackRecording()
    {
        lock (nativeCSharpGate)
        {
            var recorder = nativeSourcePackRecorder ?? throw new InvalidOperationException("native_source_pack_recording_not_active");
            try { recorder.Complete(nativeCSharpModule ?? throw new InvalidOperationException("native_source_pack_has_no_native_module")); }
            finally { recorder.Dispose(); nativeSourcePackRecorder = null; }
        }
    }

    internal static void CancelNativeSourcePackRecording()
    {
        lock (nativeCSharpGate)
        {
            nativeSourcePackRecorder?.Dispose(); nativeSourcePackRecorder = null;
        }
    }

    private static byte[] ReadNativeSourcePackEntry(ZipArchiveEntry entry, int maximum, CancellationToken cancellation)
    {
        if (entry.Length < 0 || entry.Length > maximum) throw new InvalidDataException("native_source_pack_entry_size");
        // Keep established ZIP buffering until a full-process comparison shows
        // that the direct-buffer alternative improves this workload's peak RSS.
        using var input = entry.Open();
        using var output = new MemoryStream((int)entry.Length);
        byte[] buffer = new byte[16384];
        int count;
        while ((count = input.Read(buffer, 0, buffer.Length)) != 0)
        {
            cancellation.ThrowIfCancellationRequested();
            if (output.Length + count > maximum) throw new InvalidDataException("native_source_pack_entry_size");
            output.Write(buffer, 0, count);
        }
        cancellation.ThrowIfCancellationRequested();
        if (output.Length != entry.Length) throw new InvalidDataException("native_source_pack_entry_length");
        return output.ToArray();
    }

    private static bool NativeSourcePackHashValid(string value)
        => value.Length == 64 && value.All(character => character is >= '0' and <= '9' or >= 'a' and <= 'f');

    private static string NativeSourcePackIndexHash(JsonArray rows, JsonArray blobs)
        => CSharpHash(Encoding.UTF8.GetBytes(rows.ToJsonString() + "\n" + blobs.ToJsonString()));

    private static bool NativeSourcePackKindValid(string kind)
        => kind is "projectile_method" or "projectile_lifecycle" or "projectile_interaction" or "item_dispatch";

    private sealed class NativeSourcePackReader : IDisposable
    {
        private readonly ZipArchive archive;
        private readonly Dictionary<string, (string Kind, ZipArchiveEntry Entry, int Bytes, string Sha256)> entries = new(StringComparer.Ordinal);

        internal NativeSourcePackReader(Stream stream, NativeCSharpModule module, CancellationToken cancellation)
        {
            ZipArchive? opened = null;
            try
            {
                if (stream.GetType() != typeof(FileStream) && stream.GetType() != typeof(MemoryStream))
                {
                    // .tmod resources may be forward-only, or advertise Seek
                    // with nonstandard End semantics. Only our standard .NET
                    // streams are trusted for ZIP seeks. Bound resource copies
                    // before ZipArchive can implicitly buffer without a limit.
                    var buffered = new MemoryStream();
                    try
                    {
                        using (stream)
                        {
                            byte[] buffer = new byte[16384]; int count;
                            while ((count = stream.Read(buffer, 0, buffer.Length)) != 0)
                            {
                                cancellation.ThrowIfCancellationRequested();
                                if (buffered.Length + count > NativeSourcePackArchiveBytes)
                                    throw new InvalidDataException("native_source_pack_archive_size");
                                buffered.Write(buffer, 0, count);
                            }
                        }
                        buffered.Position = 0; stream = buffered;
                    }
                    catch { buffered.Dispose(); throw; }
                }
                if (stream.Length > NativeSourcePackArchiveBytes)
                    throw new InvalidDataException("native_source_pack_archive_size");
                archive = opened = new ZipArchive(stream, ZipArchiveMode.Read, leaveOpen: false);
                if (archive.Entries.Count > NativeSourcePackEntryLimit + 1)
                    throw new InvalidDataException("native_source_pack_entry_count");
                var metadata = archive.GetEntry("manifest.json") ?? throw new InvalidDataException("native_source_pack_manifest_missing");
                var manifest = JsonNode.Parse(ReadNativeSourcePackEntry(metadata, NativeSourcePackEntryBytes, cancellation))!.AsObject();
                if (manifest["version"]?.GetValue<int>() != NativeSourcePackVersion
                    || manifest["minimumMethodIlBytes"]?.GetValue<int>() != NativeSourcePackMinimumIlBytes
                    || manifest["projectionSha256"]?.GetValue<string>() != NativeSourcePackBuild.ProjectionSha256
                    || manifest["nativeAssemblySha256"]?.GetValue<string>() != module.Sha256
                    || manifest["nativeModuleVersionId"]?.GetValue<string>() != module.Mvid.ToString()
                    || manifest["decompilerVersion"]?.GetValue<string>() != NativeCSharpVersion
                    || manifest["decompilerSha256"]?.GetValue<string>() != NativeCSharpDecompilerSha256
                    || manifest["decompilerMvid"]?.GetValue<string>() != NativeCSharpDecompilerMvid
                    || manifest["settings"]?.GetValue<string>() != "csharp_default_no_indentation_v1")
                    throw new InvalidDataException("native_source_pack_identity_mismatch");
                _ = nativeCSharpDecompilerVerified.Value;
                if (manifest["dependencies"] is not JsonArray dependencies
                    || !NativeSourcePackDependenciesMatch(module, dependencies, cancellation))
                    throw new InvalidDataException("native_source_pack_dependency_mismatch");
                var rows = manifest["entries"]!.AsArray();
                var blobs = manifest["blobs"]!.AsArray();
                if (rows.Count == 0 || rows.Count > NativeSourcePackEntryLimit
                    || blobs.Count == 0 || blobs.Count > rows.Count || archive.Entries.Count != blobs.Count + 1)
                    throw new InvalidDataException("native_source_pack_entry_count");
                var names = new HashSet<string>(StringComparer.Ordinal);
                foreach (var entry in archive.Entries)
                {
                    cancellation.ThrowIfCancellationRequested();
                    if (!names.Add(entry.FullName)) throw new InvalidDataException("native_source_pack_index_invalid");
                }
                var pins = new (ZipArchiveEntry Entry, int Bytes, string Sha256)[blobs.Count];
                var used = new bool[blobs.Count];
                var hashes = new HashSet<string>(StringComparer.Ordinal);
                for (int index = 0; index < blobs.Count; index++)
                {
                    cancellation.ThrowIfCancellationRequested();
                    var blob = blobs[index]!.AsObject();
                    int bytes = blob["bytes"]!.GetValue<int>();
                    string sha = blob["sha256"]!.GetValue<string>();
                    if (blob.Count != 2 || !NativeSourcePackHashValid(sha) || !hashes.Add(sha)
                        || bytes <= 0 || bytes > NativeSourcePackEntryBytes
                        || archive.GetEntry(sha + ".json") is not { } entry || entry.Length != bytes)
                        throw new InvalidDataException("native_source_pack_index_invalid");
                    pins[index] = (entry, bytes, sha);
                }
                // Compact, nonrecursive rows retain every complete input key.
                // The integer points only into the unique content table, never
                // to another key. Kind is checked again at each requested hit.
                foreach (var value in rows)
                {
                    cancellation.ThrowIfCancellationRequested();
                    if (value is not JsonArray row || row.Count != 3)
                        throw new InvalidDataException("native_source_pack_index_invalid");
                    string key = row[0]!.GetValue<string>();
                    string kind = row[1]!.GetValue<string>();
                    int index = row[2]!.GetValue<int>();
                    if (!NativeSourcePackHashValid(key) || !NativeSourcePackKindValid(kind)
                        || index < 0 || index >= pins.Length)
                        throw new InvalidDataException("native_source_pack_index_invalid");
                    var pin = pins[index];
                    if (!entries.TryAdd(key, (kind, pin.Entry, pin.Bytes, pin.Sha256)))
                        throw new InvalidDataException("native_source_pack_index_invalid");
                    used[index] = true;
                }
                if (used.Any(value => !value)) throw new InvalidDataException("native_source_pack_index_invalid");
                cancellation.ThrowIfCancellationRequested();
                // Blob checksums alone cannot detect a key redirected to a
                // different valid blob. Bind the complete ordered association
                // table as well. This is corruption detection, not a signature.
                if (manifest["indexSha256"]?.GetValue<string>() != NativeSourcePackIndexHash(rows, blobs))
                    throw new InvalidDataException("native_source_pack_index_integrity");
                cancellation.ThrowIfCancellationRequested();
            }
            catch { if (opened is not null) opened.Dispose(); else stream.Dispose(); throw; }
        }

        internal bool TryRead(string key, string kind, CancellationToken cancellation, out JsonObject projection)
        {
            projection = null!;
            cancellation.ThrowIfCancellationRequested();
            if (!entries.TryGetValue(key, out var pin) || pin.Kind != kind) return false;
            try
            {
                byte[] bytes = ReadNativeSourcePackEntry(pin.Entry, NativeSourcePackEntryBytes, cancellation);
                if (bytes.Length != pin.Bytes || CSharpHash(bytes) != pin.Sha256) return false;
                projection = JsonNode.Parse(bytes)!.AsObject();
                cancellation.ThrowIfCancellationRequested();
                return true;
            }
            catch (OperationCanceledException) { throw; }
            catch (Exception error) when (error is not OutOfMemoryException) { return false; }
        }
        public void Dispose() => archive.Dispose();
    }

    private sealed class NativeSourcePackRecorder : IDisposable
    {
        private readonly string outputPath, temporaryPath;
        private readonly ZipArchive archive;
        private readonly SortedDictionary<string, JsonArray> entries = new(StringComparer.Ordinal);
        private readonly Dictionary<string, (int Index, int Bytes)> blobs = new(StringComparer.Ordinal);
        private bool completed, disposed;
        private Exception? failure;

        internal void Fail(Exception error) => failure ??= error;

        internal NativeSourcePackRecorder(string path)
        {
            outputPath = System.IO.Path.GetFullPath(path);
            Directory.CreateDirectory(System.IO.Path.GetDirectoryName(outputPath)!);
            temporaryPath = outputPath + "." + Guid.NewGuid().ToString("N") + ".tmp";
            archive = new ZipArchive(System.IO.File.Create(temporaryPath), ZipArchiveMode.Create, leaveOpen: false);
        }

        internal void Add(string key, string kind, JsonObject projection, CancellationToken cancellation)
        {
            cancellation.ThrowIfCancellationRequested();
            byte[] bytes = Encoding.UTF8.GetBytes(projection.ToJsonString());
            cancellation.ThrowIfCancellationRequested();
            if (bytes.Length > NativeSourcePackEntryBytes) return; // ordinary live path remains available
            if (!NativeSourcePackHashValid(key) || !NativeSourcePackKindValid(kind))
                throw new InvalidOperationException("native_source_pack_index_invalid");
            string sha = CSharpHash(bytes);
            bool shared = blobs.TryGetValue(sha, out var blob);
            if (shared && blob.Bytes != bytes.Length)
                throw new InvalidOperationException("native_source_pack_blob_conflict");
            if (entries.TryGetValue(key, out var previous))
            {
                if (!shared || previous[1]!.GetValue<string>() != kind || previous[2]!.GetValue<int>() != blob.Index)
                    throw new InvalidOperationException("native_source_pack_key_conflict");
                return;
            }
            if (entries.Count >= NativeSourcePackEntryLimit) throw new InvalidOperationException("native_source_pack_entry_count");
            cancellation.ThrowIfCancellationRequested();
            if (!shared)
            {
                blob = (blobs.Count, bytes.Length);
                Write(sha + ".json", bytes);
                blobs.Add(sha, blob);
            }
            entries.Add(key, new JsonArray(key, kind, blob.Index));
        }

        private void Write(string name, byte[] bytes)
        {
            var entry = archive.CreateEntry(name, CompressionLevel.Optimal);
            entry.LastWriteTime = new DateTimeOffset(2000, 1, 1, 0, 0, 0, TimeSpan.Zero);
            using var output = entry.Open(); output.Write(bytes);
        }

        internal void Complete(NativeCSharpModule module)
        {
            if (failure is not null) throw new InvalidOperationException("native_source_pack_recording_failed", failure);
            if (entries.Count == 0) throw new InvalidOperationException("native_source_pack_empty");
            var manifest = new JsonObject
            {
                ["version"] = NativeSourcePackVersion,
                ["minimumMethodIlBytes"] = NativeSourcePackMinimumIlBytes,
                ["projectionSha256"] = NativeSourcePackBuild.ProjectionSha256,
                ["nativeAssemblySha256"] = module.Sha256, ["nativeModuleVersionId"] = module.Mvid.ToString(),
                ["decompilerVersion"] = NativeCSharpVersion, ["decompilerSha256"] = NativeCSharpDecompilerSha256,
                ["decompilerMvid"] = NativeCSharpDecompilerMvid, ["settings"] = "csharp_default_no_indentation_v1",
                ["dependencies"] = NativeSourcePackDependencyPins(module),
                ["entries"] = new JsonArray(entries.Values.Select(value => (JsonNode?)value).ToArray()),
                ["blobs"] = new JsonArray(blobs.OrderBy(pair => pair.Value.Index).Select(pair => (JsonNode?)new JsonObject
                    { ["sha256"] = pair.Key, ["bytes"] = pair.Value.Bytes }).ToArray()),
            };
            manifest["indexSha256"] = NativeSourcePackIndexHash(manifest["entries"]!.AsArray(), manifest["blobs"]!.AsArray());
            byte[] metadata = Encoding.UTF8.GetBytes(manifest.ToJsonString());
            if (metadata.Length > NativeSourcePackEntryBytes)
                throw new InvalidOperationException("native_source_pack_manifest_size");
            Write("manifest.json", metadata);
            archive.Dispose(); disposed = true;
            if (new FileInfo(temporaryPath).Length > NativeSourcePackArchiveBytes)
                throw new InvalidOperationException("native_source_pack_archive_size");
            System.IO.File.Move(temporaryPath, outputPath, overwrite: true); completed = true;
        }

        public void Dispose()
        {
            if (!disposed) { archive.Dispose(); disposed = true; }
            if (!completed) System.IO.File.Delete(temporaryPath);
        }
    }
}
