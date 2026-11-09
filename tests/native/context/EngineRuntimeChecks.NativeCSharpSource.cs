using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using System.Threading;
using ICSharpCode.Decompiler.CSharp.Syntax;
using InfiniCrafterLocal.Common.Services;
using Terraria;
using Terraria.ID;

internal static partial class EngineRuntimeChecks
{
    private sealed class CSharpSourceFixture : Projectile
    {
        internal static int Executions;
        private static void Opaque(ref float value) { Executions++; value = 90; }
        [MethodImpl(MethodImplOptions.NoInlining | MethodImplOptions.NoOptimization)]
        public void Closed()
        {
            if (aiStyle == 123) { float value = ai[0]; if (value > 30) friendly = true; Opaque(ref value); rotation = value; }
            if (type == 643) damage++;
        }
        public void ExternalLocal() { float value = ai[0]; if (aiStyle == 123) rotation = value; }
        public string LiteralSource() => "line1\r\nline2\"\\";
        public void ExceptionRegion() { if (aiStyle == 123) { try { rotation++; } finally { damage++; } } }
        public void OtherExceptionRegion()
        {
            if (aiStyle == 123) rotation++;
            if (type == 888) { try { damage++; } finally { friendly = true; } }
        }
        public int ExceptionDescriptors(int value)
        {
            try { if (value < 0) throw new ArgumentException(); return value + Executions; }
            catch (ArgumentException) when (value == -1) { return -1; }
            catch (InvalidOperationException) { return -2; }
            finally { Executions++; }
        }
    }

    private const BindingFlags CSharpFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
    private static readonly Type CSharpOwner = typeof(GeneratorClient);

    private static object CSharpFixtureMember(object value, string name)
        => value.GetType().GetProperty(name, CSharpFlags)?.GetValue(value)
            ?? value.GetType().GetField(name, CSharpFlags)!.GetValue(value)!;

    private static JsonObject CSharpFixtureRecord(MethodInfo method, bool regions, byte[]? bytes = null,
        bool extraWindow = false, CancellationToken cancellation = default, bool specialize = false)
    {
        var moduleType = CSharpOwner.GetNestedType("NativeCSharpModule", CSharpFlags)!;
        var documentType = CSharpOwner.GetNestedType("NativeCSharpDocument", CSharpFlags)!;
        var programType = CSharpOwner.GetNestedType("CSharpProgram", CSharpFlags)!;
        object Create(Type type, params object?[] args) => Activator.CreateInstance(type, CSharpFlags, null, args, null)!;
        using var module = (IDisposable)Create(moduleType, method.Module.FullyQualifiedName,
            bytes ?? File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
        using var document = (IDisposable)Create(documentType, method, module, cancellation);
        var program = new JsonObject { ["method"] = method.DeclaringType!.FullName + "." + method.Name,
            ["sourceModuleVersionId"] = method.Module.ModuleVersionId.ToString(),
            ["sourceMethodSha256"] = Convert.ToHexString(SHA256.HashData(method.GetMethodBody()!.GetILAsByteArray()!)).ToLowerInvariant(),
            ["coverage"] = "fixture_source_only" };
        if (regions)
        {
            var windows = new JsonArray();
            var ends = CSharpOwner.GetMethod("CSharpConditionalEnds", CSharpFlags)!.Invoke(null, new object[] { method });
            var tree = (SyntaxTree)CSharpFixtureMember(document, "Tree");
            foreach (var branch in tree.Descendants.OfType<IfElseStatement>())
            {
                object? guard = CSharpOwner.GetMethod("ReadCSharpGuard", CSharpFlags)!.Invoke(null, new[] { branch, ends });
                if (guard is null) continue;
                string field = (string)CSharpFixtureMember(guard, "Field"); int literal = (int)CSharpFixtureMember(guard, "Literal");
                if (!(field == "aiStyle" && literal == 123 || field == "type" && literal == 643)) continue;
                windows.Add(new JsonObject { ["field"] = field, ["literal"] = literal, ["guardOffset"] = (int)CSharpFixtureMember(guard, "Offset") });
            }
            Equal(true, windows.Count > 0, "fixture has an actual typed native conditional guard");
            if (extraWindow) windows.Add(new JsonObject { ["field"] = "aiStyle", ["literal"] = 123, ["guardOffset"] = 1 });
            program["identityWindows"] = windows;
        }
        var programs = Array.CreateInstance(programType, 1);
        programs.SetValue(Create(programType, program, new object[] { "fixture" }), 0);
        var record = (JsonObject)CSharpOwner.GetMethod("BuildNativeCSharpRecord", CSharpFlags)!.Invoke(null,
            new object[] { document, programs, new JsonArray(), 643, 123, cancellation })!;
        if (specialize)
            CSharpOwner.GetMethod("AttachIdentitySpecializedCSharp", CSharpFlags)!.Invoke(null,
                new object[] { record, document, 643, 123, cancellation });
        return record;
    }

    private static void CSharpSourceRefuses(Action action, string reason)
    {
        Exception? observed = null;
        try { action(); }
        catch (Exception error)
        {
            while (error is TargetInvocationException { InnerException: not null }) error = error.InnerException;
            observed = error;
        }
        Equal(true, observed is not null, "source must refuse: " + reason);
        Equal(true, observed!.Message.Contains(reason, StringComparison.OrdinalIgnoreCase), "specific source refusal: " + reason + "; actual=" + observed.Message);
    }

    private static void NativeCSharpSourceVerifiesExactPeWithoutExecution()
    {
        var method = typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.Closed))!;
        CSharpSourceFixture.Executions = 0;
        var record = CSharpFixtureRecord(method, regions: false);
        Equal("whole_method", record["coverage"]!.GetValue<string>(), "whole helper is one complete readable source record");
        string code = record["code"]!.GetValue<string>();
        Equal(true, code.Contains("Opaque", StringComparison.Ordinal) && code.Contains("643", StringComparison.Ordinal)
            && code.Contains("123", StringComparison.Ordinal), "opaque calls and both sibling branches survive");
        Equal(0, CSharpSourceFixture.Executions, "decompilation never invokes a method or constructor");
        byte[] bytes = File.ReadAllBytes(method.Module.FullyQualifiedName);
        Equal(Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant(), record["assemblySha256"]!.GetValue<string>(), "PE certificate hashes the bytes actually decompiled");
        Equal(Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(code))).ToLowerInvariant(), record["codeSha256"]!.GetValue<string>(), "code certificate matches exact rendered source");
        var literal = CSharpFixtureRecord(typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.LiteralSource))!, false);
        Equal(true, Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree.ParseText(literal["code"]!.GetValue<string>()).GetRoot().DescendantTokens()
            .Any(token => token.RawKind == (int)Microsoft.CodeAnalysis.CSharp.SyntaxKind.StringLiteralToken && token.ValueText == "line1\r\nline2\"\\"),
            "LF layout never rewrites literal CRLF, quotes or backslashes");
        CSharpSourceRefuses(() => CSharpFixtureRecord(method, false, File.ReadAllBytes(typeof(Projectile).Assembly.Location)), "csharp_pe_mvid_mismatch");
        var staleMetadata = (byte[])bytes.Clone();
        int nameOffset = staleMetadata.AsSpan().IndexOf(System.Text.Encoding.UTF8.GetBytes("Opaque\0"));
        Equal(true, nameOffset >= 0, "metadata mutation targets a real referenced method name");
        staleMetadata[nameOffset] = (byte)'Q';
        CSharpSourceRefuses(() => CSharpFixtureRecord(method, false, staleMetadata), "csharp_pe_metadata_mismatch");
        using (var pe = new PEReader(new MemoryStream(bytes, writable: false)))
        {
            var definition = pe.GetMetadataReader().GetMethodDefinition((MethodDefinitionHandle)MetadataTokens.Handle(method.MetadataToken));
            var section = pe.PEHeaders.SectionHeaders[pe.PEHeaders.GetContainingSectionIndex(definition.RelativeVirtualAddress)];
            int start = section.PointerToRawData + definition.RelativeVirtualAddress - section.VirtualAddress;
            int header = (bytes[start] & 3) == 2 ? 1 : (BitConverter.ToUInt16(bytes, start) >> 12) * 4;
            bytes[start + header] ^= 1;
        }
        CSharpSourceRefuses(() => CSharpFixtureRecord(method, false, bytes), "csharp_pe_il_mismatch");
        using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
        CSharpSourceRefuses(() => CSharpFixtureRecord(method, false, cancellation: cancelled.Token), "canceled");
    }

    // Exercise the actual module verifier independently of decompilation/region
    // admission: a later decompiler failure must not hide a false PE match.
    private static void VerifyCSharpFixtureBytes(MethodInfo method, byte[] bytes)
    {
        var type = CSharpOwner.GetNestedType("NativeCSharpModule", CSharpFlags)!;
        using var module = (IDisposable)Activator.CreateInstance(type, CSharpFlags, null,
            new object[] { method.Module.FullyQualifiedName, bytes, method.Module.ModuleVersionId }, null)!;
        type.GetMethod("Verify", CSharpFlags)!.Invoke(module, new object[] { method });
    }

    private static int CSharpFixtureBodyOffset(PEReader pe, MethodInfo method)
    {
        var definition = pe.GetMetadataReader().GetMethodDefinition((MethodDefinitionHandle)MetadataTokens.Handle(method.MetadataToken));
        var section = pe.PEHeaders.SectionHeaders[pe.PEHeaders.GetContainingSectionIndex(definition.RelativeVirtualAddress)];
        return section.PointerToRawData + definition.RelativeVirtualAddress - section.VirtualAddress;
    }

    private static void CSharpBodyMutationRefuses(MethodInfo method, byte[] original, byte[] changed, string reason)
    {
        using var baseline = new PEReader(new MemoryStream(original, writable: false));
        using var altered = new PEReader(new MemoryStream(changed, writable: false));
        Equal(true, baseline.GetMetadata().GetContent().SequenceEqual(altered.GetMetadata().GetContent()), "tamper leaves metadata/MVID intact");
        int rva = baseline.GetMetadataReader().GetMethodDefinition((MethodDefinitionHandle)MetadataTokens.Handle(method.MetadataToken)).RelativeVirtualAddress;
        Equal(true, baseline.GetMethodBody(rva).GetILBytes()!.SequenceEqual(altered.GetMethodBody(rva).GetILBytes()!), "tamper leaves IL intact");
        CSharpSourceRefuses(() => VerifyCSharpFixtureBytes(method, changed), reason);
    }

    private static void NativeCSharpSourceVerifiesMethodHeader()
    {
        var method = typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.Closed))!;
        byte[] bytes = File.ReadAllBytes(method.Module.FullyQualifiedName);
        CSharpSourceFixture.Executions = 0;
        VerifyCSharpFixtureBytes(method, bytes);
        // A tiny body has no explicit local-signature token or InitLocals bit.
        var tiny = typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.LiteralSource))!;
        VerifyCSharpFixtureBytes(tiny, bytes);
        using var pe = new PEReader(new MemoryStream(bytes, writable: false));
        int start = CSharpFixtureBodyOffset(pe, method);
        Equal(3, bytes[start] & 3, "local fixture has a fat method header");
        Equal(2, bytes[CSharpFixtureBodyOffset(pe, tiny)] & 3, "literal fixture has a tiny method header");
        var metadata = pe.GetMetadataReader();
        int otherSignature = Enumerable.Range(1, metadata.GetTableRowCount(TableIndex.StandAloneSig))
            .Select(MetadataTokens.StandaloneSignatureHandle)
            .Where(handle => MetadataTokens.GetToken(handle) != method.GetMethodBody()!.LocalSignatureMetadataToken
                && metadata.GetBlobReader(metadata.GetStandaloneSignature(handle).Signature).ReadSignatureHeader().Kind == SignatureKind.LocalVariables)
            .Select(handle => MetadataTokens.GetToken(handle)).First();
        var locals = (byte[])bytes.Clone(); BitConverter.GetBytes(otherSignature).CopyTo(locals, start + 8);
        CSharpBodyMutationRefuses(method, bytes, locals, "csharp_pe_local_signature_mismatch");
        var init = (byte[])bytes.Clone(); init[start] ^= 0x10;
        CSharpBodyMutationRefuses(method, bytes, init, "csharp_pe_init_locals_mismatch");
        var stack = (byte[])bytes.Clone(); stack[start + 2] ^= 1;
        CSharpBodyMutationRefuses(method, bytes, stack, "csharp_pe_max_stack_mismatch");
        VerifyCSharpFixtureBytes(method, bytes);
        Equal(0, CSharpSourceFixture.Executions, "header verification never executes fixture source");
    }

    private static void NativeCSharpSourceVerifiesExceptionRegions()
    {
        var method = typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.ExceptionDescriptors))!;
        byte[] bytes = File.ReadAllBytes(method.Module.FullyQualifiedName);
        CSharpSourceFixture.Executions = 0;
        VerifyCSharpFixtureBytes(method, bytes);
        using var pe = new PEReader(new MemoryStream(bytes, writable: false));
        int start = CSharpFixtureBodyOffset(pe, method);
        int header = (BitConverter.ToUInt16(bytes, start) >> 12) * 4;
        int section = (start + header + BitConverter.ToInt32(bytes, start + 4) + 3) & ~3;
        Equal(1, bytes[section] & 0x3f, "fixture extra section is EH");
        bool fat = (bytes[section] & 0x40) != 0;
        int size = fat ? 24 : 12;
        var clauses = method.GetMethodBody()!.ExceptionHandlingClauses;
        int catchIndex = Enumerable.Range(0, clauses.Count).Single(index => clauses[index].Flags == ExceptionHandlingClauseOptions.Clause);
        int filterIndex = Enumerable.Range(0, clauses.Count).Single(index => clauses[index].Flags == ExceptionHandlingClauseOptions.Filter);
        Equal(true, clauses.Any(clause => clause.Flags == ExceptionHandlingClauseOptions.Finally), "positive EH includes finally");
        // Each descriptor component must be checked; all mutations are isolated
        // byte-array copies of this harness, never an installed DLL/file write.
        foreach (var field in new[] { ("kind", 0), ("try offset", fat ? 4 : 2), ("try length", fat ? 8 : 4),
            ("handler offset", fat ? 12 : 5), ("handler length", fat ? 16 : 7) })
        {
            var changed = (byte[])bytes.Clone();
            changed[section + 4 + catchIndex * size + field.Item2] ^= field.Item1 == "kind" ? (byte)2 : (byte)1;
            CSharpBodyMutationRefuses(method, bytes, changed, "csharp_pe_exception_regions_mismatch");
        }
        var metadata = pe.GetMetadataReader();
        int argumentException = MetadataTokens.GetToken(metadata.TypeReferences.Single(handle =>
            metadata.GetString(metadata.GetTypeReference(handle).Namespace) == "System"
            && metadata.GetString(metadata.GetTypeReference(handle).Name) == nameof(ArgumentException)));
        var catchType = (byte[])bytes.Clone();
        BitConverter.GetBytes(argumentException).CopyTo(catchType, section + 4 + catchIndex * size + (fat ? 20 : 8));
        CSharpBodyMutationRefuses(method, bytes, catchType, "csharp_pe_exception_regions_mismatch");
        var filter = (byte[])bytes.Clone(); filter[section + 4 + filterIndex * size + (fat ? 20 : 8)] ^= 1;
        CSharpBodyMutationRefuses(method, bytes, filter, "csharp_pe_exception_regions_mismatch");
        var missing = (byte[])bytes.Clone(); missing[start] &= 0xf7; // Clear MoreSects, not IL or metadata.
        CSharpBodyMutationRefuses(method, bytes, missing, "csharp_pe_exception_regions_mismatch");
        var reordered = (byte[])bytes.Clone();
        Array.Copy(bytes, section + 4, reordered, section + 4 + size, size);
        Array.Copy(bytes, section + 4 + size, reordered, section + 4, size);
        CSharpBodyMutationRefuses(method, bytes, reordered, "csharp_pe_exception_regions_mismatch");
        VerifyCSharpFixtureBytes(method, bytes);
        Equal(0, CSharpSourceFixture.Executions, "EH verification never executes fixture source");
    }

    private static void NativeCSharpWholeExceptionSourceKeepsGraphRefusal()
    {
        CSharpSourceFixture.Executions = 0;
        foreach (string name in new[] { nameof(CSharpSourceFixture.ExceptionDescriptors),
            nameof(CSharpSourceFixture.ExceptionRegion), nameof(CSharpSourceFixture.OtherExceptionRegion) })
        {
            var method = typeof(CSharpSourceFixture).GetMethod(name)!;
            CSharpSourceRefuses(() => CSharpOwner.GetMethod("ReadCompleteSourceMethod", CSharpFlags)!
                .Invoke(null, new object[] { method }), "exception_regions");
            var record = CSharpFixtureRecord(method, regions: false, specialize: true);
            Equal("whole_method", record["coverage"]!.GetValue<string>(), "source-only EH is the full original method");
            Equal(false, record.ContainsKey("identitySpecialized"), "EH source never acquires an unproved identity specialization");
            Equal(0, record["entryGuards"]!.AsArray().Count, "whole EH method is not presented as a cropped guarded region");
            Equal(true, record["unresolved"]!.AsArray().Any(value => value!.GetValue<string>()
                == "exception_regions_preserved_in_source; control_flow_and_exceptional_execution_not_evaluated"),
                "literal source does not claim exceptional CFG or execution proof");
            string code = record["code"]!.GetValue<string>();
            var syntax = Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree.ParseText(code).GetRoot();
            var regions = syntax.DescendantNodes().OfType<Microsoft.CodeAnalysis.CSharp.Syntax.TryStatementSyntax>().ToArray();
            Equal(true, regions.Length > 0 && regions.Any(region => region.Finally is not null), "complete finally source survives");
            if (name == nameof(CSharpSourceFixture.ExceptionDescriptors))
                Equal(true, regions.SelectMany(region => region.Catches).Count() == 2
                    && regions.SelectMany(region => region.Catches).Any(clause => clause.Filter is not null),
                    "all catches and the catch filter survive");
            if (name == nameof(CSharpSourceFixture.OtherExceptionRegion))
                Equal(true, code.Contains("888", StringComparison.Ordinal), "EH keeps the nonmatching identity sibling");
            Equal(record.ToJsonString(), CSharpFixtureRecord(method, regions: false, specialize: true).ToJsonString(),
                "whole exception source is deterministic");
            using var cancelled = new CancellationTokenSource(); cancelled.Cancel();
            CSharpSourceRefuses(() => CSharpFixtureRecord(method, false, cancellation: cancelled.Token), "canceled");
        }
        Equal(0, CSharpSourceFixture.Executions, "exception source capture never executes the fixture");
    }

    private static void NativeCSharpExceptionHelpersReachActualCapture()
    {
        // These are native-source regression inputs, never production selectors.
        foreach (var fixture in new[] { (Type: 133, Style: 16, Method: "AI_016"), (Type: 191, Style: 26, Method: "AI_026") })
        {
            var capture = GeneratorClient.CaptureProjectileAttackReference(new Projectile { type = fixture.Type, aiStyle = fixture.Style });
            string method = "Terraria.Projectile." + fixture.Method;
            var graph = capture["motion"]!["programs"]!.AsArray().OfType<JsonObject>()
                .Single(program => program["method"]!.GetValue<string>() == method);
            Equal("unknown", graph["coverage"]!.GetValue<string>(), "native EH CFG remains unknown");
            Equal("exception_regions", graph["unresolved"]!.GetValue<string>(), "native EH keeps the exact graph refusal");
            var record = capture["nativeCSharpSource"]!["records"]!.AsArray().OfType<JsonObject>()
                .Single(value => value["method"]!.GetValue<string>() == method);
            foreach (string key in new[] { "method", "sourceMethodSha256", "sourceModuleVersionId" })
                Equal(graph[key]!.GetValue<string>(), record[key]!.GetValue<string>(), "source and failed graph retain matching " + key);
            Equal("whole_method", record["coverage"]!.GetValue<string>(), "actual native EH gets readable whole source");
            Equal(false, record.ContainsKey("identitySpecialized"), "actual native EH is never identity pruned");
            string code = record["code"]!.GetValue<string>();
            var regions = Microsoft.CodeAnalysis.CSharp.CSharpSyntaxTree.ParseText(code).GetRoot().DescendantNodes()
                .OfType<Microsoft.CodeAnalysis.CSharp.Syntax.TryStatementSyntax>().ToArray();
            Equal(true, regions.Any(region => region.Catches.Count > 0), "actual native handler remains in source");
            Equal(true, code.Length <= 120000, "source stays within the existing per-record character bound");
            Equal(true, record["graphPaths"]!.AsArray().Any(path => path!.AsArray().Count == 3
                && path[0]!.GetValue<string>() == "motion" && path[1]!.GetValue<string>() == "programs"),
                "readable source explicitly owns the refused motion graph");
        }
    }

    private static void NativeCSharpRegionsKeepAllWindowsAndRefuseNonlocalDependencies()
    {
        var method = typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.Closed))!;
        var record = CSharpFixtureRecord(method, regions: true);
        Equal("conditional_ast_regions", record["coverage"]!.GetValue<string>(), "closed lexical source bodies have explicit conditional coverage");
        Equal(2, record["coveredWindows"]!.AsArray().Count, "both repeated native windows are represented");
        Equal(2, record["entryGuards"]!.AsArray().Count, "both typed original guards remain visible");
        Equal(true, record["code"]!.GetValue<string>().Contains("Source method on", StringComparison.Ordinal), "region text retains method/parameter binding header");
        CSharpSourceRefuses(() => CSharpFixtureRecord(method, true, extraWindow: true), "csharp_region_does_not_cover_all_identity_windows");
        CSharpSourceRefuses(() => CSharpFixtureRecord(typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.ExternalLocal))!, true), "csharp_region_external_local_dependency");
        CSharpSourceRefuses(() => CSharpFixtureRecord(typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.ExceptionRegion))!, true), "csharp_region_nonlocal_control_unsupported");
        var other = CSharpFixtureRecord(typeof(CSharpSourceFixture).GetMethod(nameof(CSharpSourceFixture.OtherExceptionRegion))!, true);
        Equal(1, other["coveredWindows"]!.AsArray().Count, "unrelated dispatcher EH does not erase a closed region");
        var body = new BlockStatement(); body.Statements.Add(new GotoStatement("Done"));
        Equal("csharp_region_nonlocal_control_unsupported", (string)CSharpOwner.GetMethod("CSharpRegionRefusal", CSharpFlags)!.Invoke(null, new object[] { body, method })!, "nonlocal goto cannot become a standalone source region");
        var program = new JsonObject { ["method"] = record["method"]!.DeepClone(),
            ["sourceModuleVersionId"] = record["sourceModuleVersionId"]!.DeepClone(),
            ["sourceMethodSha256"] = record["sourceMethodSha256"]!.DeepClone(), ["coverage"] = "fixture_source_only" };
        var roles = new JsonObject { ["draw"] = new JsonObject { ["programs"] = new JsonArray(program) },
            ["motion"] = new JsonObject { ["programs"] = new JsonArray(program.DeepClone()) } };
        string drawBefore = roles["draw"]!.ToJsonString();
        var selected = (System.Collections.IEnumerable)CSharpOwner.GetMethod("CSharpPrograms", CSharpFlags)!
            .Invoke(null, new object[] { roles, Array.Empty<object>() })!;
        var paths = selected.Cast<object>().Select(value => (object[])CSharpFixtureMember(value, "Path")).ToArray();
        Equal(1, paths.Length, "source ownership selects gameplay while an actual draw graph is present");
        Equal("motion", (string)paths[0][0], "draw is outside the source provider role");
        Equal(drawBefore, roles["draw"]!.ToJsonString(), "draw graph remains exact for motif and layer extraction");
    }

    private static void NativeCSharpLastPrismRetainsReadableHelperAndInlineEffects()
    {
        var parent = GeneratorClient.CaptureProjectileAttackReference(new Projectile { type = ProjectileID.LastPrism, aiStyle = 75 });
        var records = parent["nativeCSharpSource"]!["records"]!.AsArray().OfType<JsonObject>().ToArray();
        var helper = records.Single(record => record["method"]!.GetValue<string>() == "Terraria.Projectile.AI_075");
        Equal("whole_method", helper["coverage"]!.GetValue<string>(), "shared helper is not pruned by captured identity");
        foreach (string required in new[] { "NewProjectile", "GetProjectileSource_FromThis", "Kill", "633", "600" })
            Equal(true, helper["code"]!.GetValue<string>().Contains(required, StringComparison.Ordinal), "native helper preserves source/callback/sibling detail " + required);
        Equal(true, helper["locations"]!.AsArray().Count > 0, "spawn calls and guard references retain source locations");
        Equal(true, helper["locations"]!.AsArray().Any(location => location!["startLine"] is JsonValue), "actual IL call/guard maps to rendered C# lines");
        var child = GeneratorClient.CaptureProjectileAttackReference(new Projectile { type = ProjectileID.LastPrismLaser, aiStyle = 84 });
        var inline = child["nativeCSharpSource"]!["records"]!.AsArray().OfType<JsonObject>()
            .Single(record => record["method"]!.GetValue<string>() == "Terraria.Projectile.VanillaAI");
        Equal("conditional_ast_regions", inline["coverage"]!.GetValue<string>(), "inline body uses a closed AST region");
        Equal(child["motionDispatch"]!["identityWindows"]!.AsArray().Count, inline["coveredWindows"]!.AsArray().Count, "every original identity window is covered");
        foreach (string required in new[] { "Opacity", "friendly", "LaserScan", "projectile2", "Main.projectile" })
            Equal(true, inline["code"]!.GetValue<string>().Contains(required, StringComparison.Ordinal), "inline C# retains actual effect and actor linkage " + required);
        Equal(true, inline["code"]!.GetValue<string>().Length < 30000, "source presentation needs no expanded custom expression language");
        Equal(true, records.Concat(child["nativeCSharpSource"]!["records"]!.AsArray().OfType<JsonObject>())
            .All(record => record["graphPaths"]!.AsArray().All(path => !path!.AsArray().Any(part => part is JsonValue value && value.TryGetValue<string>(out string? text) && text == "identitySelected"))),
            "replacement paths never overlap outer and selected program owners");
        Equal(true, records.Concat(child["nativeCSharpSource"]!["records"]!.AsArray().OfType<JsonObject>())
            .All(record => record["graphPaths"]!.AsArray().All(path => path!.AsArray()[0]!.ToString() != "draw")),
            "actual source records never target the draw owner");
    }
}
