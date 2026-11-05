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
    }

    private const BindingFlags CSharpFlags = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
    private static readonly Type CSharpOwner = typeof(GeneratorClient);

    private static object CSharpFixtureMember(object value, string name)
        => value.GetType().GetProperty(name, CSharpFlags)?.GetValue(value)
            ?? value.GetType().GetField(name, CSharpFlags)!.GetValue(value)!;

    private static JsonObject CSharpFixtureRecord(MethodInfo method, bool regions, byte[]? bytes = null,
        bool extraWindow = false, CancellationToken cancellation = default)
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
        return (JsonObject)CSharpOwner.GetMethod("BuildNativeCSharpRecord", CSharpFlags)!.Invoke(null,
            new object[] { document, programs, new JsonArray(), 643, 123, cancellation })!;
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
    }
}
