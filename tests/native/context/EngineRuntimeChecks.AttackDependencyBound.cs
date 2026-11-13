using System;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Text.Json.Nodes;
using InfiniCrafterLocal.Common.Services;
using Terraria;

internal static partial class EngineRuntimeChecks
{
    private static void ProjectileAttackSourceExpandedDependencyBound()
    {
        MethodInfo Fixture(int count, string field = "scale")
        {
            var assembly = AssemblyBuilder.DefineDynamicAssembly(new AssemblyName("AttackDependencyBound" + count), AssemblyBuilderAccess.Run);
            var type = assembly.DefineDynamicModule("fixture").DefineType("DependencyChain", TypeAttributes.Public);
            var method = type.DefineMethod("Source", MethodAttributes.Public | MethodAttributes.Static, typeof(void), new[] { typeof(Projectile) });
            var il = method.GetILGenerator();
            LocalBuilder? previous = null;
            for (int index = 0; index < count; index++)
            {
                var next = il.DeclareLocal(typeof(float));
                if (previous is null) il.Emit(OpCodes.Ldc_R4, 1f);
                else { il.Emit(OpCodes.Ldloc, previous); il.Emit(OpCodes.Ldc_R4, 1f); il.Emit(OpCodes.Add); }
                il.Emit(OpCodes.Stloc, next); previous = next;
            }
            il.Emit(OpCodes.Ldarg_0); il.Emit(OpCodes.Ldloc, previous!);
            il.Emit(OpCodes.Stfld, typeof(Projectile).GetField(field)!); il.Emit(OpCodes.Ret);
            return type.CreateType()!.GetMethod("Source")!;
        }
        // Inspect IL only: the fixture's source is never executed.
        var fixture = Fixture(230);
        bool rawRefused = false;
        try { _ = GeneratorClient.InspectProjectileAttackSource(fixture, "motion"); }
        catch (NotSupportedException error)
        { rawRefused = error.Message.StartsWith("connected_source_dependency_count_bound:", StringComparison.Ordinal); }
        Equal(true, rawRefused, "unspecialized all-actor source keeps its original resource bound");
        var observed = GeneratorClient.InspectProjectileAttackIdentitySource(fixture, 1234, 1);
        Equal(230, observed["dependencies"]!.AsObject().Count, "expanded bound retains every connected local definition beyond the old 192 cutoff");
        Equal(true, observed["observations"]!.AsArray().Count > 0, "the actor write is retained, not just its dependencies");
        var effect = GeneratorClient.InspectProjectileAttackSource(Fixture(230, "knockBack"), "motion");
        Equal(230, effect["dependencies"]!.AsObject().Count, "the production explicit-effect slice retains its connected definitions without an identity selector");
        Equal(true, effect["observations"]!.AsArray().Any(row => row?["expression"]?.GetValue<string>().Contains("Projectile.knockBack", StringComparison.Ordinal) == true), "the additional effect's state write is preserved");
        bool refused = false;
        try { _ = GeneratorClient.InspectProjectileAttackIdentitySource(Fixture(400), 1234, 1); }
        catch (NotSupportedException error)
        {
            refused = error.Message.StartsWith("connected_source_dependency_count_bound:", StringComparison.Ordinal);
        }
        Equal(true, refused, "larger observations still refuse explicitly rather than silently truncating dependencies");
    }
}
