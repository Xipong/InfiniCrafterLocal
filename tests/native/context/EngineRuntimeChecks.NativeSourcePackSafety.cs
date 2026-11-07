using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Reflection;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Threading;
using ICSharpCode.Decompiler.Metadata;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    // Tiny archives exercise the real reader and native verifier without
    // decompiling a dispatcher or generating the full identity catalog.
    private static object PackSafetyCreate(string type, params object?[] arguments)
        => Activator.CreateInstance(CSharpOwner.GetNestedType(type, CSharpFlags)!, CSharpFlags, null, arguments, null)!;
    private static string PackSafetyHash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    private static MethodInfo PackSafetyMethod() => typeof(Projectile).GetMethod("Kill", CSharpFlags, null, Type.EmptyTypes, null)!;
    private static JsonObject PackSafetyCertificate(MethodInfo method)
        => (JsonObject)CSharpOwner.GetMethod("MethodSourceIdentity", CSharpFlags)!.Invoke(null, new object[] { method })!;
    private static string PackSafetyKey(MethodInfo method, JsonObject input, string kind = "projectile_method")
        => (string)CSharpOwner.GetMethod("NativeSourceProjectionKey", CSharpFlags)!.Invoke(null, new object[] { kind, method, input })!;

    private static Array PackSafetyPrograms(MethodInfo method, object[] path, JsonArray? windows = null)
    {
        var row = PackSafetyCertificate(method);
        if (windows is not null) row["identityWindows"] = windows.DeepClone();
        var type = CSharpOwner.GetNestedType("CSharpProgram", CSharpFlags)!;
        var programs = Array.CreateInstance(type, 1);
        programs.SetValue(Activator.CreateInstance(type, CSharpFlags, null, new object[] { row, path }, null), 0);
        return programs;
    }
    private static JsonObject PackSafetyInput(MethodInfo method, Array programs, JsonArray calls, int type = 91, int style = 1, bool bound = true)
        => (JsonObject)CSharpOwner.GetMethod("CSharpProjectionInput", CSharpFlags)!
            .Invoke(null, new object[] { method, programs, calls, type, style, bound })!;

    private static JsonObject PackSafetyManifest(object module, string key, byte[] payload)
    {
        object Constant(string name) => CSharpOwner.GetField(name, CSharpFlags)!.GetRawConstantValue()!;
        var assembly = typeof(object).Assembly; byte[] core = File.ReadAllBytes(assembly.Location);
        return new JsonObject {
            ["version"] = (int)Constant("NativeSourcePackVersion"), ["minimumMethodIlBytes"] = (int)Constant("NativeSourcePackMinimumIlBytes"),
            ["projectionSha256"] = NativeSourcePackBuild.ProjectionSha256,
            ["nativeAssemblySha256"] = (string)CSharpFixtureMember(module, "Sha256"),
            ["nativeModuleVersionId"] = ((Guid)CSharpFixtureMember(module, "Mvid")).ToString(),
            ["decompilerVersion"] = (string)Constant("NativeCSharpVersion"),
            ["decompilerSha256"] = (string)Constant("NativeCSharpDecompilerSha256"),
            ["decompilerMvid"] = (string)Constant("NativeCSharpDecompilerMvid"), ["settings"] = "csharp_default_no_indentation_v1",
            ["dependencies"] = new JsonArray(new JsonObject { ["reference"] = assembly.FullName, ["assembly"] = assembly.FullName,
                ["sha256"] = PackSafetyHash(core), ["bytes"] = core.Length }),
            ["entries"] = new JsonArray(new JsonObject { ["key"] = key, ["kind"] = "fixture", ["bytes"] = payload.Length, ["sha256"] = PackSafetyHash(payload) })
        };
    }
    private static MemoryStream PackSafetyArchive(JsonObject manifest, string key, byte[] payload)
    {
        var stream = new MemoryStream();
        using (var archive = new ZipArchive(stream, ZipArchiveMode.Create, leaveOpen: true))
        {
            void Write(string name, byte[] bytes) { using var entry = archive.CreateEntry(name, CompressionLevel.Fastest).Open(); entry.Write(bytes); }
            Write("manifest.json", Encoding.UTF8.GetBytes(manifest.ToJsonString())); Write(key + ".json", payload);
        }
        stream.Position = 0; return stream;
    }
    private static bool PackSafetyRead(object reader, string key, CancellationToken cancellation, out JsonObject? projection)
    {
        object?[] arguments = { key, cancellation, null };
        bool found = (bool)reader.GetType().GetMethod("TryRead", CSharpFlags)!.Invoke(reader, arguments)!;
        projection = arguments[2] as JsonObject; return found;
    }
    private static bool PackSafetyReadVerified(string kind, MethodInfo method, JsonObject input, CancellationToken cancellation, out JsonObject? projection)
    {
        object?[] arguments = { kind, method, input, cancellation, null };
        bool found = (bool)CSharpOwner.GetMethod("TryReadNativeSourceProjection", CSharpFlags)!.Invoke(null, arguments)!;
        projection = arguments[4] as JsonObject; return found;
    }
    private sealed class PackSafetyScope : IDisposable
    {
        private readonly Dictionary<FieldInfo, object?> originals = new();
        internal PackSafetyScope(object module, object? reader = null, object? recorder = null)
        {
            void Set(string name, object? value) { var field = CSharpOwner.GetField(name, CSharpFlags)!; originals.Add(field, field.GetValue(null)); field.SetValue(null, value); }
            Set("nativeCSharpModule", module); Set("nativeSourcePackReader", reader);
            Set("nativeSourcePackReadAttempted", reader is not null); Set("nativeSourcePackRecorder", recorder);
        }
        public void Dispose() { foreach (var pair in originals) pair.Key.SetValue(null, pair.Value); }
    }

    private sealed class PackSafetyForwardStream : Stream
    {
        private readonly Stream inner;
        internal bool Disposed;
        internal PackSafetyForwardStream(Stream inner) { this.inner = inner; }
        public override bool CanRead => !Disposed;
        public override bool CanSeek => false;
        public override bool CanWrite => false;
        public override long Length => throw new NotSupportedException();
        public override long Position { get => throw new NotSupportedException(); set => throw new NotSupportedException(); }
        public override int Read(byte[] buffer, int offset, int count) => inner.Read(buffer, offset, count);
        public override void Flush() => throw new NotSupportedException();
        public override long Seek(long offset, SeekOrigin origin) => throw new NotSupportedException();
        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();
        protected override void Dispose(bool disposing) { if (disposing) { Disposed = true; inner.Dispose(); } base.Dispose(disposing); }
    }

    private static Stream PackSafetyTmodEntryStream(byte[] bytes)
    {
        // Use tML's actual resource slice: it advertises seeking, but supported
        // releases implement Seek(offset, End) with the opposite offset sign.
        // No mod is loaded, registered or executed by constructing this owner.
        var assembly = typeof(Projectile).Assembly;
        var fileType = assembly.GetType("Terraria.ModLoader.Core.TmodFile")!;
        var owner = Activator.CreateInstance(fileType, CSharpFlags, null,
            new object[] { "unused-source-pack-fixture.tmod", "SourcePackFixture", new Version(1, 0) }, null)!;
        var entry = Activator.CreateInstance(fileType.GetNestedType("FileEntry", CSharpFlags)!, CSharpFlags, null,
            new object?[] { "Data/native-source-pack.zip", 0, bytes.Length, bytes.Length, null }, null)!;
        var stream = (Stream)Activator.CreateInstance(assembly.GetType("Terraria.ModLoader.Core.EntryReadStream")!, CSharpFlags, null,
            new object[] { owner, entry, new MemoryStream(bytes, writable: false), false }, null)!;
        ((IList)fileType.GetField("independentEntryReadStreams", CSharpFlags)!.GetValue(owner)!).Add(stream);
        return stream;
    }

    private static void NativeSourcePackReaderPreservesBytesAndCancellation()
    {
        var method = PackSafetyMethod();
        using var module = (IDisposable)PackSafetyCreate("NativeCSharpModule", method.Module.FullyQualifiedName,
            File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        var record = PackSafetyCertificate(method); record["id"] = "fixture"; record["graphPaths"] = null;
        record["code"] = "line1\r\nline2\"\\\n"; record["coverage"] = "whole_method";
        record["unresolved"] = new JsonArray("first unknown", "second unknown");
        var projection = new JsonObject { ["strict"] = record, ["strictRefusal"] = null,
            ["mechanics"] = null, ["mechanicsRefusal"] = "fixture_readable_refusal" };
        var input = PackSafetyInput(method, PackSafetyPrograms(method, new object[] { "fixture" }), new JsonArray(), bound: false);
        string key = PackSafetyKey(method, input); byte[] payload = Encoding.UTF8.GetBytes(projection.ToJsonString());
        var manifest = PackSafetyManifest(module, key, payload);
        using var reader = (IDisposable)PackSafetyCreate("NativeSourcePackReader", PackSafetyArchive(manifest, key, payload), module, CancellationToken.None);
        Equal(true, PackSafetyRead(reader, key, CancellationToken.None, out var decoded), "tiny exact entry is readable");
        Equal(projection.ToJsonString(), decoded!.ToJsonString(), "JSON preserves complete source strings, nulls and property order");
        decoded["strict"]!["code"] = "caller mutation";
        Equal(true, PackSafetyRead(reader, key, CancellationToken.None, out decoded), "entry remains independently readable");
        Equal(projection.ToJsonString(), decoded!.ToJsonString(), "caller mutation cannot poison later projections");
        using var cancellation = new CancellationTokenSource(); cancellation.Cancel();
        CSharpSourceRefuses(() => PackSafetyRead(reader, key, cancellation.Token, out _), "canceled");
        CSharpSourceRefuses(() => PackSafetyRead(reader, new string('f', 64), cancellation.Token, out _), "canceled");
        Equal(true, PackSafetyRead(reader, key, CancellationToken.None, out _), "cancelled hit is retryable");
        using (var archive = PackSafetyArchive(manifest, key, payload))
        using (var resource = PackSafetyTmodEntryStream(archive.ToArray()))
        {
            Equal(true, resource.CanSeek, "real tmod entry advertises seeking independently of correct End semantics");
            using var resourceReader = (IDisposable)PackSafetyCreate("NativeSourcePackReader", resource, module, CancellationToken.None);
            Equal(true, PackSafetyRead(resourceReader, key, CancellationToken.None, out var resourceProjection), "real seekable tmod resource can serve a hit");
            Equal(projection.ToJsonString(), resourceProjection!.ToJsonString(), "real tmod resource retains exact projection bytes");
        }
        using (var forward = new PackSafetyForwardStream(PackSafetyArchive(manifest, key, payload)))
        using (var resourceReader = (IDisposable)PackSafetyCreate("NativeSourcePackReader", forward, module, CancellationToken.None))
        {
            Equal(true, forward.Disposed, "forward-only mod resource is consumed and closed after bounded buffering");
            Equal(true, PackSafetyRead(resourceReader, key, CancellationToken.None, out var resourceProjection), "official forward-only resource shape can serve a hit");
            Equal(projection.ToJsonString(), resourceProjection!.ToJsonString(), "forward-only resource preserves the same projection bytes");
        }
        using (var interrupted = new PackSafetyForwardStream(PackSafetyArchive(manifest, key, payload)))
        {
            CSharpSourceRefuses(() => {
                using var cancelledReader = (IDisposable)PackSafetyCreate("NativeSourcePackReader", interrupted, module, cancellation.Token);
            }, "canceled");
            Equal(true, interrupted.Disposed, "cancelled resource buffering releases the owned stream");
        }
        lock (CSharpOwner.GetField("nativeCSharpGate", CSharpFlags)!.GetValue(null)!)
        {
            using var scope = new PackSafetyScope(module, reader);
            var program = PackSafetyCertificate(method); program["observations"] = new JsonArray();
            var attack = new JsonObject { ["fixture"] = program };
            CSharpOwner.GetMethod("AttachNativeCSharpSource", CSharpFlags)!.Invoke(null,
                new object[] { attack, new MethodBase[] { method }, new JsonArray(), 91, 1, new HashSet<MethodBase>() });
            var expected = record.DeepClone().AsObject(); expected["graphPaths"] = new JsonArray(new JsonArray("fixture"));
            Equal(expected.ToJsonString(), attack["nativeCSharpSource"]!["records"]![0]!.ToJsonString(),
                "actual consumer rebinds paths without moving their property or losing unknowns");
            Equal("fixture_readable_refusal", attack["mechanicsSource"]!["unresolved"]![0]!["unresolved"]!.GetValue<string>(),
                "cached mechanics refusals remain explicit");
            Equal(true, module.GetType().GetField("typeSystem", CSharpFlags)!.GetValue(module) is null,
                "verified pack hit never initializes a decompiler or executes source");
        }
    }

    private static void NativeSourcePackReaderRejectsIdentityAndCorruption()
    {
        var method = PackSafetyMethod();
        using var module = (IDisposable)PackSafetyCreate("NativeCSharpModule", method.Module.FullyQualifiedName,
            File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        string key = new string('a', 64); byte[] payload = Encoding.UTF8.GetBytes("{\"code\":\"retained\"}");
        var manifest = PackSafetyManifest(module, key, payload);
        void Reject(Action<JsonObject> mutate, string reason)
        {
            var changed = manifest.DeepClone().AsObject(); mutate(changed);
            CSharpSourceRefuses(() => {
                using var rejected = (IDisposable)PackSafetyCreate("NativeSourcePackReader", PackSafetyArchive(changed, key, payload), module, CancellationToken.None);
            }, reason);
        }
        foreach (string field in new[] { "projectionSha256", "nativeAssemblySha256", "nativeModuleVersionId", "decompilerVersion", "decompilerSha256", "decompilerMvid", "settings" })
            Reject(value => value[field] = "different", "native_source_pack_identity_mismatch");
        foreach (string field in new[] { "version", "minimumMethodIlBytes" })
            Reject(value => value[field] = value[field]!.GetValue<int>() + 1, "native_source_pack_identity_mismatch");
        Reject(value => value["dependencies"] = new JsonArray(), "native_source_pack_dependency_mismatch");
        Reject(value => value["dependencies"]![0]!["sha256"] = new string('0', 64), "native_source_pack_dependency_mismatch");
        Reject(value => value["entries"]![0]!["bytes"] = payload.Length + 1, "native_source_pack_index_invalid");
        Reject(value => value["entries"]![0]!["key"] = new string('b', 64), "native_source_pack_index_invalid");
        var corrupt = (byte[])payload.Clone(); corrupt[10] ^= 1;
        using (var reader = (IDisposable)PackSafetyCreate("NativeSourcePackReader", PackSafetyArchive(manifest, key, corrupt), module, CancellationToken.None))
        {
            Equal(false, PackSafetyRead(reader, key, CancellationToken.None, out var result), "changed entry bytes are a miss, never source evidence");
            Equal(true, result is null, "failed checksum cannot leak a partial projection");
        }
        foreach (string invalid in new[] { "{broken", "[]", "null" })
        {
            byte[] bytes = Encoding.UTF8.GetBytes(invalid); var changed = manifest.DeepClone().AsObject();
            changed["entries"]![0]!["bytes"] = bytes.Length; changed["entries"]![0]!["sha256"] = PackSafetyHash(bytes);
            using var reader = (IDisposable)PackSafetyCreate("NativeSourcePackReader", PackSafetyArchive(changed, key, bytes), module, CancellationToken.None);
            Equal(false, PackSafetyRead(reader, key, CancellationToken.None, out _), "checksum does not admit malformed projection JSON");
        }
        var shape = CSharpOwner.GetMethod("CompleteCSharpProjection", CSharpFlags)!;
        Equal(false, (bool)shape.Invoke(null, new object[] { new JsonObject(), method })!, "empty object cannot hide missing source outcomes");
        var outcomes = new JsonObject { ["strict"] = null, ["strictRefusal"] = "explicit strict refusal",
            ["mechanics"] = null, ["mechanicsRefusal"] = "explicit mechanics refusal" };
        Equal(true, (bool)shape.Invoke(null, new object[] { outcomes, method })!, "complete explicit refusals remain valid projections");
        outcomes["strict"] = new JsonObject();
        Equal(false, (bool)shape.Invoke(null, new object[] { outcomes, method })!, "record and refusal cannot both claim the same outcome");
        PackSafetyResolverUsesHostBindings();
    }

    private static void PackSafetyResolverUsesHostBindings()
    {
        string root = Path.Combine(Path.GetTempPath(), "ifc-pack-binding-" + Guid.NewGuid().ToString("N"));
        string nested = Path.Combine(root, "Libraries", "FNA", "runtime", "FNA.dll");
        string duplicate = Path.Combine(root, "other", "FNA.dll");
        Directory.CreateDirectory(Path.GetDirectoryName(nested)!); Directory.CreateDirectory(Path.GetDirectoryName(duplicate)!);
        File.Copy(typeof(Microsoft.Xna.Framework.Vector2).Assembly.Location, nested); File.Copy(nested, duplicate);
        try
        {
            using var metadata = new PEFile(nested);
            var reference = AssemblyNameReference.Parse(metadata.FullName);
            lock (CSharpOwner.GetField("nativeCSharpGate", CSharpFlags)!.GetValue(null)!)
            {
                object? original = AppContext.GetData("TRUSTED_PLATFORM_ASSEMBLIES");
                try
                {
                    foreach (string paths in new[] { nested, nested + Path.PathSeparator + nested })
                    {
                        AppContext.SetData("TRUSTED_PLATFORM_ASSEMBLIES", paths);
                        using var resolver = (IDisposable)PackSafetyCreate("NativeCSharpResolver", PackSafetyMethod().Module.FullyQualifiedName, CancellationToken.None);
                        var resolved = (PEFile)resolver.GetType().GetMethod("Resolve", CSharpFlags)!.Invoke(resolver, new object[] { reference })!;
                        Equal(Path.GetFullPath(nested), Path.GetFullPath(resolved.FileName), "metadata resolver selects the exact host binding, including nested package layout");
                    }
                    string hostJson = Path.Combine(root, "Libraries", "System.Text.Json", "System.Text.Json.dll");
                    Directory.CreateDirectory(Path.GetDirectoryName(hostJson)!);
                    File.Copy(typeof(JsonNode).Assembly.Location, hostJson);
                    using (var overlay = File.Open(hostJson, FileMode.Append, FileAccess.Write)) overlay.WriteByte(0x7f);
                    using (var jsonMetadata = new PEFile(hostJson))
                    {
                        AppContext.SetData("TRUSTED_PLATFORM_ASSEMBLIES", hostJson);
                        using var resolver = (IDisposable)PackSafetyCreate("NativeCSharpResolver", Path.Combine(root, "tModLoader.dll"), CancellationToken.None);
                        var resolved = (PEFile)resolver.GetType().GetMethod("Resolve", CSharpFlags)!.Invoke(resolver,
                            new object[] { AssemblyNameReference.Parse(jsonMetadata.FullName) })!;
                        Equal(hostJson, Path.GetFullPath(resolved.FileName), "host-selected package wins over the framework copy with the same assembly name");
                        object?[] arguments = { resolved, 64L * 1024 * 1024, CancellationToken.None };
                        var pin = ((string Sha256, int Bytes))CSharpOwner.GetMethod("NativeSourcePackDependencyHash", CSharpFlags)!.Invoke(null, arguments)!;
                        Equal(PackSafetyHash(File.ReadAllBytes(hostJson)), pin.Sha256, "dependency pin binds the selected file bytes, including its metadata-only overlay");
                    }
                    AppContext.SetData("TRUSTED_PLATFORM_ASSEMBLIES", nested + Path.PathSeparator + duplicate);
                    using var ambiguous = (IDisposable)PackSafetyCreate("NativeCSharpResolver", PackSafetyMethod().Module.FullyQualifiedName, CancellationToken.None);
                    CSharpSourceRefuses(() => ambiguous.GetType().GetMethod("Resolve", CSharpFlags)!.Invoke(ambiguous, new object[] { reference }),
                        "csharp_platform_assembly_binding_ambiguous");
                    Equal(false, AppDomain.CurrentDomain.GetAssemblies().Where(assembly => !assembly.IsDynamic)
                        .Any(assembly => assembly.Location == nested || assembly.Location == duplicate || assembly.Location == hostJson), "host binding verification reads PE metadata without loading the copied assemblies");
                }
                finally { AppContext.SetData("TRUSTED_PLATFORM_ASSEMBLIES", original); }
            }
        }
        finally { Directory.Delete(root, recursive: true); }
    }

    private static void NativeSourcePackHitsVerifyMethodHeaders()
    {
        var method = PackSafetyMethod(); byte[] bytes = File.ReadAllBytes(method.Module.FullyQualifiedName);
        using var module = (IDisposable)PackSafetyCreate("NativeCSharpModule", method.Module.FullyQualifiedName, bytes, method.Module.ModuleVersionId);
        var input = new JsonObject { ["type"] = 91, ["style"] = 1 };
        string key = PackSafetyKey(method, input, "projectile_lifecycle"); byte[] payload = Encoding.UTF8.GetBytes("{\"fixture\":true}");
        var manifest = PackSafetyManifest(module, key, payload);
        using var reader = (IDisposable)PackSafetyCreate("NativeSourcePackReader", PackSafetyArchive(manifest, key, payload), module, CancellationToken.None);
        using var pe = new PEReader(new MemoryStream(bytes, writable: false));
        int start = CSharpFixtureBodyOffset(pe, method);
        int header = (bytes[start] & 3) == 2 ? 1 : (BitConverter.ToUInt16(bytes, start) >> 12) * 4;
        Equal(true, header > 1 && method.GetMethodBody()!.LocalSignatureMetadataToken != 0, "header fixture includes stack, init-locals and a local signature");
        lock (CSharpOwner.GetField("nativeCSharpGate", CSharpFlags)!.GetValue(null)!)
        {
            using var scope = new PackSafetyScope(module, reader);
            Equal(true, PackSafetyReadVerified("projectile_lifecycle", method, input, CancellationToken.None, out _), "verified hit succeeds before negative controls");
            using var cancellation = new CancellationTokenSource(); cancellation.Cancel();
            CSharpSourceRefuses(() => PackSafetyReadVerified("projectile_lifecycle", method, input, cancellation.Token, out _), "canceled");
            var field = CSharpOwner.GetField("nativeCSharpModule", CSharpFlags)!;
            void Reject(Action<byte[]> mutate, string reason)
            {
                var altered = (byte[])bytes.Clone(); mutate(altered);
                using var changed = (IDisposable)PackSafetyCreate("NativeCSharpModule", method.Module.FullyQualifiedName, altered, method.Module.ModuleVersionId);
                field.SetValue(null, changed);
                try { CSharpSourceRefuses(() => PackSafetyReadVerified("projectile_lifecycle", method, input, CancellationToken.None, out _), reason); }
                finally { field.SetValue(null, module); }
                Equal(true, PackSafetyReadVerified("projectile_lifecycle", method, input, CancellationToken.None, out _), "refused snapshot cannot poison the valid cached hit");
            }
            Reject(changed => changed[start + 2] ^= 1, "csharp_pe_max_stack_mismatch");
            Reject(changed => changed[start] ^= 0x10, "csharp_pe_init_locals_mismatch");
            Reject(changed => Array.Clear(changed, start + 8, 4), "csharp_pe_local_signature_mismatch");
            Reject(changed => changed[start + header] ^= 1, "csharp_pe_il_mismatch");
            Equal(true, module.GetType().GetField("typeSystem", CSharpFlags)!.GetValue(module) is null, "cached-hit verification never needs method decompilation");
        }
    }

    private static void NativeSourcePackRecorderRejectsConflictsAtomically()
    {
        string directory = Path.Combine(Path.GetTempPath(), "ifc-source-pack-safety-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory); string output = Path.Combine(directory, "pack.zip");
        byte[] previous = Encoding.UTF8.GetBytes("previous published archive"); File.WriteAllBytes(output, previous);
        try
        {
            var method = PackSafetyMethod();
            using var module = (IDisposable)PackSafetyCreate("NativeCSharpModule", method.Module.FullyQualifiedName,
                File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
            using var recorder = (IDisposable)PackSafetyCreate("NativeSourcePackRecorder", output);
            lock (CSharpOwner.GetField("nativeCSharpGate", CSharpFlags)!.GetValue(null)!)
            {
                using var scope = new PackSafetyScope(module, recorder: recorder);
                var input = new JsonObject { ["type"] = 91, ["style"] = 1 }; var projection = new JsonObject { ["code"] = "original" };
                void Record(JsonObject value, CancellationToken cancellation = default)
                    => CSharpOwner.GetMethod("RecordNativeSourceProjection", CSharpFlags)!.Invoke(null,
                        new object[] { "projectile_lifecycle", method, input, value, cancellation });
                Record(projection); Record(projection.DeepClone().AsObject());
                Equal(1, (int)CSharpFixtureMember(CSharpFixtureMember(recorder, "entries"), "Count"), "identical duplicate recording has one entry");
                using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
                CSharpSourceRefuses(() => Record(projection, cancelled.Token), "canceled");
                CSharpSourceRefuses(() => Record(new JsonObject { ["code"] = "conflicting" }), "native_source_pack_key_conflict");
                CSharpSourceRefuses(() => CSharpOwner.GetMethod("CompleteNativeSourcePackRecording", CSharpFlags)!.Invoke(null, null), "native_source_pack_recording_failed");
                Equal(true, previous.SequenceEqual(File.ReadAllBytes(output)), "caught recording conflict cannot replace the published artifact");
                Equal(0, Directory.GetFiles(directory, "*.tmp").Length, "failed completion removes the temporary archive");
            }
        }
        finally { Directory.Delete(directory, recursive: true); }
    }

    private static void NativeSourcePackKeysCoverProjectionInputs()
    {
        var method = typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.Closed))!;
        var windows = new JsonArray(new JsonObject { ["field"] = "type", ["literal"] = 91, ["guardOffset"] = 4 },
            new JsonObject { ["field"] = "aiStyle", ["literal"] = 1, ["guardOffset"] = 12 });
        JsonObject Call(int offset, params string[] predicates)
        {
            var row = PackSafetyCertificate(method); row["at"] = offset;
            row["requiredPredicates"] = new JsonArray(predicates.Select(value => (JsonNode?)JsonValue.Create(value)).ToArray()); return row;
        }
        var calls = new JsonArray(Call(40, "b12", "b12", "opaque"), Call(16, "b4"));
        var programs = PackSafetyPrograms(method, new object[] { "roots", 0 }, windows);
        var input = PackSafetyInput(method, programs, calls); string key = PackSafetyKey(method, input);
        Equal("[4,12,16,40]", input["linkOffsets"]!.ToJsonString(), "key maps the exact sorted call/predicate offset union");
        Equal(key, PackSafetyKey(method, PackSafetyInput(method, PackSafetyPrograms(method, new object[] { "moved", 7 }, windows), calls)),
            "graph paths are output-only and do not partition identical source projections");
        var duplicates = new JsonArray(calls[1]!.DeepClone(), calls[0]!.DeepClone(), calls[0]!.DeepClone());
        var foreign = Call(777, "b888"); foreign["method"] = "Other.Owner.Method"; duplicates.Add(foreign);
        Equal(key, PackSafetyKey(method, PackSafetyInput(method, programs, duplicates)), "call order, duplicates and other methods preserve the mapped offset union");
        foreach (var changed in new[] { PackSafetyInput(method, programs, calls, type: 92), PackSafetyInput(method, programs, calls, style: 2), PackSafetyInput(method, programs, calls, bound: false) })
            Equal(false, key == PackSafetyKey(method, changed), "captured identity and receiver binding participate in the key");
        foreach (string field in new[] { "field", "literal", "guardOffset" })
        {
            var changed = windows.DeepClone().AsArray(); changed[0]![field] = field == "field" ? JsonValue.Create("aiStyle") : JsonValue.Create(99);
            Equal(false, key == PackSafetyKey(method, PackSafetyInput(method, PackSafetyPrograms(method, new object[] { "roots", 0 }, changed), calls)),
                "every rendered identity window field participates: " + field);
        }
        var reordered = new JsonArray(windows[1]!.DeepClone(), windows[0]!.DeepClone());
        Equal(false, key == PackSafetyKey(method, PackSafetyInput(method, PackSafetyPrograms(method, new object[] { "roots", 0 }, reordered), calls)),
            "window order participates because the source record retains that order");
        foreach (bool predicate in new[] { false, true })
        {
            var changed = calls.DeepClone().AsArray();
            if (predicate) changed[0]!["requiredPredicates"]!.AsArray().Add("b55"); else changed[0]!["at"] = 55;
            Equal(false, key == PackSafetyKey(method, PackSafetyInput(method, programs, changed)), "call and controlling predicate offsets both participate");
        }
        Equal(false, key == PackSafetyKey(method, input, "item_dispatch"), "different projection kinds cannot alias");
        Equal(false, key == PackSafetyKey(typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.ExternalLocal))!, input), "method identity participates independently of inputs");
    }
}
