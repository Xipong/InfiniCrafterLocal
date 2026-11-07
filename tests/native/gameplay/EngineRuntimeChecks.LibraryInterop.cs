using System;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using InfiniCrafterLocal.Common.VFX;
using Microsoft.Xna.Framework;
using Mono.Cecil;
using Mono.Cecil.Cil;
using MonoMod.Cil;
using MonoMod.RuntimeDetour;
using MonoMod.Utils;
using ParticleLibrary.Core.V3.Particles;

internal static partial class EngineRuntimeChecks
{
    private static void LibraryWorldPassScopesForeignWaterOffset()
    {
        var buffer = typeof(InfiniDetachedVfxSystem).GetNestedType("LibraryBuffer", BindingFlags.NonPublic)!;
        var render = buffer.GetMethod("RenderOwned", BindingFlags.Instance | BindingFlags.NonPublic)!;
        using var body = new DynamicMethodDefinition(render);
        // Bind the actual production Apply call site, so the baseline invokes
        // its direct dependency call and the candidate invokes its scoped owner.
        var target = body.Definition.Body.Instructions.Select(i => i.Operand).OfType<MethodReference>()
            .Single(m => (m.DeclaringType.FullName == typeof(InstancedParticleEffect).FullName && m.Name == "Apply")
                || (m.DeclaringType.FullName == typeof(InfiniDetachedVfxSystem).FullName && m.Name == "ApplyWorldSpaceLibraryEffect"));
        var scoped = target.Name == "ApplyWorldSpaceLibraryEffect"
            ? typeof(InfiniDetachedVfxSystem).GetMethod(target.Name, BindingFlags.Static | BindingFlags.NonPublic) : null;
        var effect = (InstancedParticleEffect)RuntimeHelpers.GetUninitializedObject(typeof(InstancedParticleEffect));
        var priorCamera = Terraria.Main.screenPosition; int priorRange = Terraria.Main.offScreenRange;
        Vector2? observed = null; bool failAtGpuBoundary = false; int applies = 0;
        using var hook = new ILHook(typeof(InstancedParticleEffect).GetMethod("Apply")!, il => {
            var cursor = new ILCursor(il);
            cursor.GotoNext(i => i.OpCode == OpCodes.Ldarg_0,
                i => i.Operand is FieldReference field && field.Name == "_transformParameter");
            // Keep the installed library's real camera/flag/offset calculation;
            // intercept only its subsequent GPU parameter/pass application.
            // Retain the native branch-target ldarg.0 before the GPU tail;
            // removing it would orphan the preceding brfalse label.
            cursor.Index++;
            cursor.RemoveRange(il.Body.Instructions.Count - cursor.Index);
            cursor.Emit(OpCodes.Pop);
            cursor.Emit(OpCodes.Ldloc_0);
            cursor.EmitDelegate<Action<Vector2>>(offset => {
                applies++; observed = offset;
                if (failAtGpuBoundary) throw new InvalidOperationException("library GPU-boundary sentinel");
            });
            cursor.Emit(OpCodes.Ret);
        });
        void ApplyFromOwnedCallSite()
        {
            if (scoped is null) effect.Apply();
            else try { scoped.Invoke(null, new object[] { effect }); }
                catch (TargetInvocationException error) { throw error.InnerException!; }
        }
        try {
            Terraria.Main.screenPosition = new Vector2(160,240); Terraria.Main.offScreenRange = 192;
            foreach (bool incomingWaterContext in new[] { false,true }) {
                effect.UseOffScreenRange = incomingWaterContext; observed = null;
                ApplyFromOwnedCallSite();
                Equal<Vector2?>(-Terraria.Main.screenPosition, observed, "owned world pass never inherits native water translation");
                Equal(incomingWaterContext, effect.UseOffScreenRange, "foreign context is restored after Apply consumes its one-shot flag");
            }
            effect.UseOffScreenRange = true; failAtGpuBoundary = true;
            bool threw = false;
            try { ApplyFromOwnedCallSite(); }
            catch (InvalidOperationException error) when (error.Message == "library GPU-boundary sentinel") { threw = true; }
            Equal(true, threw, "native Apply failure propagates, not silently swallowed");
            Equal(true, effect.UseOffScreenRange, "foreign water context restored even on GPU-boundary failure");
            Equal(3, applies, "all controls execute installed dependency offset code exactly once");
        } finally { Terraria.Main.screenPosition = priorCamera; Terraria.Main.offScreenRange = priorRange; }
    }
}
