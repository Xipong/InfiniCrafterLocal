using System.Reflection.Metadata;
using System.Reflection.Metadata.Ecma335;
using System.Reflection.PortableExecutable;
using System.Security.Cryptography;
using System.Text.Json;
using Mono.Cecil;
using AssemblyDefinition = Mono.Cecil.AssemblyDefinition;
using TypeDefinition = Mono.Cecil.TypeDefinition;
using MethodDefinition = Mono.Cecil.MethodDefinition;
using InfiniCrafterLocal.Common.Services;

// Read official assembly metadata only; never load or execute the target.
if (args.Length is not (3 or 4) || (args.Length == 4 && args[3] != "--check")) throw new ArgumentException("Expected <assembly> <reports directory> <output .g.cs> [--check]");
using var assembly = AssemblyDefinition.ReadAssembly(args[0]);
using var stream = File.OpenRead(args[0]);
using var pe = new PEReader(stream);
var metadata = pe.GetMetadataReader();
string auditedAssemblyHash = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(args[0]))).ToLowerInvariant();
IEnumerable<TypeDefinition> Types(IEnumerable<TypeDefinition> types) => types.SelectMany(t => new[] { t }.Concat(Types(t.NestedTypes)));
var methods = Types(assembly.MainModule.Types).SelectMany(t => t.Methods).Where(m => m.HasBody).ToArray();
string Raw(MethodDefinition method) {
    var definition = metadata.GetMethodDefinition((MethodDefinitionHandle)MetadataTokens.Handle(method.MetadataToken.ToInt32()));
    return Convert.ToHexString(SHA256.HashData(pe.GetMethodBody(definition.RelativeVirtualAddress).GetILBytes()!)).ToLowerInvariant();
}
var hashes = methods.ToDictionary(m => m, Raw);
var groups = new[] { "attack", "ammo", "equipment", "buff_effect", "environment", "hit_status", "motion" };
var rows = new List<(string Group, MethodDefinition Method, string Raw)>();
foreach (string group in groups) {
    using var report = JsonDocument.Parse(group == "motion"
        ? "{\"method\":\"Projectile.AI_001\",\"sourceMethodSha256\":\"cf0488832f92e43e699ae307df6f73d90f88f17194250f0a39ca5715a9e0631b\"}"
        : File.ReadAllText(Path.Combine(args[1], "native_" + group + "_sources.generated.json")));
    void Require(string name, string hash)
    {
        var matches = methods.Where(m => hashes[m] == hash &&
            (m.DeclaringType.FullName + "." + m.Name == name || m.DeclaringType.Name + "." + m.Name == name)).ToArray();
        if (matches.Length != 1) throw new InvalidOperationException($"Unresolved/ambiguous audited source {group}: {name}");
        if (!rows.Any(r => r.Group == group && r.Method == matches[0])) rows.Add((group, matches[0], hash));
    }
    void Read(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Array) { foreach (var child in value.EnumerateArray()) Read(child); return; }
        if (value.ValueKind != JsonValueKind.Object) return;
        foreach (string key in new[] { "sourceModuleVersionId", "moduleVersionId" })
            if (value.TryGetProperty(key, out var identity) && identity.GetString() != assembly.MainModule.Mvid.ToString())
                throw new InvalidOperationException("Audited report module does not match source assembly: " + group);
        if (value.TryGetProperty("assemblySha256", out var assemblyHash) && assemblyHash.GetString() != auditedAssemblyHash)
            throw new InvalidOperationException("Audited report file does not match source assembly: " + group);
        if (value.TryGetProperty("sourceMethodSha256", out var sha))
        {
            string name = value.TryGetProperty("method", out var method) ? method.GetString()!
                : value.TryGetProperty("member", out var member) ? member.GetString()!
                : value.TryGetProperty("owner", out var owner) ? owner.GetString() + "." + value.GetProperty("name").GetString()
                : value.GetProperty("sourceKind").GetString() == "contact" ? "Player.StatusToNPC" : "Projectile.StatusNPC";
            Require(name, sha.GetString()!);
        }
        if (value.TryGetProperty("specificMatchLookupCertificate", out var specific))
            Require("Player.PickAmmo_TryFindingSpecificMatches", specific.GetString()!.Split(':')[0]);
        foreach (string key in new[] { "nativeMember" })
            if (value.TryGetProperty(key, out var dependency) && dependency.ValueKind == JsonValueKind.String)
            {
                string name = dependency.GetString()!;
                if (name.Contains(".get_", StringComparison.Ordinal) || name.Contains(".op_", StringComparison.Ordinal))
                {
                    var found = methods.Where(m => (m.DeclaringType.FullName.Replace('/', '.') + "." + m.Name).EndsWith(name, StringComparison.Ordinal)).ToArray();
                    if (found.Length == 0) throw new InvalidOperationException("Unresolved interpreted dependency " + name);
                    foreach (var method in found)
                        if (!rows.Any(r => r.Group == group && r.Method == method)) rows.Add((group, method, hashes[method]));
                }
            }
        foreach (var child in value.EnumerateObject()) Read(child.Value);
    }
    Read(report.RootElement);
    if (group == "equipment")
        foreach (var method in methods.Where(m => m.DeclaringType.FullName == "Terraria.ModLoader.StatModifier" && m.Name == "op_Addition"))
            if (!rows.Any(r => r.Group == group && r.Method == method)) rows.Add((group, method, hashes[method]));
    if (group is "equipment" or "buff_effect")
    {
        var getters = rows.Where(r => r.Group == group && r.Method.DeclaringType.FullName == "Terraria.Player" && r.Method.Name.StartsWith("get_", StringComparison.Ordinal)).Select(r => r.Method).ToArray();
        foreach (var call in getters.SelectMany(m => m.Body.Instructions).Select(i => i.Operand).OfType<MethodReference>())
            if ((call.DeclaringType.FullName == "Terraria.Player" && new[] { "GetDamage", "GetCritChance", "GetAttackSpeed", "GetArmorPenetration" }.Contains(call.Name))
                || (call.DeclaringType.FullName == "Terraria.ModLoader.DamageClass" && call.Name.StartsWith("get_", StringComparison.Ordinal)))
            {
                var dependency = call.Resolve() ?? throw new InvalidOperationException("Unresolved interpreted getter selector");
                if (!rows.Any(r => r.Group == group && r.Method == dependency)) rows.Add((group, dependency, hashes[dependency]));
            }
        var typeGetter = methods.Single(m => m.DeclaringType.FullName == "Terraria.ModLoader.DamageClass" && m.Name == "get_Type");
        if (!rows.Any(r => r.Group == group && r.Method == typeGetter)) rows.Add((group, typeGetter, hashes[typeGetter]));
    }
    if (group == "environment") {
        var getters = new[] { "UsesCustomCanPlace", "AlternatesCount", "HookPlaceOverride", "RandomStyleRange", "SpecificRandomStyles", "Width", "Height", "CoordinateHeights", "CoordinateWidth", "CoordinatePadding", "CoordinateFullWidth", "CoordinateFullHeight", "StyleWrapLimit", "StyleMultiplier", "StyleLineSkip", "Style", "StyleHorizontal" };
        foreach (var method in methods.Where(m =>
            (m.DeclaringType.FullName == "Terraria.Item" && m.Name is "NPCtoBanner" or "BannerToItem") ||
            (m.DeclaringType.FullName == "Terraria.ObjectData.TileObjectData" && getters.Contains(m.Name.Replace("get_", ""))) ||
            (m.DeclaringType.FullName == "Terraria.Main" && m.Name == "get_expertMode") ||
            (m.DeclaringType.FullName == "Terraria.ModLoader.MultipliableFloat" && m.Name == "op_Multiply")))
            if (!rows.Any(r => r.Group == group && r.Method == method)) rows.Add((group, method, hashes[method]));
    }
    if (!rows.Any(r => r.Group == group)) throw new InvalidOperationException("No audited source methods for " + group);
}
string Q(string value) => JsonSerializer.Serialize(value);
var lines = new List<string> { "// Generated by tools/generate/native_source_certificates; do not hand-edit.", "namespace InfiniCrafterLocal.Common.Services;", "internal static class NativeSourceCertificates", "{", "    internal readonly record struct Entry(string Group, string Owner, string Name, string Signature, string Shape, string AuditedCertificate);", "    internal static readonly Entry[] Methods =", "    {" };
foreach (var row in rows.OrderBy(r => r.Group).ThenBy(r => r.Method.FullName))
    lines.Add("        new(" + string.Join(", ", new[] { row.Group, row.Method.DeclaringType.FullName, row.Method.Name, row.Method.FullName, NativeSourceFingerprint.Compute(row.Method), row.Raw + ":" + assembly.MainModule.Mvid }.Select(Q)) + "),");
lines.AddRange(new[] { "    };", "}", "" });
string generated = string.Join("\n", lines);
if (args.Length == 4)
{
    if (!File.Exists(args[2]) || File.ReadAllText(args[2]) != generated) throw new InvalidOperationException("Stale native semantic certificates");
}
else File.WriteAllText(args[2], generated);
Console.WriteLine($"Generated {rows.Count} audited method certificates across {groups.Length} existing catalogs.");
