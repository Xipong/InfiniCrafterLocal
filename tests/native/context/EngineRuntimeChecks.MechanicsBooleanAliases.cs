using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json.Nodes;
using System.Threading;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void MechanicsSourceBindsBooleanAliases()
    {
        MechanicsSourceFixture.Executions = 0;
        var selected = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.BoolAlias));
        string code = selected["code"]!.GetValue<string>();
        Equal(false, code.Contains("981") || code.Contains("983"), "false immutable alias removes impossible effects");
        Equal(true, code.Contains("982") && code.Contains("984") && code.Contains("Touch()"), "reachable effects and opaque condition prefixes stay");
        var other = MechanicsFixtureRecord(nameof(MechanicsSourceFixture.BoolAlias), capturedType: 178);
        Equal(true, other["code"]!.GetValue<string>().Contains("981"), "opposite identity retains selected effects");
        foreach (var pair in new[] { ("BoolReassigned", "985"), ("BoolRef", "986"), ("BoolLoop", "987"), ("BoolNested", "988"), ("BoolException", "989"), ("BoolCapture", "990") })
            Equal(true, MechanicsFixtureRecord(pair.Item1)["code"]!.GetValue<string>().Contains(pair.Item2), "unsupported alias remains conservative: " + pair.Item1);
        JsonObject Native(int identity)
        {
            var method = typeof(Projectile).GetMethod("AI_026", BindingFlags.NonPublic | BindingFlags.Instance)!;
            object Create(Type type, params object?[] values) => Activator.CreateInstance(type, CSharpFlags, null, values, null)!;
            using var module = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpModule", CSharpFlags)!, method.Module.FullyQualifiedName,
                File.ReadAllBytes(method.Module.FullyQualifiedName), method.Module.ModuleVersionId);
            using var document = (IDisposable)Create(CSharpOwner.GetNestedType("NativeCSharpDocument", CSharpFlags)!, method, module, CancellationToken.None);
            return (JsonObject)CSharpOwner.GetMethod("BuildMechanicsSourceRecord", CSharpFlags)!.Invoke(null, new object[] { document, identity, 26, CancellationToken.None, true })!;
        }
        var spider = Native(390);
        string spiderCode = spider["code"]!.GetValue<string>();
        Equal(false, spiderCode.Contains(" = 195;"), "real Spider no longer contains ranged sibling spawn195");
        foreach (string fact in new[] { "spiderMinion", "OwnerMinionAttackTargetNPC", "CanBeChasedBy", "Collision.SolidCollision", ".Intersects(", "TileID.Sets.Platforms" })
            Equal(true, spiderCode.Contains(fact), "Spider behavior remains in readable source: " + fact);
        Equal(true, spider["excludedCallOffsets"]!.AsArray().Count > 0, "removed native calls have IL exclusion anchors");
        var ranged = Native(191);
        Equal(true, ranged["code"]!.GetValue<string>().Contains(" = 195;"), "real ranged parent retains its spawn195");
        Equal(true, spider["approximation"]!.GetValue<string>().Contains("assumed stable across opaque calls"), "local propagation does not certify identity assumption");
        Equal(0, MechanicsSourceFixture.Executions, "analysis executes no fixture mechanics");
    }
}
